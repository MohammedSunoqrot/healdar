# Healdar — Regulatory Source Document Research

**Research date:** 2026-09-13
**Scope:** Gap and staleness analysis of the Healdar RAG corpus at `data/raw_docs/` across 6 jurisdictions.
**Method:** Live web search + direct HTTP retrieval. Every row marked **Verified** below was fetched and its cover page / document-control block parsed to confirm title, version and date. Rows marked **Inferred** could not be fetched from this network and rest on search-index evidence only.

---

## 0. Executive summary

| Finding | Severity |
|---|---|
| `KSA_SDAIA/` is **empty** — the README's "SFDA + SDAIA" claim and the `KSA_SDAIA` jurisdiction in code are unbacked by any document | Critical |
| The download script's premise that SDAIA "blocks bots" is **wrong** — all SDAIA PDFs fetch fine with a browser `User-Agent` + `Referer` (see §1.1) | High — unblocks 8 auto-downloads |
| `SFDA_MDS-G025_AI_Guidance_2025.pdf` is **not AI guidance** — it is *Guidance on General Wellness Devices* | Critical — mis-citation risk |
| `EU_MDCG_2025-7_Implementation_Timelines.pdf` is **about spectacle frames and contact lenses** (Master UDI-DI), not AI/MDR timelines | Critical — mis-citation risk |
| `EU_MDR_2017-745_Consolidated_2023.pdf` is the 2023-03-20 consolidation; the in-force text is the **2026-01-01** consolidation | High |
| **IVDR (EU) 2017/746 is absent entirely**, as are MDCG cybersecurity (2019-16) and the two MDSW guidances (2023-4, 2025-4) | High |
| FDA **Clinical Decision Support Software** (reissued 2026-01-29) and **Cybersecurity premarket** (reissued 2026-02-03) are both absent | High |
| SDAIA AI Ethics Principles **2025 edition** supersedes the 2023 v1.0 the download script targets | High |

---

## 1. Recommended additions

### 1.1 KSA — SDAIA (folder `KSA_SDAIA/`) — currently empty

> **Auto-download note.** `sdaia.gov.sa` sits behind an F5 WAF that returns a 246-byte "Request Rejected" HTML page to bare clients and rejects `HEAD` outright. It serves the real PDF on a `GET` carrying a browser `User-Agent` **and** `Referer: https://sdaia.gov.sa/en/SDAIA/about/Pages/RegulationsAndPolicies.aspx`. All eight rows below were retrieved this way and parsed. The script's "manual download" list can be automated.

| Folder | Suggested filename | Official title | URL | Pub. date | Why it matters | Auto-downloadable |
|---|---|---|---|---|---|---|
| KSA_SDAIA | `KSA_SDAIA_AI_Ethics_Principles_2025.pdf` | AI Ethics Principles (2025 edition) | https://sdaia.gov.sa/en/SDAIA/about/Documents/ai-principles.pdf | 2025 ed. (PDF built 2025-10-02), 50 pp | The foundational Saudi AI governance instrument: 7 principles + controls, tiered risk categorisation, full-lifecycle application. **Supersedes the Sept-2023 v1.0 the download script targets.** | Yes (UA + Referer) — **Verified** |
| KSA_SDAIA | `KSA_SDAIA_AI_Adoption_Framework_2025.pdf` | Artificial Intelligence Adoption Framework (2025) | https://sdaia.gov.sa/en/SDAIA/about/Files/AIAdoptionFramework.pdf | 2025 ed. (built 2025-11-13), 48 pp | Cross-sector AI adoption reference; explicitly names healthcare. Supersedes the "2024" edition in the script. | Yes — **Verified** |
| KSA_SDAIA | `KSA_SDAIA_GenAI_Guidelines_Government_2025.pdf` | Generative Artificial Intelligence for Government — Guidelines | https://sdaia.gov.sa/en/SDAIA/about/Files/GenAIGuidelinesForGovernmentENCompressed.pdf | 2025 ed., 30 pp | Governs GenAI in government entities incl. public hospitals: risk tiering, human oversight for high-risk outputs, data-office duties, adoption checklist. | Yes — **Verified** |
| KSA_SDAIA | `KSA_SDAIA_GenAI_Guidelines_Public_2025.pdf` | Generative Artificial Intelligence for Public — Guidelines | https://sdaia.gov.sa/en/SDAIA/about/Files/GenerativeAIPublicEN.pdf | 2025 ed., 22 pp | Public-facing GenAI principles, risks and mitigations; the consumer-side counterpart to the government guidelines. | Yes — **Verified** |
| KSA_SDAIA | `KSA_SDAIA_PDPL_Law_2023.pdf` | Personal Data Protection Law (Royal Decree M/19 of 9/2/1443H, amended by M/148 of 5/9/1444H) | https://sdaia.gov.sa/en/SDAIA/about/Documents/PersonalDataProtectionLaw.pdf | English text v2, 23 Apr 2023, 16 pp | The primary Saudi data-protection statute — the legal substrate for every health-AI data question in KSA. | Yes — **Verified** |
| KSA_SDAIA | `KSA_SDAIA_PDPL_Implementing_Regulations_2023.pdf` | Implementing Regulation of the PDPL **+** Regulation on Personal Data Transfer outside the Kingdom (combined) | https://sdaia.gov.sa/en/SDAIA/about/Documents/ImplementingRegulation.pdf | 2023-09-07, 40 pp | Operative rules: data-subject rights, breach notification, DPO, registration, transfers. **Prefer this 40-page combined file** over `ImplementingRegulationPersonalDataProtectionLaw.pdf` (27 pp), which omits the transfer regulation. | Yes — **Verified** |
| KSA_SDAIA | `KSA_SDAIA_Data_Transfer_Outside_Kingdom_Regulation_2024.pdf` | Regulation on Personal Data Transfer outside the Kingdom, Version 2.0 | https://sdaia.gov.sa/Documents/RegulationonPersonalDataEN.pdf | v2.0, August 2024, 11 pp | Standalone **v2.0** — newer than the version bundled in the 2023 combined file. Governs cross-border transfer of Saudi health data to cloud/AI vendors. | Yes — **Verified** |
| KSA_SDAIA | `KSA_SDAIA_Secondary_Use_of_Data_Rules_2025.pdf` | General Rules for Secondary Use of Data, Issue 1.0 | https://sdaia.gov.sa/Documents/GeneralRulesForSecondaryUseOfData_EN.pdf | Issue 1.0, 2025, 8 pp | Directly on point for **training health-AI models on existing patient data** — the single most commonly asked secondary-use question. Short, dense, high RAG value. | Yes — **Verified** |

