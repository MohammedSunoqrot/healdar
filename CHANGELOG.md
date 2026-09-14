# Changelog

## 2.1.0 — 2026-09-14

Follow-up conversations.

- **Answers stack as a conversation.** Each answer used to replace the previous one, so
  nobody could tell that follow-ups were possible. Turns now stay on the page, the
  question box sits under the latest answer, and **New conversation** starts fresh. A
  question opened from the sidebar history shows on its own, with a way back.
- **Follow-ups are understood in context.** "Why that class and not a lower one?" is
  rewritten to stand alone by the same model call that plans the searches, and the
  rewrite is shown under the question (*Understood as: …*). It replaces a keyword test
  ("it", "this", "compare"…) that missed real follow-ups and rewrote unrelated new
  questions against stale history. Refusal is still decided on the rewritten question,
  so an off-topic follow-up is refused as before.
- **Follow-ups build on the previous answer.** The pages it cited are carried into the
  new evidence, and the model sees the previous answer's opening *and* conclusion. It
  used to see the first 300 characters — once cutting off "most likely Class IIb", after
  which the follow-up argued the software was Class IIa.
- **Suggested follow-ups.** Each answer offers two or three next questions (what would
  change the conclusion, how another jurisdiction treats the same product); one click
  asks them. In Arabic they are translated, or left out if translation fails.
- **Citations in any form are linked.** "(Source 4)" and a bare "Source 6 lists …" showed
  as plain text with no reference behind them, and one answer lost its reference list
  entirely. Both now link like "[Source 4]", keeping their wording.
- Blockquoted rule text no longer shows a literal ">"; sidebar history and suggested
  questions are left-aligned lists.

## 2.0.0 — 2026-09-13

A reliability and usability release. Two faults had already taken the deployed app down,
and a third would have produced wrong answers rather than no answers.

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
  answer. Measured the corpus (best match on-topic at most 0.40, off-topic at least 0.66)
  and gated at 0.53. Off-topic questions are now refused — verified on 8 cases in the evaluation set.

- **Citation numbers did not match the reference list** — in two places. The renderer
  deduplicated and re-numbered the passages the prompt had already numbered, so whenever
  two shared a page every later reference shifted. And the PDF and Word exports numbered
  the *cited* sources from 1, so an answer citing [2] and [4] got a reference list
  labelled [1] and [2]. One list now governs the prompt, the screen and both exports.

- **Chat history leaked between visitors.** `last_session.json` was a single
  process-wide file with no per-session key, so on a shared deployment one visitor's
  refresh loaded the previous visitor's questions and answers. Disk persistence is now
  off by default (`HEALDAR_PERSIST_SESSION`).

- **The analytics panel showed every visitor's activity to every visitor**, including a
  CSV download of the shared log. It now shows *your own session only* (see Interface).

### Interface

- **Answers apply the rules to your case.** Asked to classify a described product,
  the old prompt ("answer using ONLY the context") produced "the context does not
  contain the classification rules". Healdar now walks through the deciding rule, shows
  how the facts meet its conditions, reaches a conclusion ("most likely Class IIb") with
  its assumptions and what would change it, and cites each rule it relies on. Anything
  taken from general knowledge rather than the documents is marked as such.
- **Light mode rebuilt properly.** The old app forced Streamlit's dark theme and
  repainted a "light mode" with CSS overrides that Streamlit's own widgets never
  received — hence black buttons, a black header bar, an unreadable comparison toggle and
  a dark footer block. Both palettes are now native Streamlit themes, the app follows the
  system setting (switchable from the ⋮ menu: System, Light or Dark), and Healdar's
  custom components derive their colours from the active theme.
- **Answers read as formatted text.** Models write Markdown whether asked to or not; the
  old renderer escaped it and showed raw `**`, `###` and table pipes. A new
  `formatting.py` parses answers once and renders headings, lists, emphasis and tables
  natively in the app, the PDF and the Word export. The prompt also asks for plain
  prose and simple lists. Numbered lists keep their numbering when the model puts
  blank lines between items (previously every item restarted at "1.").
- **Citations in any bracket style.** GPT-OSS often writes `【Source 2】` rather than
  `[Source 2]`; those showed as raw text and were missing from the reference list.
  Every variant — including grouped `[Source 1, 3]` — is now normalised on arrival.
- **Version and release date** are shown in the sidebar (and in the header and exports).
- **"Your session" panel** replaces the global analytics: questions asked, average time,
  share answered, languages and jurisdictions — for this browser tab only, with a CSV of
  your own session.
- A visible **Ask** button (Enter still works); starter questions **ask immediately**
  instead of only filling the box, in a two-column grid.
- References are native, click-to-open `<details>` elements, with the match score and
  right-to-left excerpts for Arabic sources.
- The sidebar credit is no longer a fixed-position block that overlapped content.
- PDF export folds characters the built-in font cannot draw (non-breaking hyphens,
  narrow spaces, ≤ ≥ →) instead of printing black boxes, and notes Arabic excerpts
  rather than rendering them as empty glyphs.

### Corpus

Grew from 27 documents / 1,978 passages to **63 documents / 3,572 passages from 16
regulators.**

- **`KSA_SDAIA/` was empty** while the README advertised SDAIA coverage. Added all 8
  SDAIA documents: AI Ethics Principles (2025), AI Adoption Framework (2025), the two
  GenAI guideline sets, PDPL and its implementing regulations, cross-border transfer
  rules, and the secondary-use rules.
- **EU IVDR 2017/746**, previously absent; the 2023 MDR text replaced by the 2026-01-01
  consolidation.
