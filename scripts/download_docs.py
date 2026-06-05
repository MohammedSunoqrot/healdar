"""
Healdar — Regulatory PDF Downloader
=====================================
Run this script once to download all source regulatory documents.

Usage:
    python download_docs.py

Requirements:
    pip install requests
"""

import time
import requests
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent / "data" / "raw_docs"

# Docs that must be downloaded manually — their servers block automated requests.
# Open each URL in a browser, save as the indicated filename in the correct subfolder.
MANUAL_DOWNLOADS = [
    {
        "url": "https://sdaia.gov.sa/en/SDAIA/about/Documents/ai-principles.pdf",
        "dest": "KSA_SDAIA/KSA_SDAIA_AI_Ethics_Principles_2023.pdf",
        "label": "SDAIA — AI Ethics Principles (Sep 2023)",
    },
    {
        "url": "https://sdaia.gov.sa/en/SDAIA/about/Files/AIAdoptionFramework.pdf",
        "dest": "KSA_SDAIA/KSA_SDAIA_AI_Adoption_Framework_2024.pdf",
        "label": "SDAIA — AI Adoption Framework (2024)",
    },
    {
        "url": "https://sdaia.gov.sa/en/SDAIA/about/Files/GenAIGuidelinesForGovernmentENCompressed.pdf",
        "dest": "KSA_SDAIA/KSA_SDAIA_GenAI_Guidelines_Government_2025.pdf",
        "label": "SDAIA — Generative AI Guidelines for Government (2025)",
    },
    {
        "url": "https://sdaia.gov.sa/en/SDAIA/about/Files/GenerativeAIPublicEN.pdf",
        "dest": "KSA_SDAIA/KSA_SDAIA_GenAI_Guidelines_Public_2025.pdf",
        "label": "SDAIA — Generative AI Guidelines for Public (2025)",
    },
    {
        "url": "https://sdaia.gov.sa/en/SDAIA/about/Documents/Personal%20Data%20English%20V2-23April2023-%20Reviewed-.pdf",
        "dest": "KSA_SDAIA/KSA_SDAIA_Personal_Data_Protection_Law_2023.pdf",
        "label": "SDAIA — Personal Data Protection Law (PDPL) (2023)",
    },
    {
        "url": "https://sdaia.gov.sa/en/SDAIA/about/Documents/ImplementingRegulation.pdf",
        "dest": "KSA_SDAIA/KSA_SDAIA_PDPL_Implementing_Regulations.pdf",
        "label": "SDAIA — PDPL Implementing Regulations",
    },
]

