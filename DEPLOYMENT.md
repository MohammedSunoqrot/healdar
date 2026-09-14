# Healdar — Deployment Guide

Three supported targets: **Docker** (self-hosted, full control), **HuggingFace Spaces**,
and **Streamlit Cloud**.

---

## Before you deploy

### 1. Pull the Git LFS objects

The vector store is LFS-tracked. A clone without `git lfs pull` yields ~130-byte pointer
stubs. Chroma will open them, report the correct document count, and then throw on the
first query — which, before this was handled, surfaced to users as
*"no relevant information found"* for **every** question.

```bash
git lfs pull
python -c "import sys; sys.path.insert(0,'src'); import config, vectorstore; \
print(vectorstore.find_lfs_pointers(config.DATA_DIR) or 'no pointer stubs')"
```

Healdar now detects this and rebuilds from `chunks.json` automatically, but rebuilding
takes a minute or two — pulling properly is faster.

### 2. Run the checks

```bash
pytest tests -q
python eval/run_eval.py
```

`./deploy.sh` does both for you and refuses to push if either fails.

### 3. Build the corpus (only if you changed the documents)

```bash
python scripts/download_docs.py    # fetch + validate source PDFs
python src/ingest.py               # PDFs  → data/processed/chunks.json
python src/embed.py --rebuild      # chunks → data/processed/vectorstore/
```

Commit both `data/processed/chunks.json` and `data/processed/vectorstore/`.

---

## Option 1 — Docker

```bash
docker build -t healdar .
docker run -d --name healdar -p 8501:8501 -e GROQ_API_KEY=gsk_your_key healdar
```

Then open <http://localhost:8501>.

The build verifies the vector store and repairs it from `chunks.json` if needed, and warms
the embedding model into the image — so a cold container serves its first request
immediately instead of downloading ~470 MB of weights mid-query. Build time ~6 min, final
image ~1.5 GB.

With an env file (never commit it):

```bash
docker run -d --name healdar -p 8501:8501 --env-file .env healdar
```

To keep analytics across restarts, mount the runtime directory:

```bash
docker run -d --name healdar -p 8501:8501 --env-file .env \
  -v healdar-runtime:/app/data/runtime healdar
```

The container runs as an unprivileged user (`uid 10001`).

### On a cloud VM

```bash
curl -fsSL https://get.docker.com | sh
git clone https://github.com/MohammedSunoqrot/healdar.git && cd healdar
git lfs pull
docker build -t healdar .
docker run -d --restart=unless-stopped -p 8501:8501 \
  -e GROQ_API_KEY=gsk_your_key healdar
```

Put nginx in front for HTTPS:

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

## Option 2 — HuggingFace Spaces

The Space is **public**. `deploy.sh` therefore treats publishing as opt-in:

```bash
./deploy.sh          # tests + eval, then push to GitHub only
./deploy.sh --hf     # ... and publish to the public Space (asks to confirm)
```

`--hf` refuses to run from any branch other than `main`.

In **Settings → Variables and secrets**, add:

| Name | Value |
|---|---|
| `GROQ_API_KEY` | `gsk_your_key_here` |

Recommended for a public Space:

| Name | Value | Why |
|---|---|---|
| `HEALDAR_RATE_LIMIT_QUERIES` | `20` | Anyone who opens the page spends your API quota |
| `HEALDAR_PERSIST_SESSION` | `0` | Default. The history file is process-wide, not per-visitor |
| `HEALDAR_ANALYTICS_QUESTIONS` | `0` | Default. Questions can carry sensitive detail |

Notes:

- **Push LFS objects to the Space's own storage.** HuggingFace has separate LFS storage
  from GitHub; if the objects never reach it, the Space checks out pointer stubs. The
  startup integrity check will rebuild from `chunks.json`, but the first request will be
  slow. Verify with `git lfs push hf main --all`.
- Do **not** set `HF_HUB_OFFLINE` — the embedding model must be downloadable on cold start.
- The filesystem is ephemeral: `analytics.db` resets on every restart.

---

## Option 3 — Streamlit Cloud

1. Push to GitHub.
2. [share.streamlit.io](https://share.streamlit.io) → **New app** → set **Main file path**
   to `src/app.py`.
3. **Advanced settings → Secrets**:

```toml
GROQ_API_KEY = "gsk_your_key_here"
```

First deploy downloads the embedding model (~470 MB); expect a ~3 min cold start. The free
tier gives 1 GB RAM — the model plus the vector store sit around 500 MB. The filesystem is
ephemeral here too.

---

## Environment variables

`GROQ_API_KEY` is the only required one. Everything else has a working default — see
[.env.example](.env.example) for the annotated list, and the table in
[README.md](README.md#configuration) for the ones worth tuning.

---

## When something breaks

| Symptom | Cause | Fix |
|---|---|---|
| Every question answers "no relevant material found" | Vector store is pointer stubs or corrupt | `git lfs pull`, or `python src/embed.py --rebuild`. The app self-heals if `HEALDAR_AUTO_REBUILD=1` (the default). |
| "The configured language model was rejected" | Groq retired the model | Set `GROQ_MODEL_ANSWER` to a current model from [the model list](https://console.groq.com/docs/models) |
| "Healdar is temporarily unavailable" on load | Missing `GROQ_API_KEY`, or the index could not be opened or rebuilt | The card shows the underlying error; check the container logs |
| Rate-limit warnings under load | Groq free-tier quota: 8,000 tokens a minute for `gpt-oss-120b`, and one question requests about 5,000 of them | Set `HEALDAR_RATE_LIMIT_QUERIES`, or upgrade the Groq plan. `HEALDAR_QUERY_PLANNING=0` saves ~650 tokens a question, at the cost of weaker answers to case questions |
| "Healdar has used today's free AI allowance" | Both models' daily allowances are used up. The free plan gives `gpt-oss-120b` 200,000 tokens a day (about 40 questions); after that answers come from the backup `gpt-oss-20b` until its allowance runs out too | Wait for the time the message shows, or upgrade the Groq plan |
| Answers are hedged or refused too often | Relevance gate too tight for your corpus | Raise `HEALDAR_MAX_DISTANCE`, then re-run `python eval/run_eval.py` to confirm off-topic questions are still refused |

---

## Updating the corpus

Regulations are revised. `docs/document-research.md` records each document's version and
publication date. To refresh:

1. Update the URL and `expect` string in `scripts/download_docs.py`.
2. `python scripts/download_docs.py --force --only <substring>`
3. `python src/ingest.py && python src/embed.py --rebuild`
4. `python eval/run_eval.py` — confirm nothing regressed.
5. Commit `chunks.json` and `vectorstore/`, then deploy.

The downloader asserts that each PDF contains an expected identifier on its opening pages.
That check exists because two files in this corpus were named as AI guidance while actually
containing general-wellness and spectacle-frame UDI text — a mislabelled source is worse
than a missing one, because retrieval surfaces it under the wrong question with a citation
that looks authoritative.
