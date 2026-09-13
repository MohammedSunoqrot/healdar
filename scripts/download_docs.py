"""
Healdar — regulatory source document downloader.

    python scripts/download_docs.py                # fetch anything missing
    python scripts/download_docs.py --force        # re-fetch everything
    python scripts/download_docs.py --verify       # check what is on disk
    python scripts/download_docs.py --only SDAIA   # filter by path substring

Three things this script is careful about, each learned from a real failure:

1. A 200 response is not a PDF. sdaia.gov.sa sits behind a WAF that answers
   bare clients with HTTP 200 and a 246-byte "Request Rejected" HTML page. We
   assert the Content-Type and the %PDF magic number before writing.

2. Some hosts need a Referer as well as a browser User-Agent, and reject HEAD
   outright. Everything here uses GET with per-document headers.

3. A file can download perfectly and still be the wrong document. Two files in
   this corpus were named as AI guidance but contained general-wellness and
   spectacle-frame UDI text respectively -- invisible until someone read them.
   Each entry carries an `expect` string that must appear in the first page, so
   a silent substitution upstream fails loudly here instead of turning into a
   confident mis-citation months later.

Requires: pip install requests pymupdf
"""

from __future__ import annotations

import argparse
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent / "data" / "raw_docs"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
SDAIA_REFERER = "https://sdaia.gov.sa/en/SDAIA/about/Pages/RegulationsAndPolicies.aspx"


@dataclass
class Doc:
    url: str
    dest: str
    label: str
    # Text that must appear on page 1 — catches wrong-document substitutions.
    expect: str = ""
    referer: str = ""
    fallback_url: str = ""
    note: str = ""

    @property
    def path(self) -> Path:
        return BASE_DIR / self.dest

    def headers(self) -> dict:
        h = {"User-Agent": UA, "Accept": "application/pdf,*/*"}
        if self.referer:
            h["Referer"] = self.referer
        return h


def sdaia(dest: str, url: str, label: str, expect: str = "") -> Doc:
    return Doc(url=url, dest=dest, label=label, expect=expect, referer=SDAIA_REFERER)


