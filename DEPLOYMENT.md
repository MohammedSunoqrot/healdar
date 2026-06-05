# Healdar — Deployment Guide

Two supported targets: **Streamlit Cloud** (easiest, free tier available) and **Docker** (self-hosted, full control).

---

## Prerequisites — build the vectorstore locally first

The vectorstore must be built before deploying. Run these once from the project root:

```bash
python src/ingest.py   # PDF → data/chunks.json
python src/embed.py    # chunks.json → data/vectorstore/
```

Both output files (`data/chunks.json` and `data/vectorstore/`) must be committed to Git **or** copied into the Docker image.

---

## Option 1 — Streamlit Cloud

Streamlit Cloud hosts Streamlit apps for free (public repos) or on a paid plan (private repos).

### Steps

**1. Push to GitHub**

```bash
git init
git add .
git commit -m "Initial Healdar commit"
git remote add origin https://github.com/<you>/healdar.git
git push -u origin main
```

Make sure `data/vectorstore/` and `data/chunks.json` are committed (they are not large — ~33 MB total).

Add this to `.gitignore` to protect your secrets:
```
src/.env
.streamlit/secrets.toml
```

**2. Connect to Streamlit Cloud**

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub
2. Click **New app** → select your repo → set **Main file path** to `src/app.py`
3. Click **Advanced settings** → **Secrets** and paste:

```toml
GROQ_API_KEY = "gsk_your_key_here"
```

4. Click **Deploy**

### Notes

- First deploy downloads the sentence-transformers model (~90 MB) — expect ~3 min cold start
- Free tier: 1 GB RAM, 1 CPU. Healdar fits comfortably (model + vectorstore ≈ 400 MB)
- The app sleeps after inactivity; first request after sleep takes ~10 s to wake

---

## Option 2 — Docker

### Build

```bash
docker build -t healdar .
```

Build time: ~5 min (downloads torch CPU ~250 MB + other packages).
Final image size: ~1.5 GB.

### Run

```bash
docker run -d \
  --name healdar \
  -p 8501:8501 \
  -e GROQ_API_KEY=gsk_your_key_here \
  healdar
```

Then open `http://localhost:8501`.

Or use a `.env` file (never commit it):

```bash
docker run -d --name healdar -p 8501:8501 --env-file src/.env healdar
```

### Stop / restart

```bash
docker stop healdar
docker start healdar
docker logs healdar      # view logs
```

### Deploy to a cloud VM (e.g. AWS EC2 / Azure VM / DigitalOcean Droplet)

1. SSH into the VM
2. Install Docker: `curl -fsSL https://get.docker.com | sh`
3. Copy the image (or build on the VM):
   ```bash
   # Option A — build on VM (clone repo first)
   git clone https://github.com/<you>/healdar.git && cd healdar
   docker build -t healdar .

   # Option B — push image from local machine
   docker tag healdar <dockerhub-user>/healdar
   docker push <dockerhub-user>/healdar
   # On VM:
   docker pull <dockerhub-user>/healdar
   docker tag <dockerhub-user>/healdar healdar
   ```
4. Run with the key:
   ```bash
   docker run -d --restart=unless-stopped \
     -p 8501:8501 \
     -e GROQ_API_KEY=gsk_your_key_here \
     healdar
   ```
5. Open port 8501 in the VM's security group / firewall

To serve on port 80/443 with HTTPS, put nginx in front:

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    location / {
        proxy_pass         http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
    }
}
```

---

## Environment variables reference

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | ✅ | Groq API key from [console.groq.com](https://console.groq.com) |

---

## Re-ingesting documents

To add new PDFs, copy them into `data/raw_docs/<jurisdiction>/` then re-run:

```bash
python src/ingest.py
python src/embed.py
```

For Docker, rebuild the image after re-ingesting. For Streamlit Cloud, commit the updated `data/` files and push — Streamlit will auto-redeploy.
