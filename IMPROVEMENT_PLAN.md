# Healdar — Improvement Plan

_Full review of the codebase, RAG pipeline, deployment, and tests. Findings are grouped by
priority. Each item states the problem, why it matters, and the concrete fix._

Reviewed at commit `3c232b2`. Stack verified installed: Streamlit 1.58.0, chromadb 1.5.9,
sentence-transformers 5.5.1, groq 1.4.0, Python 3.13.

---

## 0. CRITICAL — the app is broken or about to break

### 0.1 Groq models `llama-3.1-8b-instant` and `llama-3.3-70b-versatile` are decommissioned
- **Problem:** Groq announced deprecation of both models on 2026‑06‑17 with **end‑of‑life
  2026‑08‑16** for free and developer tiers. After that date, requests to those model IDs
  return errors. Healdar hard-codes both (`rag_pipeline.py:40-41`). Every code path —
  translation, reformulation, generation — depends on them. As of now the app most likely
  errors on every query on a non-enterprise key.
- **Fix:**
  1. Migrate: `GROQ_MODEL` → `openai/gpt-oss-20b`, `GROQ_MODEL_LARGE` → `openai/gpt-oss-120b`
     (both 131k context, faster than the Llama models). Verify quality on the Arabic
     translation path especially.
  2. **Make model IDs environment-configurable** (`GROQ_MODEL`, `GROQ_MODEL_LARGE` env vars
     with sane defaults) so the next deprecation is a config change, not a redeploy.
  3. Add a **startup self-check**: on `HealdarRAG.__init__`, do one tiny `chat.completions`
     call (`max_tokens=1`); if the model ID is rejected, fail fast with a clear message in
     the UI ("model X unavailable — set GROQ_MODEL") instead of failing per-query.
  4. Subscribe to Groq deprecation notices; add a comment in `rag_pipeline.py` linking
     `https://console.groq.com/docs/deprecations`.

### 0.2 No retrieval relevance threshold → confident hallucination
- **Problem:** `_retrieve` always asks Chroma for `TOP_K=5` and returns whatever comes back.
  `distances` is requested in the query but **never used**. With a jurisdiction filter and a
  small corpus, Chroma almost always returns 5 chunks even for a totally unrelated question,
  so `no_context` (which only triggers on an *empty* list) essentially never fires. The LLM
  is then handed 5 irrelevant passages and told to answer "using ONLY the context" — it
  produces a plausible, cited, wrong answer. For a regulatory tool this is the single biggest
  reliability risk.
- **Fix:**
  1. Use the cosine distances. Drop chunks above a distance cutoff (tune empirically, e.g.
     `> 0.45` for MiniLM cosine). If nothing survives → real `no_context`.
  2. Show the retrieval score on each reference row ("relevance 0.82") so users can judge.
  3. If the top chunk is weak but not empty, prepend a visible hedge: _"Limited relevant
     material found — treat this answer as partial."_
  4. Add a "coverage" check: after generation, if the answer contains no `[Source N]` tag at
     all, surface a warning rather than presenting it as grounded.

### 0.3 `last_session.json` is a single global file shared by every user
- **Problem:** `save_session` / `load_session` write one file at
  `data/runtime/last_session.json` with **no per-session key**. On any multi-user deployment
  (HF Spaces, a shared URL) user B's refresh loads user A's questions and answers. That is a
  privacy leak and a correctness bug. `st.session_state` is per-session; the file is not.
- **Fix:** Either (a) drop file persistence entirely and rely on `st.session_state` (simplest,
  recommended for a public Space), or (b) key the file by a per-browser token stored in a
  cookie / `st.query_params` and expire old files. Given HF Spaces has an ephemeral
  filesystem anyway, (a) is the right call. Keep an in-memory history only.

### 0.4 Startup failures dump a raw traceback to users
- **Problem:** `load_rag()` is `@st.cache_resource`; if `GROQ_API_KEY` is missing or the
  vectorstore path is wrong, `HealdarRAG.__init__` raises and Streamlit renders a full Python
  traceback to the end user. Same for a Chroma index that fails to load (version mismatch,
  un-pulled LFS pointer).
- **Fix:** Wrap `load_rag()` in `main()` in a try/except that renders a friendly, bilingual
  "Healdar is temporarily unavailable" card and logs the real error server-side. Add an
  explicit check that `chroma.sqlite3` is a real DB file and not a 130-byte LFS pointer.

---

## 1. HIGH — reliability & correctness