DOCS: list[Doc] = [
    # ══════════════════════════════════════════════════════════════════════
    # SAUDI ARABIA — SDAIA (data protection + national AI governance)
    # ══════════════════════════════════════════════════════════════════════
    sdaia("KSA_SDAIA/KSA_SDAIA_AI_Ethics_Principles_2025.pdf",
          "https://sdaia.gov.sa/en/SDAIA/about/Documents/ai-principles.pdf",
          "SDAIA — AI Ethics Principles (2025 edition)", "AI Ethics"),
    sdaia("KSA_SDAIA/KSA_SDAIA_AI_Adoption_Framework_2025.pdf",
          "https://sdaia.gov.sa/en/SDAIA/about/Files/AIAdoptionFramework.pdf",
          "SDAIA — AI Adoption Framework (2025)", "Adoption"),
    sdaia("KSA_SDAIA/KSA_SDAIA_GenAI_Guidelines_Government_2025.pdf",
          "https://sdaia.gov.sa/en/SDAIA/about/Files/GenAIGuidelinesForGovernmentENCompressed.pdf",
          "SDAIA — Generative AI Guidelines for Government (2025)", "Generative"),
    sdaia("KSA_SDAIA/KSA_SDAIA_GenAI_Guidelines_Public_2025.pdf",
          "https://sdaia.gov.sa/en/SDAIA/about/Files/GenerativeAIPublicEN.pdf",
          "SDAIA — Generative AI Guidelines for Public (2025)", "Generative"),
    sdaia("KSA_SDAIA/KSA_SDAIA_PDPL_Law_2023.pdf",
          "https://sdaia.gov.sa/en/SDAIA/about/Documents/PersonalDataProtectionLaw.pdf",
          "SDAIA — Personal Data Protection Law (PDPL)", "Personal Data"),
    sdaia("KSA_SDAIA/KSA_SDAIA_PDPL_Implementing_Regulations_2023.pdf",
          "https://sdaia.gov.sa/en/SDAIA/about/Documents/ImplementingRegulation.pdf",
          "SDAIA — PDPL Implementing Regulations (+ transfer regulation)", "Regulation"),
    sdaia("KSA_SDAIA/KSA_SDAIA_Data_Transfer_Outside_Kingdom_2024.pdf",
          "https://sdaia.gov.sa/Documents/RegulationonPersonalDataEN.pdf",
          "SDAIA — Personal Data Transfer outside the Kingdom v2.0 (2024)", "Transfer"),
    sdaia("KSA_SDAIA/KSA_SDAIA_Secondary_Use_of_Data_Rules_2025.pdf",
          "https://sdaia.gov.sa/Documents/GeneralRulesForSecondaryUseOfData_EN.pdf",
          "SDAIA — General Rules for Secondary Use of Data (2025)", "Secondary Use"),

    # ══════════════════════════════════════════════════════════════════════
    # SAUDI ARABIA — SFDA (medical device regulator)
    # ══════════════════════════════════════════════════════════════════════
    Doc("https://www.sfda.gov.sa/sites/default/files/2023-01/MDS-G010ML.pdf",
        "SFDA/SFDA_MDS-G010_AI-ML_Medical_Devices_Guidance_2023.pdf",
        "SFDA MDS-G010 — AI/ML Medical Devices Guidance", "MDS-G-010"),
    Doc("https://www.sfda.gov.sa/sites/default/files/2020-03/MDS_G23.pdf",
        "SFDA/SFDA_MDS-G023_SaMD_Guidance_2018.pdf",
        "SFDA MDS-G023 — Software as a Medical Device Guidance", "MDS"),
    Doc("https://www.sfda.gov.sa/sites/default/files/2025-03/MDS-G025.pdf",
        "SFDA/SFDA_MDS-G025_General_Wellness_Devices_2025.pdf",
        "SFDA MDS-G025 — General Wellness Devices Guidance",
        "General Wellness",
        note="Named 'AI Guidance' in earlier versions of this script; it is not."),
    Doc("https://www.sfda.gov.sa/sites/default/files/2025-08/MDS-G027.pdf",
        "SFDA/SFDA_MDS-G027_Digital_Health_Products_2025.pdf",
        "SFDA MDS-G027 — Digital Health Products Guidance", "MDS-G-027"),
    Doc("https://www.sfda.gov.sa/sites/default/files/2025-03/MDS-G024.pdf",
        "SFDA/SFDA_MDS-G024_ISO13485_Requirements_2025.pdf",
        "SFDA MDS-G024 — ISO 13485 / SFDA-MDS requirement mapping", "13485"),
    Doc("https://www.sfda.gov.sa/sites/default/files/2019-10/MDS-G38.pdf",
        "SFDA/SFDA_MDS-G038_PreMarket_Cybersecurity_2019.pdf",
        "SFDA MDS-G38 — Pre-Market Cybersecurity of Medical Devices", "Cybersecurity"),
    Doc("https://www.sfda.gov.sa/sites/default/files/2019-10/MDS-G37.pdf",
        "SFDA/SFDA_MDS-G037_PostMarket_Cybersecurity_2019.pdf",
        "SFDA MDS-G37 — Post-Market Cybersecurity of Medical Devices", "Cybersecurity"),
    Doc("https://www.sfda.gov.sa/sites/default/files/2019-10/MDS-G36.pdf",
        "SFDA/SFDA_MDS-G036_Cybersecurity_Healthcare_Providers_2019.pdf",
        "SFDA MDS-G36 — Medical Device Cybersecurity for Healthcare Providers",
        "Cybersecurity"),

    # ══════════════════════════════════════════════════════════════════════
    # SAUDI ARABIA — National Health Information Center
    # ══════════════════════════════════════════════════════════════════════
    Doc("https://nhic.gov.sa/standards/Policies/IS0303-Saudi-Health-Information-Exchange-Policies-v1.0.pdf",
        "KSA_NHIC/KSA_NHIC_Health_Information_Exchange_Policies_2016.pdf",
        "NHIC IS0303 — Saudi Health Information Exchange Policies", "Health Information"),
    Doc("https://nhic.gov.sa/standards/Telehealth/Telehealth-Application-Guidelines.pdf",
        "KSA_NHIC/KSA_NHIC_Telehealth_Application_Guidelines.pdf",
        "NHIC — Telehealth Application Guidelines", "Telehealth"),

    # ══════════════════════════════════════════════════════════════════════
    # UAE
    # ══════════════════════════════════════════════════════════════════════
    Doc("https://ai.gov.ae/wp-content/uploads/resources/UAE_National_Strategy_for_Artificial_Intelligence_2031.pdf",
        "UAE_National/UAE_National_AI_Strategy_2031.pdf",
        "UAE — National AI Strategy 2031", "Artificial Intelligence",
        fallback_url="https://ai.gov.ae/wp-content/uploads/2021/07/UAE-National-Strategy-for-Artificial-Intelligence-2031.pdf"),
    Doc("https://www.doh.gov.ae/-/media/Feature/Resources/Standards/2025/Responsible-AI-Standard-V1.ashx",
        "UAE_DoH_AbuDhabi/UAE_DoH_Responsible_AI_Standard_V1_2025.pdf",
        "UAE DoH Abu Dhabi — Responsible AI Standard V1 (2025)", "Responsible"),
    Doc("https://www.doh.gov.ae/-/media/E9C1470A575146B18015DEBE57E47F8D.ashx",
        "UAE_DoH_AbuDhabi/UAE_DoH_Policy_AI_in_Healthcare_2018.pdf",
        "UAE DoH Abu Dhabi — Policy on Use of AI in Healthcare (2018)", "Artificial"),
    Doc("https://www.doh.gov.ae/-/media/B5F0E47029F04CD8AD4CA16DC1FDBC66.ashx",
        "UAE_DoH_AbuDhabi/UAE_DoH_Digital_Health_Policy_2020.pdf",
        "UAE DoH Abu Dhabi — Digital Health Policy (2020)", "Digital Health"),
    Doc("https://www.doh.gov.ae/-/media/8BD7C5DEC5974781B4C11BA00964B6F7.ashx",
        "UAE_DoH_AbuDhabi/UAE_DoH_Responsible_AI_Risk_Management_Protocol.pdf",
        "UAE DoH Abu Dhabi — Responsible AI Risk Management Protocol", "Risk"),
    Doc("https://www.doh.gov.ae/-/media/Feature/Resources/Standards/2025/2102025--DataGovernanceStandard.ashx",
        "UAE_DoH_AbuDhabi/UAE_DoH_Data_Governance_Standard_2025.pdf",
        "UAE DoH Abu Dhabi — Data Governance Standard (2025)", "Data Governance"),
    Doc("https://www.doh.gov.ae/-/media/Feature/Resources/Standards/2025/050825_Standard-use-of-AI-in-detecting-PT-AD.ashx",
        "UAE_DoH_AbuDhabi/UAE_DoH_Standard_AI_Detecting_PT_AD_2025.pdf",
        "UAE DoH Abu Dhabi — Standard for Use of AI in Detecting PT/AD (2025)", "AI"),
    Doc("https://dha.gov.ae/uploads/012025/Standards%20for%20Consnet%20and%20Access%20Control2025129762.pdf",
        "UAE_DHA_Dubai/UAE_DHA_Standards_Health_Info_Consent_Access_2025.pdf",
        "UAE DHA Dubai — Health Info Consent & Access Control Standards (2025)", "Consent"),
    Doc("https://dha.gov.ae/uploads/012023/Standards%20for%20Telehealth%20Services2023158613.pdf",
        "UAE_DHA_Dubai/UAE_DHA_Standards_Telehealth_Services_V4_2025.pdf",
        "UAE DHA Dubai — Telehealth Services Standards V4 (2025)", "Telehealth"),
    Doc("https://dha.gov.ae/uploads/102022/NABIDH%20Policies%20&%20Standards%20-%20Interoperability%20and%20Data%20Exchange%20Standards2022100429.pdf",
        "UAE_DHA_Dubai/UAE_DHA_Standards_Interoperability_Data_Exchange_V2_2025.pdf",
        "UAE DHA Dubai — NABIDH Interoperability & Data Exchange Standards V2", "Interoperability"),

    # ══════════════════════════════════════════════════════════════════════
    # QATAR
    # ══════════════════════════════════════════════════════════════════════
    Doc("https://www.moph.gov.qa/Style%20Library/MOPH/Files/strategies/National%20E-Health%20and%20Data%20Management%20Strategy/1.%20National%20E-Health%20and%20Data%20Management%20Strategy%20english.pdf",
        "Qatar_MOPH/Qatar_MOPH_National_EHealth_Data_Strategy.pdf",
        "Qatar MOPH — National E-Health & Data Management Strategy", "Health"),
    Doc("https://www.moph.gov.qa/_layouts/15/download.aspx?SourceUrl=%2FAdmin%2FLists%2FPublicationsAttachments%2FAttachments%2F309%2FQatar+Health+Report+2024+-+Eng.pdf",
        "Qatar_MOPH/Qatar_MOPH_Health_Report_2024.pdf",
        "Qatar MOPH — Qatar Health Report 2024", "Health"),
    Doc("https://moph.gov.qa/_layouts/15/download.aspx?SourceUrl=/Admin/Lists/PublicationsAttachments/Attachments/269/NCG+Handbook+for+Qatar+2023-2028.pdf",
        "Qatar_MOPH/Qatar_MOPH_NCG_Handbook_2023-2028.pdf",
        "Qatar MOPH — National Clinical Guidelines Handbook 2023-2028", "Clinical"),
    Doc("https://prod16-assets.sprinklr.com/prod16-cdata/DAM/160136/33fb390b-d120-47f2-8708-532dcb1e15c3-1252740832/MCIT_National_AI_Strategy_-_AI.pdf",
        "Qatar_MCIT/Qatar_MCIT_National_AI_Strategy_2019.pdf",
        "Qatar MCIT — National AI Strategy 2019", "Artificial Intelligence",
        fallback_url="https://www.mcit.gov.qa/wp-content/uploads/sites/4/2025/02/national_artificial_intelligence_strategy_for_qatar_2019_en.pdf"),
    Doc("https://www.mcit.gov.qa/wp-content/uploads/sites/4/2025/04/AI-Guidelines-_-En.pdf",
        "Qatar_MCIT/Qatar_MCIT_AI_Ethics_Use_Guidelines_2025.pdf",
        "Qatar MCIT — Guidelines for Ethical Use of AI (2025)", "Artificial Intelligence"),
    Doc("https://www.mcit.gov.qa/wp-content/uploads/sites/4/2025/05/AI-Guidelines-Developers_-EN.pdf",
        "Qatar_MCIT/Qatar_MCIT_AI_Ethics_Development_Guidelines_2025.pdf",
        "Qatar MCIT — Guidelines for Ethical Development of AI (2025)", "Artificial Intelligence"),
    Doc("https://prod16-assets.sprinklr.com/prod16-cdata/DAM/160136/9d77e677-a7f4-4659-a890-8e723c53e6dc-1081146622/MCIT_National_AI_Policy_Consul.pdf",
        "Qatar_MCIT/Qatar_MCIT_National_AI_Policy_Consultation.pdf",
        "Qatar MCIT — National AI Policy Consultation Document", "AI"),
    Doc("https://assurance.ncsa.gov.qa/sites/default/files/publications/policy/2024/CSSP_Guidelines_for_Secure_Usage_and_Adoption_of_Artificial_intelligence-Eng-v1.0_2.pdf",
        "Qatar_NCSA/Qatar_NCSA_AI_Secure_Adoption_Guidelines_2024.pdf",
        "Qatar NCSA — Secure Adoption & Usage of AI v1.0 (2024)", "Artificial Intelligence"),
    # ══════════════════════════════════════════════════════════════════════
    # EUROPEAN UNION
    # ══════════════════════════════════════════════════════════════════════
    Doc("https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:02017R0745-20260101",
        "EU_MDR_MDCG/EU_MDR_2017-745_Consolidated_2026.pdf",
        "EU MDR — Regulation (EU) 2017/745 consolidated (in force 2026-01-01)",
        "2017/745"),
    Doc("https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:02017R0746-20250110",
        "EU_MDR_MDCG/EU_IVDR_2017-746_Consolidated_2025.pdf",
        "EU IVDR — Regulation (EU) 2017/746 consolidated (2025-01-10)", "2017/746"),
    Doc("https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=OJ:L_202401689",
        "EU_MDR_MDCG/EU_AI_Act_2024-1689.pdf",
        "EU AI Act — Regulation (EU) 2024/1689", "2024/1689"),
    Doc("https://health.ec.europa.eu/document/download/b45335c5-1679-4c71-a91c-fc7a4d37f12b_en?filename=md_mdcg_2019_11_guidance_qualification_classification_software_en.pdf",
        "EU_MDR_MDCG/EU_MDCG_2019-11_Software_Qualification_Classification.pdf",
        "MDCG 2019-11 Rev.1 — Software Qualification & Classification", "MDCG 2019-11"),
    Doc("https://health.ec.europa.eu/system/files/2020-09/md_mdcg_2020_1_guidance_clinic_eva_md_software_en_0.pdf",
        "EU_MDR_MDCG/EU_MDCG_2020-1_Clinical_Evaluation_MDSW.pdf",
        "MDCG 2020-1 — Clinical Evaluation of Medical Device Software", "MDCG 2020-1"),
    Doc("https://health.ec.europa.eu/system/files/2023-12/mdcg_2023-5_en.pdf",
        "EU_MDR_MDCG/EU_MDCG_2023-5_Qualification_Classification_Software.pdf",
        "MDCG 2023-5 — Qualification & Classification of Software", "MDCG 2023-5"),
    Doc("https://health.ec.europa.eu/document/download/b2c4e715-f2b4-4d24-af60-056b5d41a72e_en?filename=md_mdcg_2023-4_software_en.pdf",
        "EU_MDR_MDCG/EU_MDCG_2023-4_MDSW_Hardware_Combinations_2023.pdf",
        "MDCG 2023-4 — MDSW Hardware Combinations", "MDCG 2023-4"),
    Doc("https://health.ec.europa.eu/document/download/ec9b0f40-7f82-43a7-b833-ebd45b772eae_en?filename=mdcg_2025-4_en.pdf",
        "EU_MDR_MDCG/EU_MDCG_2025-4_MDSW_Online_Platforms_2025.pdf",
        "MDCG 2025-4 — MDSW apps on online platforms", "MDCG 2025-4"),
    Doc("https://health.ec.europa.eu/document/download/b78a17d7-e3cd-4943-851d-e02a2f22bbb4_en?filename=mdcg_2025-6_en.pdf",
        "EU_MDR_MDCG/EU_MDCG_2025-6_FAQ_MDR_IVDR_AI_Act.pdf",
        "MDCG 2025-6 — FAQ on MDR/IVDR & AI Act interplay", "MDCG 2025-6"),
    Doc("https://health.ec.europa.eu/document/download/a9ad86b7-1b8e-4bae-beb4-48b2b3ed2f05_en?filename=mdcg_2025-10_en.pdf",
        "EU_MDR_MDCG/EU_MDCG_2025-10_Post_Market_Surveillance_2025.pdf",
        "MDCG 2025-10 — Post-market surveillance of devices and IVDs", "MDCG 2025-10"),
    Doc("https://health.ec.europa.eu/document/download/b23b362f-8a56-434c-922a-5b3ca4d0a7a1_en?filename=md_cybersecurity_en.pdf",
        "EU_MDR_MDCG/EU_MDCG_2019-16_Cybersecurity_Medical_Devices.pdf",
        "MDCG 2019-16 Rev.1 — Cybersecurity for medical devices", "Cybersecurity"),
    Doc("https://ec.europa.eu/newsroom/dae/redirection/document/118119",
        "EU_MDR_MDCG/EU_GPAI_Code_of_Practice_Safety_Security_2025.pdf",
        "GPAI Code of Practice — Safety and Security chapter (2025)", "General-Purpose"),
    Doc("https://ec.europa.eu/newsroom/dae/redirection/document/118120",
        "EU_MDR_MDCG/EU_GPAI_Code_of_Practice_Transparency_2025.pdf",
        "GPAI Code of Practice — Transparency chapter (2025)", "Transparency"),

    # ══════════════════════════════════════════════════════════════════════
    # UNITED STATES — FDA
    # ══════════════════════════════════════════════════════════════════════
    Doc("https://www.fda.gov/media/145022/download",
        "USA_FDA/USA_FDA_AIML_SaMD_Action_Plan_2021.pdf",
        "FDA — AI/ML-Based SaMD Action Plan (2021)", "Action Plan"),
    Doc("https://www.fda.gov/media/153486/download",
        "USA_FDA/USA_FDA_GMLP_Guiding_Principles_2021.pdf",
        "FDA — Good Machine Learning Practice Guiding Principles (2021)",
        "Machine Learning"),
    Doc("https://www.fda.gov/media/173206/download",
        "USA_FDA/USA_FDA_PCCP_Guiding_Principles_2023.pdf",
        "FDA — PCCP for ML-Enabled Devices: Guiding Principles (2023)", "Change Control"),
    Doc("https://www.fda.gov/media/187905/download",
        "USA_FDA/USA_FDA_PCCP_Final_Guidance_AI_Devices_2024.pdf",
        "FDA — Marketing Submission Recommendations for PCCP (Final, 2024)",
        "Change Control"),
    Doc("https://www.fda.gov/media/179269/download",
        "USA_FDA/USA_FDA_Transparency_ML_Medical_Devices_2024.pdf",
        "FDA — Transparency for ML-Enabled Medical Devices (2024)", "Transparency"),
    Doc("https://www.fda.gov/files/medical%20devices/published/US-FDA-Artificial-Intelligence-and-Machine-Learning-Discussion-Paper.pdf",
        "USA_FDA/USA_FDA_AIML_Discussion_Paper.pdf",
        "FDA — AI/ML in Medical Devices Discussion Paper", "Artificial Intelligence"),
    Doc("https://www.fda.gov/media/109618/download",
        "USA_FDA/USA_FDA_Clinical_Decision_Support_Software_2026.pdf",
        "FDA — Clinical Decision Support Software (2026-01-29)", "Clinical Decision Support"),
    Doc("https://www.fda.gov/media/119933/download",
        "USA_FDA/USA_FDA_Cybersecurity_Premarket_Submissions_2026.pdf",
        "FDA — Cybersecurity in Medical Devices: QMS & Premarket (2026-02-03)",
        "Cybersecurity"),
    Doc("https://www.fda.gov/media/189581/download",
        "USA_FDA/USA_FDA_EMA_Good_AI_Practice_Drug_Development_2026.pdf",
        "FDA/EMA — Guiding Principles of Good AI Practice in Drug Development (2026)",
        "Artificial Intelligence"),

    # ══════════════════════════════════════════════════════════════════════
    # INTERNATIONAL
    # ══════════════════════════════════════════════════════════════════════
    Doc("https://iris.who.int/server/api/core/bitstreams/e9e62c65-6045-481e-bd04-20e206bc5039/content",
        "International/INT_WHO_Ethics_Governance_AI_Health_LMM_2024.pdf",
        "WHO — Ethics & governance of AI for health: large multi-modal models (2024)",
        "health"),
]

