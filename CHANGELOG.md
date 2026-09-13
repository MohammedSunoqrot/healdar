# Changelog

## 2.0.0 — unreleased (branch `v2-reliability`)

A reliability release. Two faults had already taken the deployed app down, and a third
would have produced wrong answers rather than no answers.

### Fixed — the app was broken in production

- **Groq retired both models on 2026-08-16.** `llama-3.1-8b-instant` and
  `llama-3.3-70b-versatile` were decommissioned for free and developer tiers, so every
  query failed. Migrated to `openai/gpt-oss-120b` (answers, Arabic translation) and
  `openai/gpt-oss-20b` (query translation, follow-up rewriting). Model IDs are now
  environment variables, and a startup check reports a retired model in plain language
  instead of failing on every query.

- **The committed vector store was corrupt.** `index_metadata.pickle` was a 131-byte Git
  LFS pointer stub rather than the real HNSW metadata. Chroma opened it, reported all
  1,978 documents, then threw on the first query — and the old `_retrieve` caught that
  exception and returned an empty list, so users were told *"no relevant information
  found"* for **every single question**. The index now proves it can answer a query at
  startup, detects LFS pointer stubs, and rebuilds itself from `chunks.json` if anything
  is wrong.

- **Retrieval had no relevance threshold.** `distances` was requested from Chroma and
  never used, so `no_context` effectively never fired: any question returned five
  passages, and the model dutifully summarised them into a confident, cited, wrong
  answer. Measured the corpus (on-topic 0.19–0.48, off-topic 0.76–0.91) and gated at
  0.62. Off-topic questions are now refused — verified on 8 cases in the evaluation set.

- **Citation numbers did not match the reference list.** The prompt numbered the
  retrieved passages, then the renderer deduplicated them by (filename, page) and
  re-numbered from 1. Whenever two passages shared a page, every later reference shifted
  and the highest-numbered citation was dropped — clicking `[3]` showed the text the
  model had cited as `[4]`. Same-page passages are now merged *before* the prompt is
  built, so one list governs the prompt, the sources and the UI.

- **Chat history leaked between visitors.** `last_session.json` was a single
  process-wide file with no per-session key, so on a shared deployment one visitor's
  refresh loaded the previous visitor's questions and answers. Disk persistence is now
  off by default (`HEALDAR_PERSIST_SESSION`).

### Fixed — corpus integrity

- `SFDA_MDS-G025_AI_Guidance_2025.pdf` was **not AI guidance** — it is *Guidance on
  General Wellness Devices*. Renamed. A mislabelled source is worse than a missing one:
  retrieval surfaces it under the wrong question with a citation that looks authoritative.
- `EU_MDCG_2025-7_Implementation_Timelines.pdf` was about **Master UDI-DI for contact
  lenses and spectacle frames**, with no health-AI relevance. Removed.
- Corrected the dates on four more files whose names misstated their actual version.
- The downloader now asserts each PDF contains an expected identifier on its opening
  pages, so a silent substitution upstream fails at download instead of months later.
- The download manifest is now authoritative: any PDF on disk it does not list is flagged, and a CI test fails if an unlisted file is ingested. That is how the superseded 2023 MDR text briefly sat in the index beside the 2026 consolidation, both citeable.

### Added — corpus

Grew from 27 documents / 1,978 chunks to **59 documents / 3,404 chunks**.

- **`KSA_SDAIA/` was empty** while the README advertised SDAIA coverage and the code had
  a `KSA_SDAIA` jurisdiction — the `ksa` alias silently behaved like `sfda`. Added all 8
  SDAIA documents: AI Ethics Principles (2025), AI Adoption Framework (2025), the two
  GenAI guideline sets, PDPL + implementing regulations, cross-border transfer rules, and
  the secondary-use rules. The old script's "SDAIA blocks bots" premise was wrong; the
  WAF just needs a `Referer`.
- **EU IVDR 2017/746** — absent entirely, which left the already-ingested MDCG 2025-6
  MDR/IVDR/AI-Act FAQ partly uninterpretable. Replaced the 2023 MDR text with the 2026-01-01
  consolidation.