### 1.1 Citation numbers in the answer don't match the reference list
- **Problem:** `ask()` builds the prompt by enumerating all 5 retrieved `chunks` →
  `[Source 1..5]`. `render_answer` then **re-dedupes** sources by `(filename, page_number)`
  and **re-indexes from 1** (`app.py:666-669`). If two retrieved chunks share a page, the
  deduped list has 4 entries, so `[Source 5]` cited by the model is silently dropped, and the
  reference shown as `[3]` may be the passage the model called Source 4. Users click a
  citation and get the wrong text.
- **Fix:** Deduplicate **once, before** `_build_prompt` in `ask()`, so the prompt numbering,
  `RAGAnswer.sources`, and the UI all share one index space. `render_answer` should not
  re-dedupe or re-number — just filter to cited numbers.

### 1.2 Groq error handling is string-matching, no timeout, no retry
- **Problem:** `_generate` / `_translate_*` detect rate limits with
  `"rate limit" in str(exc).lower()`. The groq SDK raises typed exceptions
  (`groq.RateLimitError`, `groq.APIStatusError`, `groq.APIConnectionError`,
  `groq.APITimeoutError`). String matching is brittle and will miss localized or reworded
  messages. There is also no explicit request timeout and no retry/backoff, so a transient
  502 fails the whole query and a hung connection spins the spinner forever.
- **Fix:**
  - `Groq(api_key=..., timeout=30.0, max_retries=2)`.
  - Catch `groq.RateLimitError` explicitly → `RateLimitError`. Catch
    `groq.APIConnectionError` / `APITimeoutError` → a distinct "service unavailable" message.
  - Wrap the LLM calls in a small bounded backoff (e.g. `tenacity`, 2 retries, jitter) for
    5xx only.

### 1.3 `datetime.utcnow()` is deprecated; analytics "today" is timezone-inconsistent
- **Problem:** `analytics.py:66` uses `datetime.utcnow()` (deprecated in 3.12+, removed
  later). Rows are stored in UTC but the "today" query filters on `date.today()` (local
  date). Near midnight the counts are wrong.
- **Fix:** `datetime.now(timezone.utc)`. Decide on one zone for "today" (UTC is fine) and use
  it consistently. Consider storing an integer epoch too, for range queries.

### 1.4 Comparison mode and the Arabic pipeline run every LLM call serially
- **Problem:** Compare mode calls `rag.ask()` twice back-to-back. Each `ask()` can itself do
  translate → reformulate → generate → translate. An Arabic comparison is up to **8 serial
  Groq calls** behind one spinner — slow, and it multiplies rate-limit exposure.
- **Fix:** Run the two `ask()` calls concurrently with `concurrent.futures.ThreadPoolExecutor`
  (the groq client is thread-safe for separate requests). Within `ask()`, the translate and
  reformulate steps can't be parallel, but you can skip reformulation more aggressively
  (see 2.7) and stream the generation.

### 1.5 `_retrieve` turns infrastructure errors into "no information found"
- **Problem:** `except Exception: return []` means a Chroma corruption, an OOM, or a schema
  mismatch is presented to the user as _"I could not find relevant information"_ — the exact
  wording used for a genuine empty result. Users conclude the regulation is silent when the
  system is broken.