**Secondary SDAIA candidates** (lower priority, include if breadth is wanted):

| Folder | Suggested filename | Official title | URL | Pub. date | Why it matters | Auto-downloadable |
|---|---|---|---|---|---|---|
| KSA_SDAIA | `KSA_SDAIA_Deepfakes_Guidelines_2025.pdf` | Deepfakes Guidelines: Mitigating Risks While Fostering Innovation | https://sdaia.gov.sa/en/SDAIA/about/Files/File0001.pdf | 2025 ed. (built 2025-11-13), 56 pp | Synthetic-media guidance with developer/regulator/consumer duties. Relevant to synthetic medical imaging and patient-identity fraud. | Yes — **Verified** |
| KSA_SDAIA | `KSA_SDAIA_NDMO_Data_Management_PDP_Standards_2021.pdf` | National Data Management and Personal Data Protection Standards, Version 1.5 | https://sdaia.gov.sa/en/SDAIA/about/Documents/DataManagementPersonalDataProtectionStandards.pdf | v1.5, January 2021, 173 pp | NDMO's 15-domain control catalogue — the operational standard Saudi health entities are audited against. Large; chunk carefully. | Yes — **Verified** |

### 1.2 KSA — SFDA (folder `SFDA/`)

| Folder | Suggested filename | Official title | URL | Pub. date | Why it matters | Auto-downloadable |
|---|---|---|---|---|---|---|
| SFDA | `SFDA_MDS-G38_PreMarket_Cybersecurity_Medical_Devices_2019.pdf` | MDS-G38 — Guidance to Pre-Market Cybersecurity of Medical Devices | https://www.sfda.gov.sa/sites/default/files/2019-10/MDS-G38.pdf | v1.0, 18/6/2019, 10 pp | Closes the named cybersecurity gap for KSA. Applies to all device categories using software. Still the current version. | Yes — **Verified** |
| SFDA | `SFDA_MDS-G37_PostMarket_Cybersecurity_Medical_Devices_2019.pdf` | MDS-G37 — Guidance to Post-Market Cybersecurity of Medical Devices | https://www.sfda.gov.sa/sites/default/files/2019-10/MDS-G37.pdf | v1.0, 18/6/2019, 9 pp | Post-market counterpart — vulnerability handling over the deployed life of AI/software devices. | Yes — **Verified** |
| SFDA | `SFDA_MDS-G36_Cybersecurity_Healthcare_Providers_2019.pdf` | MDS-G36 — Guidance to Medical Devices Cybersecurity for Healthcare Providers | https://www.sfda.gov.sa/sites/default/files/2019-10/MDS-G36.pdf | v1.0, 18/6/2019, 9 pp | Deployer-side duties — the perspective most Healdar users (hospitals) actually occupy. | Yes — **Verified** |
| SFDA | `SFDA_MDS-G024_ISO13485_Requirements_2025.pdf` | MDS-G024 — Guidance for ISO 13485 Requirements and Corresponding SFDA-MDS Requirements | https://www.sfda.gov.sa/sites/default/files/2025-03/MDS-G024.pdf | v1.0, 25/03/2025, 29 pp | Maps ISO 13485 clauses to SFDA requirements — lets Healdar answer QMS questions **without ingesting the paywalled ISO standard itself**. High value per page. | Yes — **Verified** |