- **FDA Clinical Decision Support Software (2026)** — the guidance that decides whether
  clinical AI is a regulated device at all.
- **Cybersecurity**, previously a hole in every jurisdiction: SFDA MDS-G36/37/38,
  MDCG 2019-16, FDA premarket (2026).
- MDCG 2023-4, 2025-4, 2025-10; the GPAI Code of Practice; SFDA MDS-G024 (ISO 13485
  mapping, which answers QMS questions without the paywalled standard); Saudi NHIC health
  information exchange and telehealth; WHO guidance on large multi-modal models in health.

### Added — retrieval quality

- **Hybrid search.** BM25 alongside dense retrieval, fused with Reciprocal Rank Fusion.
  Regulatory questions turn on exact tokens — "Article 120", "MDS-G010", "Annex VIII" —
  that embeddings blur. Lexical-only hits are scored against the query vector so the
  relevance gate applies uniformly.
- **Jurisdiction balancing.** The EU is 47% of the corpus and was crowding out every
  other body in "all jurisdictions" mode. A soft per-jurisdiction cap now guarantees
  smaller corpora a slot without wasting context when only one has material.
- **Coverage signalling.** Answers carry a self-assessed `full`/`partial` marker; the UI
  shows a caution banner for partial coverage or a weak best match, and each citation
  displays how well it actually matched.

### Added — engineering

- **Evaluation harness** (`eval/`): 54 curated cases measuring retrieval hit-rate,
  refusal, jurisdiction diversity, citation validity, grounding and term coverage. Exits
  non-zero below threshold, so it gates CI and `deploy.sh`. One case is annotated as a
  deliberate known failure rather than deleted to keep the score green.
- **CI** (`.github/workflows/ci.yml`): lint, tests with coverage, an LFS-pointer check,
  the retrieval evaluation, and a Docker build — weekly as well as on push.
- Tests: 48 → 167. Two test files had pointed at a `code/` directory that has not existed
  since the rename and only imported by accident; the Streamlit mock could not load
  `app.py` at all.
- `src/config.py` centralises every tunable, all environment-overridable.

### Changed

- Comparison mode queries both jurisdictions **in parallel** (was up to eight serial Groq
  calls for an Arabic comparison).
- Typed Groq exception handling with explicit timeout and retries, replacing
  `"rate limit" in str(exc)`. Rate limits, outages, retired models and index failures are
  now distinguishable — and an index failure no longer masquerades as "no information".
- Startup failures render a readable card instead of a Python traceback.
- Arabic detection uses a character ratio, so one Arabic word in an English question no
  longer diverts the whole query through translation.
- Follow-up rewriting requires an actual back-reference, not just a short question.
- Analytics: UTC throughout (`datetime.utcnow()` was deprecated, and "today" was computed
  in local time against UTC rows); question text is no longer stored by default.
- Optional per-session rate limit, so a public deployment cannot drain the API quota.
- `deploy.sh` runs tests and evaluation first, and publishing to the **public**
  HuggingFace Space is opt-in via `--hf` with a typed confirmation.
- Docker: runs unprivileged, verifies and repairs the index at build time, bakes in the
  embedding model, drops the unused `torchvision` (~30 MB).
- Fixed a `</script>` breakout in the copy-to-clipboard component.
- Finished the RegRadar → Healdar rename in the Dockerfile and docs.

### Known gaps

- UAE Federal Decree-Law 45/2021 — no official English PDF exists.
- Qatar Law 13/2016 — the official portal serves a broken TLS chain, and disabling
  certificate verification to fetch the text of a law is not an acceptable trade.
- IMDRF N88/N81 — `imdrf.org` was unreachable during research; URLs unverified.
- One evaluation case fails by design: "reused to train an AI model" does not reach the
  SDAIA secondary-use rules. A vocabulary gap of the kind a cross-encoder reranker is
  meant to close — left visible as a target for the next retrieval change.

---

## 1.0.0

Initial release.
