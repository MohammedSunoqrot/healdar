"""
Healdar — Health AI Regulatory Navigator
Streamlit frontend.

Theming: Streamlit draws its own widgets from the light and dark palettes in
.streamlit/config.toml and follows the visitor's system setting (switchable
from the ⋮ menu: System / Light / Dark). Healdar's own components — answer card,
references, notices — take their colours from the inherited text colour via
CSS color-mix(), so they follow whichever theme is active without the app
having to know which one that is. (The previous version repainted a "light
mode" with CSS overrides over a forced dark theme; Streamlit's widgets never
got those colours, which is why light mode had black buttons and header.)
"""

import csv
import dataclasses
import html as _html
import importlib
import io
import json
import logging
import sys
import time as _time
from datetime import date, datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as _components

SCRIPT_DIR   = Path(__file__).resolve().parent   # src/
PROJECT_ROOT = SCRIPT_DIR.parent                  # Healdar/
sys.path.insert(0, str(SCRIPT_DIR))

import config

# Hot-reload rag_pipeline on each rerun so prompt edits land without restarting
# the server. Development only: in production this rebuilds the RAGAnswer class
# on every run, which breaks isinstance checks and wastes work.
if config.DEV_MODE and "rag_pipeline" in sys.modules:
    importlib.reload(sys.modules["rag_pipeline"])

import analytics as _analytics
import export as _export
import formatting
from rag_pipeline import (
    HealdarError,
    HealdarRAG,
    ModelUnavailableError,
    RAGAnswer,
    RateLimitError,
    RetrievalError,
    ServiceUnavailableError,
)

logger = logging.getLogger("healdar.app")

# ---------------------------------------------------------------------------
# Jurisdictions — keys match rag_pipeline.JURISDICTION_MAP
# ---------------------------------------------------------------------------
JURISDICTIONS = {
    "all":   {"flag": "🌍", "color": "#555B6E",
              "en": "All jurisdictions", "short_en": "All jurisdictions",
              "ar": "جميع الجهات", "short_ar": "جميع الجهات"},
    "sfda":  {"flag": "🇸🇦", "color": "#00843D",
              "en": "Saudi Arabia · SFDA, SDAIA, NHIC", "short_en": "Saudi Arabia",
              "ar": "السعودية · SFDA، SDAIA، NHIC", "short_ar": "السعودية"},
    "uae":   {"flag": "🇦🇪", "color": "#CC0001",
              "en": "UAE · Federal, DoH, DHA", "short_en": "UAE",
              "ar": "الإمارات · اتحادي، دائرة الصحة، هيئة الصحة", "short_ar": "الإمارات"},
    "qatar": {"flag": "🇶🇦", "color": "#8D1B3D",
              "en": "Qatar · MOPH, MCIT, NCSA, law", "short_en": "Qatar",
              "ar": "قطر · وزارة الصحة، الاتصالات، الأمن السيبراني، القانون", "short_ar": "قطر"},
    "eu":    {"flag": "🇪🇺", "color": "#003399",
              "en": "European Union · MDR, IVDR, AI Act", "short_en": "European Union",
              "ar": "الاتحاد الأوروبي · MDR، IVDR، AI Act", "short_ar": "الاتحاد الأوروبي"},
    "fda":   {"flag": "🇺🇸", "color": "#1A1A6E",
              "en": "United States · FDA", "short_en": "United States",
              "ar": "الولايات المتحدة · FDA", "short_ar": "الولايات المتحدة"},
    "intl":  {"flag": "🌐", "color": "#0072CE",
              "en": "International · WHO, IMDRF", "short_en": "International",
              "ar": "دولي · WHO، IMDRF", "short_ar": "دولي"},
}

# Folder tag in the index → jurisdiction key above (for colours).
JX_COLOR_MAP: dict[str, str] = {
    "EU_Legislation":    "eu",
    "EU_MDCG":           "eu",
    "EU_AI_Office":      "eu",
    "KSA_SFDA":          "sfda",
    "KSA_SDAIA":         "sfda",
    "KSA_NHIC":          "sfda",
    "Qatar_MOPH":        "qatar",
    "Qatar_MCIT":        "qatar",
    "Qatar_NCSA":        "qatar",
    "Qatar_Legislation": "qatar",
    "UAE_Federal":       "uae",
    "UAE_DoH_AbuDhabi":  "uae",
    "UAE_DHA_Dubai":     "uae",
    "USA_FDA":           "fda",
    "INT_WHO":           "intl",
    "INT_IMDRF":         "intl",
}