### 1.3 KSA — National Health Information Center (suggested new folder `KSA_NHIC/`)

| Folder | Suggested filename | Official title | URL | Pub. date | Why it matters | Auto-downloadable |
|---|---|---|---|---|---|---|
| KSA_NHIC | `KSA_NHIC_Health_Information_Exchange_Policies_2016.pdf` | IS0303 — Saudi Health Information Exchange Policies, Version 1.0 | https://nhic.gov.sa/standards/Policies/IS0303-Saudi-Health-Information-Exchange-Policies-v1.0.pdf | v1.0, 21 Apr 2016, 43 pp | The national HIE consent/disclosure/access policy set — the KSA analogue of the DHA NABIDH and DoH data-governance documents already in the corpus. Still the operative national standard. | Yes — **Verified** |
| KSA_NHIC | `KSA_NHIC_Telehealth_Application_Guidelines.pdf` | Telehealth Application Guidelines | https://nhic.gov.sa/standards/Telehealth/Telehealth-Application-Guidelines.pdf | undated, 74 pp | Gives KSA telehealth coverage to match the DHA telehealth standard. Note: no version/date block on the cover — cite with caution. | Yes — **Verified** |
| KSA_NHIC | `KSA_NHIC_HIE_Testing_Certification_Policies_2016.pdf` | IS0304 — Saudi HIE Testing and Certification Policies, Version 1.0 | https://nhic.gov.sa/standards/Policies/IS0304-Saudi-Health-Information-Exchange-Testing-and-Certification-Policies-v1.0.pdf | v1.0, 21 Apr 2016, 16 pp | Conformance/certification route for systems joining the national HIE. Lower priority. | Yes — **Verified** |

### 1.4 EU (folder `EU_MDR_MDCG/`)