# Documents that genuinely could not be automated. Kept visible rather than
# quietly dropped, so the gap stays on the record.
MANUAL_DOWNLOADS = [
    {
        "label": "UAE Federal Decree-Law 45/2021 — Personal Data Protection Law",
        "dest": "UAE_National/UAE_Federal_PDPL_45_2021.pdf",
        "why": "uaelegislation.gov.ae returns 403 behind a Cloudflare challenge; "
               "the official u.ae publication is Arabic only. No official English "
               "PDF located — circulating English copies are private-site mirrors.",
    },
    {
        "label": "Qatar National Health Strategy 2024-2030",
        "dest": "Qatar_MOPH/Qatar_MOPH_National_Health_Strategy_2024-2030.pdf",
        "why": "moph.gov.qa publishes a landing page only, no downloadable PDF. "
               "Request from nationalpmo@moph.gov.qa.",
    },
    {
        "label": "IMDRF N88 (GMLP) and N81 (software risk characterization), 2025",
        "dest": "International/",
        "why": "imdrf.org was unreachable during research (TCP timeout, not a "
               "block). URLs are unverified — confirm before scripting.",
    },
    {
        "label": "Qatar Law No. 13 of 2016 on Protecting Personal Data Privacy",
        "dest": "Qatar_National/Qatar_Law_13_2016_Personal_Data_Privacy.pdf",
        "why": "almeezan.qa (the official legal portal) serves an incomplete TLS "
               "chain, so verification fails. Disabling certificate checks to "
               "fetch the text of a law is not an acceptable trade: a MITM could "
               "substitute altered legislation and it would be cited as "
               "authoritative. Download it manually in a browser from "
               "https://www.almeezan.qa/LawPage.aspx?id=3948&language=en",
    },
]


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch(doc: Doc, url: str) -> tuple[bool, str]:
    """Download `url` into doc.path. Returns (ok, error)."""
    try:
        r = requests.get(url, headers=doc.headers(), timeout=90, allow_redirects=True)
    except Exception as exc:
        return False, f"request failed: {exc}"

    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"

    body = r.content
    ctype = r.headers.get("Content-Type", "").lower()

    # A 200 with an HTML body is a WAF rejection page, not a document.
    if not body.startswith(b"%PDF"):
        if "html" in ctype or body[:512].lstrip()[:1] == b"<":
            return False, f"got HTML not PDF ({len(body)} bytes, {ctype})"
        return False, f"not a PDF (starts {body[:8]!r}, {ctype})"

    if len(body) < 4096:
        return False, f"suspiciously small ({len(body)} bytes)"

    doc.path.parent.mkdir(parents=True, exist_ok=True)
    doc.path.write_bytes(body)
    return True, ""


