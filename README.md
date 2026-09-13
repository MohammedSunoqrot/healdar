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

Healdar answers regulatory questions in **English and Arabic**, grounded in 60 official
documents from SFDA, SDAIA, NHIC, UAE DoH & DHA, Qatar MOPH/MCIT/NCSA, the EU, the US FDA,
and the WHO — with a citation and a page number for every claim.

---

## What makes it trustworthy

A regulatory assistant that invents an obligation is worse than no assistant. Three
properties matter more than fluency here:

| Property | How it works |
|---|---|
| **It refuses** | Retrieval is gated on cosine distance. Ask it about cookie recipes and it returns nothing rather than summarising five irrelevant passages into a confident wrong answer. Measured: on-topic queries score 0.19–0.48, off-topic 0.76–0.91; the gate sits at 0.62. |
| **Citations line up** | Source numbering is decided in exactly one place. `[Source 3]` in the text is always the third entry in the reference list — verified end-to-end by the evaluation harness. |
| **It admits gaps** | Every answer carries a self-assessed coverage marker. When the documents only partly cover a question, the answer says so and the UI shows a caution banner. |

---

## Features

| Feature | Detail |
|---|---|
| **Bilingual** | English and Arabic UI; Arabic queries are translated for retrieval, then answered in Arabic |
| **7 jurisdictions** | 🇸🇦 Saudi Arabia · 🇦🇪 UAE · 🇶🇦 Qatar · 🇪🇺 EU · 🇺🇸 US · 🌐 International (WHO) · 🌍 All |
| **Hybrid retrieval** | Dense embeddings **+** BM25, fused with Reciprocal Rank Fusion — so "Article 120" and "MDS-G010" are found by exact token, not just by meaning |
| **Balanced comparison** | In "all jurisdictions" mode, no single corpus can crowd out the others (the EU alone is 53% of the chunks) |
| **Comparison mode** | Two jurisdictions side by side, queried in parallel |
| **Relevance shown** | Each citation displays how well it actually matched |
| **Export** | Download answers as PDF or Word (.docx) |
| **Analytics** | Usage dashboard with CSV export; question text is not stored by default |
| **Dark / Light theme** | Switchable from the sidebar |

---

## Architecture

```
User question (EN or AR)
        │
        ├── Arabic? ──► translate to English            gpt-oss-20b
        │
        ├── follow-up? ──► rewrite as standalone        gpt-oss-20b
        │
        ▼
┌────────────────────────────────────────────────┐
│  HYBRID RETRIEVAL over 3,849 chunks            │
│    dense    ChromaDB + all-MiniLM-L6-v2        │
│    lexical  BM25 over the same chunks          │
│    fuse     Reciprocal Rank Fusion             │
│    gate     drop anything past max_distance    │──► nothing relevant?
│    balance  cap passages per jurisdiction      │      answer "not covered"
└───────────────────────┬────────────────────────┘
                        ▼
            merge same-page passages          ← fixes citation numbering
                        ▼
            generate cited answer             gpt-oss-120b
                        ▼
            Arabic? ──► translate             gpt-oss-120b
                        ▼
            Cited answer + references + coverage badge
```

---

## Project structure

```
Healdar/
├── src/
│   ├── app.py              # Streamlit frontend
│   ├── config.py           # all tunables, every one env-overridable
│   ├── rag_pipeline.py     # orchestration: translate → retrieve → generate
│   ├── retrieval.py        # hybrid search, relevance gate, balancing
│   ├── vectorstore.py      # index lifecycle, integrity checks, auto-repair
│   ├── ingest.py           # PDF → chunks.json
│   ├── embed.py            # chunks.json → ChromaDB
│   ├── export.py           # PDF / Word export
│   └── analytics.py        # SQLite usage analytics
│
├── eval/
│   ├── golden.jsonl        # 54 curated cases, incl. 8 that must be refused
│   └── run_eval.py         # retrieval + generation metrics, CI-gating
│
├── scripts/download_docs.py  # fetch + validate all 59 source documents
├── docs/document-research.md # provenance, gaps, superseded versions
│
├── data/
│   ├── processed/
│   │   ├── chunks.json         # source of truth (committed, plain JSON)
│   │   └── vectorstore/        # derived index (committed via Git LFS)
│   ├── raw_docs/               # source PDFs — NOT committed
│   └── runtime/                # analytics DB — NOT committed
│
├── tests/                  # 163 tests
└── .github/workflows/ci.yml
```

---

## Quick start

```bash
git clone https://github.com/MohammedSunoqrot/healdar.git
cd healdar
git lfs pull                      # IMPORTANT — see note below

python -m venv .venv
.venv\Scripts\activate            # Windows
source .venv/bin/activate         # Linux / macOS

pip install -r requirements.txt
cp .env.example .env              # then add your Groq key
```