| Folder | Suggested filename | Official title | URL | Pub. date | Why it matters | Auto-downloadable |
|---|---|---|---|---|---|---|
| EU_MDR_MDCG | `EU_IVDR_2017-746_Consolidated_2025.pdf` | Regulation (EU) 2017/746 (IVDR), consolidated text | https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:02017R0746-20250110 | consolidation in force 2025-01-10, 208 pp | **The corpus has no IVDR at all**, yet MDCG 2025-6 (already ingested) is a joint MDR/IVDR + AI Act FAQ and is uninterpretable without it. AI-driven diagnostics frequently fall under IVDR, not MDR. Highest-value single EU addition. | Yes — **Verified** |
| EU_MDR_MDCG | `EU_MDCG_2019-16_Rev1_Cybersecurity_Medical_Devices.pdf` | MDCG 2019-16 Rev.1 — Guidance on Cybersecurity for medical devices | https://health.ec.europa.eu/document/download/b23b362f-8a56-434c-922a-5b3ca4d0a7a1_en?filename=md_cybersecurity_en.pdf | Dec 2019, rev.1 July 2020, 46 pp | The EU cybersecurity counterpart to SFDA MDS-G37/38 and FDA's premarket guidance — a whole topic currently unrepresented in the EU folder. | Yes — **Verified** |
| EU_MDR_MDCG | `EU_MDCG_2025-4_MDSW_Apps_Online_Platforms_2025.pdf` | MDCG 2025-4 — Guidance on the safe making available of medical device software (MDSW) apps on online platforms | https://health.ec.europa.eu/document/download/ec9b0f40-7f82-43a7-b833-ebd45b772eae_en?filename=mdcg_2025-4_en.pdf | June 2025, 8 pp | 2025 MDSW guidance directly on app-store distribution of health AI. Short and high-signal. | Yes — **Verified** |
| EU_MDR_MDCG | `EU_MDCG_2023-4_MDSW_Hardware_Combinations_2023.pdf` | MDCG 2023-4 — Medical Device Software (MDSW) – Hardware combinations | https://health.ec.europa.eu/document/download/b2c4e715-f2b4-4d24-af60-056b5d41a72e_en?filename=md_mdcg_2023-4_software_en.pdf | October 2023, 8 pp | Completes the MDSW guidance set (2019-11, 2020-1, 2023-4, 2025-4). Covers AI software shipped with/for specific hardware — e.g. wearables, imaging. | Yes — **Verified** |
| EU_MDR_MDCG | `EU_MDCG_2025-10_Post_Market_Surveillance_2025.pdf` | MDCG 2025-10 — Guidance on post-market surveillance of medical devices and in vitro diagnostic medical devices | https://health.ec.europa.eu/document/download/a9ad86b7-1b8e-4bae-beb4-48b2b3ed2f05_en?filename=mdcg_2025-10_en.pdf | December 2025, 23 pp | Newest MDCG substantive guidance. PMS is where AI model drift and real-world performance monitoring obligations live. | Yes — **Verified** |
| EU_MDR_MDCG | `EU_GPAI_Code_of_Practice_Safety_Security_2025.pdf` | Code of Practice for General-Purpose AI Models — Safety and Security Chapter | https://ec.europa.eu/newsroom/dae/redirection/document/118119 | 10 July 2025, 43 pp | The operative AI Act GPAI compliance route. Relevant wherever a health product is built on a foundation model. Substantive chapter of the three. | Yes — **Verified** |
| EU_MDR_MDCG | `EU_GPAI_Code_of_Practice_Transparency_2025.pdf` | Code of Practice for General-Purpose AI Models — Transparency Chapter | https://ec.europa.eu/newsroom/dae/redirection/document/118120 | 10 July 2025, 6 pp | Model-documentation duties for GPAI providers. Short. | Yes — **Verified** |
| EU_MDR_MDCG | `EU_GPAI_Code_of_Practice_Copyright_2025.pdf` | Code of Practice for General-Purpose AI Models — Copyright Chapter | https://ec.europa.eu/newsroom/dae/redirection/document/118115 | 10 July 2025, 6 pp | Completes the Code. Lowest health relevance of the three — optional. | Yes — **Verified** |
| EU_MDR_MDCG | `EU_MDCG_2020-16_Rev5_IVD_Classification_2026.pdf` | MDCG 2020-16 rev.5 — Guidance on Classification Rules for in-vitro Diagnostic Medical Devices under Regulation (EU) 2017/746 | https://health.ec.europa.eu/document/download/12f9756a-1e0d-4aed-9783-d948553f1705_en?filename=md_mdcg_2020_guidance_classification_ivd-md_en.pdf | rev.5, September 2026, 55 pp | Only worth ingesting **alongside** the IVDR. Freshest revision (Sept 2026); classification drives everything downstream. | Yes — **Verified** |
| EU_MDR_MDCG | `EU_MDCG_2025-9_Breakthrough_Devices_2025.pdf` | MDCG 2025-9 — Guidance on Breakthrough Devices (BtX) under Regulations 2017/745 & 2017/746 | https://health.ec.europa.eu/document/download/edca94c7-62ab-4dd5-8539-2b347bd14809_en?filename=mdcg_2025-9.pdf | December 2025, 36 pp | New EU expedited pathway; pilot roll-out expected Q2 2026. Optional — include only for market-access breadth. | Yes — **Verified** |

### 1.5 USA — FDA (folder `USA_FDA/`)

| Folder | Suggested filename | Official title | URL | Pub. date | Why it matters | Auto-downloadable |
|---|---|---|---|---|---|---|
| USA_FDA | `USA_FDA_Clinical_Decision_Support_Software_2026.pdf` | Clinical Decision Support Software — Guidance for Industry and FDA Staff | https://www.fda.gov/media/109618/download | **issued 2026-01-29**, 27 pp | The guidance that decides whether clinical AI is a regulated device at all — the most-asked US health-AI question, and absent from the corpus. Cover states it supersedes the 2026-01-06 issue; the long-cited 2022 version is two generations stale. | Yes — **Verified** |
| USA_FDA | `USA_FDA_Cybersecurity_Medical_Devices_Premarket_2026.pdf` | Cybersecurity in Medical Devices: Quality Management System Considerations and Content of Premarket Submissions | https://www.fda.gov/media/119933/download | **issued 2026-02-03**, 64 pp | Brand-new revision (supersedes the 2025-06-27 issue). Gives the US leg of the cybersecurity topic that SFDA and MDCG additions cover elsewhere. | Yes — **Verified** |
| USA_FDA | `USA_FDA_EMA_Good_AI_Practice_Drug_Development_2026.pdf` | Guiding Principles of Good AI Practice in Drug Development (FDA–EMA joint) | https://www.fda.gov/media/189581/download | January 2026, 2 pp | Joint FDA/EMA 10-principle statement issued 2026-01-14 — human oversight, risk management, data governance, lifecycle control. Extends coverage to drug/biologic AI and is cross-jurisdictional. Tiny file, high citation value. | Yes — **Verified** |
| USA_FDA | `USA_FDA_DRAFT_AI_Enabled_Device_Software_Lifecycle_2025.pdf` | Artificial Intelligence-Enabled Device Software Functions: Lifecycle Management and Marketing Submission Recommendations — **DRAFT** | https://www.fda.gov/media/184856/download | **DRAFT**, 2025-01-06, 67 pp | Confirmed still **draft** on FDA's live AI-in-SaMD page as of this research; on FDA's FY-2026 "B" list for finalisation. It is nonetheless the most comprehensive statement of FDA thinking on AI device lifecycle. **Ingest only with `DRAFT` in the filename and a draft flag in metadata**, or hold until final. | Yes — **Verified** |
| USA_FDA | `USA_FDA_DRAFT_AI_Regulatory_Decision_Making_Drugs_2025.pdf` | Considerations for the Use of AI to Support Regulatory Decision-Making for Drug and Biological Products — **DRAFT** | https://www.fda.gov/media/184830/download | **DRAFT**, 2025-01-07, 23 pp | Introduces the 7-step risk-based credibility-assessment framework. Same draft caveat. Lower priority than the device draft for a health-AI device tool. | Yes — **Verified** |