# ---------------------------------------------------------------------------
# UI strings (English / Arabic)
# ---------------------------------------------------------------------------
T = {
    "en": {
        "tagline":        "Health AI Regulatory Intelligence",
        "q_placeholder":  "Ask about health-AI regulation, e.g. post-market surveillance for AI medical devices",
        "ask":            "Ask",
        "disclaimer":     "For informational purposes only — not legal or regulatory advice. Always verify against the official documents.",
        "compare_toggle": "⚖️ Compare two jurisdictions",
        "jx_label":       "Jurisdiction",
        "compare_left":   "First jurisdiction",
        "compare_right":  "Second jurisdiction",
        "about_title":    "ℹ️ About Healdar",
        "about_body":     (
            "Healdar answers questions about health-AI regulation using only official "
            "documents from Gulf, European, US and international regulators. Every claim "
            "is cited to a document and page; when the documents don't cover a question, "
            "Healdar says so instead of guessing."
        ),
        "theme_hint":     "Light or dark mode follows your system. Switch any time from the ⋮ menu at the top right (System, Light or Dark).",
        "loading":        "Searching the regulatory documents…",
        "loading_index":  "Loading the regulatory index…",
        "lang_label":     "Language",
        "no_context":     "No relevant material was found in the selected documents for this question. Try another jurisdiction or rephrase.",
        "copy":           "📋 Copy",
        "copied":         "✓ Copied",
        "page":           "p.",
        "clear_history":  "🗑 Clear history",
        "history_label":  "Recent questions",
        "export_pdf":     "📄 PDF",
        "export_word":    "📝 Word",
        "session_title":  "📊 Your session",
        "session_empty":  "A summary of your questions in this session will appear here.",
        "session_note":   "Only your own questions in this browser tab. Nothing here is shared with other visitors, and it resets when you close the tab.",
        "stat_questions": "Questions",
        "stat_avg":       "Avg. time",
        "stat_answered":  "Answered",
        "stat_compare":   "Comparisons",
        "stat_lang":      "Language",
        "stat_jx":        "Jurisdictions",
        "session_dl":     "⬇ Download my session (CSV)",
        "rate_limit":     "⏳ The language-model rate limit was reached — please wait a moment and try again.",
        "starter_prompt": "Try asking",
        "weak_match":     "Only loosely related material was found — verify against the source documents before relying on this.",
        "partial_answer": "The documents only partly cover this question. Treat the answer as incomplete.",
        "err_title":      "Healdar is temporarily unavailable",
        "err_model":      "The configured language model was rejected by the provider. It has most likely been retired — set GROQ_MODEL_ANSWER to a current model.",
        "err_service":    "The language-model service is unreachable right now. Please try again shortly.",
        "err_retrieval":  "The regulatory index could not be searched. This is a system fault, not an absence of regulation.",
        "err_generic":    "Something went wrong handling that request.",
        "throttled":      "You have reached this session's question limit. Please wait a little before asking again.",
        "references":     "References",
        "version":        "Version",
        "released":       "Released",
        "corpus_line":    "{docs} official documents · {bodies} regulators",
        "developed_by":   "Developed by",
        "sources_meta":   "{n} cited sources",
        "followup_placeholder": "Ask a follow-up, e.g. what if the software works without a clinician?",
        "new_conversation": "✚ New conversation",
        "suggested":      "Suggested follow-ups",
        "understood_as":  "Understood as",
        "back_to_thread": "← Back to the conversation",
    },
    "ar": {
        "tagline":        "الذكاء التنظيمي للذكاء الاصطناعي الصحي",
        "q_placeholder":  "اسأل عن تنظيم الذكاء الاصطناعي الصحي، مثل مراقبة ما بعد التسويق للأجهزة الطبية",
        "ask":            "اسأل",
        "disclaimer":     "لأغراض إعلامية فقط، وليست استشارة قانونية أو تنظيمية. تحقّق دائماً من الوثائق الرسمية.",
        "compare_toggle": "⚖️ المقارنة بين جهتين",
        "jx_label":       "الجهة التنظيمية",
        "compare_left":   "الجهة الأولى",
        "compare_right":  "الجهة الثانية",
        "about_title":    "ℹ️ حول هيلدار",
        "about_body":     (
            "يجيب هيلدار عن أسئلة تنظيم الذكاء الاصطناعي الصحي اعتماداً على الوثائق الرسمية "
            "فقط من الجهات التنظيمية الخليجية والأوروبية والأمريكية والدولية. كل معلومة موثّقة "
            "بالوثيقة ورقم الصفحة، وعندما لا تغطي الوثائق السؤال يوضّح ذلك بدلاً من التخمين."
        ),
        "theme_hint":     "يتبع الوضع الفاتح أو الداكن إعدادات جهازك، ويمكنك تغييره في أي وقت من قائمة ⋮ أعلى الصفحة (System / Light / Dark).",
        "loading":        "جارٍ البحث في الوثائق التنظيمية…",
        "loading_index":  "جارٍ تحميل فهرس الوثائق…",
        "lang_label":     "اللغة",
        "no_context":     "لم يُعثر على محتوى ذي صلة في الوثائق المختارة لهذا السؤال. جرّب جهة أخرى أو أعد صياغة السؤال.",
        "copy":           "📋 نسخ",
        "copied":         "✓ تم النسخ",
        "page":           "ص.",
        "clear_history":  "🗑 مسح السجل",
        "history_label":  "الأسئلة الأخيرة",
        "export_pdf":     "📄 PDF",
        "export_word":    "📝 Word",
        "session_title":  "📊 جلستك",
        "session_empty":  "سيظهر هنا ملخص أسئلتك في هذه الجلسة.",
        "session_note":   "أسئلتك أنت فقط في علامة التبويب هذه. لا يُشارك أي شيء مع الزوار الآخرين، ويُمسح عند إغلاق الصفحة.",
        "stat_questions": "الأسئلة",
        "stat_avg":       "متوسط الوقت",
        "stat_answered":  "تمت الإجابة",
        "stat_compare":   "المقارنات",
        "stat_lang":      "اللغة",
        "stat_jx":        "الجهات",
        "session_dl":     "⬇ تنزيل جلستي (CSV)",
        "rate_limit":     "⏳ تم الوصول إلى حد الطلبات — يرجى الانتظار لحظة ثم المحاولة مجدداً.",
        "starter_prompt": "جرّب أن تسأل",
        "weak_match":     "لم يُعثر إلا على محتوى ضعيف الصلة — يُرجى التحقق من الوثائق الرسمية قبل الاعتماد على هذه الإجابة.",
        "partial_answer": "الوثائق تغطي هذا السؤال جزئياً فقط. اعتبر الإجابة غير مكتملة.",
        "err_title":      "هيلدار غير متاح مؤقتاً",
        "err_model":      "رفض المزوّد النموذج اللغوي المُهيأ، وعلى الأرجح تم إيقافه — يُرجى ضبط GROQ_MODEL_ANSWER على نموذج حالي.",
        "err_service":    "خدمة النموذج اللغوي غير متاحة حالياً. يُرجى المحاولة بعد قليل.",
        "err_retrieval":  "تعذّر البحث في فهرس الوثائق التنظيمية. هذا خلل تقني وليس غياباً للتشريع.",
        "err_generic":    "حدث خطأ أثناء معالجة الطلب.",
        "throttled":      "لقد بلغت حد عدد الأسئلة لهذه الجلسة. يُرجى الانتظار قليلاً.",
        "references":     "المصادر",
        "version":        "الإصدار",
        "released":       "تاريخ الإصدار",
        "corpus_line":    "{docs} وثيقة رسمية · {bodies} جهة تنظيمية",
        "developed_by":   "تطوير",
        "sources_meta":   "{n} مصادر مستشهد بها",
        "followup_placeholder": "اطرح سؤال متابعة، مثلاً: ماذا لو عمل البرنامج دون تدخل الطبيب؟",
        "new_conversation": "✚ محادثة جديدة",
        "suggested":      "أسئلة متابعة مقترحة",
        "understood_as":  "فُهم السؤال على أنه",
        "back_to_thread": "→ العودة إلى المحادثة",
    },
}

STARTERS = {
    "en": [
        "What are the post-market surveillance requirements for AI medical devices?",
        "How does SFDA regulate AI-based Software as a Medical Device?",
        "What does the EU AI Act require for high-risk medical AI systems?",
        "When is clinical decision support software regulated by the FDA?",
        "Can patient data be reused to train AI models under Saudi data protection rules?",
        "What are the IMDRF good machine learning practice principles?",
    ],
    "ar": [
        "ما هي متطلبات مراقبة ما بعد التسويق لأجهزة الذكاء الاصطناعي الطبية؟",
        "كيف تنظّم هيئة الغذاء والدواء السعودية البرمجيات الطبية القائمة على الذكاء الاصطناعي؟",
        "ما متطلبات قانون الاتحاد الأوروبي للذكاء الاصطناعي للأنظمة الطبية عالية المخاطر؟",
        "متى تخضع برمجيات دعم القرار السريري لتنظيم إدارة الغذاء والدواء الأمريكية؟",
        "ما حقوق صاحب البيانات في قانون حماية البيانات الشخصية الإماراتي؟",
        "ما مبادئ الممارسة الجيدة للتعلم الآلي الصادرة عن IMDRF؟",
    ],
}

_AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو",
              "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


def release_date_label(lang: str) -> str:
    d = date.fromisoformat(config.RELEASE_DATE)
    if lang == "ar":
        return f"{d.day} {_AR_MONTHS[d.month - 1]} {d.year}"
    return d.strftime("%d %b %Y").lstrip("0")


