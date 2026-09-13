# ── Healdar — Dockerfile ─────────────────────────────────────────────────────
# Multi-stage build: the builder installs dependencies, the runtime copies only
# what is needed to serve.
#
#   docker build -t healdar .
#   docker run -p 8501:8501 -e GROQ_API_KEY=gsk_... healdar
#   docker run -p 8501:8501 --env-file .env healdar
#
# Note on Git LFS: the vector store is tracked with LFS. If you build from a
# clone that has not run `git lfs pull`, the COPY below picks up ~130-byte
# pointer stubs instead of the index. That used to produce a container that
# started happily and answered "no relevant information found" to every single
# question. Two things now prevent that: chunks.json is plain JSON (never LFS),
# and the build step below verifies the index and rebuilds it from chunks.json
# if it is unusable — so the image always ships a working store.

# ── Stage 1: dependency builder ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /install

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libglib2.0-0 \
        libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/deps \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.txt


# ── Stage 2: runtime image ───────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /deps /usr/local

WORKDIR /app

COPY src/        ./src/
COPY .streamlit/ ./.streamlit/

# chunks.json is the source of truth and is plain JSON, so it is always intact.
# The vector store is a build artefact derived from it.
COPY data/processed/chunks.json  ./data/processed/chunks.json
COPY data/processed/vectorstore/ ./data/processed/vectorstore/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ENABLE_CORS=false \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    HF_HOME=/app/.cache/huggingface

# Verify the index and repair it if needed, and warm the embedding model into
# the image. Doing this at build time means a cold container serves its first
# request immediately instead of downloading ~90 MB of weights mid-query.
RUN python -c "import sys; sys.path.insert(0, 'src'); \
import vectorstore; c = vectorstore.load_collection(); \
print('vector store OK:', c.count(), 'documents')"

# Run unprivileged. Everything above is owned by root and stays read-only to
# the app; only the runtime data directory and the model cache need to be
# writable.
RUN useradd --create-home --uid 10001 healdar \
    && mkdir -p /app/data/runtime \
    && chown -R healdar:healdar /app/data/runtime /app/.cache
USER healdar

# GROQ_API_KEY must be injected at runtime via -e or --env-file.
# Never bake secrets into the image.

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request as u; \
u.urlopen('http://localhost:8501/_stcore/health', timeout=5)"

CMD ["streamlit", "run", "src/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0"]