### 1.6 Qatar (folder `Qatar_NCSA/` or new `Qatar_National/`)

| Folder | Suggested filename | Official title | URL | Pub. date | Why it matters | Auto-downloadable |
|---|---|---|---|---|---|---|
| Qatar_National | `Qatar_Law_13_2016_Personal_Data_Privacy_Protection.pdf` | Law No. (13) of 2016 on Protecting Personal Data Privacy | https://www.almeezan.qa/EnglishLaws//132016.pdf | 2016, 19 pp | The **only binding statute** in Qatar's corpus slice — everything currently ingested for Qatar is strategy or voluntary guidance. First GCC general data-protection law; governs health data and consent. Source is Al Meezan, Qatar's official legal portal. | Yes — **Verified** |

### 1.7 International / foundational (suggested new folder `International/`)

| Folder | Suggested filename | Official title | URL | Pub. date | Why it matters | Auto-downloadable |
|---|---|---|---|---|---|---|
| International | `INT_WHO_Ethics_Governance_AI_Health_LMM_2024.pdf` | Ethics and governance of artificial intelligence for health: Guidance on large multi-modal models | https://iris.who.int/server/api/core/bitstreams/e9e62c65-6045-481e-bd04-20e206bc5039/content | 18 Jan 2024, 98 pp | WHO's 40+ recommendations on generative AI in health — the most frequently cited non-binding international reference, and the natural neutral answer when a question spans all six jurisdictions. Openly licensed. | Yes — **Verified** |
| International | `INT_IMDRF_N88_Good_Machine_Learning_Practice_2025.pdf` | IMDRF/AIML WG/N88 FINAL:2025 — Good machine learning practice for medical device development: Guiding principles | https://www.imdrf.org/sites/default/files/2025-02/IMDRF_AIML%20WG_GMLP_N88%20Final.pdf | FINAL, 27 Jan 2025 | The harmonised international GMLP text that SFDA MDS-G010 and FDA's GMLP principles both descend from — it is the common ancestor that makes cross-jurisdiction answers coherent. | **Inferred** — `imdrf.org` was unreachable from this network (connection timeout, not a block page). Re-verify before scripting. |
| International | `INT_IMDRF_N81_Software_Risk_Characterization_2025.pdf` | IMDRF/SaMD WG/N81 FINAL:2025 — Characterization Considerations for Medical Device Software and Software-Specific Risk | https://www.imdrf.org/sites/default/files/2025-01/IMDRF_SaMD%20WG_Software-Specific%20Risk_N81%20Final_0.pdf | FINAL, 27 Jan 2025 | Supersedes the N12-era framing; broadens from SaMD to all medical device software incl. embedded. Underpins classification reasoning in several jurisdictions. | **Inferred** — same caveat as N88. |

---

## 2. Superseded / needs refresh

### 2.1 Wrong content — fix before anything else

These two files are not what their names claim. In a citation-generating RAG tool this is worse than a missing document, because retrieval will surface them under the wrong query and the citation will look authoritative.