# ---------------------------------------------------------------------------
# CSS — theme-agnostic: every colour is derived from the inherited text colour
# (currentColor) or is a brand colour that reads on both backgrounds.
# ---------------------------------------------------------------------------
_CSS = """
<style>
:root { --hd-accent: #3B5BDB; }

/* Header */
.hd-header { text-align:center; padding:1rem 0 .3rem; }
.hd-logo { font-size:2.5rem; line-height:1; }
.hd-title { font-size:2.4rem; font-weight:800; letter-spacing:-.5px; margin:.25rem 0 0; }
.hd-tagline { opacity:.72; font-size:1rem; }
.hd-corpus { display:inline-block; margin-top:.55rem; font-size:.78rem; padding:.2rem .75rem;
  border-radius:999px; background:color-mix(in srgb, currentColor 6%, transparent);
  border:1px solid color-mix(in srgb, currentColor 12%, transparent); }
.hd-rtl { direction:rtl; text-align:right; }

/* Question bubble */
.hd-q { margin:1.1rem 0 .55rem; padding:.6rem 1rem; border-radius:12px;
  border-inline-start:3px solid var(--hd-accent);
  background:color-mix(in srgb, currentColor 4%, transparent); font-size:.95rem; }

/* Answer card */
.hd-card { border:1px solid color-mix(in srgb, currentColor 13%, transparent);
  background:color-mix(in srgb, currentColor 2.5%, transparent);
  border-radius:14px; padding:1.15rem 1.45rem .85rem; margin:.25rem 0 .55rem;
  font-size:.97rem; line-height:1.75; }
.hd-card-head { display:flex; justify-content:space-between; align-items:center;
  gap:.6rem; margin-bottom:.85rem; flex-wrap:wrap; }
.hd-badge { display:inline-flex; align-items:center; gap:.35rem; padding:.22rem .8rem;
  border-radius:999px; font-size:.78rem; font-weight:700; color:#fff; }
.hd-meta { font-size:.72rem; opacity:.6; }
.hd-understood { display:block; margin-top:.3rem; font-size:.76rem; font-weight:400; opacity:.72; }
/* Question lists read as lists: left-aligned, not centred button captions.
   Keyed containers give a stable class; Streamlit's own button markup is not. */
.st-key-hd_history button, .st-key-hd_history button *,
.st-key-hd_followups button, .st-key-hd_followups button * {
  justify-content:flex-start !important; text-align:left !important; }
.hd-body p { margin:0 0 .75rem; }
.hd-body ul, .hd-body ol { margin:0 0 .85rem; padding-inline-start:1.4rem; }
.hd-body li { margin-bottom:.35rem; }
.hd-body .ans-h { font-weight:700; margin:1rem 0 .35rem; }
.hd-body code { font-size:.86em; padding:.05rem .3rem; border-radius:4px;
  background:color-mix(in srgb, currentColor 8%, transparent); }
.ans-table { overflow-x:auto; margin:.3rem 0 .9rem; }
.ans-table table { border-collapse:collapse; width:100%; font-size:.86rem; }
.ans-table th, .ans-table td { border:1px solid color-mix(in srgb, currentColor 15%, transparent);
  padding:.4rem .6rem; text-align:start; vertical-align:top; }
.ans-table th { background:color-mix(in srgb, currentColor 6%, transparent); }
.fn-ref { color:color-mix(in srgb, var(--hd-accent) 72%, currentColor); font-size:.72em;
  font-weight:700; vertical-align:super; cursor:help; margin-inline-start:1px; }

/* Notices */
.notice { display:flex; gap:.5rem; align-items:flex-start;
  background:color-mix(in srgb, #D69E2E 13%, transparent);
  border:1px solid color-mix(in srgb, #D69E2E 45%, transparent);
  border-radius:9px; padding:.55rem .8rem; margin:0 0 .85rem; font-size:.84rem; line-height:1.5; }
.no-context { opacity:.78; font-style:italic; text-align:center; padding:1.1rem 0; }

/* References — native <details>, so they open without any JavaScript */
.refs-section { border-top:1px solid color-mix(in srgb, currentColor 12%, transparent);
  margin-top:1rem; padding-top:.55rem; }
.refs-title { font-size:.68rem; font-weight:700; letter-spacing:1px; text-transform:uppercase;
  opacity:.55; margin-bottom:.25rem; }
details.ref > summary { list-style:none; display:flex; align-items:center; gap:.5rem;
  cursor:pointer; padding:.3rem .45rem; border-radius:7px; font-size:.83rem; }
details.ref > summary::-webkit-details-marker { display:none; }
details.ref > summary:hover { background:color-mix(in srgb, currentColor 6%, transparent); }
.ref-num { font-weight:700; color:color-mix(in srgb, var(--hd-accent) 72%, currentColor);
  min-width:1.7rem; font-size:.78rem; }
.ref-dot { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
.ref-label { flex:1; opacity:.88; line-height:1.35; }
.ref-score { font-size:.7rem; opacity:.6; font-variant-numeric:tabular-nums; }
.ref-toggle { font-size:.7rem; opacity:.5; width:.9rem; text-align:center; }
.ref-toggle::after { content:"▾"; }
details.ref[open] .ref-toggle::after { content:"▴"; }
.ref-excerpt { margin:.15rem 0 .55rem 2.2rem; padding:.6rem .85rem; border-left:3px solid;
  border-radius:0 6px 6px 0; background:color-mix(in srgb, currentColor 4%, transparent);
  font-size:.8rem; line-height:1.6; white-space:pre-wrap; max-height:15rem; overflow:auto; }
.refs-section.hd-rtl .ref-excerpt { margin:.15rem 2.2rem .55rem 0; border-left:none;
  border-right:3px solid; border-radius:6px 0 0 6px; }
.disclaimer { font-size:.74rem; opacity:.58; margin-top:.8rem; padding-top:.6rem;
  border-top:1px solid color-mix(in srgb, currentColor 10%, transparent); text-align:center; }

/* Sidebar */
.sidebar-label { font-size:.68rem; font-weight:700; letter-spacing:1px; text-transform:uppercase;
  opacity:.58; margin:.85rem 0 .2rem; }
.hd-brand { display:flex; align-items:center; gap:.5rem; flex-wrap:wrap; }
.hd-brand-name { font-weight:800; font-size:1.3rem; }
.hd-ver { display:inline-block; font-size:.72rem; padding:.12rem .55rem; border-radius:999px;
  font-weight:700; background:color-mix(in srgb, var(--hd-accent) 16%, transparent);
  color:color-mix(in srgb, var(--hd-accent) 75%, currentColor); }
.hd-ver-date { font-size:.74rem; opacity:.65; margin:.15rem 0 .2rem; }
.hd-stats { display:grid; grid-template-columns:1fr 1fr; gap:.45rem; margin:.2rem 0 .55rem; }
.hd-stat { border:1px solid color-mix(in srgb, currentColor 12%, transparent);
  border-radius:9px; padding:.4rem .55rem; }
.hd-stat-l { font-size:.68rem; opacity:.62; }
.hd-stat-v { font-size:1.12rem; font-weight:700; }
.hd-bar { display:flex; align-items:center; gap:.45rem; font-size:.76rem; margin:.15rem 0; }
.hd-bar-name { width:6.2rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.hd-bar-track { flex:1; height:6px; border-radius:4px;
  background:color-mix(in srgb, currentColor 10%, transparent); }
.hd-bar-fill { height:6px; border-radius:4px; background:var(--hd-accent); }
.hd-small { font-size:.74rem; opacity:.65; line-height:1.45; }
.hd-foot { margin-top:1.2rem; padding-top:.75rem;
  border-top:1px solid color-mix(in srgb, currentColor 12%, transparent); font-size:.76rem; }
a.hd-li { display:inline-flex; align-items:center; gap:.35rem; margin-top:.35rem;
  padding:.25rem .65rem; border-radius:5px; background:#0A66C2; color:#fff !important;
  text-decoration:none !important; font-weight:600; font-size:.72rem; }
[data-testid="stSidebar"] [data-testid="stBaseButton-tertiary"] {
  justify-content:flex-start; text-align:start; }
[data-testid="stSidebar"] [data-testid="stBaseButton-tertiary"] p {
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Cached resources
# ---------------------------------------------------------------------------
_RAG_VERSION = "9"   # bump to invalidate st.cache_resource after pipeline changes


@st.cache_resource(show_spinner=False)
def load_rag(v: str = _RAG_VERSION) -> HealdarRAG:
    return HealdarRAG()


@st.cache_data(show_spinner=False)
def corpus_stats() -> tuple[int, int]:
    """(documents, regulator folders) in the committed index — shown under the title."""
    try:
        chunks = json.loads(config.CHUNKS_FILE.read_text(encoding="utf-8"))
        docs = {c["metadata"]["filename"] for c in chunks}
        bodies = {c["metadata"]["jurisdiction"] for c in chunks}
        return len(docs), len(bodies)
    except Exception:
        return 0, 0


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def jx_color(jurisdiction: str) -> str:
    key = JX_COLOR_MAP.get(jurisdiction, "all")
    return JURISDICTIONS.get(key, JURISDICTIONS["all"])["color"]


def jx_display(jx_key: str, lang: str) -> str:
    j = JURISDICTIONS[jx_key]
    return f'{j["flag"]} {j[lang]}'


def jx_short(jx_key: str, lang: str) -> str:
    return JURISDICTIONS[jx_key][f"short_{lang}"]


def prettify_filename(filename: str) -> str:
    """"SFDA_MDS-G010_AI-ML_Guidance_2023.pdf" → "SFDA MDS-G010 AI-ML Guidance 2023"."""
    return Path(filename).stem.replace("_", " ")


def badge_html(jx_key: str, lang: str) -> str:
    j = JURISDICTIONS[jx_key]
    return (f'<span class="hd-badge" style="background:{j["color"]}">'
            f'{j["flag"]} {_html.escape(jx_short(jx_key, lang))}</span>')


def _tidy_excerpt(text: str, limit: int = 1800) -> str:
    lines = [ln.rstrip() for ln in (text or "").strip().splitlines()]
    out, blank = [], 0
    for ln in lines:
        blank = blank + 1 if not ln.strip() else 0
        if blank <= 1:
            out.append(ln)
    tidy = "\n".join(out)
    return tidy[:limit].rstrip() + ("…" if len(tidy) > limit else "")


def text_to_html(text: str, ref_tooltips: dict | None = None) -> str:
    """
    Answer text → safe HTML. Markdown is rendered (never shown raw), and
    [Source N] becomes a footnote superscript with an optional hover tooltip.
    """
    def _ref_tag(m) -> str:
        n = int(m.group(1))
        tip = (ref_tooltips or {}).get(n, "")
        title = f' title="{_html.escape(tip)}"' if tip else ""
        return f'<sup class="fn-ref"{title}>[{n}]</sup>'

    return formatting.to_html(text, cite=_ref_tag)


def source_strip_html(indexed_sources: list[tuple[int, dict]], lang: str, card_id: str) -> str:
    """
    Numbered reference list matching the [N] superscripts in the answer.
    Each entry is a native <details> element: click to read the passage.
    """
    if not indexed_sources:
        return ""
    page_lbl = T[lang]["page"]
    rtl = " hd-rtl" if lang == "ar" else ""
    rows = []
    for idx, s in indexed_sources:
        color = jx_color(s.get("jurisdiction", ""))
        name = _html.escape(prettify_filename(s.get("filename", "")))
        rel = s.get("relevance")
        score = (f'<span class="ref-score">{round(float(rel) * 100)}%</span>'
                 if isinstance(rel, (int, float)) else "")
        excerpt = _html.escape(_tidy_excerpt(s.get("text") or ""))
        rows.append(
            f'<details class="ref" id="rref-{card_id}-{idx}">'
            f'<summary><span class="ref-num">[{idx}]</span>'
            f'<span class="ref-dot" style="background:{color}"></span>'
            f'<span class="ref-label">{name} · {page_lbl}{s.get("page_number", "")}</span>'
            f'{score}<span class="ref-toggle"></span></summary>'
            f'<div class="ref-excerpt" dir="auto" style="border-color:{color}">{excerpt}</div>'
            f'</details>'
        )
    return (f'<div class="refs-section{rtl}"><div class="refs-title">'
            f'{T[lang]["references"]}</div>{"".join(rows)}</div>')


def select_cited_sources(answer: str, sources: list[dict]) -> list[tuple[int, dict]]:
    """
    Pair each [Source N] cited in `answer` with sources[N-1].

    `sources` IS the citation numbering: the pipeline merges same-page passages
    before building the prompt, so entry N is exactly what the model saw as
    [Source N]. Never re-order or re-number it here — the previous version
    deduplicated and re-indexed at render time, which shifted every reference
    and silently dropped any citation past the end of the shortened list.
    """
    cited = {int(n) for n in config.CITATION_RE.findall(answer)}
    indexed = [(i, s) for i, s in enumerate(sources, start=1) if i in cited]
    # A citation pointing past the end means something upstream went out of
    # sync. Show every source rather than a misleadingly partial list.
    if cited and not indexed:
        return list(enumerate(sources, start=1))
    return indexed


def build_history_context(chat_history: list) -> list[dict] | None:
    """Last 3 single-mode turns (English text, with each answer's sources) for follow-ups."""
    single = [
        {"question_en": e["result"].question_en, "answer_en": e["result"].answer_en,
         "sources": e["result"].sources}
        for e in chat_history
        if e.get("mode") == "single"
        and e["result"].question_en
        and e["result"].answer_en
    ]
    return single[-3:] if single else None


def _copy_component_html(text: str, label_copy: str, label_copied: str) -> str:
    # json.dumps alone is not enough inside a <script> block: a literal
    # "</script>" in the answer text would close the tag early.
    text_js = json.dumps(text).replace("</", "<\\/")
    copy_js = json.dumps(label_copy)
    done_js = json.dumps(label_copied)
    # Runs in an iframe that cannot see the app theme, so it uses a neutral
    # grey that reads on both light and dark backgrounds.
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
        '*{margin:0;padding:0;box-sizing:border-box}'
        'body{background:transparent;font-family:"Source Sans Pro",sans-serif}'
        'button{background:transparent;border:1px solid rgba(128,138,160,.55);'
        'color:#7d879c;border-radius:8px;font-size:14px;cursor:pointer;width:100%;'
        'height:38px;transition:border-color .15s,color .15s}'
        'button:hover{border-color:#3B5BDB;color:#3B5BDB}'
        '</style></head><body><button id="cb"></button><script>'
        f'var TEXT={text_js},COPY={copy_js},DONE={done_js};'
        'var b=document.getElementById("cb");b.textContent=COPY;'
        'b.addEventListener("click",function(){'
        'function done(){b.textContent=DONE;setTimeout(function(){b.textContent=COPY;},1500);}'
        'if(navigator.clipboard){navigator.clipboard.writeText(TEXT).then(done,fallback);}else{fallback();}'
        'function fallback(){var t=document.createElement("textarea");t.value=TEXT;'
        't.style.cssText="position:fixed;opacity:0";document.body.appendChild(t);t.select();'
        'try{document.execCommand("copy")}catch(e){}document.body.removeChild(t);done();}'
        '});</script></body></html>'
    )


