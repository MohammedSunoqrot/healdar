"""
Healdar — Health AI Regulatory Navigator
Streamlit frontend
"""

import dataclasses
import html as _html
import json
import logging
import re
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as _components

logger = logging.getLogger("healdar.app")

# ---------------------------------------------------------------------------
# Path setup — app.py lives in code/, so rag_pipeline is in the same directory
# ---------------------------------------------------------------------------
import importlib

SCRIPT_DIR   = Path(__file__).resolve().parent   # src/
PROJECT_ROOT = SCRIPT_DIR.parent                  # Healdar/
sys.path.insert(0, str(SCRIPT_DIR))

import config

# Hot-reload rag_pipeline on each rerun so prompt edits land without restarting
# the server. Development only: in production this rebuilds the RAGAnswer class
# on every run, which breaks isinstance checks and wastes work.
if config.DEV_MODE and "rag_pipeline" in sys.modules:
    importlib.reload(sys.modules["rag_pipeline"])

import time as _time

import analytics as _analytics
import export as _export
from rag_pipeline import (
    HealdarError,
    HealdarRAG,
    ModelUnavailableError,
    RAGAnswer,
    RateLimitError,
    RetrievalError,
    ServiceUnavailableError,
)

# ---------------------------------------------------------------------------
# Jurisdiction metadata — keys match rag_pipeline.py JURISDICTION_MAP
# ---------------------------------------------------------------------------
JURISDICTIONS = {
    "all":   {"flag": "🌍", "en": "All Jurisdictions",     "ar": "جميع الجهات",                        "color": "#555B6E"},
    "sfda":  {"flag": "🇸🇦", "en": "Saudi Arabia (SFDA)",  "ar": "المملكة العربية السعودية (SFDA)",     "color": "#00843D"},
    "uae":   {"flag": "🇦🇪", "en": "UAE (DoH)",            "ar": "الإمارات العربية المتحدة (DoH)",      "color": "#CC0001"},
    "qatar": {"flag": "🇶🇦", "en": "Qatar (MOPH)",         "ar": "قطر (وزارة الصحة العامة)",           "color": "#8D1B3D"},
    "eu":    {"flag": "🇪🇺", "en": "European Union (MDR)", "ar": "الاتحاد الأوروبي (MDR)",             "color": "#003399"},
    "fda":   {"flag": "🇺🇸", "en": "United States (FDA)",  "ar": "الولايات المتحدة الأمريكية (FDA)",   "color": "#1A1A6E"},
    "intl":  {"flag": "🌐", "en": "International (WHO)",   "ar": "دولي (منظمة الصحة العالمية)",        "color": "#0072CE"},
}

# ---------------------------------------------------------------------------
# UI string translations (English / Arabic)
# ---------------------------------------------------------------------------
T = {
    "en": {
        "tagline":        "Health AI Regulatory Intelligence",
        "q_placeholder":  "e.g. What are the post-market surveillance requirements for AI medical devices?",
        "submit":         "🔍  Ask Healdar",
        "clear":          "✕  Clear",
        "sources_label":  "📄  Sources",
        "disclaimer":     "For informational purposes only. Always consult official regulatory bodies.",
        "compare_toggle": "⚖️  Enable Comparison Mode",
        "jx_label":       "Jurisdiction",
        "compare_left":   "First Jurisdiction",
        "compare_right":  "Second Jurisdiction",
        "about_title":    "About Healdar",
        "about_body":     (
            "Healdar is an AI-powered regulatory intelligence tool that helps you navigate "
            "health AI regulations across the Gulf region, Europe, and the United States. "
            "Answers are grounded in official regulatory documents."
        ),
        "loading":        "Searching regulatory documents…",
        "lang_label":     "🌐 Language",
        "no_context":     "No relevant content found in the selected jurisdiction's documents for this query.",
        "copy":           "📋 Copy",
        "copied":         "✓ Copied",
        "page":           "p.",
        "light_mode":     "☀️ Light Mode",
        "dark_mode":      "🌙 Dark Mode",
        "clear_history":  "🗑 Clear history",
        "history_label":  "Recent questions",
        "export_pdf":       "📄 PDF",
        "export_word":      "📝 Word",
        "analytics_title":  "📊 Analytics",
        "analytics_today":  "today",
        "analytics_dl":     "⬇ Download CSV",
        "rate_limit":       "⏳ API rate limit reached — please wait a moment and try again.",
        "starter_prompt":   "Try asking:",
        "weak_match":       "Only loosely related material was found — verify against the source documents before relying on this.",
        "partial_answer":   "The retrieved documents only partly cover this question. Treat the answer as incomplete.",
        "relevance":        "match",
        "err_title":        "Healdar is temporarily unavailable",
        "err_model":        "The configured language model was rejected by the provider. It has most likely been retired — set GROQ_MODEL_ANSWER to a current model.",
        "err_service":      "The language model service is unreachable right now. Please try again shortly.",
        "err_retrieval":    "The regulatory index could not be searched. This is a system fault, not an absence of regulation.",
        "err_generic":      "Something went wrong handling that request.",
        "throttled":        "You have reached this session's query limit. Please wait a little before asking again.",
    },
    "ar": {
        "tagline":        "الذكاء التنظيمي للصحة الرقمية",
        "q_placeholder":  "مثال: ما هي متطلبات مراقبة ما بعد التسويق لأجهزة الذكاء الاصطناعي الطبية؟",
        "submit":         "🔍  اسأل هيلدار",
        "clear":          "✕  مسح",
        "sources_label":  "📄  المصادر",
        "disclaimer":     "لأغراض إعلامية فقط. استشر دائماً الهيئات التنظيمية الرسمية.",
        "compare_toggle": "⚖️  وضع المقارنة",
        "jx_label":       "الجهة التنظيمية",
        "compare_left":   "الجهة الأولى",
        "compare_right":  "الجهة الثانية",
        "about_title":    "حول هيلدار",
        "about_body":     (
            "هيلدار أداة ذكاء اصطناعي متخصصة في اللوائح التنظيمية للصحة الرقمية "
            "في منطقة الخليج وأوروبا والولايات المتحدة. تستند الإجابات إلى وثائق تنظيمية رسمية معتمدة."
        ),
        "loading":        "جارٍ البحث في الوثائق التنظيمية…",
        "lang_label":     "🌐 اللغة",
        "no_context":     "لم يُعثر على محتوى ذي صلة في وثائق الجهة التنظيمية المختارة.",
        "copy":           "📋 نسخ",
        "copied":         "✓ تم النسخ",
        "page":           "ص.",
        "light_mode":     "☀️ الوضع الفاتح",
        "dark_mode":      "🌙 الوضع الداكن",
        "clear_history":  "🗑 مسح المحادثة",
        "history_label":  "الأسئلة الأخيرة",
        "export_pdf":       "📄 PDF",
        "export_word":      "📝 Word",
        "analytics_title":  "📊 الإحصائيات",
        "analytics_today":  "اليوم",
        "analytics_dl":     "⬇ تنزيل CSV",
        "rate_limit":       "⏳ تم الوصول إلى حد الطلبات — يرجى الانتظار لحظة ثم المحاولة مجدداً.",
        "starter_prompt":   "جرّب أن تسأل:",
        "weak_match":       "لم يُعثر إلا على محتوى ضعيف الصلة — يُرجى التحقق من الوثائق الرسمية قبل الاعتماد على هذه الإجابة.",
        "partial_answer":   "الوثائق المسترجَعة تغطي هذا السؤال جزئياً فقط. اعتبر الإجابة غير مكتملة.",
        "relevance":        "تطابق",
        "err_title":        "هيلدار غير متاح مؤقتاً",
        "err_model":        "رفض المزوّد النموذج اللغوي المُهيأ، وعلى الأرجح تم إيقافه — يُرجى ضبط GROQ_MODEL_ANSWER على نموذج حالي.",
        "err_service":      "خدمة النموذج اللغوي غير متاحة حالياً. يُرجى المحاولة بعد قليل.",
        "err_retrieval":    "تعذّر البحث في فهرس الوثائق التنظيمية. هذا خلل تقني وليس غياباً للتشريع.",
        "err_generic":      "حدث خطأ أثناء معالجة الطلب.",
        "throttled":        "لقد بلغت حد عدد الأسئلة لهذه الجلسة. يُرجى الانتظار قليلاً.",
    },
}