| File | Filename implies | **Actual content (verified by parsing the PDF)** | Action |
|---|---|---|---|
| `SFDA/SFDA_MDS-G025_AI_Guidance_2025.pdf` | SFDA AI guidance, 2025 | **MDS-G-025-V1/250312 — "Guidance on General Wellness Devices"**, v1.0, 12/03/2025, 11 pp. Not about AI. | Rename to `SFDA_MDS-G025_General_Wellness_Devices_2025.pdf`. Keep it (general-wellness carve-out is genuinely useful), but stop presenting it as AI guidance. Re-check any eval/test fixtures that assert "MDS-G025 = AI guidance". |
| `EU_MDR_MDCG/EU_MDCG_2025-7_Implementation_Timelines.pdf` | AI Act / MDR implementation timelines | **MDCG 2025-7 Rev.1 — "MDCG Position Paper: Timelines of the implementation of 'Master UDI-DI' to contact lenses and spectacle frames, spectacle lenses and ready-to-wear reading spectacles"**, Rev.1 Dec 2025, 6 pp. Nothing to do with AI. | **Remove from the corpus.** It has no health-AI relevance and its filename actively invites wrong retrieval. If EU timelines are wanted, MDCG 2025-6 (already ingested) carries the AI Act/MDR interplay dates. |

### 2.2 Genuinely outdated — refresh in place

| File | Current corpus version | Latest available | Action |
|---|---|---|---|
| `EU_MDR_MDCG/EU_MDR_2017-745_Consolidated_2023.pdf` | Consolidation of **2023-03-20** (231 pp — byte-for-byte page-count match with CELEX `02017R0745-20230320`) | **`02017R0745-20260101`** (233 pp), in force 1 Jan 2026 | Replace via https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:02017R0745-20260101 and rename to `EU_MDR_2017-745_Consolidated_2026.pdf`. **Verified.** Three intervening consolidations (2024-07-09, 2025-01-10, 2026-01-01) are missing from the current copy. |
| *(download script target, not yet ingested)* SDAIA AI Ethics Principles 2023 | Script points at the Sept-2023 **v1.0** on `dgp.sdaia.gov.sa` (49 pp — **verified**, cover reads "AI Ethics Principles / September 2023 / Version 1.0") | **2025 edition**, 50 pp, at `sdaia.gov.sa/en/SDAIA/about/Documents/ai-principles.pdf` | Update the script to the 2025 edition (§1.1). Do not ingest the 2023 v1.0. |
| *(download script target)* SDAIA AI Adoption Framework 2024 | Script labels it 2024 | **2025 edition**, 48 pp — **verified** | Update label and URL to the 2025 edition. |

### 2.3 Filename/metadata inaccuracies — content is fine, labels are not

Worth fixing because Healdar's citations presumably surface these filenames to users.

| File | Problem | Correct descriptor |
|---|---|---|
| `UAE_DHA_Dubai/UAE_DHA_Standards_Telehealth_Services_2023.pdf` | Named 2023; the file is actually **Version (4)**, i.e. the current DHA/HRS/HPSD/ST-14 Issue 4 (issued 26/09/2025, effective 26/11/2025) | Rename to `..._Telehealth_Services_V4_2025.pdf`. **Content is current — no re-download needed.** |
| `UAE_DHA_Dubai/UAE_DHA_Standards_Interoperability_Data_Exchange.pdf` | No year; file is **Version (2), DHA 2025** | Rename to `..._Interoperability_Data_Exchange_V2_2025.pdf`. Content current. |
| `SFDA/SFDA_MDS-G023_SaMD_Guidance_2020.pdf` | Named 2020; cover reads **Version 1.0, Version Date 9/4/2018** | Rename to `..._SaMD_Guidance_2018.pdf`. Still the current MDS-G23 — no newer version found. |
| `SFDA/SFDA_MDS-G010_AI-ML_Medical_Devices_Guidance_2023.pdf` | Named 2023; cover reads **Version 1.0, Version Date 29/11/2022** (doc ref `MDS-G-010-V1/230103`, published Jan 2023) | Acceptable as-is, but the *version date* is 2022. Confirmed **still the current version** against the live SFDA file — no refresh needed. |
| `UAE_DoH_AbuDhabi/UAE_DoH_Policy_AI_in_Healthcare.pdf` | No year | It is **DoH, April 2018** (11 pp). Rename to `..._Policy_AI_in_Healthcare_2018.pdf` so its age is visible next to the 2025 Responsible AI Standard. |

### 2.4 Confirmed current — no action

Checked and found already up to date, so these need no work:

- `EU_MDCG_2019-11_Software_Qualification_Classification.pdf` — already **Rev.1, June 2025** (36 pp). This is the newest revision; the 2-page infographic on the EC site is a separate summary, not a replacement.
- `EU_MDCG_2023-5`, `EU_MDCG_2025-6`, `EU_AI_Act_2024-1689` — current.
- `SFDA_MDS-G027_Digital_Health_Products_2025.pdf` — matches the live SFDA file exactly (v1.0, 11/8/2025).
- All six `UAE_DoH_AbuDhabi/` files — V1/2025 (Oct 2025) or the 2018/2020 foundational policies; all current.
- `Qatar_NCSA_AI_Secure_Adoption_Guidelines_2024.pdf` — **no "V6" exists.** NCSA's AI guidance is still *Guidelines for Secure Adoption and Usage of Artificial Intelligence, Version 1.0 (2024)*. The corpus copy is current; the "V6" in the task brief appears to be a misremembering.
- `USA_FDA_PCCP_Final_Guidance_AI_Devices_2024.pdf` — matches FDA media/166704 (Dec 2024 final, 49 pp). Current.