@st.cache_data(show_spinner=False, max_entries=64)
def _pdf_bytes(question, answer, sources, jx_label, question_original) -> bytes:
    return _export.to_pdf(question=question, answer=answer, sources=sources,
                          jurisdiction=jx_label, question_original=question_original)


@st.cache_data(show_spinner=False, max_entries=64)
def _docx_bytes(question, answer, sources, jx_label, lang) -> bytes:
    return _export.to_docx(question=question, answer=answer, sources=sources,
                           jurisdiction=jx_label, lang=lang)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def understood_as(result: RAGAnswer) -> str:
    """The rewritten question behind a follow-up, when it differs from what was typed."""
    searched = (getattr(result, "search_question", "") or "").strip()
    asked = (result.question_en or result.question or "").strip()
    return searched if searched and searched.lower() != asked.lower() else ""


def render_question_bubble(question: str, lang: str, understood: str = "") -> None:
    rtl = " hd-rtl" if lang == "ar" else ""
    # A rewritten follow-up is shown, so the reader can see what was searched.
    extra = (f'<span class="hd-understood">{_html.escape(T[lang]["understood_as"])}: '
             f'<span dir="ltr">{_html.escape(understood)}</span></span>' if understood else "")
    st.markdown(f'<div class="hd-q{rtl}">🔍 {_html.escape(question)}{extra}</div>',
                unsafe_allow_html=True)