- **FDA Clinical Decision Support Software (2026)**; **cybersecurity** guidance, a hole in
  every jurisdiction (SFDA MDS-G36/37/38, MDCG 2019-16, FDA premarket 2026).
- MDCG 2023-4, 2025-4, 2025-10; the GPAI Code of Practice; SFDA MDS-G024; Saudi NHIC
  health information exchange and telehealth; WHO guidance on large multi-modal models.
- **IMDRF N81 and N88 (2025)**, **Qatar Law 13/2016** and the **UAE Federal Decree-Law
  45/2021 (PDPL)** — supplied manually, since none has a reliable automated source.
- **Arabic extraction.** The UAE PDPL's official text is Arabic, and its fonts carry
  reversed ligature mappings that PyMuPDF reproduces faithfully ("عىل" for "على",
  "املعالجة" for "المعالجة"). Ingest now extracts Arabic documents with both PyMuPDF
  and pypdf and keeps whichever reads as correct Arabic — for this file, 559 correctly
  spelled marker words versus −452.
- **Folders reorganised** as `<Country>_<Body>`. `EU_MDR_MDCG` had grown to hold the AI
  Act, the IVDR and the GPAI Code; it is now `EU_Legislation`, `EU_MDCG` and
  `EU_AI_Office`. Balancing in "all jurisdictions" mode now caps a *jurisdiction* rather
  than each folder, so a country split across three regulators does not get three quotas.

### Fixed — corpus integrity

- `SFDA_MDS-G025_AI_Guidance_2025.pdf` was **not AI guidance** — it is *Guidance on
  General Wellness Devices*. Renamed.
- `EU_MDCG_2025-7_Implementation_Timelines.pdf` was about **Master UDI-DI for contact
  lenses and spectacle frames**. Removed.
- Corrected the dates on four more files whose names misstated their version.
- The downloader asserts each PDF contains an expected identifier on its opening pages.
- The download manifest is authoritative: any PDF on disk it does not list is flagged,
  and a CI test fails if an unlisted file is ingested.

### Retrieval quality

- **Hybrid search**: BM25 alongside dense retrieval, fused with Reciprocal Rank Fusion.
- **Multilingual embeddings** (`paraphrase-multilingual-MiniLM-L12-v2`), chosen by
  benchmark on this corpus: 92.6% hit@5 with a +0.261 on/off-topic distance gap,
  against 89.8% / +0.255 for the previous English-only `all-MiniLM-L6-v2`, which could
  not find the Arabic UAE PDPL from English questions at all. `multilingual-e5-small`
  was rejected: its on- and off-topic distances overlap (gap −0.011), so no threshold
  could refuse off-topic questions reliably.
- **Acronym-aware keyword search.** "AI-based" shared no keyword with guidance that
  writes "AI", so the starter question *"How does SFDA regulate AI-based Software as a
  Medical Device?"* never retrieved SFDA's AI/ML guidance (MDS-G010) — and the answer
  claimed SFDA had no AI-specific guidance. The keyword query now splits hyphenated
  words and spells out common acronyms (AI, SaMD, PCCP, PDPL, …); MDS-G010 is now the
  top Saudi result. The embedding query is untouched, so the relevance gate's
  calibration is unchanged (`HEALDAR_QUERY_EXPANSION=0` turns it off).
- **Case questions reach the rule that decides them.** "Suggest the class of this
  retinal-screening software" is worded nothing like MDR Annex VIII Rule 11, so it
  retrieved FAQ pages. A planning step now asks the model which provisions the question
  depends on, in the regulation's own wording, and searches each alongside the question.
  Results are merged round-robin, so every planned search keeps its best page (merging by
  summed rank let half-matches push out the Rule 11 page); MDCG 2019-11's Rule 11 pages
  now reach both classification test questions. The user's own question still alone
  decides whether anything relevant exists, so off-topic questions are refused as before.
- **Jurisdiction balancing** with a soft cap per jurisdiction — which steps aside when
  the question names its jurisdiction. With the selector on "All", *"… under the EU
  MDR"* had the EU capped at two passages and the rest filled with FDA and SFDA pages,
  dropping the Rule 11 pages; such a question now searches the jurisdictions it names.
  An explicit selection is never overridden.
- **Coverage signalling**: a self-assessed `full`/`partial` marker drives a caution
  banner, and each citation shows how well it matched.

### Engineering

- **Evaluation harness** (`eval/`): 60 curated cases measuring retrieval hit-rate,
  refusal, jurisdiction diversity, citation validity, grounding and term coverage. It
  gates CI and `deploy.sh`.
- **CI** (`.github/workflows/ci.yml`): lint, tests with coverage, an LFS-pointer check,
  the retrieval evaluation, and a Docker build — weekly as well as on push.
- Tests: 48 → 244 (268 in 2.1.0).
- `src/config.py` centralises every tunable, all environment-overridable.
- Comparison mode queries both jurisdictions in parallel; typed Groq error handling with
  timeouts and retries; readable startup-failure card; ratio-based Arabic detection;
  UTC analytics with no question text stored by default; optional per-session rate
  limit; unprivileged Docker image; `deploy.sh` publishes to the public Space only with
  `--hf` and a typed confirmation.

### Known gaps

- Qatar National Health Strategy 2024–2030 — published as a web page only.
- One evaluation case fails by design: "reused to train an AI model" does not reach the
  SDAIA secondary-use rules — a vocabulary gap of the kind a cross-encoder reranker is
  meant to close, left visible as a target for the next retrieval change.

---

## 1.0.0

Initial release.
