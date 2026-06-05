---
title: Healdar
emoji: 📡🩺
colorFrom: indigo
colorTo: blue
sdk: streamlit
sdk_version: 1.58.0
app_file: src/app.py
pinned: false
license: apache-2.0
---

# 📡🩺 Healdar — Health AI Regulatory Navigator

**Bilingual AI assistant for navigating health AI regulations across the Gulf region, Europe, and the United States.**

Healdar uses Retrieval-Augmented Generation (RAG) to give grounded, source-cited answers to regulatory questions in both **English and Arabic** — covering SFDA, UAE DoH, Qatar MOPH, EU MDR, and US FDA.

---

## Features

| Feature | Detail |
|---|---|
| **Bilingual** | English and Arabic UI; Arabic queries auto-translated for retrieval then answered in Arabic |
| **6 jurisdictions** | 🇸🇦 SFDA · 🇦🇪 UAE DoH · 🇶🇦 Qatar MOPH · 🇪🇺 EU MDR · 🇺🇸 US FDA · 🌍 All |
| **Comparison mode** | Side-by-side answers from two jurisdictions at once |
| **Source citations** | Every answer shows the exact document and page number |
| **Export** | Download answers as PDF or Word (.docx) |
| **Chat history** | Conversation context carried across questions |
| **Analytics** | Built-in query analytics dashboard (CSV export) |
| **Dark / Light theme** | Switchable from the sidebar |

---

## Architecture

```
User question (EN or AR)
        │
        ▼
┌───────────────────────────────────┐
│  Arabic path: translate → EN      │  Llama 3.1 8B (Groq)
│  English path: use as-is          │
└───────────────────┬───────────────┘
                    │
                    ▼
        ┌───────────────────┐
        │  ChromaDB retrieval│  all-MiniLM-L6-v2 embeddings
        │  top-5 chunks      │  filtered by jurisdiction
        └─────────┬─────────┘
                  │
                  ▼
        ┌───────────────────┐
        │  Answer generation │  Llama 3.1 8B (Groq)
        └─────────┬─────────┘
                  │
        ┌─────────▼─────────┐
        │  Arabic path only  │  Llama 3.3 70B (Groq) — high-quality translation
        └─────────┬─────────┘
                  │
                  ▼
        Cited answer + source strip
```

---

## Project Structure

```
Healdar/
├── src/
│   ├── app.py              # Streamlit frontend
│   ├── rag_pipeline.py     # RAG logic (retrieval + generation)
│   ├── ingest.py           # PDF → chunks.json
│   ├── embed.py            # chunks.json → ChromaDB vectorstore
│   ├── export.py           # PDF / Word export helpers
│   └── analytics.py        # SQLite query analytics
│
├── scripts/
│   └── download_docs.py    # Helper to download regulatory PDFs
│
├── data/
│   ├── processed/
│   │   ├── chunks.json         # Chunked text (committed)
│   │   └── vectorstore/        # ChromaDB index (committed)
│   ├── raw_docs/               # Source PDFs — NOT committed (.gitignore)
│   └── runtime/
│       ├── analytics.db        # Local analytics — NOT committed
│       └── last_session.json   # Last session cache — NOT committed
│
├── tests/                  # pytest test suite
├── .streamlit/
│   ├── config.toml         # Theme + server settings
│   └── secrets.toml.example
│
├── .env.example            # Copy to .env and fill in your key
├── Dockerfile              # Multi-stage Docker build
├── requirements.txt
├── run.bat                 # Windows launcher
├── run.sh                  # Linux/macOS launcher
├── deploy.sh               # Push to GitHub + HuggingFace
└── LICENSE                 # Apache 2.0
```

---

## Quick Start (Local)

### 1. Clone and create the environment

```bash
git clone https://github.com/MohammedSunoqrot/healdar.git
cd healdar
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Set your Groq API key

```bash
# Copy the example and fill in your key
cp .env.example .env
```

Edit `.env`:

```
GROQ_API_KEY=gsk_your_key_here
```

Get a free key at [console.groq.com](https://console.groq.com).

### 3. Run

The vectorstore is already built and committed. Just launch the app:

```bash
# Windows
.\run.bat

# Linux / macOS
./run.sh
```

Then open [http://localhost:8501](http://localhost:8501).

> **To rebuild the vectorstore** (e.g. after adding new regulatory PDFs):
> ```bash
> python src/ingest.py   # PDF → data/processed/chunks.json
> python src/embed.py    # chunks.json → data/processed/vectorstore/
> ```

---

## Deploying on HuggingFace Spaces

1. Fork or push this repo to your HF Space (see `deploy.sh`)
2. In the Space settings → **Variables and secrets**, add:

   | Name | Value |
   |---|---|
   | `GROQ_API_KEY` | `gsk_your_key_here` |

3. HF Spaces auto-deploys on every push to `main`.

---

## Deploying on Streamlit Cloud

1. Push to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**
3. Select your repo, set **Main file path** to `src/app.py`
4. Under **Advanced settings → Secrets**, paste:

   ```toml
   GROQ_API_KEY = "gsk_your_key_here"
   ```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | ✅ Yes | Groq API key — [console.groq.com](https://console.groq.com) |
| `HF_HUB_OFFLINE` | No | Set to `1` to skip HuggingFace Hub network checks (set automatically by `run.bat` / `run.sh`) |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | [Streamlit](https://streamlit.io) 1.58 |
| LLM | [Groq](https://groq.com) — Llama 3.1 8B + Llama 3.3 70B |
| Embeddings | [sentence-transformers](https://www.sbert.net/) — `all-MiniLM-L6-v2` |
| Vector store | [ChromaDB](https://www.trychroma.com/) 1.5 |
| PDF parsing | PyMuPDF + pypdf |
| Export | ReportLab (PDF) + python-docx (Word) |
| Analytics | SQLite via Python stdlib |

---

## Supported Regulatory Documents

| Jurisdiction | Body | Coverage |
|---|---|---|
| 🇸🇦 Saudi Arabia | SFDA + SDAIA | Medical devices, AI regulations |
| 🇦🇪 UAE | DoH Abu Dhabi, DHA Dubai | Health AI frameworks |
| 🇶🇦 Qatar | MOPH, MCIT, NCSA | Digital health policy |
| 🇪🇺 European Union | EU MDR, MDCG guidance | Medical device regulation |
| 🇺🇸 United States | FDA | AI/ML-based SaMD guidance |

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

Copyright 2026 Mohammed R. S. Sunoqrot