def _flatten(text: str) -> str:
    """
    Normalise PDF text for substring matching.

    Two traps make a naive `expect in text` check fail on perfectly good files:
    typographic ligatures (PDFs render "Artificial" as "Arti<ﬁ>cial", U+FB01)
    and line breaks landing mid-phrase ("MDCG\\n2019-11"). NFKC expands the
    ligatures; collapsing whitespace handles the wrapping.
    """
    return " ".join(unicodedata.normalize("NFKC", text).split()).lower()


# Title pages are often a cover sheet or a header-only page, so scan a few.
VERIFY_PAGES = 3


def verify_content(doc: Doc) -> tuple[bool, str]:
    """Check that doc.expect appears near the front. Skipped when expect is empty."""
    if not doc.expect:
        return True, ""
    try:
        import fitz
    except ImportError:
        return True, "pymupdf not installed — content check skipped"
    try:
        with fitz.open(str(doc.path)) as pdf:
            if pdf.page_count == 0:
                return False, "PDF has no pages"
            front = "\n".join(
                pdf[i].get_text() for i in range(min(VERIFY_PAGES, pdf.page_count))
            )
    except Exception as exc:
        return False, f"unreadable PDF: {exc}"

    if _flatten(doc.expect) not in _flatten(front):
        snippet = _flatten(front)[:110]
        return False, (
            f"expected {doc.expect!r} in the first {VERIFY_PAGES} pages; "
            f"found: {snippet!r}"
        )
    return True, ""