Then:

```bash
.\run.bat        # Windows
./run.sh         # Linux / macOS
```

Open <http://localhost:8501>.

> **Why `git lfs pull` matters.** The vector store is LFS-tracked. Without it you get
> ~130-byte pointer stubs, and Chroma opens fine, reports the right document count, and
> then throws on the first query. Healdar now detects this and rebuilds the index from
> `chunks.json` automatically — but pulling properly is faster than re-embedding 3,849
> chunks.

### Rebuilding the corpus

```bash
python scripts/download_docs.py       # fetch + validate source PDFs
python src/ingest.py                  # PDFs  → chunks.json
python src/embed.py --rebuild         # chunks → vector store
```

### Running the checks

```bash
pytest tests -q                       # 163 unit tests
python eval/run_eval.py               # retrieval metrics (no API key needed)
python eval/run_eval.py --full        # also generates answers (uses Groq)
ruff check src tests eval scripts
```

---

## Configuration

Everything is environment-overridable — see `.env.example` for the full list.

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | — | **Required.** [console.groq.com](https://console.groq.com) |
| `GROQ_MODEL_ANSWER` | `openai/gpt-oss-120b` | Writes the answer |
| `GROQ_MODEL_LARGE` | `openai/gpt-oss-120b` | Arabic translation |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Query translation, follow-up rewriting |
| `HEALDAR_MAX_DISTANCE` | `0.62` | Relevance gate — lower refuses more |
| `HEALDAR_TOP_K` | `5` | Passages given to the model |
| `HEALDAR_HYBRID` | `1` | BM25 alongside dense search |
| `HEALDAR_MAX_PER_JX` | `2` | Per-jurisdiction cap in "all" mode |
| `HEALDAR_PERSIST_SESSION` | `0` | Chat history to disk — **leave off when shared** |
| `HEALDAR_ANALYTICS_QUESTIONS` | `0` | Store raw question text |
| `HEALDAR_RATE_LIMIT_QUERIES` | `0` | Per-session throttle (0 = off) |

> **Models get retired.** Groq decommissioned `llama-3.1-8b-instant` and
> `llama-3.3-70b-versatile` on 2026-08-16, which broke every query at once. Healdar now
> checks its configured model at startup and says so plainly. Keep an eye on
> [the deprecation schedule](https://console.groq.com/docs/deprecations); switching is a
> config change, not a code change.

---

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for Docker, Streamlit Cloud, and HuggingFace Spaces.

`./deploy.sh` runs the tests and the evaluation, then pushes to GitHub. Publishing to the
**public** HuggingFace Space is opt-in via `./deploy.sh --hf`.

---

## Coverage

60 documents, 3,849 chunks.

| Jurisdiction | Bodies | Documents |
|---|---|---|
| 🇸🇦 Saudi Arabia | SFDA, SDAIA, NHIC | 18 |
| 🇪🇺 European Union | MDR, IVDR, AI Act, MDCG, GPAI Code | 14 |
| 🇺🇸 United States | FDA | 9 |
| 🇦🇪 UAE | DoH Abu Dhabi, DHA Dubai, National | 10 |
| 🇶🇦 Qatar | MOPH, MCIT, NCSA | 8 |
| 🌐 International | WHO | 1 |

Provenance, publication dates, superseded versions, and the documents deliberately
*excluded* (paywalled standards, drafts, non-primary sources) are recorded in
[docs/document-research.md](docs/document-research.md).

**Known gaps**, needing manual sourcing: UAE Federal Decree-Law 45/2021 (no official
English PDF), Qatar Law 13/2016 (the official portal serves a broken TLS chain — not
worth disabling certificate verification to fetch the text of a law), and IMDRF N88/N81.

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | [Streamlit](https://streamlit.io) 1.58 |
| LLM | [Groq](https://groq.com) — GPT-OSS 120B + 20B |
| Embeddings | [sentence-transformers](https://www.sbert.net/) `all-MiniLM-L6-v2` |
| Lexical search | [rank-bm25](https://github.com/dorianbrown/rank_bm25) |
| Vector store | [ChromaDB](https://www.trychroma.com/) 1.5 |
| PDF parsing | PyMuPDF |
| Export | ReportLab (PDF) + python-docx (Word) |
| Analytics | SQLite |

---

## Disclaimer

Healdar is an informational tool. It is not legal or regulatory advice. Always verify
against the official published documents and consult the relevant regulatory body.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

Copyright 2026 Mohammed R. S. Sunoqrot