- **Fix:** Let unexpected exceptions propagate to a distinct error card ("retrieval failed,
  try again"). Reserve the empty-list path for genuinely zero results.

### 1.6 The test suite is partly broken and there is no CI
- **Problems:**
  - `tests/test_embed.py:11` and `tests/test_ingest.py:13` set
    `CODE_DIR = .../ "code"` — the directory is `src`. These modules only import today by
    accident, because `test_app_helpers.py` (loaded earlier by the discoverer) inserts
    `src/` on `sys.path` before it crashes.
  - `tests/test_app_helpers.py` does `sys.modules.setdefault("streamlit", MagicMock())`, but
    Streamlit is actually installed, and `app.py` now does
    `import streamlit.components.v1` → `ModuleNotFoundError: 'streamlit' is not a package`.
    The whole module fails to import (1 error in the current run).
  - `pytest` isn't even in the environment; `.pytest_cache/lastfailed` references a test
    (`test_more_than_3_shows_overflow_button`) that no longer exists.
- **Fix:**
  - Add a `tests/conftest.py` that puts `src/` on `sys.path` once; delete the per-file
    `sys.path` hacks and fix `code` → `src`.
  - Mock Streamlit properly (a small fake package, or `pytest-mock` with
    `sys.modules["streamlit"]` **and** `sys.modules["streamlit.components.v1"]`), or better:
    move the pure helpers (`text_to_html`, `prettify_filename`, `source_strip_html`,
    `build_history_context`, …) into `src/ui_helpers.py` with **no Streamlit import**, and
    test that. `app.py` becomes a thin shell.
  - Add `pytest`, `pytest-cov`, `ruff`, `mypy` to a `requirements-dev.txt`.
  - Add a GitHub Actions workflow: lint + type-check + tests on push/PR.

### 1.7 `importlib.reload(rag_pipeline)` runs on every rerun in production
- **Problem:** `app.py:27-28` reloads the module on every Streamlit rerun. This is a dev
  convenience but in production it (a) wastes work and (b) creates a *new* `RAGAnswer` class
  object each time, which is the reason the fragile `dataclasses.is_dataclass` /
  `RAGAnswer(**dict)` round-tripping exists in the session code.
- **Fix:** Guard it behind `if os.getenv("HEALDAR_DEV"):`. Remove the reload in prod and the
  serialization hacks get simpler.

### 1.8 Docker / HF Spaces deployment gaps
- Vectorstore files are **Git LFS pointers**. `Dockerfile` does `COPY data/processed/...`; a
  build from a clone without `git lfs pull` copies 130-byte pointer files and Chroma fails at
  runtime. Add `RUN git lfs pull` (needs git+git-lfs in the builder) or document it loudly,
  or ship the vectorstore as a build artifact / release asset instead of LFS.
- Container runs as **root**. Add a non-root `USER`.
- `HEALTHCHECK` calls `urllib.request.urlopen(...)` with **no timeout** — can hang the
  health probe. Add `timeout=5`.
- `requirements.txt` header says "Python 3.13"; `Dockerfile` uses `python:3.11-slim`. Pick
  one and align (3.11 is the safer base; then test locally on 3.11 too).
- `torchvision` is pulled but **not used** (text-only sentence-transformers). Drop it — saves
  ~30 MB and a whole dependency tree.
- Dockerfile header + Chroma collection name still say **"RegRadar" / "regradar"** — finish
  the rename (see 3.1).
- `.dockerignore` doesn't exclude `data/runtime/` — exclude it.

### 1.9 HF Spaces has an ephemeral filesystem — analytics silently reset
- **Problem:** `analytics.db` lives on the container FS. Every Space restart / redeploy wipes
  it. The analytics dashboard will look busy then empty for no visible reason.
- **Fix:** Persist to an HF Dataset repo (append-only JSONL), or a free hosted Postgres
  (Supabase/Neon), or Turso/libSQL. At minimum, put a note in the UI that stats are
  per-deployment. Same caveat already true (worse) for `last_session.json` — see 0.3.

---

## 2. MEDIUM — answer quality & usefulness

### 2.1 Generate with the larger model, not just translate with it
- Today the 8B model writes every English answer; the 70B/120B model only does Arabic
  translation. Regulatory Q&A (multi-clause synthesis, cross-jurisdiction nuance) is exactly
  where a bigger model earns its keep, and Groq is fast enough. Use `gpt-oss-120b` for
  generation; keep a small model only for the cheap translate/reformulate steps. Make it
  configurable and measure with the eval set (2.6).

### 2.2 Add a reranker
- MiniLM bi-encoder retrieval alone is mediocre for precise regulatory queries. Retrieve
  top‑15–20, then rerank to top‑5 with a cross-encoder
  (`cross-encoder/ms-marco-MiniLM-L-6-v2`, ~80 MB, CPU-fine) or a hosted reranker
  (Cohere Rerank, Jina). Big precision win for a small cost.

### 2.3 Hybrid search (dense + lexical)
- Regulatory text is full of exact tokens that dense search fumbles: "Article 120",
  "MDS‑G010", "Rule 11", "Annex VIII", "Class IIb". Add a BM25 / keyword index (e.g.
  `rank_bm25` over the same chunks, or Chroma's `$contains`) and fuse scores (RRF). This
  markedly improves recall on "what does Article X say" questions.

### 2.4 Structure-aware chunking
- Current chunking splits **per page** then by characters. Regulatory clauses routinely span
  page breaks, and a 500-token window cuts mid-article. Improve `ingest.py` to:
  - Concatenate the whole document, then split on heading patterns
    (`^Article \d+`, `^\d+\.\d+`, `^Annex`, `^Section`) with a token cap and overlap.
  - Carry `article` / `section` / `heading` into chunk metadata and show it in citations
    ("EU MDR — Article 10 — p.14"). Much more useful than page number alone.
  - Keep `page_number` as the page where the chunk **starts**.

### 2.5 Multilingual embeddings
- `all-MiniLM-L6-v2` is English-only. Arabic queries are round-tripped through English
  translation (extra latency + a translation-error surface) and you **cannot** add
  Arabic-language source documents. Switch to `intfloat/multilingual-e5-base` or
  `paraphrase-multilingual-mpnet-base-v2`. Then Arabic queries embed directly, Arabic
  regulatory PDFs (SFDA/MOPH publish Arabic originals) become ingestible, and English
  retrieval quality is usually comparable or better. Requires a one-time re-embed.

### 2.6 Build an evaluation harness (do this early — it de-risks everything above)
- Create `eval/golden.jsonl`: 30–50 curated questions per jurisdiction with the expected
  source document(s)/article(s) and 2–3 must-mention facts.
- Metrics: retrieval hit-rate@5 (did the right doc/article come back?), citation faithfulness
  (does every `[Source N]` claim actually appear in chunk N? — check with a cheap LLM grader
  or NLI), answer completeness (must-mention coverage), refusal correctness (does it say
  "not covered" when it should?).
- Run it in CI on a nightly schedule and before any model / chunking / embedding change.
  Without this, every improvement in section 2 is a guess.

### 2.7 Smarter follow-up handling
- `_needs_reformulation` fires on any question ≤ 7 words — lots of legitimate standalone
  questions ("SFDA post-market surveillance rules?") get a needless extra LLM round-trip and
  can be *mis*-rewritten using stale history. Tighten: only reformulate when a
  pronoun/deixis pattern **and** history exist, or when retrieval on the raw query returns
  weak scores. Also feed history into **compare mode** (currently it's dropped there).

### 2.8 Query cache
- Wrap `rag.ask` results in `st.cache_data(ttl=…)` keyed on
  `(question_normalized, jurisdiction, history_hash)`. Identical repeat questions (starter
  prompts, demos, shared links) then cost nothing and return instantly.

### 2.9 Response streaming
- Stream tokens from Groq into the answer card (`stream=True` + a placeholder). Perceived
  latency drops dramatically, which matters when a compare query is doing real work.

### 2.10 Corpus: SDAIA is claimed everywhere but absent
- `JURISDICTION_MAP` has `"ksa": ["SFDA", "KSA_SDAIA"]`, the README says "SFDA + SDAIA",
  `download_docs.py` lists 6 SDAIA PDFs — but `chunks.json` contains **zero** `KSA_SDAIA`
  chunks. The `ksa` alias silently behaves like `sfda`. Either ingest the SDAIA documents
  (PDPL, AI Ethics Principles, GenAI guidelines) or remove the claim from the README and the
  alias. Same check for `Qatar_NCSA` AI Guide V6 and any other "planned but not ingested"
  docs.

### 2.11 "All jurisdictions" retrieval is EU-dominated
- EU is 971 / 1978 chunks (49%). A top-5 over "all" is usually 4× EU + 1× other. For
  genuinely comparative "all" questions, retrieve per-jurisdiction (e.g. top-3 each) then
  rerank/merge, or at least cap chunks-per-jurisdiction in the merge.

### 2.12 Document freshness / provenance
- Regulations are revised. Add a `data/sources.yaml` with, per document: official title, URL,
  version/date, retrieved-on date. Surface "as published <date>" in the citation and a
  global "corpus last updated" line in the About panel. Add a script that re-checks source
  URLs for changes.

### 2.13 Arabic PDF export is actually English
- `export.to_pdf` deliberately falls back to the English answer for Arabic queries because no
  Arabic font is embedded. An Arabic user exporting a PDF gets a language they may not have
  asked for. Bundle a subsetted Arabic font (Amiri / Noto Naskh Arabic, ~few hundred KB
  subset) and use `reportlab` RTL, or switch the PDF path to `weasyprint`/`fpdf2` with proper
  shaping. If it stays English-only, say so in the button tooltip.

### 2.14 Tell the user when the answer is partial
- The prompt says "if the context does not contain enough information … say so". Reinforce:
  ask the model to end with an explicit `COVERAGE: full | partial | none` line, parse it, and
  render a small badge. Pairs well with 0.2.

---

## 3. LOWER — polish, security, infra

### 3.1 Finish the RegRadar → Healdar rename
- Chroma `COLLECTION_NAME = "regradar"` (rag_pipeline + embed), Dockerfile header/examples.
  Renaming the collection means a re-embed; if you don't want that now, at least rename the
  constant's *comment* and the Dockerfile text, and leave a `# collection kept as 'regradar'
  for back-compat` note.

### 3.2 HTML-injection surface
- The app builds a lot of HTML with f-strings and `unsafe_allow_html=True`. Most inputs are
  escaped (`_html.escape`) or from fixed sets, but audit:
  - `_copy_component_html` puts `json.dumps(answer)` inside a `<script>` — a literal
    `</script>` in model output breaks out. Use `json.dumps(text).replace("</", "<\\/")`.
  - Confirm `s["page_number"]` etc. are always ints (they are, from `embed.py`), but assert.
- Add a Content-Security-Policy via a Streamlit static config / reverse proxy for the
  deployed Space.

### 3.3 Abuse protection for a public deployment
- A public Space with your Groq key = anyone can burn your quota. Add a lightweight per-IP /
  per-session rate limit (e.g. N queries / 10 min in `st.session_state` + a shared counter),
  and/or put the Space behind HF's auth, and/or a simple shared password
  (`st.secrets["APP_PASSWORD"]`).

### 3.4 Observability
- Structured logging (JSON) with a per-request id threaded through `ask()`.
- Optional Sentry (`sentry-sdk`) for exceptions.
- Log retrieval scores + which model answered, so you can debug bad answers after the fact.

### 3.5 Dependency hygiene
- Split `requirements.txt` (prod) vs `requirements-dev.txt`.
- Add `.python-version` / `runtime.txt`.
- Consider `pip-tools` or `uv` lockfile with hashes.
- README front-matter `sdk_version: 1.58.0` — keep it in sync with what's actually installed
  and tested; bump deliberately.

### 3.6 Accessibility & UI robustness
- Font sizes down to 0.67rem and color-only jurisdiction dots fail WCAG. Add text labels /
  patterns; raise minimum font size; check contrast in both themes.
- The heavy `!important` CSS overrides fight Streamlit internals and break on Streamlit
  upgrades. Lean on `.streamlit/config.toml` theming + `[data-testid]` selectors sparingly;
  re-test after each Streamlit bump.
- `render_question_bubble` / `_deserialise_entry` assume every history entry has `lang`,
  `mode`, etc. An old persisted file (or a schema change) throws `KeyError`. Use `.get` with
  defaults, or version the persisted schema. (Moot if you drop persistence per 0.3.)

### 3.7 Small correctness nits
- `_is_arabic` returns True on a *single* Arabic character — one Arabic quotation mark in an
  English question forces the whole Arabic pipeline. Use a ratio (≥ 20% Arabic chars).
- Citation regex differs across files: `\[Source\s*(\d+)[^\]]*\]` vs `\[Source\s*(\d+)\]`.
  Centralize one pattern in a shared module.
- `_translate_to_arabic`: if the model drops a `CITEnREF` placeholder, the tag vanishes
  silently. After restore, check all placeholders were re-substituted; if not, fall back to
  the English answer or re-append a plain references list.
- `analytics.get_summary` divides by `max_n` / `total` — guard the empty cases (mostly done,
  but `top_jx[0]["n"]` assumes non-empty after the check; fine, just note it).
- `RAGAnswer.print()` shadows the builtin `print` as a method name — harmless but confusing;
  rename to `to_stdout()`.

### 3.8 Docs
- Add `CONTRIBUTING.md`, a `CHANGELOG.md`, and GitHub issue/PR templates.
- `DEPLOYMENT.md` still references `data/chunks.json` / `data/vectorstore/` (old paths — now
  under `data/processed/`) and `src/.env` (should be `.env`). Fix.
- README architecture diagram still shows the old two-Llama flow — update after the model
  migration.

---

## Suggested execution order

| Phase | Items | Outcome |
|---|---|---|
| **P0 — unbreak (1–2 days)** | 0.1, 0.4, 1.2, 1.3 | App works again on a current Groq key, fails gracefully |
| **P1 — trust (3–5 days)** | 0.2, 1.1, 1.5, 2.6 (eval harness first), 0.3 | Answers are grounded, citations line up, "don't know" works, regressions measurable |
| **P2 — quality (1–2 weeks)** | 2.1, 2.2, 2.3, 2.4, 2.5, 2.11 | Materially better retrieval and answers; re-embed once with multilingual + structure-aware chunks |
| **P3 — hardening (ongoing)** | 1.6, 1.8, 1.9, 3.3, 3.4, 3.5 | CI, clean Docker, persistent analytics, abuse protection |
| **P4 — polish** | 2.7–2.10, 2.12–2.14, 3.1, 3.2, 3.6–3.8 | UX, docs, a11y, provenance |

The eval harness (2.6) is listed in P1 on purpose: build ~30 golden questions **before** you
touch the model, embeddings, or chunking, so every later change is measured rather than
guessed.