def process(doc: Doc, force: bool) -> str:
    """Returns one of: skip, ok, mismatch, fail."""
    if doc.path.exists() and not force:
        ok, err = verify_content(doc)
        if ok:
            print(f"  [have] {doc.dest}")
            return "skip"
        print(f"  [BAD ] {doc.dest}\n         {err}")
        return "mismatch"

    print(f"  [get ] {doc.label}")
    ok, err = fetch(doc, doc.url)
    if not ok and doc.fallback_url:
        print(f"         primary failed ({err}) — trying fallback")
        time.sleep(2)
        ok, err = fetch(doc, doc.fallback_url)

    if not ok:
        print(f"         FAILED: {err}")
        return "fail"

    content_ok, content_err = verify_content(doc)
    size_kb = doc.path.stat().st_size // 1024
    if not content_ok:
        print(f"         WRONG CONTENT ({size_kb} KB): {content_err}")
        return "mismatch"

    print(f"         saved {size_kb} KB -> {doc.dest}")
    return "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Healdar source documents.")
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    parser.add_argument("--verify", action="store_true",
                        help="only check files already on disk")
    parser.add_argument("--only", default="", help="filter by substring of the dest path")
    args = parser.parse_args()

    docs = [d for d in DOCS if args.only.lower() in d.dest.lower()]
    print(f"{len(docs)} document(s) selected\n")

    results: dict[str, list[str]] = {"ok": [], "skip": [], "fail": [], "mismatch": []}

    for doc in docs:
        if args.verify:
            if not doc.path.exists():
                print(f"  [miss] {doc.dest}")
                results["fail"].append(doc.dest)
                continue
            ok, err = verify_content(doc)
            print(f"  [{'ok  ' if ok else 'BAD '}] {doc.dest}" + (f"\n         {err}" if err else ""))
            results["ok" if ok else "mismatch"].append(doc.dest)
            continue

        results[process(doc, args.force)].append(doc.dest)
        if not doc.path.exists() or args.force:
            time.sleep(1)                             # be polite between hosts

    print("\n" + "=" * 70)
    print(f"  downloaded {len(results['ok'])} | already present {len(results['skip'])} "
          f"| failed {len(results['fail'])} | wrong content {len(results['mismatch'])}")

    for dest in results["fail"]:
        print(f"    FAILED   {dest}")
    for dest in results["mismatch"]:
        print(f"    MISMATCH {dest}")

    missing_manual = [m for m in MANUAL_DOWNLOADS
                      if not (BASE_DIR / m["dest"]).exists()]
    if missing_manual:
        print("\n  Known gaps requiring manual sourcing:")
        for m in missing_manual:
            print(f"    - {m['label']}\n      {m['why']}")

    stray = orphans()
    if stray:
        print("\n  NOT IN MANIFEST -- would be ingested; remove or add to DOCS:")
        for p in stray:
            print(f"    {p.relative_to(BASE_DIR)}")

    print("=" * 70)
    print("\nNext: python src/ingest.py && python src/embed.py --rebuild\n")
    return 1 if (results["fail"] or results["mismatch"] or stray) else 0


def orphans() -> list[Path]:
    """
    PDFs on disk that the manifest does not list.

    The manifest is the authoritative corpus. An unlisted file is usually a
    superseded version left behind after a refresh -- exactly how the 2023 MDR
    consolidation ended up ingested next to the 2026 one, both citeable.
    """
    if not BASE_DIR.exists():
        return []
    listed = {d.path.resolve() for d in DOCS}
    return sorted(p for p in BASE_DIR.rglob("*.pdf") if p.resolve() not in listed)


if __name__ == "__main__":
    sys.exit(main())