---

## 3. Considered and excluded

### 3.1 Paywalled standards — noted, deliberately not ingested

Per the research rules, no paywalled content is included. All of these are referenced *by* documents already in or proposed for the corpus, so Healdar will encounter their identifiers; it should be able to name them and say they are not in the corpus rather than hallucinate their contents.

| Standard | Relevance | Mitigation already in the plan |
|---|---|---|
| **ISO 13485** (QMS for medical devices) | Cited by SFDA, MDR, FDA | **SFDA MDS-G024** (§1.2) maps ISO 13485 clauses to SFDA requirements and is free — it carries much of the answerable substance. |
| **ISO 14971** (risk management) | Cited throughout | Partially covered by IMDRF N81 and MDCG risk guidance. |
| **IEC 62304** (software lifecycle) | Cited by MDR, FDA, SFDA | Partially covered by MDCG 2019-11 rev.1 and the FDA lifecycle draft. |
| **ISO/IEC 42001** (AI management systems) | Increasingly cited in GCC AI governance | Partially covered by SDAIA AI Ethics Principles 2025 + AI Adoption Framework 2025. |
| **ISO/IEC 23894**, **ISO/TR 24971** | Secondary references | No free equivalent; note as out-of-scope. |

*Recommendation:* add a short `standards-not-ingested.md` note (or a system-prompt line) listing these, so the model answers "ISO 13485 is not in Healdar's corpus; the closest ingested source is SFDA MDS-G024" instead of improvising clause text.

### 3.2 Drafts — excluded or flagged

| Document | Status | Decision |
|---|---|---|
| **Draft Commission Guidelines on the classification of high-risk AI systems** (Art. 6 AI Act), published 19 May 2026, consultation closed 23 June 2026 | Draft, not adopted | **Exclude for now.** Highly relevant once adopted (it decides whether medical AI is Annex I high-risk). Re-check after adoption — this is the single highest-value EU document to watch. |
| **IMDRF/AIML WG/N93 DRAFT:202X** — Technical Framework for AI Life Cycle Management (7 Apr 2026) | Draft | Exclude. Track for finalisation. |
| **IMDRF/SaMD WG(PD)/N90 DRAFT:2025** — PCCPs (29 Sep 2025) | Draft | Exclude. Track for finalisation. |
| **FDA AI-Enabled Device Software Functions: Lifecycle Management** (Jan 2025) | Draft | **Included with an explicit `DRAFT` filename prefix** (§1.5) — its substantive importance outweighs the draft risk *provided* the draft status is visible in filename and metadata. If the pipeline cannot carry that flag, hold it until final. |
| **FDA Considerations for AI in Regulatory Decision-Making for Drugs** (Jan 2025) | Draft | Same treatment, lower priority. |

### 3.3 Non-authoritative or low-value sources — excluded