DOCS = [

    # ══════════════════════════════════════════════════════════════════════════
    # 🇸🇦  SAUDI ARABIA — SFDA  (Medical Device Regulator)
    # ══════════════════════════════════════════════════════════════════════════
    {
        "url": "https://www.sfda.gov.sa/sites/default/files/2023-01/MDS-G010ML.pdf",
        "dest": "SFDA/SFDA_MDS-G010_AI-ML_Medical_Devices_Guidance_2023.pdf",
        "label": "SFDA MDS-G010 — AI/ML Medical Devices Guidance (2023)",
    },
    {
        "url": "https://www.sfda.gov.sa/sites/default/files/2025-03/MDS-G025.pdf",
        "dest": "SFDA/SFDA_MDS-G025_AI_Guidance_2025.pdf",
        "label": "SFDA MDS-G025 — AI Guidance (Mar 2025)",
    },
    {
        "url": "https://www.sfda.gov.sa/sites/default/files/2020-03/MDS_G23.pdf",
        "dest": "SFDA/SFDA_MDS-G023_SaMD_Guidance_2020.pdf",
        "label": "SFDA MDS-G023 — Software as a Medical Device Guidance (2020)",
    },
    {
        "url": "https://www.sfda.gov.sa/sites/default/files/2025-08/MDS-G027.pdf",
        "dest": "SFDA/SFDA_MDS-G027_Digital_Health_Products_2025.pdf",
        "label": "SFDA MDS-G027 — Digital Health Products Guidance (Aug 2025)",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 🇦🇪  UAE — National / Federal
    # ══════════════════════════════════════════════════════════════════════════
    {
        # Primary URL blocked (403); using alternate path on same domain
        "url": "https://ai.gov.ae/wp-content/uploads/resources/UAE_National_Strategy_for_Artificial_Intelligence_2031.pdf",
        "dest": "UAE_National/UAE_National_AI_Strategy_2031.pdf",
        "label": "UAE — National AI Strategy 2031",
        "fallback_url": "https://ai.gov.ae/wp-content/uploads/2021/07/UAE-National-Strategy-for-Artificial-Intelligence-2031.pdf",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 🇦🇪  UAE — Department of Health, Abu Dhabi (DoH)
    # ══════════════════════════════════════════════════════════════════════════
    {
        "url": "https://www.doh.gov.ae/-/media/Feature/Resources/Standards/2025/Responsible-AI-Standard-V1.ashx",
        "dest": "UAE_DoH_AbuDhabi/UAE_DoH_Responsible_AI_Standard_V1_2025.pdf",
        "label": "UAE DoH Abu Dhabi — Responsible AI Standard V1 (2025)",
    },
    {
        "url": "https://www.doh.gov.ae/-/media/E9C1470A575146B18015DEBE57E47F8D.ashx",
        "dest": "UAE_DoH_AbuDhabi/UAE_DoH_Policy_AI_in_Healthcare.pdf",
        "label": "UAE DoH Abu Dhabi — Policy on Use of AI in Healthcare",
    },
    {
        "url": "https://www.doh.gov.ae/-/media/B5F0E47029F04CD8AD4CA16DC1FDBC66.ashx",
        "dest": "UAE_DoH_AbuDhabi/UAE_DoH_Digital_Health_Policy_2020.pdf",
        "label": "UAE DoH Abu Dhabi — Digital Health Policy (2020)",
    },
    {
        "url": "https://www.doh.gov.ae/-/media/8BD7C5DEC5974781B4C11BA00964B6F7.ashx",
        "dest": "UAE_DoH_AbuDhabi/UAE_DoH_Responsible_AI_Risk_Management_Protocol.pdf",
        "label": "UAE DoH Abu Dhabi — Responsible AI Risk Management Protocol",
    },
    {
        "url": "https://www.doh.gov.ae/-/media/Feature/Resources/Standards/2025/2102025--DataGovernanceStandard.ashx",
        "dest": "UAE_DoH_AbuDhabi/UAE_DoH_Data_Governance_Standard_2025.pdf",
        "label": "UAE DoH Abu Dhabi — Data Governance Standard (2025)",
    },
    {
        "url": "https://www.doh.gov.ae/-/media/Feature/Resources/Standards/2025/050825_Standard-use-of-AI-in-detecting-PT-AD.ashx",
        "dest": "UAE_DoH_AbuDhabi/UAE_DoH_Standard_AI_Detecting_PT_AD_2025.pdf",
        "label": "UAE DoH Abu Dhabi — Standard for Use of AI in Detecting PT/AD (2025)",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 🇦🇪  UAE — Dubai Health Authority (DHA)
    # ══════════════════════════════════════════════════════════════════════════
    {
        "url": "https://dha.gov.ae/uploads/012025/Standards%20for%20Consnet%20and%20Access%20Control2025129762.pdf",
        "dest": "UAE_DHA_Dubai/UAE_DHA_Standards_Health_Info_Consent_Access_2025.pdf",
        "label": "UAE DHA Dubai — Standards for Health Info Consent & Access Control (2025)",
    },
    {
        "url": "https://dha.gov.ae/uploads/012023/Standards%20for%20Telehealth%20Services2023158613.pdf",
        "dest": "UAE_DHA_Dubai/UAE_DHA_Standards_Telehealth_Services_2023.pdf",
        "label": "UAE DHA Dubai — Standards for Telehealth Services (2023)",
    },
    {
        "url": "https://dha.gov.ae/uploads/102022/NABIDH%20Policies%20&%20Standards%20-%20Interoperability%20and%20Data%20Exchange%20Standards2022100429.pdf",
        "dest": "UAE_DHA_Dubai/UAE_DHA_Standards_Interoperability_Data_Exchange.pdf",
        "label": "UAE DHA Dubai — NABIDH Interoperability & Data Exchange Standards",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 🇶🇦  QATAR — Ministry of Public Health (MOPH)
    # ══════════════════════════════════════════════════════════════════════════
    {
        "url": "https://www.moph.gov.qa/Style%20Library/MOPH/Files/strategies/National%20E-Health%20and%20Data%20Management%20Strategy/1.%20National%20E-Health%20and%20Data%20Management%20Strategy%20english.pdf",
        "dest": "Qatar_MOPH/Qatar_MOPH_National_EHealth_Data_Strategy.pdf",
        "label": "Qatar MOPH — National E-Health & Data Management Strategy",
    },
    {
        "url": "https://www.moph.gov.qa/_layouts/15/download.aspx?SourceUrl=%2FAdmin%2FLists%2FPublicationsAttachments%2FAttachments%2F309%2FQatar+Health+Report+2024+-+Eng.pdf",
        "dest": "Qatar_MOPH/Qatar_MOPH_Health_Report_2024.pdf",
        "label": "Qatar MOPH — Qatar Health Report 2024",
    },
    {
        "url": "https://moph.gov.qa/_layouts/15/download.aspx?SourceUrl=/Admin/Lists/PublicationsAttachments/Attachments/269/NCG+Handbook+for+Qatar+2023-2028.pdf",
        "dest": "Qatar_MOPH/Qatar_MOPH_NCG_Handbook_2023-2028.pdf",
        "label": "Qatar MOPH — National Clinical Guidelines Handbook 2023–2028",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 🇶🇦  QATAR — Ministry of Communications & IT (MCIT)
    # Sprinklr CDN mirrors used — official MCIT server returns 500
    # ══════════════════════════════════════════════════════════════════════════
    {
        "url": "https://prod16-assets.sprinklr.com/prod16-cdata/DAM/160136/33fb390b-d120-47f2-8708-532dcb1e15c3-1252740832/MCIT_National_AI_Strategy_-_AI.pdf",
        "dest": "Qatar_MCIT/Qatar_MCIT_National_AI_Strategy_2019.pdf",
        "label": "Qatar MCIT — National AI Strategy 2019",
        "fallback_url": "https://www.mcit.gov.qa/wp-content/uploads/sites/4/2025/02/national_artificial_intelligence_strategy_for_qatar_2019_en.pdf",
    },
    {
        # MCIT server returns 500; using URL with CSRF token as fallback
        "url": "https://www.mcit.gov.qa/wp-content/uploads/sites/4/2025/04/AI-Guidelines-_-En.pdf?csrt=5818954097072277596",
        "dest": "Qatar_MCIT/Qatar_MCIT_AI_Ethics_Use_Guidelines_2025.pdf",
        "label": "Qatar MCIT — Principles & Guidelines for Ethical Use of AI (2025)",
        "fallback_url": "https://www.mcit.gov.qa/wp-content/uploads/sites/4/2025/04/AI-Guidelines-_-En.pdf",
    },
    {
        "url": "https://www.mcit.gov.qa/wp-content/uploads/sites/4/2025/05/AI-Guidelines-Developers_-EN.pdf?csrt=5818954097072277596",
        "dest": "Qatar_MCIT/Qatar_MCIT_AI_Ethics_Development_Guidelines_2025.pdf",
        "label": "Qatar MCIT — Principles & Guidelines for Ethical Development of AI (2025)",
        "fallback_url": "https://www.mcit.gov.qa/wp-content/uploads/sites/4/2025/05/AI-Guidelines-Developers_-EN.pdf",
    },
    {
        # Bonus: National AI Policy consultation doc (found via CDN)
        "url": "https://prod16-assets.sprinklr.com/prod16-cdata/DAM/160136/9d77e677-a7f4-4659-a890-8e723c53e6dc-1081146622/MCIT_National_AI_Policy_Consul.pdf",
        "dest": "Qatar_MCIT/Qatar_MCIT_National_AI_Policy_Consultation.pdf",
        "label": "Qatar MCIT — National AI Policy Consultation Document",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 🇶🇦  QATAR — National Cyber Security Agency (NCSA)
    # Both URLs return HTML (session-gated). Scribd copy used as fallback note.
    # ══════════════════════════════════════════════════════════════════════════
    {
        "url": "https://assurance.ncsa.gov.qa/sites/default/files/publications/policy/2024/CSSP_Guidelines_for_Secure_Usage_and_Adoption_of_Artificial_intelligence-Eng-v1.0_2.pdf?csrt=1485093683095070046",
        "dest": "Qatar_NCSA/Qatar_NCSA_AI_Secure_Adoption_Guidelines_2024.pdf",
        "label": "Qatar NCSA — Guidelines for Secure Adoption & Usage of AI v1.0 (2024)",
        "manual_fallback": "Open https://www.scribd.com/document/707571046/ and download, or visit https://assurance.ncsa.gov.qa directly",
    },
    {
        "url": "https://ncsa.gov.qa/sites/default/files/2024-02/AI-Guide-en-V6.pdf",
        "dest": "Qatar_NCSA/Qatar_NCSA_AI_Guide_V6_2024.pdf",
        "label": "Qatar NCSA — AI Guide V6 (2024)",
        "manual_fallback": "Visit https://ncsa.gov.qa and navigate to Publications > AI Guide",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 🇺🇸  USA — FDA  (Medical Device Regulator)
    # ══════════════════════════════════════════════════════════════════════════
    {
        "url": "https://www.fda.gov/media/145022/download",
        "dest": "USA_FDA/USA_FDA_AIML_SaMD_Action_Plan_2021.pdf",
        "label": "FDA — AI/ML-Based SaMD Action Plan (Jan 2021)",
    },
    {
        "url": "https://www.fda.gov/media/153486/download",
        "dest": "USA_FDA/USA_FDA_GMLP_Guiding_Principles_2021.pdf",
        "label": "FDA — Good Machine Learning Practice (GMLP) Guiding Principles (Oct 2021)",
    },
    {
        "url": "https://www.fda.gov/media/173206/download",
        "dest": "USA_FDA/USA_FDA_PCCP_Guiding_Principles_2023.pdf",
        "label": "FDA — Predetermined Change Control Plans for ML-Enabled Devices: Guiding Principles (Oct 2023)",
    },
    {
        "url": "https://www.fda.gov/media/187905/download",
        "dest": "USA_FDA/USA_FDA_PCCP_Final_Guidance_AI_Devices_2024.pdf",
        "label": "FDA — Marketing Submission Recommendations for PCCP for AI-Enabled Device Software (Final, Dec 2024)",
    },
    {
        "url": "https://www.fda.gov/media/179269/download",
        "dest": "USA_FDA/USA_FDA_Transparency_ML_Medical_Devices_2024.pdf",
        "label": "FDA — Transparency for ML-Enabled Medical Devices: Guiding Principles (Jun 2024)",
    },
    {
        "url": "https://www.fda.gov/files/medical%20devices/published/US-FDA-Artificial-Intelligence-and-Machine-Learning-Discussion-Paper.pdf",
        "dest": "USA_FDA/USA_FDA_AIML_Discussion_Paper.pdf",
        "label": "FDA — AI/ML in Medical Devices Discussion Paper (foundational)",
    },

    # ══════════════════════════════════════════════════════════════════════════
    # 🇪🇺  EU — MDR / MDCG
    # ══════════════════════════════════════════════════════════════════════════
    {
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:02017R0745-20230320",
        "dest": "EU_MDR_MDCG/EU_MDR_2017-745_Consolidated_2023.pdf",
        "label": "EU MDR — Regulation (EU) 2017/745 consolidated text (Mar 2023)",
    },
    {
        "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=OJ:L_202401689",
        "dest": "EU_MDR_MDCG/EU_AI_Act_2024-1689.pdf",
        "label": "EU AI Act — Regulation (EU) 2024/1689",
    },
    {
        "url": "https://health.ec.europa.eu/document/download/b78a17d7-e3cd-4943-851d-e02a2f22bbb4_en?filename=mdcg_2025-6_en.pdf",
        "dest": "EU_MDR_MDCG/EU_MDCG_2025-6_FAQ_MDR_IVDR_AI_Act.pdf",
        "label": "MDCG 2025-6 — FAQ on MDR/IVDR & AI Act Interplay (June 2025)",
    },
    {
        "url": "https://health.ec.europa.eu/system/files/2023-12/mdcg_2023-5_en.pdf",
        "dest": "EU_MDR_MDCG/EU_MDCG_2023-5_Qualification_Classification_Software.pdf",
        "label": "MDCG 2023-5 — Qualification & Classification of Software under MDR/IVDR",
    },
    {
        "url": "https://health.ec.europa.eu/system/files/2020-09/md_mdcg_2020_1_guidance_clinic_eva_md_software_en_0.pdf",
        "dest": "EU_MDR_MDCG/EU_MDCG_2020-1_Clinical_Evaluation_MDSW.pdf",
        "label": "MDCG 2020-1 — Clinical Evaluation of Medical Device Software (MDSW)",
    },
    {
        "url": "https://health.ec.europa.eu/document/download/ad6ae143-baa2-451a-8c5e-0c5d22983e88_en?filename=mdcg_2025-7_en.pdf",
        "dest": "EU_MDR_MDCG/EU_MDCG_2025-7_Implementation_Timelines.pdf",
        "label": "MDCG 2025-7 Rev.1 — Implementation Timelines Position Paper",
    },
    {
        "url": "https://health.ec.europa.eu/document/download/b45335c5-1679-4c71-a91c-fc7a4d37f12b_en?filename=md_mdcg_2019_11_guidance_qualification_classification_software_en.pdf",
        "dest": "EU_MDR_MDCG/EU_MDCG_2019-11_Software_Qualification_Classification.pdf",
        "label": "MDCG 2019-11 — Software Qualification & Classification under MDR/IVDR (foundational)",
    },

]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def fetch(url, dest_path):
    """Attempt download; return (success, error_message)."""
    r = requests.get(url, headers=HEADERS, timeout=60, stream=True)
    r.raise_for_status()

    content_type = r.headers.get("Content-Type", "")
    chunks = list(r.iter_content(chunk_size=8192))
    first_bytes = b"".join(chunks)[:10]

    if "html" in content_type and not first_bytes.startswith(b"%PDF"):
        return False, "Got HTML instead of PDF (login/redirect page)"

    with open(dest_path, "wb") as f:
        for chunk in chunks:
            f.write(chunk)
    return True, None


def download_all():
    ok, failed, skipped_manual = [], [], []

    for doc in DOCS:
        dest_path = BASE_DIR / doc["dest"]
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        if dest_path.exists():
            print(f"  [SKIP] Already exists: {dest_path.name}")
            ok.append(doc["label"])
            continue

        print(f"  [↓]  {doc['label']}")
        success, err = False, None

        # Try primary URL
        try:
            success, err = fetch(doc["url"], dest_path)
        except Exception as e:
            err = str(e)

        # Try fallback URL if available
        if not success and "fallback_url" in doc:
            print(f"       ↳ Retrying with fallback URL…")
            time.sleep(2)
            try:
                success, err = fetch(doc["fallback_url"], dest_path)
            except Exception as e:
                err = str(e)

        if success:
            size_kb = dest_path.stat().st_size // 1024
            print(f"       ✓ Saved ({size_kb} KB) → {doc['dest']}")
            ok.append(doc["label"])
        else:
            manual_note = doc.get("manual_fallback", "")
            print(f"       ✗ FAILED: {err}")
            if manual_note:
                print(f"       → Manual fallback: {manual_note}")
            failed.append((doc["label"], doc["url"], err, manual_note))

        time.sleep(1)  # polite delay between requests

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"Auto-downloaded: {len(ok)}/{len(DOCS)}")

    if failed:
        print(f"\nFailed ({len(failed)}) — see manual download instructions below:")
        for label, url, err, manual in failed:
            print(f"  • {label}")
            print(f"    URL  : {url}")
            print(f"    Error: {err}")
            if manual:
                print(f"    Manual: {manual}")

    # ── Manual-only list ─────────────────────────────────────────────────────
    pending_manual = [
        d for d in MANUAL_DOWNLOADS
        if not (BASE_DIR / d["dest"]).exists()
    ]
    if pending_manual:
        print(f"\n{'=' * 60}")
        print("MANUAL DOWNLOADS REQUIRED (open each URL in a browser):")
        print("These servers block automated requests.\n")
        for d in pending_manual:
            print(f"  {d['label']}")
            print(f"    URL : {d['url']}")
            print(f"    Save: data/raw_docs/{d['dest']}\n")
    else:
        print("\nAll manual downloads already present.")


if __name__ == "__main__":
    download_all()
