---
title: Healdar
emoji: 📡🩺
colorFrom: indigo
colorTo: blue
sdk: streamlit
sdk_version: 1.58.0
python_version: "3.11"
app_file: src/app.py
pinned: false
license: apache-2.0
---

# 📡🩺 Healdar — Health AI Regulatory Navigator

**Version 2.1.0 · released 14 September 2026**

**Bilingual AI assistant for navigating health AI regulations across the Gulf region, Europe, the United States and international bodies.**

Healdar answers regulatory questions in **English and Arabic**, grounded in **63 official
documents from 16 regulators** — SFDA, SDAIA, NHIC, UAE federal law, DoH Abu Dhabi, DHA
Dubai, Qatar MOPH/MCIT/NCSA and Law 13/2016, the EU (MDR, IVDR, AI Act, MDCG, GPAI Code),
the US FDA, the WHO and the IMDRF — with a citation and a page number for every claim.

---

## What makes it trustworthy

A regulatory assistant that invents an obligation is worse than no assistant. Three
properties matter more than fluency here:

| Property | How it works |
|---|---|
| **It refuses** | Retrieval is gated on cosine distance. Ask it about cookie recipes and it returns nothing rather than summarising five irrelevant passages into a confident wrong answer. Measured on this corpus: every on-topic question's best match scores at most 0.40 and every off-topic one at least 0.66; the gate sits in the gap at 0.53. |
| **Citations line up** | Source numbering is decided in exactly one place. `[3]` in the answer is always the third entry in the reference list — on screen, in the PDF and in the Word export — verified end-to-end by the evaluation harness. |
| **It admits gaps** | Every answer carries a self-assessed coverage marker. When the documents only partly cover a question, the answer says so and a caution banner appears. |

---

## Features

| Feature | Detail |
|---|---|
| **Bilingual** | English and Arabic interface and answers, right-to-left where needed |
| **Arabic sources** | The UAE PDPL is indexed in its official Arabic text and is found from English questions, via multilingual embeddings |
| **7 jurisdiction views** | 🇸🇦 Saudi Arabia · 🇦🇪 UAE · 🇶🇦 Qatar · 🇪🇺 EU · 🇺🇸 US · 🌐 International (WHO, IMDRF) · 🌍 All |
| **Reasons through your case** | Describe a product and ask how the rules apply — which class, which pathway. Healdar searches for the rules that decide it, applies them step by step, cites the page behind each step, and states its assumptions |
| **Follow-up conversation** | Answers stack as a conversation. Ask "why not Class IIa?" or "how would SFDA see it?" and Healdar reads it in context — showing what it understood — builds on the pages the last answer cited, and suggests next questions. **New conversation** starts fresh |
| **Hybrid retrieval** | Dense embeddings **+** BM25, fused with Reciprocal Rank Fusion — so "Article 120" and "MDS-G010" are found by exact token, not just by meaning |
| **Balanced "all" mode** | Passages are capped per jurisdiction, so the EU (44% of the corpus) cannot crowd out the Gulf regulators |
| **Comparison mode** | Two jurisdictions side by side, queried in parallel |
| **Readable answers** | Lists, emphasis and tables are rendered properly — no stray `**` or `|` — in the app and in both exports |
| **Relevance shown** | Every reference shows how well it matched; click it to read the passage |
| **Export** | PDF and Word, with the same citation numbers as the answer |
| **Your session** | A private summary of *your own* questions this session — nothing is shown to other visitors |
| **Light & dark** | Follows your system setting; switch any time from the ⋮ menu (top right): System, Light or Dark |
| **Version shown** | The sidebar shows the running version and its release date |

---

## Architecture

```
User question (EN or AR)
        │
        ├── Arabic? ──► translate to English            gpt-oss-20b
        │
        ├── plan: rewrite a follow-up to stand alone,   gpt-oss-120b
        │         name the rules that decide it ─► 3 searches
        │
        ├── follow-up? ──► add the pages the last answer cited
        │
        ▼
┌────────────────────────────────────────────────┐
│  HYBRID RETRIEVAL over 3,572 passages          │
│    dense    ChromaDB + multilingual MiniLM     │
│    lexical  BM25 over the same passages        │
│    fuse     Reciprocal Rank Fusion             │
│    gate     drop anything past max_distance    │──► nothing relevant?
│    balance  cap passages per jurisdiction      │      answer "not covered"
└───────────────────────┬────────────────────────┘
                        ▼
            merge same-page passages          ← one citation numbering
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
│   ├── config.py           # all tunables (env-overridable), version and release date
│   ├── rag_pipeline.py     # orchestration: translate → retrieve → generate
│   ├── retrieval.py        # hybrid search, relevance gate, balancing
│   ├── vectorstore.py      # index lifecycle, integrity checks, auto-repair
│   ├── formatting.py       # answer text → HTML / PDF / Word, no raw Markdown
│   ├── ingest.py           # PDF → chunks.json (picks the right extractor for Arabic)
│   ├── embed.py            # chunks.json → ChromaDB
│   ├── export.py           # PDF / Word export
│   └── analytics.py        # anonymous operator log (never shown to visitors)
│
├── eval/
│   ├── golden.jsonl        # 60 curated cases, incl. 8 that must be refused
│   └── run_eval.py         # retrieval + generation metrics, CI-gating
│
├── scripts/download_docs.py  # the authoritative manifest of all 63 source documents
├── docs/document-research.md # provenance, gaps, superseded versions
│
├── data/
│   ├── processed/
│   │   ├── chunks.json         # source of truth (committed, plain JSON)
│   │   └── vectorstore/        # derived index (committed via Git LFS)
│   ├── raw_docs/               # source PDFs, one folder per regulator — NOT committed
│   └── runtime/                # local runtime data — NOT committed
│
├── tests/                  # 269 tests
└── .github/workflows/ci.yml
```