| Source | Reason |
|---|---|
| Scribd copies of NCSA AI Guidelines and Qatar Law 13/2016 | Rule violation (non-official mirror). Official sources were located instead: `assurance.ncsa.gov.qa` and `almeezan.qa`. |
| `dataguidance.com` hosted copy of Qatar Law 13/2016 and Saudi HIE policies | Commercial aggregator, not a primary source. Official equivalents found and verified. |
| `regulations.ai`, `vision2030.ai`, `frameworks.alfaben.app`, law-firm client alerts (CMS, DLA Piper, Jones Day, McGuireWoods, etc.) | Secondary commentary. Used only as **leads** to locate primary URLs; none proposed for ingestion. |
| `urac.org` copy of DHA Telehealth Standards v2 | Third-party mirror of a superseded version. Corpus already holds v4. |
| **SDAIA National AI Index (NAII)** — `sdaia.gov.sa/en/SDAIA/about/Files/NAII.pdf` (22 pp, Sept 2025) | Verified real, but it is a **measurement index methodology**, not regulatory guidance. No compliance obligations to retrieve. Excluded as noise. |
| **SDAIA National Occupational Standard Framework for Data & AI** (`File0002.pdf`, 86 pp) and **Saudi Academic Framework for AI Qualifications** (`File0003.pdf`, 36 pp) | Verified real and current (2025), but they are **workforce/education frameworks** — job cards and academic benchmarks. No regulatory content for health-AI questions. Excluded. |
| **SDAIA Agentic AI report** (`Agentic_AI_090725.V.pdf`, 82 pp, July 2025) | **Arabic only** — cover and body are Arabic; the corpus and pipeline are English. Also a research study, not a regulatory instrument. Excluded. |
| **Saudi Health Data Dictionary v2** — `nhic.gov.sa/standards/Saudi-Health-Data-Dictionary-v2.pdf` (516 pp) | Verified and official, but it is a **data-element reference table**, not prose. 516 pages of tabular field definitions would flood the vector store with near-identical low-information chunks and degrade retrieval. Excluded on RAG-quality grounds. |
| **MDCG 2026-1 through 2026-5** | All verified as current, but all concern **EMDN nomenclature, EUDAMED SSCP management, and UDI assignment** (2026-1/2/3: EMDN revisions; 2026-4: SS(C)P in EUDAMED; 2026-5: UDI between manufacturers and distributors). Two are `.xlsx`. No AI or software content. Explicitly excluded so future audits do not re-raise them. |
| **MDCG 2025-1/2/3, 2025-8** | EMDN ad-hoc procedure, EMDN submissions, and Master UDI-DI for spectacles. No AI/software relevance. Excluded. |
| **MDCG 2025-5** (IVD performance studies Q&A, June 2025) | Relevant only if the corpus takes on IVD clinical-performance questions. Deferred — add after IVDR lands and only if scope expands. |
| **Qatar National Health Strategy 2024-2030** | Searched; **no official downloadable PDF found** on `moph.gov.qa` (landing page only, at `/english/NHS/Pages/About.aspx`). Not proposed. Would need a manual request to `nationalpmo@moph.gov.qa`. |
| **UAE Federal Decree-Law 45/2021 (PDPL)** | Genuinely desirable — it is the federal statute behind the DoH/DHA standards already ingested. **But:** `uaelegislation.gov.ae` returns **HTTP 403 behind Cloudflare** ("Just a moment..." challenge), and the official `u.ae` publication is **Arabic only**; no official English PDF was located. The widely circulated English text (`protection-data.ae`) is a private-site copy and fails the primary-source rule. **Flagged as an open gap — manual sourcing required**, not an auto-download candidate. |

---

## 4. Practical notes for the download script

1. **Drop the "SDAIA blocks bots" assumption.** Send a browser `User-Agent` *and* `Referer: https://sdaia.gov.sa/en/SDAIA/about/Pages/RegulationsAndPolicies.aspx`, and use `GET` (not `HEAD` — the WAF rejects `HEAD` for PDFs even with good headers). All eight SDAIA documents in §1.1 then download cleanly. This converts the entire manual-download list to automated.
2. **Validate content type, not just status code.** `sdaia.gov.sa` returns **HTTP 200** with a 246-byte `text/html` rejection page on failure. A status-only check will silently ingest garbage. Assert `content-type: application/pdf` **and** a `%PDF` magic-number prefix.
3. **`sfda.gov.sa`, `nhic.gov.sa`, `health.ec.europa.eu`, `eur-lex.europa.eu`, `fda.gov`, `iris.who.int`, `almeezan.qa`** all served correctly with a plain browser UA — no special handling needed.
4. **`imdrf.org` was unreachable from this network** (TCP timeout on both `curl` and WebFetch — a connectivity issue, not a block page). Its two URLs are the only unverified rows in this report; confirm them before adding to the script.
5. **Assert the version string after download.** Given the two wrong-content files found in §2.1, a post-download check that the first page contains the expected document code (e.g. `MDS-G-025`, `MDCG 2025-7`) would have caught both at ingest time.

---

## 5. Suggested priority order

1. **Fix §2.1** — remove `EU_MDCG_2025-7`, rename `SFDA_MDS-G025`. Costs nothing, removes two live mis-citation risks.
2. **Populate `KSA_SDAIA/`** with the 8 documents in §1.1 — closes the README's headline coverage gap.
3. **Add IVDR** + refresh the MDR consolidation to 2026-01-01.
4. **Add FDA CDS Software (2026)** — the highest-traffic US question the corpus currently cannot answer.
5. Add the SFDA cybersecurity trio + MDCG 2019-16 (cybersecurity is currently a hole in every jurisdiction).
6. Add MDCG 2023-4 / 2025-4 / 2025-10, FDA cybersecurity 2026, FDA-EMA Good AI Practice, WHO LMM, Qatar Law 13/2016.
7. Apply the §2.3 renames.
8. Resolve the two open manual gaps: UAE Federal PDPL 45/2021 (English) and IMDRF N88/N81 URL verification.
