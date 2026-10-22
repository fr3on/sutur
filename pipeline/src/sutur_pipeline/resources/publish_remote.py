#!/usr/bin/env python3
"""Runs on the production host (python3 publish_remote.py DIR): creates a throwaway admin, uploads the volume through
POST /api/admin/books, then stores the cast pictures and the cast list, links the volume in the series and deletes the admin."""
import json
import secrets
import subprocess
import sys
from pathlib import Path

D = Path(sys.argv[1])
m = json.loads((D / "publish.json").read_text(encoding="utf-8"))
B = "http://127.0.0.1:8090"
email, pw, jar = f"sutur-pub-{secrets.token_hex(3)}@example.test", secrets.token_urlsafe(14), D / "cj.txt"
NODE = 'const {MongoClient}=require("mongodb");const bcrypt=require("bcryptjs");(async()=>{const c=await MongoClient.connect(process.env.MONGODB_URI);const db=c.db(process.env.MONGODB_DB);%s;await c.close()})().catch(e=>{console.error(e);process.exit(1)})'


def node(body, **env):
    args = ["docker", "exec", "-i", "-e", f"EMAIL={email}", "-e", f"PW={pw}"] + [x for k, v in env.items() for x in ("-e", f"{k}={v}")]
    r = subprocess.run(args + ["sutur", "node", "-e", NODE % body], text=True, capture_output=True, stdin=subprocess.DEVNULL)
    if r.returncode:
        sys.exit(r.stderr)
    return r.stdout


def curl(*a):
    return subprocess.run(["curl", "-s", "-b", str(jar), "-c", str(jar), *a], text=True, capture_output=True).stdout


try:
    node('await db.collection("users").insertOne({email:process.env.EMAIL,name:"Publisher",passwordHash:await bcrypt.hash(process.env.PW,12),createdAt:new Date(),role:"admin"})')
    csrf = json.loads(curl(f"{B}/api/auth/csrf"))["csrfToken"]
    curl("-o", "/dev/null", "-X", "POST", f"{B}/api/auth/callback/credentials", "--data-urlencode", f"csrfToken={csrf}", "--data-urlencode", f"email={email}", "--data-urlencode", f"password={pw}", "--data-urlencode", "json=true")
    slug = m["slug"]
    exists = node('console.log(await db.collection("books").countDocuments({slug:process.env.SLUG}))', SLUG=slug).strip() != "0"
    files = ["-F", f"pdf=@{D}/book.pdf;type=application/pdf", "-F", f"cover=@{D}/cover.png;type=image/png"]
    if exists:   # a coming-soon record already holds the texts: PUT attaches the PDF and cover and publishes it
        out = curl("-m", "290", "-X", "PUT", f"{B}/api/admin/books/{slug}", *files)
    else:
        keys = ["title", "titleEn", "author", "authorEn", "genre", "genreEn", "volume", "volumeEn", "age", "notes", "notesEn", "summary", "summaryEn",
                "seriesSlug", "seriesTitle", "seriesTitleEn", "volumeNo", "sourceName", "sourceUrl", "slug"]
        form = [x for k in keys if m.get(k) not in (None, "") for x in ("-F", f"{k}={m[k]}")]
        out = curl("-m", "290", "-X", "POST", f"{B}/api/admin/books", *form, *files)
    print("upload:", out)
    if '"slug"' not in out:
        sys.exit("upload failed")
    # Cast pictures: into the bucket when the site runs on S3 (S3_BUCKET set in the container), else into the data volume.
    s3 = subprocess.run(["docker", "exec", "sutur", "printenv", "S3_BUCKET"], capture_output=True, text=True).stdout.strip()
    PUT = 'const {S3Client,PutObjectCommand}=require("@aws-sdk/client-s3");const fs=require("fs");new S3Client({region:process.env.S3_REGION||"eu-west-3"}).send(new PutObjectCommand({Bucket:process.env.S3_BUCKET,Key:process.argv[1],Body:fs.readFileSync(process.argv[2]),ContentType:"image/webp"})).catch(e=>{console.error(e);process.exit(1)})'
    if not s3:
        subprocess.run(["docker", "exec", "sutur", "mkdir", "-p", f"/data/media/{slug}"], check=True)
    for f in sorted(D.glob("cast-*.webp")):
        if s3:
            subprocess.run(["docker", "cp", str(f), f"sutur:/tmp/{f.name}"], check=True)
            subprocess.run(["docker", "exec", "-w", "/app", "sutur", "node", "-e", PUT, f"media/{slug}/{f.name}", f"/tmp/{f.name}"], check=True)
        else:
            subprocess.run(["docker", "cp", str(f), f"sutur:/data/media/{slug}/{f.name}"], check=True)
    node('const col=db.collection("books");const r=await col.updateOne({slug:process.env.SLUG},{$set:Object.assign({characters:JSON.parse(process.env.CAST),stats:JSON.parse(process.env.STATS)},process.env.AGE?{age:process.env.AGE}:{})});'
         'let l=0;if(process.env.BASE){l=(await col.updateOne({slug:process.env.BASE,"series.no":Number(process.env.NO)},{$set:{"series.$.slug":process.env.SLUG}})).modifiedCount}'
         'const b=await col.findOne({slug:process.env.SLUG});console.log(b.slug,b.status,"age",b.age,"pages",b.pages.length,"cast",b.characters.length,"linked",l)',
         SLUG=slug, CAST=json.dumps(m["castList"], ensure_ascii=False), STATS=json.dumps(m.get("stats", {})), AGE=m.get("age", "") if m.get("age") == "18" else "", BASE=m.get("seriesBook", ""), NO=m.get("volumeNo", 0))
finally:
    node('await db.collection("users").deleteMany({email:process.env.EMAIL})')
    print("publisher removed")
