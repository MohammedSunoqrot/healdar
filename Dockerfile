# ── RegRadar — Dockerfile ────────────────────────────────────────────────────
# Multi-stage build: builder installs deps, runtime copies only what's needed.
# Image size: ~1.5 GB (dominated by torch CPU + sentence-transformers weights)
#
# Build:
#   docker build -t regradar .
#
# Run:
#   docker run -p 8501:8501 -e GROQ_API_KEY=gsk_... regradar
#
# Or with a .env file:
#   docker run -p 8501:8501 --env-file .env regradar

# ── Stage 1: dependency builder ───────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /install

# System libraries needed by ChromaDB / PyMuPDF / sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libglib2.0-0 \
        libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install into an isolated prefix so we can copy it cleanly
RUN pip install --no-cache-dir --prefix=/deps \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -r requirements.txt


# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Runtime libs only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /deps /usr/local

WORKDIR /app

# Copy application code
COPY src/        ./src/
COPY .streamlit/ ./.streamlit/

# Copy pre-built vectorstore and chunks
# (built locally via: python src/ingest.py && python src/embed.py)
COPY data/processed/vectorstore/ ./data/processed/vectorstore/
COPY data/processed/chunks.json  ./data/processed/chunks.json

# Streamlit config
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_ENABLE_CORS=false
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# GROQ_API_KEY must be injected at runtime via -e or --env-file
# Never bake secrets into the image.

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

CMD ["streamlit", "run", "src/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0"]
