import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from sutur_pipeline.clients import JsonHttp, OpenAIImageClient, OpenAIVisionClient
from sutur_pipeline.errors import TransportError


class Handler(BaseHTTPRequestHandler):
    hits = 0
    seen_auth = ""

    def log_message(self, *a: object) -> None:
        pass

    def do_POST(self) -> None:
        Handler.hits += 1
        Handler.seen_auth = self.headers.get("Authorization", "")
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/flaky" and Handler.hits < 3:
            self.send_response(503)
            self.end_headers()
            return
        if self.path == "/bad":
            self.send_response(400)
            self.end_headers()
            return
        out: dict = {"echo": body}
        if self.path == "/v1/images/generations":
            out = {"data": [{"b64_json": "aGk="}]}   # "hi"
        if self.path == "/v1/chat/completions":
            out = {"choices": [{"message": {"content": "yes"}}]}
        raw = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        Handler.hits = 0

    def test_post_and_auth_header(self) -> None:
        out = JsonHttp(self.url, "k", retries=1).post("/x", {"a": 1})
        self.assertEqual(out["echo"], {"a": 1})
        self.assertEqual(Handler.seen_auth, "Bearer k")

    def test_retries_server_errors(self) -> None:
        self.assertIn("echo", JsonHttp(self.url, retries=3, backoff=0.01).post("/flaky", {}))
        self.assertEqual(Handler.hits, 3)

    def test_client_errors_are_not_retried(self) -> None:
        with self.assertRaises(TransportError):
            JsonHttp(self.url, retries=3, backoff=0.01).post("/bad", {})
        self.assertEqual(Handler.hits, 1)

    def test_unreachable_server(self) -> None:
        with self.assertRaises(TransportError):
            JsonHttp("http://127.0.0.1:1", retries=1, timeout=1).post("/x", {})

    def test_key_not_in_repr(self) -> None:
        self.assertNotIn("topsecret", repr(JsonHttp(self.url, "topsecret")))

    def test_image_and_vision_clients(self) -> None:
        http = JsonHttp(self.url, retries=1)
        self.assertEqual(OpenAIImageClient(http, "m", 9).generate("p", 64, 64, 1), b"hi")
        self.assertEqual(OpenAIVisionClient(http, "m").ask(b"jpeg", "q"), "yes")


if __name__ == "__main__":
    unittest.main()