def render_answer(result: RAGAnswer, jx_key: str, lang: str, card_id: str = "") -> None:
    card_id = card_id or jx_key
    indexed_cited = select_cited_sources(result.answer, result.sources)
    tooltips = {
        idx: f"{prettify_filename(s['filename'])} · {T[lang]['page']}{s['page_number']}"
        for idx, s in indexed_cited
    }

    # Say plainly when the evidence is thin, rather than presenting a hedged
    # answer with the same confidence as a solid one.
    notices = []
    if not result.no_context:
        if getattr(result, "quality", "ok") == "weak":
            notices.append(T[lang]["weak_match"])
        if getattr(result, "coverage", "full") == "partial":
            notices.append(T[lang]["partial_answer"])
    notice_html = "".join(
        f'<div class="notice"><span>⚠️</span><span>{_html.escape(n)}</span></div>'
        for n in notices
    )

    dir_attr = ' dir="rtl"' if lang == "ar" else ""
    if result.no_context:
        body = f'<p class="no-context">{_html.escape(T[lang]["no_context"])}</p>'
        meta = ""
    else:
        body = f'{notice_html}<div class="hd-body"{dir_attr}>{text_to_html(result.answer, tooltips)}</div>'
        meta = (f'<span class="hd-meta">'
                f'{_html.escape(T[lang]["sources_meta"].format(n=len(indexed_cited)))}</span>'
                if indexed_cited else "")

    st.markdown(
        f'<div class="hd-card"><div class="hd-card-head">{badge_html(jx_key, lang)}{meta}</div>'
        f'{body}{source_strip_html(indexed_cited, lang, card_id)}'
        f'<div class="disclaimer">{_html.escape(T[lang]["disclaimer"])}</div></div>',
        unsafe_allow_html=True,
    )

    if result.no_context:
        return

    plain = formatting.to_plain(config.CITATION_RE.sub(r"[\1]", result.answer))
    copy_html = _copy_component_html(plain, T[lang]["copy"], T[lang]["copied"])
    fname = f"healdar_{jx_key}_{_export._file_date()}"
    label = jx_short(jx_key, "en")
    sources = tuple(indexed_cited)
    col_copy, col_pdf, col_word, _ = st.columns([1, 1, 1, 3])
    with col_copy:
        _components.html(copy_html, height=42)
    with col_pdf:
        st.download_button(
            T[lang]["export_pdf"],
            _pdf_bytes(result.question_en or result.question,
                       result.answer_en or result.answer, sources, label, result.question),
            file_name=f"{fname}.pdf", mime="application/pdf",
            width="stretch", key=f"pdf_{card_id}_{id(result)}",
        )
    with col_word:
        st.download_button(
            T[lang]["export_word"],
            _docx_bytes(result.question, result.answer, sources, label, lang),
            file_name=f"{fname}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            width="stretch", key=f"word_{card_id}_{id(result)}",
        )


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
def error_message(exc: Exception, lang: str) -> str:
    if isinstance(exc, RateLimitError):
        return T[lang]["rate_limit"]
    if isinstance(exc, ModelUnavailableError):
        return T[lang]["err_model"]
    if isinstance(exc, ServiceUnavailableError):
        return T[lang]["err_service"]
    if isinstance(exc, RetrievalError):
        return T[lang]["err_retrieval"]
    return T[lang]["err_generic"]


def show_error(exc: Exception, lang: str) -> None:
    """Warn the user, and log the real cause for whoever runs the service."""
    logger.warning("Query failed: %s: %s", type(exc).__name__, exc)
    st.warning(error_message(exc, lang))