`data/raw_docs/` is organised as `<Country>_<Body>`: `KSA_SFDA`, `KSA_SDAIA`, `KSA_NHIC`,
`UAE_Federal`, `UAE_DoH_AbuDhabi`, `UAE_DHA_Dubai`, `Qatar_MOPH`, `Qatar_MCIT`,
`Qatar_NCSA`, `Qatar_Legislation`, `EU_Legislation`, `EU_MDCG`, `EU_AI_Office`,
`USA_FDA`, `INT_WHO`, `INT_IMDRF`.

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
> then throws on the first query. Healdar detects this and rebuilds the index from
> `chunks.json` automatically — but pulling properly is faster than re-embedding.

### Rebuilding the corpus

```bash
python scripts/download_docs.py       # fetch + validate source PDFs
python src/ingest.py                  # PDFs  → chunks.json
python src/embed.py --rebuild         # chunks → vector store
```

Four documents have no reliable automated source and are supplied by hand (the manifest
marks them `manual=True`): IMDRF N81 and N88, Qatar Law 13/2016, and the UAE Federal
Decree-Law 45/2021, whose official text is Arabic only.

### Running the checks

```bash
pytest tests -q                       # 269 tests
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
| `HEALDAR_MAX_DISTANCE` | `0.53` | Relevance gate — lower refuses more |
| `HEALDAR_EMBED_MODEL` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | Embedding model — rebuild the index after changing |
| `HEALDAR_TOP_K` | `5` | Passages given to the model |
| `HEALDAR_HYBRID` | `1` | BM25 alongside dense search |
| `HEALDAR_QUERY_PLANNING` | `1` | Search for the rules a question depends on, not just its wording |
| `GROQ_MODEL_PLANNER` | `openai/gpt-oss-120b` | Plans those searches |
| `HEALDAR_MAX_PER_JX` | `2` | Per-jurisdiction cap in "all" mode |
| `HEALDAR_PERSIST_SESSION` | `0` | Chat history to disk — **leave off when shared** |
| `HEALDAR_ANALYTICS_QUESTIONS` | `0` | Store raw question text in the operator log |
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

63 documents, 3,572 passages, 16 regulators.

| Jurisdiction | Bodies | Documents |
|---|---|---|
| 🇸🇦 Saudi Arabia | SFDA, SDAIA, NHIC | 18 |
| 🇪🇺 European Union | MDR, IVDR, AI Act · MDCG · AI Office (GPAI Code) | 13 |
| 🇦🇪 UAE | Federal (AI Strategy, PDPL 45/2021) · DoH Abu Dhabi · DHA Dubai | 11 |
| 🇶🇦 Qatar | MOPH · MCIT · NCSA · Law 13/2016 | 9 |
| 🇺🇸 United States | FDA | 9 |
| 🌐 International | WHO · IMDRF (N81, N88) | 3 |

Provenance, publication dates, superseded versions, and the documents deliberately
*excluded* (paywalled standards, drafts, non-primary sources) are recorded in
[docs/document-research.md](docs/document-research.md).

**Known gap:** the Qatar National Health Strategy 2024–2030 is published as a web page
only, with no downloadable document.

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | [Streamlit](https://streamlit.io) 1.58 |
| LLM | [Groq](https://groq.com) — GPT-OSS 120B + 20B |
| Embeddings | [sentence-transformers](https://www.sbert.net/) `paraphrase-multilingual-MiniLM-L12-v2` — reads Arabic and English |
| Lexical search | [rank-bm25](https://github.com/dorianbrown/rank_bm25) |
| Vector store | [ChromaDB](https://www.trychroma.com/) 1.5 |
| PDF parsing | PyMuPDF, with pypdf for Arabic documents whose fonts PyMuPDF mis-decodes |
| Export | ReportLab (PDF) + python-docx (Word) |

---

## Disclaimer

Healdar is an informational tool. It is not legal or regulatory advice. Always verify
against the official published documents and consult the relevant regulatory body.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

Copyright 2026 Mohammed R. S. Sunoqrot