# ---------------------------------------------------------------------------
# CSS — theme palettes and structural rules
# ---------------------------------------------------------------------------

# All colors are CSS custom properties so only :root changes per theme.
_THEME_VARS = {
    "dark": (
        "--bg-main:#0e1117;--bg-sidebar:#161b27;--bg-card:#161b27;"
        "--bg-hover:#1e2438;--border:#2a2f45;"
        "--text-primary:#dde2ef;--text-secondary:#7a8499;--text-muted:#454e63;"
        "--text-src:#8a93a8;--text-num:#5a6480;--text-disc:#525a6e;"
        "--title-color:#f0f2f6;--tagline-color:#7a8499;"
        "--modal-bg:#1a1f30;--modal-border:#3a4060;"
        "--modal-jx:#6b7a99;--modal-body:#c0c8dc;--modal-close-hover:#2a2f45;"
        "--copy-border:#2a2f45;--copy-color:#7a8499;"
        "--copy-hover-border:#4a5568;--copy-hover-color:#a0aec0;"
    ),
    "light": (
        "--bg-main:#f2f5fc;--bg-sidebar:#e8ecf6;--bg-card:#ffffff;"
        "--bg-hover:#edf1fb;--border:#cdd4ea;"
        "--text-primary:#1c2340;--text-secondary:#4f6080;--text-muted:#8898b8;"
        "--text-src:#4f6080;--text-num:#6878a0;--text-disc:#7888a8;"
        "--title-color:#1c2340;--tagline-color:#4f6080;"
        "--modal-bg:#ffffff;--modal-border:#cdd4ea;"
        "--modal-jx:#5868a0;--modal-body:#2c3860;--modal-close-hover:#edf1fb;"
        "--copy-border:#cdd4ea;--copy-color:#5868a0;"
        "--copy-hover-border:#9aaad0;--copy-hover-color:#1c2340;"
    ),
}

_LIGHT_WIDGET_OVERRIDES = """
    body, .stApp { background-color: var(--bg-main) !important; }

    /* ── Inputs ── */
    [data-testid="stTextInput"] input {
        background: #fff !important; color: var(--text-primary) !important;
        border-color: var(--border) !important;
    }

    /* ── Selectbox ── */
    [data-testid="stSelectbox"] > div > div {
        background: #fff !important; color: var(--text-primary) !important;
        border-color: var(--border) !important;
    }
    div[data-baseweb="select"] * { color: var(--text-primary) !important; }
    [data-baseweb="popover"] * { background: #fff !important; color: var(--text-primary) !important; }

    /* ── All sidebar text ── */
    [data-testid="stSidebar"] * { color: var(--text-primary) !important; }

    /* ── Radio / toggle / checkbox labels ── */
    label, .stRadio label, .stCheckbox label,
    [data-testid="stToggle"] label,
    [data-testid="stWidgetLabel"] { color: var(--text-primary) !important; }

    /* ── Expander ── */
    .streamlit-expanderHeader,
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] summary p { color: var(--text-primary) !important; }
    [data-testid="stExpander"] { border-color: var(--border) !important; }

    /* ── Markdown / paragraph text ── */
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] div { color: var(--text-primary) !important; }

    /* ── Horizontal rules ── */
    hr { border-color: var(--border) !important; }
"""

