# GPU box setup

What the pipeline talks to, and how it was brought up on a fresh GH200 (96 GB, Ubuntu 22.04, aarch64) on 2026-10-22. The compose file is `gpu/docker-compose.yml` in the book repo.

| Server | Port | Model | Memory | Env var |
|---|---|---|---|---|
| Z-Image, copy 1 and 2 | 8000, 8001 | Tongyi-MAI/Z-Image-Turbo (vLLM-Omni) | ~22 GB each | `GPU_URLS` |
| text LLM | 8100 | Qwen/Qwen2.5-7B-Instruct (vLLM, `LLM_MEM=0.2`) | ~19 GB | `LLM_URL` |
| vision | 8200 | Qwen/Qwen2.5-VL-7B-Instruct (vLLM, `VL_MEM=0.30`) | ~29 GB | `VL_URL` |

Total about 88 GB of 96. `VL_MEM=0.2` is not enough: the model takes 15.6 GB and vLLM reports a negative KV cache; 0.30 works.

```bash
# once: docker with the NVIDIA runtime (already on the Lambda image), apt packages for the pipeline
sudo apt-get install -y tesseract-ocr libfribidi0 libraqm0
uv venv ~/manga-venv --python 3.12 && uv pip install --python ~/manga-venv/bin/python pillow numpy

# servers (API_KEY is generated on the box into ~/webtoon-gpu/.env, never copied anywhere)
mkdir -p ~/webtoon-gpu ~/hf-cache && cp docker-compose.yml ~/webtoon-gpu/
printf 'BIND=127.0.0.1\nHF_CACHE=/home/ubuntu/hf-cache\nVL_MEM=0.30\nAPI_KEY=%s\n' "$(openssl rand -hex 16)" > ~/webtoon-gpu/.env
cd ~/webtoon-gpu
sudo docker compose --profile zimage up -d --scale zimage=2   # wait for /health on 8000 and 8001 (about a minute with a warm cache)
sudo docker compose --profile llm up -d llm                   # then this (about 2 minutes), then:
sudo docker compose --profile vl up -d vl                     # start them one after another: each takes its memory share at start
```

Fonts (not in any repo): `Waseem.ttc`, `Baghdad.ttc`, `Tahoma Bold.ttf` into `~/manga/fonts` (`FONT_DIR`), and the site's `private/fonts` and the Geist file into `~/manga/site` (`SITE_DIR`).

Run: `~/pipe.sh <root> run BOOK VOL <tasks>` where the script exports the server URLs and `UNSLOTH_API_KEY=$(grep ^API_KEY= ~/webtoon-gpu/.env | cut -d= -f2)`.

The old data backup (`/root/backups/gpu-backup.tar.gz` on the production host) holds only work files (`manga/comic/...`, about 10,500 files); the servers are rebuilt from the compose file and the Hugging Face cache, not from the backup.