def render_unavailable(exc: Exception, lang: str) -> None:
    """Failure card for when the pipeline cannot start at all."""
    logger.error("Startup failed: %s: %s", type(exc).__name__, exc, exc_info=True)
    rtl = " hd-rtl" if lang == "ar" else ""
    st.markdown(
        f'<div class="hd-card{rtl}"><h4 style="margin-top:0">⚠️ {_html.escape(T[lang]["err_title"])}</h4>'
        f'<p>{_html.escape(error_message(exc, lang))}</p>'
        f'<p class="hd-small">{_html.escape(f"{type(exc).__name__}: {exc}")}</p></div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Per-session throttle
# ---------------------------------------------------------------------------
def throttle_exceeded() -> bool:
    """
    Has this session used up its query allowance?

    Pure check with no side effect. Streamlit re-runs the whole script on every
    interaction — a language switch, a history click — so a check that also
    *recorded* a query would drain the allowance without any model call ever
    being made. Recording is record_query()'s job, and it is called only where
    a request is actually about to be issued.

    Disabled unless HEALDAR_RATE_LIMIT_QUERIES is set.
    """
    if config.RATE_LIMIT_QUERIES <= 0:
        return False
    now = _time.time()
    recent = [t for t in st.session_state.get("query_times", [])
              if now - t < config.RATE_LIMIT_WINDOW]
    st.session_state.query_times = recent
    return len(recent) >= config.RATE_LIMIT_QUERIES


def record_query() -> None:
    """Count one query against the session allowance."""
    if config.RATE_LIMIT_QUERIES <= 0:
        return
    st.session_state.query_times = [*st.session_state.get("query_times", []), _time.time()]


# ---------------------------------------------------------------------------
# Session statistics — this visitor's own questions only, kept in session_state
# ---------------------------------------------------------------------------
def log_session_query(lang: str, mode: str, jurisdictions: list[str], seconds: float,
                      answered: bool, coverage: str) -> None:
    st.session_state.session_log.append({
        "time":          datetime.now().strftime("%H:%M:%S"),
        "language":      lang,
        "mode":          mode,
        "jurisdictions": " + ".join(jurisdictions),
        "seconds":       round(seconds, 1),
        "answered":      answered,
        "coverage":      coverage,
    })


def session_csv(log: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["time", "language", "mode", "jurisdictions",
                                             "seconds", "answered", "coverage"])
    writer.writeheader()
    writer.writerows(log)
    return buf.getvalue().encode("utf-8-sig")


def render_session_panel(lang: str) -> None:
    log = st.session_state.session_log
    if not log:
        st.caption(T[lang]["session_empty"])
        st.caption(T[lang]["session_note"])
        return

    n = len(log)
    avg = sum(r["seconds"] for r in log) / n
    answered = round(100 * sum(1 for r in log if r["answered"]) / n)
    compares = sum(1 for r in log if r["mode"] == "compare")
    stats = [(T[lang]["stat_questions"], n), (T[lang]["stat_avg"], f"{avg:.0f}s"),
             (T[lang]["stat_answered"], f"{answered}%"), (T[lang]["stat_compare"], compares)]
    st.markdown(
        '<div class="hd-stats">' + "".join(
            f'<div class="hd-stat"><div class="hd-stat-l">{_html.escape(str(k))}</div>'
            f'<div class="hd-stat-v">{_html.escape(str(v))}</div></div>' for k, v in stats
        ) + "</div>",
        unsafe_allow_html=True,
    )

    def bars(title: str, counts: dict[str, int]) -> str:
        top = max(counts.values())
        rows = "".join(
            f'<div class="hd-bar"><span class="hd-bar-name">{_html.escape(k)}</span>'
            f'<div class="hd-bar-track"><div class="hd-bar-fill" style="width:{round(100 * v / top)}%"></div></div>'
            f'<span>{v}</span></div>'
            for k, v in sorted(counts.items(), key=lambda kv: -kv[1])
        )
        return f'<div class="sidebar-label">{_html.escape(title)}</div>{rows}'

    langs: dict[str, int] = {}
    jxs: dict[str, int] = {}
    for r in log:
        name = "English" if r["language"] == "en" else "العربية"
        langs[name] = langs.get(name, 0) + 1
        for key in r["jurisdictions"].split(" + "):
            if key in JURISDICTIONS:
                label = jx_short(key, lang)
                jxs[label] = jxs.get(label, 0) + 1
    st.markdown(bars(T[lang]["stat_lang"], langs) + (bars(T[lang]["stat_jx"], jxs) if jxs else ""),
                unsafe_allow_html=True)
    st.download_button(T[lang]["session_dl"], session_csv(log),
                       file_name=f"healdar_session_{_export._file_date()}.csv",
                       mime="text/csv", width="stretch", key="session_csv")
    st.caption(T[lang]["session_note"])


# ---------------------------------------------------------------------------
# Optional disk persistence of chat history (off by default)
# ---------------------------------------------------------------------------
_SESSION_FILE = PROJECT_ROOT / "data" / "runtime" / "last_session.json"
_MAX_PERSISTED = 15


def _serialise_entry(entry: dict) -> dict:
    e = dict(entry)
    for key in ("result", "result_l", "result_r"):
        val = e.get(key)
        if val is not None and dataclasses.is_dataclass(val) and not isinstance(val, type):
            e[key] = dataclasses.asdict(val)
    return e


def _deserialise_entry(entry: dict) -> dict:
    e = dict(entry)
    for key in ("result", "result_l", "result_r"):
        if key in e and isinstance(e[key], dict):
            e[key] = RAGAnswer(**e[key])
    return e


def save_session(chat_history: list) -> None:
    """
    Write recent history to disk. Off by default: the file is process-wide, not
    per-visitor, so on a shared deployment it would show one person's questions
    and answers to the next person who loads the page.
    """
    if not config.PERSIST_SESSION:
        return
    try:
        payload = [_serialise_entry(e) for e in chat_history[-_MAX_PERSISTED:]]
        _SESSION_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    except Exception:
        pass


def load_session() -> list:
    if not config.PERSIST_SESSION:
        return []
    try:
        if not _SESSION_FILE.exists():
            return []
        return [_deserialise_entry(e)
                for e in json.loads(_SESSION_FILE.read_text(encoding="utf-8"))]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
def init_state() -> None:
    if "chat_history" not in st.session_state:
        persisted = load_session()
        if persisted:
            st.session_state["chat_history"] = persisted
            last = persisted[-1]
            if last.get("mode") == "single":
                st.session_state["last_result"] = last["result"]
                st.session_state["thread"] = [last]
                st.session_state["used_jx"] = last.get("jurisdiction")
            elif last.get("mode") == "compare":
                st.session_state["last_result_l"] = last["result_l"]
                st.session_state["last_result_r"] = last["result_r"]
                st.session_state["used_jx_l"] = last.get("jx_l")
                st.session_state["used_jx_r"] = last.get("jx_r")

    defaults: dict = {
        "lang": "en", "compare": False, "q_input": "", "pending_q": None,
        "scroll_latest": False, "thread": [],
        "last_jx": "all", "last_result": None,
        "last_jx_l": "sfda", "last_jx_r": "eu",
        "last_result_l": None, "last_result_r": None,
        "used_jx": None, "used_jx_l": None, "used_jx_r": None,
        "chat_history": [], "selected_hist_idx": None, "session_log": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _ask_starter(question: str) -> None:
    """Starter and suggested follow-up buttons ask directly."""
    st.session_state.pending_q = question
    st.session_state.selected_hist_idx = None


def _on_submit() -> None:
    """Queue the typed question and empty the box, ready for a follow-up."""
    q = st.session_state.get("q_input", "").strip()
    if q:
        st.session_state.pending_q = q
        st.session_state.selected_hist_idx = None
    st.session_state.q_input = ""


def _new_conversation() -> None:
    st.session_state.thread = []
    st.session_state.selected_hist_idx = None


def _back_to_thread() -> None:
    st.session_state.selected_hist_idx = None


def _clear_history() -> None:
    for key in ("last_result", "last_result_l", "last_result_r",
                "used_jx", "used_jx_l", "used_jx_r", "selected_hist_idx"):
        st.session_state[key] = None
    st.session_state.chat_history = []
    st.session_state.thread = []
    save_session([])


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def render_sidebar(lang: str) -> tuple[str, bool]:
    with st.sidebar:
        st.markdown(
            f'<div class="hd-brand"><span class="hd-brand-name">📡🩺 Healdar</span>'
            f'<span class="hd-ver">v{config.APP_VERSION}</span></div>'
            f'<div class="hd-ver-date">{T[lang]["released"]}: {release_date_label(lang)}</div>',
            unsafe_allow_html=True,
        )

        st.markdown(f'<div class="sidebar-label">{T[lang]["lang_label"]}</div>',
                    unsafe_allow_html=True)
        pick = st.radio("lang_radio", ["English", "العربية"], index=0 if lang == "en" else 1,
                        horizontal=True, label_visibility="collapsed")
        chosen = "en" if pick == "English" else "ar"
        if chosen != lang:
            st.session_state.lang = chosen
            st.rerun()

        st.divider()
        compare = st.toggle(T[lang]["compare_toggle"], value=st.session_state.compare)
        st.session_state.compare = compare

        keys = list(JURISDICTIONS)
        if not compare:
            st.markdown(f'<div class="sidebar-label">{T[lang]["jx_label"]}</div>',
                        unsafe_allow_html=True)
            opts = [jx_display(k, lang) for k in keys]
            sel = st.selectbox("jx_single", opts, index=keys.index(st.session_state.last_jx),
                               label_visibility="collapsed")
            st.session_state.last_jx = keys[opts.index(sel)]
        else:
            cmp_keys = [k for k in keys if k != "all"]
            opts = [jx_display(k, lang) for k in cmp_keys]
            for side, label, fallback in (("l", "compare_left", 0), ("r", "compare_right", 1)):
                st.markdown(f'<div class="sidebar-label">{T[lang][label]}</div>',
                            unsafe_allow_html=True)
                cur = st.session_state[f"last_jx_{side}"]
                idx = cmp_keys.index(cur) if cur in cmp_keys else fallback
                sel = st.selectbox(f"jx_{side}", opts, index=idx, label_visibility="collapsed")
                st.session_state[f"last_jx_{side}"] = cmp_keys[opts.index(sel)]

        hist = st.session_state.chat_history
        if hist:
            st.divider()
            st.markdown(f'<div class="sidebar-label">{T[lang]["history_label"]}</div>',
                        unsafe_allow_html=True)
            sel_idx = st.session_state.selected_hist_idx
            active = sel_idx if sel_idx is not None else len(hist) - 1
            with st.container(key="hd_history"):
                for i in range(len(hist) - 1, -1, -1):
                    q = hist[i]["question"]
                    q_short = (q[:46] + "…") if len(q) > 46 else q
                    marker = "● " if i == active else ""
                    if st.button(f"{marker}{q_short}", key=f"hist_btn_{i}", type="tertiary",
                                 width="stretch", help=q):
                        st.session_state.selected_hist_idx = i
                        st.rerun()
            st.button(T[lang]["clear_history"], width="stretch", on_click=_clear_history)

        st.divider()
        with st.expander(T[lang]["session_title"]):
            render_session_panel(lang)

        with st.expander(T[lang]["about_title"]):
            docs, bodies = corpus_stats()
            rtl = " hd-rtl" if lang == "ar" else ""
            st.markdown(
                f'<div class="hd-small{rtl}" style="opacity:.85">{_html.escape(T[lang]["about_body"])}</div>'
                + (f'<div class="hd-small{rtl}" style="margin-top:.5rem">'
                   f'{_html.escape(T[lang]["corpus_line"].format(docs=docs, bodies=bodies))}</div>'
                   if docs else "")
                + f'<div class="hd-small{rtl}" style="margin-top:.5rem">{_html.escape(T[lang]["theme_hint"])}</div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            f'<div class="hd-foot">'
            f'<div class="hd-small">{T[lang]["developed_by"]}</div>'
            f'<div style="font-weight:700">Mohammed R. S. Sunoqrot</div>'
            f'<a class="hd-li" href="https://www.linkedin.com/in/mohammed-r-s-sunoqrot" '
            f'target="_blank" rel="noopener noreferrer">in&nbsp; LinkedIn</a>'
            f'<div class="hd-small" style="margin-top:.6rem">Healdar v{config.APP_VERSION} · '
            f'{T[lang]["released"]} {release_date_label(lang)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    return st.session_state.lang, compare


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
_SCROLL_JS = (
    "<script>setTimeout(function(){var d=window.parent.document;"
    "var q=d.querySelectorAll('.hd-q');if(q.length){q[q.length-1]"
    ".scrollIntoView({behavior:'smooth',block:'start'});}},350);</script>"
)


def question_form(lang: str, placeholder: str) -> None:
    """The question box. Submitting queues the question; the page then runs it."""
    _, mid, _ = st.columns([1, 8, 1])
    with mid, st.form("question_form", clear_on_submit=False, border=False):
        c_in, c_btn = st.columns([6, 1], vertical_alignment="bottom")
        with c_in:
            st.text_input("question", placeholder=placeholder,
                          key="q_input", label_visibility="collapsed")
        with c_btn:
            st.form_submit_button(f"🔍 {T[lang]['ask']}", type="primary",
                                  width="stretch", on_click=_on_submit)


def render_starters(lang: str) -> None:
    rtl = " hd-rtl" if lang == "ar" else ""
    _, mid, _ = st.columns([1, 8, 1])
    with mid:
        st.markdown(f'<div class="sidebar-label{rtl}" style="margin-top:1.2rem">'
                    f'{T[lang]["starter_prompt"]}</div>', unsafe_allow_html=True)
        cols = st.columns(2)
        for i, s in enumerate(STARTERS[lang]):
            with cols[i % 2]:
                st.button(s, key=f"starter_{lang}_{i}", width="stretch",
                          on_click=_ask_starter, args=(s,))


def _take_pending(lang: str) -> str | None:
    """The queued question, if any -- unless this session is over its limit."""
    q = st.session_state.pending_q
    st.session_state.pending_q = None
    if q and throttle_exceeded():
        st.warning(T[lang]["throttled"])
        return None
    return q


# ── Single jurisdiction: a conversation ──────────────────────────────────
def _run_single(rag: HealdarRAG, q: str, lang: str) -> bool:
    """Ask one question as the next turn of the conversation."""
    record_query()
    jx = st.session_state.last_jx
    try:
        with st.spinner(T[lang]["loading"]):
            t0 = _time.perf_counter()
            result = rag.ask(q, jurisdiction=jx,
                             history=build_history_context(st.session_state.thread))
            secs = _time.perf_counter() - t0
    except HealdarError as exc:
        show_error(exc, lang)
        return False
    _analytics.log_query(q, lang, "single", jurisdiction=jx,
                         response_ms=int(secs * 1000), no_context=result.no_context)
    log_session_query(lang, "single", [jx], secs, not result.no_context, result.coverage)
    entry = {"question": q, "mode": "single", "lang": lang, "jurisdiction": jx, "result": result}
    st.session_state.thread.append(entry)
    st.session_state.chat_history.append(entry)
    save_session(st.session_state.chat_history)
    return True


def render_thread(rag: HealdarRAG, lang: str) -> None:
    """
    Every turn stays on the page, the box sits under the latest answer, and a
    follow-up carries the conversation with it. (Each answer used to replace
    the last, so nobody could tell that follow-ups were possible.)
    """
    thread = st.session_state.thread
    rtl = " hd-rtl" if lang == "ar" else ""
    if not thread:
        question_form(lang, T[lang]["q_placeholder"])

    _, mid, _ = st.columns([1, 8, 1])
    with mid:
        for i, entry in enumerate(thread):
            e_lang = entry.get("lang", lang)
            render_question_bubble(entry["question"], e_lang, understood_as(entry["result"]))
            render_answer(entry["result"], entry["jurisdiction"], e_lang, card_id=f"t{i}")

        pending = _take_pending(lang)
        if pending:
            render_question_bubble(pending, lang)
            if _run_single(rag, pending, lang):
                st.session_state.scroll_latest = True
                st.rerun()

        last = thread[-1]["result"] if thread else None
        followups = getattr(last, "followups", None) or []
        if followups and not last.no_context:
            st.markdown(f'<div class="sidebar-label{rtl}" style="margin-top:.9rem">'
                        f'{T[lang]["suggested"]}</div>', unsafe_allow_html=True)
            with st.container(key="hd_followups"):
                for j, fu in enumerate(followups):
                    st.button(f"↳ {fu}", key=f"fu_{len(thread)}_{j}", width="stretch",
                              on_click=_ask_starter, args=(fu,))

    if not thread:
        render_starters(lang)
        return

    question_form(lang, T[lang]["followup_placeholder"])
    _, mid, _ = st.columns([1, 8, 1])
    with mid:
        st.button(T[lang]["new_conversation"], type="tertiary", on_click=_new_conversation)
    if st.session_state.scroll_latest:
        st.session_state.scroll_latest = False
        _components.html(_SCROLL_JS, height=0)


# ── Comparison: one question, two jurisdictions ─────────────────────────
def _last_compare_entry() -> dict | None:
    return next((e for e in reversed(st.session_state.chat_history)
                 if e.get("mode") == "compare"), None)


def _run_compare(rag: HealdarRAG, q: str, lang: str) -> bool:
    record_query()
    jx_l, jx_r = st.session_state.last_jx_l, st.session_state.last_jx_r
    try:
        with st.spinner(T[lang]["loading"]):
            t0 = _time.perf_counter()
            # Both sides run concurrently — sequentially this was up to eight
            # Groq calls behind one spinner in Arabic.
            res_l, res_r = rag.ask_many([(q, jx_l), (q, jx_r)])
            secs = _time.perf_counter() - t0
    except HealdarError as exc:
        show_error(exc, lang)
        return False
    _analytics.log_query(q, lang, "compare", jx_left=jx_l, jx_right=jx_r,
                         response_ms=int(secs * 1000),
                         no_context=res_l.no_context and res_r.no_context)
    log_session_query(lang, "compare", [jx_l, jx_r], secs,
                      not (res_l.no_context and res_r.no_context),
                      "partial" if "partial" in (res_l.coverage, res_r.coverage) else "full")
    st.session_state.chat_history.append(
        {"question": q, "mode": "compare", "lang": lang,
         "jx_l": jx_l, "jx_r": jx_r, "result_l": res_l, "result_r": res_r})
    save_session(st.session_state.chat_history)
    return True


def _requery_compare(rag: HealdarRAG, lang: str) -> None:
    """Re-ask the last comparison for whichever side's jurisdiction changed."""
    last = _last_compare_entry()
    if last is None or throttle_exceeded():
        return
    jx_l, jx_r = st.session_state.last_jx_l, st.session_state.last_jx_r
    changed = [(side, jx) for side, jx in (("l", jx_l), ("r", jx_r)) if jx != last[f"jx_{side}"]]
    if not changed:
        return
    record_query()
    try:
        with st.spinner(T[lang]["loading"]):
            t0 = _time.perf_counter()
            answers = rag.ask_many([(last["question"], jx) for _, jx in changed])
            secs = _time.perf_counter() - t0
    except HealdarError as exc:
        show_error(exc, lang)
        return
    log_session_query(lang, "compare", [jx_l, jx_r], secs, True, "full")
    for (side, jx), answer in zip(changed, answers, strict=True):
        last[f"result_{side}"], last[f"jx_{side}"] = answer, jx


def render_compare_entry(entry: dict, lang: str) -> None:
    e_lang = entry.get("lang", lang)
    render_question_bubble(entry["question"], e_lang)
    col_l, col_r = st.columns(2, gap="large")
    with col_l:
        render_answer(entry["result_l"], entry["jx_l"], e_lang, card_id="left")
    with col_r:
        render_answer(entry["result_r"], entry["jx_r"], e_lang, card_id="right")


def render_compare(rag: HealdarRAG, lang: str) -> None:
    question_form(lang, T[lang]["q_placeholder"])
    pending = _take_pending(lang)
    if pending:
        if _run_compare(rag, pending, lang):
            st.rerun()
    else:
        _requery_compare(rag, lang)
    last = _last_compare_entry()
    if last is None:
        render_starters(lang)
    else:
        render_compare_entry(last, lang)


def render_history_entry(entry: dict, lang: str) -> None:
    """A past question opened from the sidebar, with a way back."""
    _, mid, _ = st.columns([1, 8, 1])
    with mid:
        st.button(T[lang]["back_to_thread"], type="tertiary", on_click=_back_to_thread)
    e_lang = entry.get("lang", lang)
    if entry.get("mode") != "single":
        render_compare_entry(entry, lang)
        return
    _, mid, _ = st.columns([1, 8, 1])
    with mid:
        render_question_bubble(entry["question"], e_lang, understood_as(entry["result"]))
        render_answer(entry["result"], entry["jurisdiction"], e_lang, card_id="hist")


def main() -> None:
    st.set_page_config(
        page_title="Healdar — Health AI Regulatory Navigator",
        page_icon="📡",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    init_state()
    inject_css()
    _analytics.init_db()

    lang, compare = render_sidebar(st.session_state.lang)

    # ── Header ───────────────────────────────────────────────────────────
    docs, bodies = corpus_stats()
    corpus = (f'<div class="hd-corpus">{_html.escape(T[lang]["corpus_line"].format(docs=docs, bodies=bodies))}'
              f' · v{config.APP_VERSION}</div>' if docs else "")
    st.markdown(
        f'<div class="hd-header"><div class="hd-logo">📡🩺</div>'
        f'<div class="hd-title">Healdar</div>'
        f'<div class="hd-tagline">{T[lang]["tagline"]}</div>{corpus}</div>',
        unsafe_allow_html=True,
    )

    # A missing API key, a retired model or a corrupt index used to surface as
    # a raw Python traceback. Show a readable card instead.
    try:
        with st.spinner(T[lang]["loading_index"]):
            rag = load_rag(_RAG_VERSION)
    except Exception as exc:
        render_unavailable(exc, lang)
        return

    hist = st.session_state.chat_history
    sel = st.session_state.selected_hist_idx
    if sel is not None and 0 <= sel < len(hist):
        render_history_entry(hist[sel], lang)
    elif compare:
        render_compare(rag, lang)
    else:
        render_thread(rag, lang)


if __name__ == "__main__":
    main()