def inject_css(theme: str = "dark") -> None:
    vars_css   = _THEME_VARS.get(theme, _THEME_VARS["dark"])
    extra      = _LIGHT_WIDGET_OVERRIDES if theme == "light" else ""

    st.markdown(
        f"""
        <style>
        :root {{ {vars_css} }}
        /* ── Base ── */
        [data-testid="stAppViewContainer"] {{ background-color: var(--bg-main); }}
        [data-testid="stSidebar"]          {{ background-color: var(--bg-sidebar); border-right: 1px solid var(--border); }}
        [data-testid="stSidebar"] > div:first-child {{ padding-bottom: 6rem; }}
        [data-testid="stSidebar"] hr       {{ border-color: var(--border); }}

        /* ── Header ── */
        .rr-header  {{ text-align: center; padding: 2rem 0 1.2rem; }}
        .rr-emoji   {{ font-size: 3rem; line-height: 1.1; }}
        .rr-title   {{ font-size: 2.8rem; font-weight: 800; color: var(--title-color); letter-spacing: -0.5px; margin: 0.1rem 0; }}
        .rr-tagline {{ color: var(--tagline-color); font-size: 1rem; letter-spacing: 0.4px; }}
        .rr-divider {{ border: none; border-top: 1px solid var(--border); margin: 1.2rem 0 1.8rem; }}

        /* ── Answer card ── */
        .answer-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.4rem 1.8rem 1rem;
            margin-top: 0.6rem;
            color: var(--text-primary);
            font-size: 0.96rem;
            line-height: 1.8;
        }}
        /* Sidebar history list */
        div[data-testid="stSidebar"] .hist-item button {{
            background: transparent !important;
            border: none !important;
            border-radius: 6px !important;
            color: var(--text-secondary) !important;
            font-size: 0.8rem !important;
            text-align: left !important;
            padding: 0.35rem 0.6rem !important;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            width: 100%;
            cursor: pointer;
            transition: background 0.15s;
        }}
        div[data-testid="stSidebar"] .hist-item button:hover {{
            background: var(--bg-hover, rgba(255,255,255,0.07)) !important;
            color: var(--text-primary) !important;
        }}
        div[data-testid="stSidebar"] .hist-item-active button {{
            background: var(--bg-hover, rgba(255,255,255,0.1)) !important;
            color: var(--text-primary) !important;
            font-weight: 600 !important;
        }}
        /* Question bubble shown above each answer card */
        .chat-q-bubble {{
            display: inline-block;
            max-width: 75%;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 18px 18px 18px 4px;
            padding: 0.55rem 1rem;
            margin: 1.4rem 0 0.5rem;
            font-size: 0.92rem;
            color: var(--text-secondary);
            font-style: italic;
        }}
        .chat-q-bubble.rtl {{
            border-radius: 18px 18px 4px 18px;
            margin-left: auto;
            display: block;
            text-align: right;
        }}
        /* Subtle divider between history entries */
        .chat-entry-sep {{
            border: none;
            border-top: 1px dashed var(--border);
            margin: 1.2rem 0 0;
            opacity: 0.5;
        }}
        .answer-card p  {{ margin: 0 0 0.7rem; }}
        .answer-card br {{ display: block; margin-bottom: 0.4rem; }}
        .answer-card ul, .answer-card ol {{
            margin: 0 0 0.8rem 0;
            padding-left: 1.4rem;
        }}
        .answer-card li {{ margin-bottom: 0.3rem; line-height: 1.7; }}
        /* RTL lists (Arabic) */
        .rtl ul, .rtl ol {{ padding-left: 0; padding-right: 1.4rem; }}
        /* RTL refs section */
        .refs-section.rtl {{ direction: rtl; text-align: right; }}
        .refs-section.rtl .ref-row {{ flex-direction: row-reverse; }}
        .refs-section.rtl .ref-excerpt {{ margin: 0.05rem 2.3rem 0.4rem 0; }}

        /* ── Card header ── */
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }}

        /* ── Jurisdiction badge ── */
        .jx-badge {{ display: inline-block; padding: 4px 14px; border-radius: 20px; font-size: 0.78rem; font-weight: 700; color: #fff; letter-spacing: 0.2px; }}

        /* ── Footnote superscript in answer text ── */
        .fn-ref {{
            color: #3b5bdb;
            font-size: 0.72em;
            font-weight: 700;
            vertical-align: super;
            cursor: default;
            letter-spacing: 0;
        }}

        /* ── References section ── */
        .refs-section {{
            border-top: 1px solid var(--border);
            margin-top: 1.1rem;
            padding-top: 0.6rem;
        }}
        .refs-title {{
            font-size: 0.67rem;
            font-weight: 700;
            letter-spacing: 1px;
            text-transform: uppercase;
            color: var(--text-muted);
            margin-bottom: 0.3rem;
        }}
        /* One reference row: [N] · dot · label · toggle arrow */
        .ref-row {{
            display: flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.26rem 0.4rem;
            border-radius: 5px;
            cursor: pointer;
            user-select: none;
            transition: background 0.1s;
        }}
        .ref-row:hover {{ background: var(--bg-hover); }}
        .ref-num {{
            font-size: 0.74rem;
            font-weight: 700;
            color: #3b5bdb;
            min-width: 24px;
            flex-shrink: 0;
        }}
        /* Small colored circle = jurisdiction at a glance */
        .ref-dot {{
            width: 7px;
            height: 7px;
            border-radius: 50%;
            flex-shrink: 0;
        }}
        .ref-label {{
            font-size: 0.8rem;
            color: var(--text-src);
            flex: 1;
            line-height: 1.35;
        }}
        .ref-toggle {{
            font-size: 0.7rem;
            color: var(--text-muted);
            flex-shrink: 0;
            width: 14px;
            text-align: center;
        }}
        /* Excerpt expands inline below its row — no modal, no disruption */
        .ref-excerpt {{
            display: none;
            background: var(--bg-hover);
            border-left: 3px solid #555;
            border-radius: 0 4px 4px 4px;
            padding: 0.6rem 0.85rem;
            margin: 0.05rem 0 0.4rem 2.3rem;
            font-size: 0.79rem;
            color: var(--text-secondary);
            line-height: 1.65;
            font-style: italic;
            white-space: pre-wrap;
        }}
        .ref-excerpt.open {{ display: block; }}

        /* ── Disclaimer ── */
        .disclaimer {{ color: var(--text-disc); font-size: 0.76rem; margin-top: 0.9rem; padding-top: 0.7rem; border-top: 1px solid var(--border); text-align: center; }}

        /* ── Caution banner (weak match / partial coverage) ── */
        .notice {{
            display: flex;
            align-items: flex-start;
            gap: 0.5rem;
            background: rgba(214, 158, 46, 0.10);
            border: 1px solid rgba(214, 158, 46, 0.45);
            border-radius: 8px;
            padding: 0.55rem 0.8rem;
            margin: 0 0 0.9rem;
            font-size: 0.8rem;
            line-height: 1.5;
            color: var(--text-primary);
        }}
        .notice.rtl {{ direction: rtl; text-align: right; }}
        .notice-icon {{ flex-shrink: 0; }}

        /* ── Relevance score on a reference row ── */
        .ref-score {{
            font-size: 0.68rem;
            color: var(--text-num);
            flex-shrink: 0;
            font-variant-numeric: tabular-nums;
        }}

        /* ── No-context notice ── */
        .no-context {{ color: var(--text-secondary); font-style: italic; text-align: center; padding: 1.5rem 0; }}

        /* ── Sidebar micro-labels ── */
        .sidebar-label {{ font-size: 0.7rem; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; color: var(--text-muted); margin: 1rem 0 0.3rem; }}

        /* ── RTL helper ── */
        .rtl {{ direction: rtl; text-align: right; }}

        /* ── Hide form submit button — Enter key still works ── */
        [data-testid="stFormSubmitButton"] {{ display: none !important; }}

        {extra}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Cached RAG pipeline — loads the model once, reused across reruns.
# Bump _RAG_VERSION after changing rag_pipeline.py to force re-creation.
# ---------------------------------------------------------------------------
_RAG_VERSION = "7"   # bump to invalidate st.cache_resource after pipeline changes

@st.cache_resource(show_spinner=False)
def load_rag(v: str = _RAG_VERSION) -> HealdarRAG:
    return HealdarRAG()


# ---------------------------------------------------------------------------
# Map raw ChromaDB jurisdiction values → JURISDICTIONS keys (for color lookup)
# ---------------------------------------------------------------------------
JX_COLOR_MAP: dict[str, str] = {
    "EU_MDR_MDCG":      "eu",
    "SFDA":             "sfda",
    "KSA_SDAIA":        "sfda",
    "KSA_NHIC":         "sfda",
    "Qatar_MCIT":       "qatar",
    "Qatar_MOPH":       "qatar",
    "Qatar_NCSA":       "qatar",
    "Qatar_National":   "qatar",
    "UAE_DHA_Dubai":    "uae",
    "UAE_DoH_AbuDhabi": "uae",
    "UAE_National":     "uae",
    "USA_FDA":          "fda",
    "International":    "intl",
}

def jx_color(jurisdiction: str) -> str:
    return JURISDICTIONS.get(JX_COLOR_MAP.get(jurisdiction, "all"), JURISDICTIONS["all"])["color"]


# ---------------------------------------------------------------------------
# Helper: prettify a raw filename for display
#   "SFDA_MDS-G010_AI-ML_Medical_Devices_Guidance_2023.pdf"
#   → "SFDA MDS-G010 AI-ML Medical Devices Guidance 2023"
# ---------------------------------------------------------------------------
def prettify_filename(filename: str) -> str:
    return Path(filename).stem.replace("_", " ")


# ---------------------------------------------------------------------------
# Helper: numbered source-pill strip with click-to-preview modals
#
#   • Each pill is numbered [1][2]… to match [Source N] refs in the answer
#   • Clicking a pill opens a small modal showing the retrieved text excerpt
#   • First 3 pills are always visible; "+N more" reveals ALL remaining ones
#   • card_id makes modal element IDs unique across comparison-mode cards
# ---------------------------------------------------------------------------
MAX_VISIBLE_SOURCES = 3

def source_strip_html(indexed_sources: list[tuple[int, dict]], lang: str, card_id: str) -> str:
    """
    Render a compact numbered reference list that matches [N] superscripts in the answer.

    Design:
      [1] ● SFDA MDS-G010 AI-ML Medical Devices Guidance 2023 · p.4  ▾
          "Post-market continuous monitoring of safety, effectiveness..."   ← expands inline

    • No modal — excerpt expands below the row in place
    • Colored dot = instant jurisdiction identification
    • Hover on the row toggles the excerpt; ▾/▴ shows state
    • Works in both dark and light mode via CSS variables
    """
    if not indexed_sources:
        return ""

    page_lbl   = T[lang]["page"]
    title_text = "المصادر" if lang == "ar" else "References"
    rtl_class  = " rtl" if lang == "ar" else ""
    parts      = []          # alternating: row-div, excerpt-div

    for idx, s in indexed_sources:
        color    = jx_color(s["jurisdiction"])
        doc_name = _html.escape(prettify_filename(s["filename"]))
        exc_id   = f"rref-{card_id}-{idx}"

        # Toggle logic: find the excerpt div by data-exc attribute on the row,
        # then toggle its 'open' class and flip the arrow — no external function needed.
        toggle_js = (
            "var e=document.getElementById(this.dataset.exc);"
            "var op=e.classList.toggle('open');"
            "this.querySelector('.ref-toggle').textContent=op?'▴':'▾';"
        )

        # Show how well this passage actually matched, so a reader can weigh a
        # borderline citation instead of assuming every reference is equally solid.
        rel = s.get("relevance")
        score_html = (
            f'<span class="ref-score">{round(float(rel) * 100)}%</span>'
            if isinstance(rel, (int, float)) else ""
        )

        parts.append(
            f'<div class="ref-row" data-exc="{exc_id}" onclick="{toggle_js}">'
            f'  <span class="ref-num">[{idx}]</span>'
            f'  <span class="ref-dot" style="background:{color}"></span>'
            f'  <span class="ref-label">{doc_name}&nbsp;·&nbsp;{page_lbl}{s["page_number"]}</span>'
            f'  {score_html}'
            f'  <span class="ref-toggle">▾</span>'
            f'</div>'
        )

        excerpt = _html.escape((s.get("text") or "").strip())
        parts.append(
            f'<div class="ref-excerpt" id="{exc_id}" '
            f'style="border-left-color:{color}">{excerpt}</div>'
        )

    return (
        f'<div class="refs-section{rtl_class}">'
        f'  <div class="refs-title">{title_text}</div>'
        f'  {"".join(parts)}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Helper: colored jurisdiction badge HTML
# ---------------------------------------------------------------------------
def badge_html(jx_key: str, lang: str) -> str:
    j = JURISDICTIONS[jx_key]
    name = j["en"] if lang == "en" else j["ar"]
    return (
        f'<span class="jx-badge" style="background:{j["color"]}">'
        f'{j["flag"]} {name}</span>'
    )


# ---------------------------------------------------------------------------
# Helper: jurisdiction display label for selectbox options
# ---------------------------------------------------------------------------
def jx_display(jx_key: str, lang: str) -> str:
    j = JURISDICTIONS[jx_key]
    name = j["en"] if lang == "en" else j["ar"]
    return f'{j["flag"]} {name}'


# ---------------------------------------------------------------------------
# Helper: answer text → safe HTML
#   • Escapes HTML chars
#   • Converts [Source N] → <sup class="fn-ref" title="…">[N]</sup>
#     so citations read naturally as footnote superscripts
#   • ref_tooltips: optional {source_num: "Doc Name · p.X"} for hover text
# ---------------------------------------------------------------------------
def text_to_html(text: str, ref_tooltips: dict | None = None) -> str:
    safe = _html.escape(text)

    def _ref_tag(m: re.Match) -> str:
        n       = int(m.group(1))
        tooltip = (ref_tooltips or {}).get(n, "")
        title   = f' title="{_html.escape(tooltip)}"' if tooltip else ""
        return f'<sup class="fn-ref"{title}>[{n}]</sup>'

    # Matches clean "[Source 1]" and legacy "[Source 1: file.pdf | p.4]" alike.
    safe = config.CITATION_RE.sub(_ref_tag, safe)

    # Process line-by-line so mixed blocks (intro sentence + bullets) work correctly.
    # Consecutive bullet lines → <ul>, numbered lines → <ol>, other lines → <p>.
    # A transition between types (or an empty line) flushes the current buffer.
    _BULLET   = re.compile(r'^[*\-–—•]\s+(.*)', re.DOTALL)
    _NUMBERED = re.compile(r'^\d+[.)]\s+(.*)',  re.DOTALL)

    out:    list[str] = []
    ul_buf: list[str] = []
    ol_buf: list[str] = []
    p_buf:  list[str] = []

    def _flush() -> None:
        if ul_buf:
            out.append('<ul>' + ''.join(f'<li>{i}</li>' for i in ul_buf) + '</ul>')
            ul_buf.clear()
        if ol_buf:
            out.append('<ol>' + ''.join(f'<li>{i}</li>' for i in ol_buf) + '</ol>')
            ol_buf.clear()
        if p_buf:
            out.append('<p>' + '<br>'.join(p_buf) + '</p>')
            p_buf.clear()

    for line in safe.split('\n'):
        s = line.strip()
        if not s:
            _flush()
            continue
        bm = _BULLET.match(s)
        nm = _NUMBERED.match(s)
        if bm:
            if p_buf or ol_buf:
                _flush()
            ul_buf.append(bm.group(1))
        elif nm:
            if p_buf or ul_buf:
                _flush()
            ol_buf.append(nm.group(1))
        else:
            if ul_buf or ol_buf:
                _flush()
            p_buf.append(s)

    _flush()
    return ''.join(out)


def render_question_bubble(question: str, lang: str) -> None:
    """Render the user's question as a styled bubble above the answer card."""
    rtl_class = " rtl" if lang == "ar" else ""
    safe_q = _html.escape(question)
    st.markdown(
        f'<div class="chat-q-bubble{rtl_class}">🔍 {safe_q}</div>',
        unsafe_allow_html=True,
    )


def build_history_context(chat_history: list) -> list[dict] | None:
    """
    Extract the last 3 single-mode entries as conversation context for the RAG pipeline.
    Returns None when there's no usable history.
    """
    single = [
        {"question_en": e["result"].question_en, "answer_en": e["result"].answer_en}
        for e in chat_history
        if e["mode"] == "single"
        and e["result"].question_en
        and e["result"].answer_en
    ]
    return single[-3:] if single else None


_COPY_THEME_CSS = {
    "dark":  {"border": "#2a2f45", "color": "#7a8499", "hover_border": "#4a5568", "hover_color": "#a0aec0"},
    "light": {"border": "#cdd4ea", "color": "#5868a0", "hover_border": "#9aaad0", "hover_color": "#1c2340"},
}


def _copy_component_html(text: str, label_copy: str, label_copied: str) -> str:
    c = _COPY_THEME_CSS.get(st.session_state.get("theme", "dark"), _COPY_THEME_CSS["dark"])
    # json.dumps alone is not enough inside a <script> block: a literal
    # "</script>" in the answer text would close the tag early.
    text_js = json.dumps(text).replace("</", "<\\/")
    copy_js = json.dumps(label_copy)
    done_js = json.dumps(label_copied)
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<style>'
        '* {margin:0;padding:0;box-sizing:border-box}'
        'body {background:transparent;padding:0}'
        f'button {{background:transparent;border:1px solid {c["border"]};'
        f'color:{c["color"]};border-radius:6px;padding:3px 12px;font-size:12px;'
        f'cursor:pointer;white-space:nowrap;width:100%;height:32px;'
        f'transition:border-color 0.15s,color 0.15s}}'
        f'button:hover {{border-color:{c["hover_border"]};color:{c["hover_color"]}}}'
        '</style></head>'
        '<body>'
        '<button id="cb"></button>'
        '<script>'
        f'var TEXT={text_js},COPY={copy_js},DONE={done_js};'
        'var btn=document.getElementById("cb");'
        'btn.textContent=COPY;'
        'btn.addEventListener("click",function(){'
        '  var ta=document.createElement("textarea");'
        '  ta.value=TEXT;'
        '  ta.style.cssText="position:fixed;top:0;left:0;width:1px;height:1px;opacity:0;";'
        '  document.body.appendChild(ta);ta.focus();ta.select();'
        '  try{document.execCommand("copy")}catch(e){}'
        '  document.body.removeChild(ta);'
        '  btn.textContent=DONE;'
        '  setTimeout(function(){btn.textContent=COPY;},1500);'
        '});'
        '</script>'
        '</body></html>'
    )


# ---------------------------------------------------------------------------
# Helper: render one RAGAnswer as a self-contained styled card
#   Everything (badge, answer, sources, disclaimer) is one HTML block so
#   there are no stray Streamlit wrappers breaking the layout.
# ---------------------------------------------------------------------------
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


def render_answer(result: RAGAnswer, jx_key: str, lang: str) -> None:
    rtl = 'class="rtl"' if lang == "ar" else ""

    indexed_cited = select_cited_sources(result.answer, result.sources)

    # Build hover tooltips for the superscripts: [1] → "Doc Name · p.X"
    tooltips = {
        idx: f"{prettify_filename(s['filename'])} · {T[lang]['page']}{s['page_number']}"
        for idx, s in indexed_cited
    }

    # Caution banners: say plainly when the evidence is thin, rather than
    # presenting a hedged answer with the same confidence as a solid one.
    rtl_cls = " rtl" if lang == "ar" else ""
    notices = []
    if not result.no_context:
        if getattr(result, "quality", "ok") == "weak":
            notices.append(T[lang]["weak_match"])
        if getattr(result, "coverage", "full") == "partial":
            notices.append(T[lang]["partial_answer"])
    notice_html = "".join(
        f'<div class="notice{rtl_cls}"><span class="notice-icon">⚠️</span>'
        f'<span>{_html.escape(n)}</span></div>'
        for n in notices
    )

    body_html = (
        f'<p class="no-context">{T[lang]["no_context"]}</p>'
        if result.no_context
        else f'{notice_html}<div {rtl}>{text_to_html(result.answer, tooltips)}</div>'
    )

    strip      = source_strip_html(indexed_cited, lang, card_id=jx_key)
    disclaimer = f'<div class="disclaimer">⚠️ {_html.escape(T[lang]["disclaimer"])}</div>'

    st.markdown(
        f'<div class="answer-card">'
        f'  <div class="card-header">'
        f'    {badge_html(jx_key, lang)}'
        f'  </div>'
        f'  {body_html}'
        f'  {strip}'
        f'  {disclaimer}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Copy + Export buttons ──────────────────────────────────────────────
    copy_html = _copy_component_html(result.answer, T[lang]["copy"], T[lang]["copied"])

    if not result.no_context:
        cited_sources = [s for _, s in indexed_cited]
        # PDF uses English answer; Word uses the displayed answer (handles Arabic natively)
        answer_for_pdf  = result.answer_en if result.answer_en else result.answer
        fname = f"healdar_{jx_key}_{_export._file_date()}"

        pdf_bytes  = _export.to_pdf(
            question          = result.question_en or result.question,
            answer            = answer_for_pdf,
            sources           = cited_sources,
            jurisdiction      = jx_key,
            question_original = result.question,
        )
        docx_bytes = _export.to_docx(
            question     = result.question,
            answer       = result.answer,
            sources      = cited_sources,
            jurisdiction = jx_key,
            lang         = lang,
        )

        col_copy, col_pdf, col_word, *_ = st.columns([1, 1, 1, 3])
        with col_copy:
            _components.html(copy_html, height=38)
        with col_pdf:
            st.download_button(
                T[lang]["export_pdf"], pdf_bytes,
                file_name=f"{fname}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key=f"pdf_{jx_key}_{id(result)}",
            )
        with col_word:
            st.download_button(
                T[lang]["export_word"], docx_bytes,
                file_name=f"{fname}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                key=f"word_{jx_key}_{id(result)}",
            )
    else:
        col_copy, *_ = st.columns([1, 5])
        with col_copy:
            _components.html(copy_html, height=38)


# ---------------------------------------------------------------------------
# Error presentation — map a pipeline failure onto a readable message
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
    """Full-page failure card for when the pipeline cannot start at all."""
    logger.error("Startup failed: %s: %s", type(exc).__name__, exc, exc_info=True)
    rtl_s = "direction:rtl;text-align:right;" if lang == "ar" else ""
    st.markdown(
        f'<div class="answer-card" style="{rtl_s}">'
        f'  <h3 style="margin-top:0;">⚠️ {_html.escape(T[lang]["err_title"])}</h3>'
        f'  <p>{_html.escape(error_message(exc, lang))}</p>'
        f'  <p style="font-size:0.78rem;color:var(--text-muted);">'
        f'    {_html.escape(f"{type(exc).__name__}: {exc}")}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )


def throttle_exceeded() -> bool:
    """
    Has this session used up its query allowance?

    Pure check with no side effect. Streamlit re-runs the whole script on every
    interaction — a theme toggle, a language switch, a history click — so a
    check that also *recorded* a query would drain the allowance without any
    model call ever being made. Recording is record_query()'s job, and it is
    called only where a request is actually about to be issued.

    Disabled unless HEALDAR_RATE_LIMIT_QUERIES is set.
    """
    if config.RATE_LIMIT_QUERIES <= 0:
        return False
    now = _time.time()
    recent = [
        t for t in st.session_state.get("query_times", [])
        if now - t < config.RATE_LIMIT_WINDOW
    ]
    st.session_state.query_times = recent
    return len(recent) >= config.RATE_LIMIT_QUERIES


def record_query() -> None:
    """Count one query against the session allowance."""
    if config.RATE_LIMIT_QUERIES <= 0:
        return
    st.session_state.query_times = [*st.session_state.get("query_times", []), _time.time()]


# ---------------------------------------------------------------------------
# Clear callback — resets the input and all stored results
# ---------------------------------------------------------------------------
def do_clear() -> None:
    st.session_state.q_input      = ""
    st.session_state.last_result   = None
    st.session_state.last_result_l = None
    st.session_state.last_result_r = None


# ---------------------------------------------------------------------------
# Session persistence — survives page refresh (local / Docker with volume).
# Note: Streamlit Cloud has an ephemeral filesystem, so persistence is
# limited to the lifetime of the current deployment there.
# ---------------------------------------------------------------------------
_SESSION_FILE = PROJECT_ROOT / "data" / "runtime" / "last_session.json"
_MAX_PERSISTED = 15   # keep last N entries


def _serialise_entry(entry: dict) -> dict:
    """Convert RAGAnswer dataclass instances to plain dicts for JSON."""
    e = dict(entry)
    for key in ("result", "result_l", "result_r"):
        val = e.get(key)
        # Use is_dataclass so this works even after module reload creates a new class
        if val is not None and dataclasses.is_dataclass(val) and not isinstance(val, type):
            e[key] = dataclasses.asdict(val)
    return e


def _deserialise_entry(entry: dict) -> dict:
    """Reconstruct RAGAnswer objects from plain dicts."""
    e = dict(entry)
    for key in ("result", "result_l", "result_r"):
        if key in e and isinstance(e[key], dict):
            e[key] = RAGAnswer(**e[key])
    return e


def save_session(chat_history: list) -> None:
    """
    Write the last N history entries to disk.

    Off by default. The file is process-wide, not per-visitor, so on any shared
    deployment enabling this would show one person's questions and answers to
    the next person who loads the page.
    """
    if not config.PERSIST_SESSION:
        return
    try:
        payload = [_serialise_entry(e) for e in chat_history[-_MAX_PERSISTED:]]
        _SESSION_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def load_session() -> list:
    """Read persisted history from disk. Returns empty list on any error."""
    if not config.PERSIST_SESSION:
        return []
    try:
        if not _SESSION_FILE.exists():
            return []
        raw = json.loads(_SESSION_FILE.read_text(encoding="utf-8"))
        return [_deserialise_entry(e) for e in raw]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
def init_state() -> None:
    # Restore persisted session before applying defaults so history survives refresh
    if "chat_history" not in st.session_state:
        persisted = load_session()
        if persisted:
            st.session_state["chat_history"] = persisted
            # Re-hydrate the last-result pointers so jurisdiction auto-refresh works
            last = persisted[-1]
            if last.get("mode") == "single":
                st.session_state["last_result"] = last["result"]
                st.session_state["used_jx"]     = last.get("jurisdiction")
            elif last.get("mode") == "compare":
                st.session_state["last_result_l"] = last["result_l"]
                st.session_state["last_result_r"] = last["result_r"]
                st.session_state["used_jx_l"]     = last.get("jx_l")
                st.session_state["used_jx_r"]     = last.get("jx_r")

    defaults: dict = {
        "lang":              "en",
        "theme":             "dark",
        "compare":           False,
        "q_input":           "",
        "last_jx":           "all",
        "last_result":       None,
        "last_jx_l":         "sfda",
        "last_jx_r":         "eu",
        "last_result_l":     None,
        "last_result_r":     None,
        "used_jx":           None,
        "used_jx_l":         None,
        "used_jx_r":         None,
        "chat_history":      [],
        "selected_hist_idx": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------
def main() -> None:
    # Must be first Streamlit call — kept here so the module is importable in tests
    st.set_page_config(
        page_title="Healdar 📡🩺",
        page_icon="📡",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    init_state()
    inject_css(st.session_state.theme)

    _analytics.init_db()
    lang: str = st.session_state.lang

    # A missing API key, a retired model or a corrupt index used to surface as a
    # raw Python traceback in the browser. Show a readable card instead.
    try:
        rag = load_rag(_RAG_VERSION)
    except Exception as exc:
        render_unavailable(exc, lang)
        return

    lang = st.session_state.lang
    theme: str = st.session_state.theme

    # ── Sidebar ──────────────────────────────────────────────────────────
    with st.sidebar:

        # Dark / light mode toggle
        is_light = st.toggle(
            T[lang]["light_mode"] if theme == "dark" else T[lang]["dark_mode"],
            value=(theme == "light"),
        )
        new_theme = "light" if is_light else "dark"
        if new_theme != theme:
            st.session_state.theme = new_theme
            st.rerun()

        st.markdown("---")

        # Language toggle
        st.markdown(f'<div class="sidebar-label">{T[lang]["lang_label"]}</div>', unsafe_allow_html=True)
        lang_pick = st.radio(
            "lang_radio",
            options=["English", "العربية"],
            index=0 if lang == "en" else 1,
            horizontal=True,
            label_visibility="collapsed",
        )
        chosen_lang = "en" if lang_pick == "English" else "ar"
        if chosen_lang != lang:
            st.session_state.lang = chosen_lang
            st.rerun()
        lang = st.session_state.lang

        st.markdown("---")

        # Comparison mode toggle
        compare = st.toggle(T[lang]["compare_toggle"], value=st.session_state.compare)
        st.session_state.compare = compare

        st.markdown("---")

        # Jurisdiction selector(s)
        all_keys = list(JURISDICTIONS.keys())
        all_opts = [jx_display(k, lang) for k in all_keys]

        if not compare:
            st.markdown(f'<div class="sidebar-label">{T[lang]["jx_label"]}</div>', unsafe_allow_html=True)
            cur_idx = all_keys.index(st.session_state.last_jx)
            sel_opt = st.selectbox("jx_single", all_opts, index=cur_idx, label_visibility="collapsed")
            st.session_state.last_jx = all_keys[all_opts.index(sel_opt)]

        else:
            cmp_keys = [k for k in all_keys if k != "all"]
            cmp_opts = [jx_display(k, lang) for k in cmp_keys]

            st.markdown(f'<div class="sidebar-label">{T[lang]["compare_left"]}</div>', unsafe_allow_html=True)
            l_idx = cmp_keys.index(st.session_state.last_jx_l) if st.session_state.last_jx_l in cmp_keys else 0
            sel_l = st.selectbox("jx_left", cmp_opts, index=l_idx, label_visibility="collapsed")
            st.session_state.last_jx_l = cmp_keys[cmp_opts.index(sel_l)]

            st.markdown(f'<div class="sidebar-label">{T[lang]["compare_right"]}</div>', unsafe_allow_html=True)
            r_idx = cmp_keys.index(st.session_state.last_jx_r) if st.session_state.last_jx_r in cmp_keys else 1
            sel_r = st.selectbox("jx_right", cmp_opts, index=r_idx, label_visibility="collapsed")
            st.session_state.last_jx_r = cmp_keys[cmp_opts.index(sel_r)]

        # ── Chat history ─────────────────────────────────────────────────
        if st.session_state.chat_history:
            st.markdown("---")
            st.markdown(
                f'<div class="sidebar-label">{T[lang]["history_label"]}</div>',
                unsafe_allow_html=True,
            )
            hist = st.session_state.chat_history
            sel  = st.session_state.selected_hist_idx

            # Newest first
            for i, entry in enumerate(reversed(hist)):
                actual_idx = len(hist) - 1 - i
                q = entry["question"]
                q_short = (q[:44] + "…") if len(q) > 44 else q
                is_active = (sel == actual_idx) or (sel is None and actual_idx == len(hist) - 1)
                css_class = "hist-item-active" if is_active else "hist-item"
                st.markdown(f'<div class="{css_class}">', unsafe_allow_html=True)
                if st.button(q_short, key=f"hist_btn_{actual_idx}", use_container_width=True):
                    st.session_state.selected_hist_idx = actual_idx
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

            if st.button(T[lang]["clear_history"], use_container_width=True):
                st.session_state.chat_history        = []
                st.session_state.last_result         = None
                st.session_state.last_result_l       = None
                st.session_state.last_result_r       = None
                st.session_state.used_jx             = None
                st.session_state.used_jx_l           = None
                st.session_state.used_jx_r           = None
                st.session_state.selected_hist_idx   = None
                save_session([])  # wipe persisted file
                st.rerun()

        # About
        with st.expander(T[lang]["about_title"]):
            rtl_style = "direction:rtl;text-align:right;" if lang == "ar" else ""
            st.markdown(
                f'<p style="font-size:0.85rem;color:#7a8499;{rtl_style}">'
                f'{_html.escape(T[lang]["about_body"])}</p>',
                unsafe_allow_html=True,
            )

        # ── Analytics panel ───────────────────────────────────────────────
        with st.expander(T[lang]["analytics_title"]):
            stats = _analytics.get_summary()
            if not stats.get("total"):
                st.caption("No data yet — stats appear after the first query.")
            else:
                total   = stats["total"]
                today   = stats.get("today", 0)
                avg_ms  = stats.get("avg_response_ms")
                rtl_s   = "direction:rtl;text-align:right;" if lang == "ar" else ""

                # ── Key numbers ──
                st.markdown(
                    f'<div style="display:flex;gap:1rem;flex-wrap:wrap;{rtl_s}">'
                    f'  <div style="flex:1;min-width:70px;background:var(--bg-card);'
                    f'       border:1px solid var(--border);border-radius:8px;padding:.5rem .7rem;">'
                    f'    <div style="font-size:.7rem;color:var(--text-secondary);">Queries</div>'
                    f'    <div style="font-size:1.3rem;font-weight:700;">{total}</div>'
                    f'    <div style="font-size:.68rem;color:var(--text-secondary);">'
                    f'      {today} {T[lang]["analytics_today"]}</div>'
                    f'  </div>'
                    + (
                    f'  <div style="flex:1;min-width:70px;background:var(--bg-card);'
                    f'       border:1px solid var(--border);border-radius:8px;padding:.5rem .7rem;">'
                    f'    <div style="font-size:.7rem;color:var(--text-secondary);">Avg time</div>'
                    f'    <div style="font-size:1.3rem;font-weight:700;">{avg_ms // 1000 if avg_ms and avg_ms >= 1000 else (avg_ms or "—")}{"s" if avg_ms and avg_ms >= 1000 else ("ms" if avg_ms else "")}</div>'
                    f'  </div>'
                    if avg_ms else ""
                    )
                    + f'  <div style="flex:1;min-width:70px;background:var(--bg-card);'
                    f'       border:1px solid var(--border);border-radius:8px;padding:.5rem .7rem;">'
                    f'    <div style="font-size:.7rem;color:var(--text-secondary);">Compare</div>'
                    f'    <div style="font-size:1.3rem;font-weight:700;">{stats.get("compare_pct", 0)}%</div>'
                    f'  </div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # ── Language split ──
                langs = stats.get("languages", [])
                if langs:
                    st.markdown(
                        '<div style="font-size:.72rem;color:var(--text-secondary);'
                        'margin:.6rem 0 .2rem;">Language</div>',
                        unsafe_allow_html=True,
                    )
                    for row in langs:
                        pct = round(row["n"] / total * 100)
                        label = "🇬🇧 EN" if row["language"] == "en" else "🇸🇦 AR"
                        st.markdown(
                            f'<div style="display:flex;align-items:center;gap:.4rem;'
                            f'margin-bottom:.25rem;font-size:.78rem;">'
                            f'  <span style="width:3rem;">{label}</span>'
                            f'  <div style="flex:1;background:var(--border);border-radius:4px;height:6px;">'
                            f'    <div style="width:{pct}%;background:#0a66c2;border-radius:4px;height:6px;"></div>'
                            f'  </div>'
                            f'  <span style="color:var(--text-secondary);width:2.5rem;text-align:right;">'
                            f'    {pct}%</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                # ── Top jurisdictions ──
                top_jx = stats.get("top_jurisdictions", [])
                if top_jx:
                    max_n = top_jx[0]["n"]
                    st.markdown(
                        '<div style="font-size:.72rem;color:var(--text-secondary);'
                        'margin:.6rem 0 .2rem;">Top jurisdictions</div>',
                        unsafe_allow_html=True,
                    )
                    for row in top_jx:
                        pct = round(row["n"] / max_n * 100)
                        st.markdown(
                            f'<div style="display:flex;align-items:center;gap:.4rem;'
                            f'margin-bottom:.25rem;font-size:.75rem;">'
                            f'  <span style="width:3.5rem;overflow:hidden;text-overflow:ellipsis;'
                            f'  white-space:nowrap;">{row["jurisdiction"]}</span>'
                            f'  <div style="flex:1;background:var(--border);border-radius:4px;height:6px;">'
                            f'    <div style="width:{pct}%;background:#00843d;border-radius:4px;height:6px;"></div>'
                            f'  </div>'
                            f'  <span style="color:var(--text-secondary);width:1.5rem;text-align:right;">'
                            f'    {row["n"]}</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                # ── CSV download ──
                st.download_button(
                    T[lang]["analytics_dl"],
                    data=_analytics.export_csv(),
                    file_name=f"healdar_analytics_{_export._file_date()}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        # Developer credit — pinned at the bottom of the sidebar
        st.markdown(
            """
            <div style="
                position: fixed;
                bottom: 0;
                left: 0;
                width: 18rem;
                padding: 0.75rem 1.1rem;
                background: var(--sidebar-bg, #161b22);
                border-top: 1px solid var(--border-color, #30363d);
                z-index: 100;
            ">
                <p style="margin:0 0 0.4rem;font-size:0.72rem;color:#7a8499;line-height:1.4;">
                    Developed by<br>
                    <strong style="color:var(--text-primary,#e6edf3);font-size:0.78rem;">
                        Mohammed R. S. Sunoqrot
                    </strong>
                </p>
                <a href="https://www.linkedin.com/in/mohammed-r-s-sunoqrot"
                   target="_blank" rel="noopener noreferrer"
                   style="
                       display: inline-flex;
                       align-items: center;
                       gap: 0.35rem;
                       padding: 0.28rem 0.7rem;
                       background: #0a66c2;
                       color: #fff;
                       border-radius: 4px;
                       font-size: 0.72rem;
                       font-weight: 600;
                       text-decoration: none;
                       transition: background 0.2s;
                   "
                   onmouseover="this.style.background='#004182'"
                   onmouseout="this.style.background='#0a66c2'"
                >
                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12"
                         viewBox="0 0 24 24" fill="white">
                        <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037
                                 -1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046
                                 c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286z
                                 M5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.064 2.064 0 1 1
                                 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452z
                                 M22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24
                                 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2
                                 0 22.222 0h.003z"/>
                    </svg>
                    LinkedIn
                </a>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Header ───────────────────────────────────────────────────────────
    rtl_header = "direction:rtl;" if lang == "ar" else ""
    st.markdown(
        f"""
        <div class="rr-header" style="{rtl_header}">
            <div class="rr-emoji">📡🩺</div>
            <div class="rr-title">Healdar</div>
            <div class="rr-tagline">{T[lang]["tagline"]}</div>
        </div>
        <hr class="rr-divider">
        """,
        unsafe_allow_html=True,
    )

    # ── Question input — Enter submits, buttons hidden via CSS ───────────
    with st.form("question_form", clear_on_submit=False):
        question: str = st.text_input(
            label="question",
            placeholder=T[lang]["q_placeholder"],
            key="q_input",
            label_visibility="collapsed",
        )
        # Hidden submit button — required by st.form but invisible (CSS display:none)
        submitted = st.form_submit_button(label="go")

    # Empty submission clears the last answer
    if submitted and not question.strip():
        st.session_state.last_result   = None
        st.session_state.last_result_l = None
        st.session_state.last_result_r = None

    # ── Execute RAG on submit ─────────────────────────────────────────────
    q = st.session_state.q_input.strip()   # current text in the input box

    if submitted and q and throttle_exceeded():
        st.warning(T[lang]["throttled"])
    elif submitted and q:
        record_query()
        try:
            if not compare:
                jx       = st.session_state.last_jx
                hist_ctx = build_history_context(st.session_state.chat_history)
                with st.spinner(T[lang]["loading"]):
                    _t0 = _time.perf_counter()
                    result = rag.ask(q, jurisdiction=jx, history=hist_ctx)
                    _ms = int((_time.perf_counter() - _t0) * 1000)
                _analytics.log_query(q, lang, "single", jurisdiction=jx,
                                     response_ms=_ms, no_context=result.no_context)
                st.session_state.last_result = result
                st.session_state.used_jx     = jx
                st.session_state.chat_history.append({
                    "question": q, "mode": "single", "lang": lang,
                    "jurisdiction": jx, "result": result,
                })
                st.session_state.selected_hist_idx = None
                save_session(st.session_state.chat_history)

            else:
                jx_l = st.session_state.last_jx_l
                jx_r = st.session_state.last_jx_r
                hist_ctx = build_history_context(st.session_state.chat_history)
                with st.spinner(T[lang]["loading"]):
                    _t0 = _time.perf_counter()
                    # Run both jurisdictions concurrently — sequentially this was
                    # two full pipelines (up to eight Groq calls in Arabic) behind
                    # a single spinner.
                    res_l, res_r = rag.ask_many(
                        [(q, jx_l), (q, jx_r)], history=hist_ctx
                    )
                    _ms = int((_time.perf_counter() - _t0) * 1000)
                _analytics.log_query(q, lang, "compare", jx_left=jx_l, jx_right=jx_r,
                                     response_ms=_ms, no_context=res_l.no_context and res_r.no_context)
                st.session_state.last_result_l = res_l
                st.session_state.last_result_r = res_r
                st.session_state.used_jx_l     = jx_l
                st.session_state.used_jx_r     = jx_r
                st.session_state.chat_history.append({
                    "question": q, "mode": "compare", "lang": lang,
                    "jx_l": jx_l, "jx_r": jx_r,
                    "result_l": res_l, "result_r": res_r,
                })
                st.session_state.selected_hist_idx = None
                save_session(st.session_state.chat_history)

        except HealdarError as exc:
            show_error(exc, lang)

    # ── Auto-refresh when jurisdiction changes (updates last history entry in-place) ──
    # This re-queries the model, so it counts against the throttle too — changing
    # the jurisdiction selector repeatedly is otherwise a free way to spend quota.
    elif q and not submitted and not throttle_exceeded():
      try:
        if not compare and st.session_state.last_result is not None:
            jx = st.session_state.last_jx
            if jx != st.session_state.used_jx:
                record_query()
                hist_ctx = build_history_context(st.session_state.chat_history[:-1])
                with st.spinner(T[lang]["loading"]):
                    _t0 = _time.perf_counter()
                    result = rag.ask(q, jurisdiction=jx, history=hist_ctx)
                    _ms = int((_time.perf_counter() - _t0) * 1000)
                _analytics.log_query(q, lang, "single", jurisdiction=jx,
                                     response_ms=_ms, no_context=result.no_context)
                st.session_state.last_result = result
                st.session_state.used_jx     = jx
                if st.session_state.chat_history:
                    st.session_state.chat_history[-1]["result"]       = result
                    st.session_state.chat_history[-1]["jurisdiction"] = jx

        elif compare:
            jx_l      = st.session_state.last_jx_l
            jx_r      = st.session_state.last_jx_r
            changed_l = (st.session_state.last_result_l is not None and
                         jx_l != st.session_state.used_jx_l)
            changed_r = (st.session_state.last_result_r is not None and
                         jx_r != st.session_state.used_jx_r)
            if changed_l or changed_r:
                record_query()
                pending = []
                if changed_l:
                    pending.append((q, jx_l))
                if changed_r:
                    pending.append((q, jx_r))
                with st.spinner(T[lang]["loading"]):
                    _t0 = _time.perf_counter()
                    answers = rag.ask_many(pending)
                    _ms = int((_time.perf_counter() - _t0) * 1000)
                if changed_l:
                    res_l = answers.pop(0)
                    st.session_state.last_result_l = res_l
                    st.session_state.used_jx_l     = jx_l
                if changed_r:
                    res_r = answers.pop(0)
                    st.session_state.last_result_r = res_r
                    st.session_state.used_jx_r     = jx_r
                _analytics.log_query(q, lang, "compare", jx_left=jx_l, jx_right=jx_r, response_ms=_ms)
                if st.session_state.chat_history:
                    last = st.session_state.chat_history[-1]
                    if changed_l:
                        last["result_l"] = res_l
                        last["jx_l"] = jx_l
                    if changed_r:
                        last["result_r"] = res_r
                        last["jx_r"] = jx_r
      except HealdarError as exc:
          show_error(exc, lang)

    # ── Empty state — starter questions ──────────────────────────────────
    hist = st.session_state.chat_history
    if not hist:
        starters = {
            "en": [
                "What are the post-market surveillance requirements for AI medical devices?",
                "How does SFDA regulate AI-based Software as a Medical Device (SaMD)?",
                "What does the EU AI Act require for high-risk medical AI systems?",
                "How do Qatar and UAE differ in their health AI regulatory frameworks?",
                "What are the FDA's guidelines for AI/ML-based software in medical devices?",
            ],
            "ar": [
                "ما هي متطلبات مراقبة ما بعد التسويق لأجهزة الذكاء الاصطناعي الطبية؟",
                "كيف تنظّم هيئة الغذاء والدواء السعودية البرمجيات الطبية القائمة على الذكاء الاصطناعي؟",
                "ما متطلبات قانون الاتحاد الأوروبي للذكاء الاصطناعي للأنظمة الطبية عالية المخاطر؟",
                "كيف تختلف أُطر تنظيم الذكاء الاصطناعي الصحي بين قطر والإمارات؟",
                "ما إرشادات إدارة الغذاء والدواء الأمريكية للبرمجيات الطبية القائمة على الذكاء الاصطناعي؟",
            ],
        }
        rtl_s = "direction:rtl;text-align:right;" if lang == "ar" else ""
        _, center, _ = st.columns([1, 4, 1])
        with center:
            st.markdown(
                f'<p style="font-size:0.82rem;color:var(--text-secondary);'
                f'margin:2rem 0 0.6rem;{rtl_s}">{T[lang]["starter_prompt"]}</p>',
                unsafe_allow_html=True,
            )
            for s in starters[lang]:
                st.button(
                    s,
                    use_container_width=True,
                    key=f"starter_{s[:20]}",
                    on_click=lambda v=s: st.session_state.__setitem__("q_input", v),
                )

    # ── Display selected or latest history entry ──────────────────────────
    if hist:
        sel_idx = st.session_state.selected_hist_idx
        entry   = hist[sel_idx] if (sel_idx is not None and 0 <= sel_idx < len(hist)) else hist[-1]

        render_question_bubble(entry["question"], entry["lang"])

        if entry["mode"] == "single":
            _, center, _ = st.columns([1, 4, 1])
            with center:
                render_answer(entry["result"], entry["jurisdiction"], entry["lang"])
        else:
            col_l, col_r = st.columns(2, gap="large")
            with col_l:
                render_answer(entry["result_l"], entry["jx_l"], entry["lang"])
            with col_r:
                render_answer(entry["result_r"], entry["jx_r"], entry["lang"])


if __name__ == "__main__":
    main()
