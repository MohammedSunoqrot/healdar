"""
Healdar Export — generate PDF and Word reports from a RAGAnswer.

PDF  : reportlab (no system dependencies, pure Python)
Word : python-docx (native Unicode / Arabic support)

Arabic note:
  PDF uses the English answer (result.answer_en) because embedding a full
  Arabic-capable font would add ~1 MB to the project. Word uses the displayed
  answer (which may be Arabic) since .docx handles Unicode natively.
"""

import io
import re
from datetime import datetime


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _clean_citations(text: str) -> str:
    """Replace [Source N] tags with plain (N) for text-format export."""
    return re.sub(r'\[Source\s*(\d+)[^\]]*\]', r'(\1)', text, flags=re.IGNORECASE)


def _safe_filename(jx: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_-]', '_', jx.lower())


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _file_date() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M")


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def to_pdf(
    question: str,
    answer: str,          # English answer (for reliable font rendering)
    sources: list[dict],
    jurisdiction: str,
    question_original: str = "",   # original (may be Arabic) shown as a note
) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, HRFlowable, ListFlowable, ListItem,
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER

    ACCENT  = colors.HexColor("#0a66c2")
    GREY    = colors.HexColor("#7a8499")
    BORDER  = colors.HexColor("#30363d")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=2.2*cm, leftMargin=2.2*cm,
        topMargin=2*cm, bottomMargin=2.5*cm,
        title="Healdar Report",
        author="Healdar",
    )

    base = getSampleStyleSheet()

    def style(name, **kw):
        p = ParagraphStyle(name, parent=base["Normal"], **kw)
        return p

    s_title   = style("RRTitle",    fontSize=22, textColor=ACCENT,  spaceAfter=2,  alignment=TA_CENTER, fontName="Helvetica-Bold")
    s_tagline = style("RRTagline",  fontSize=10, textColor=GREY,   spaceAfter=2,  alignment=TA_CENTER)
    s_meta    = style("RRMeta",     fontSize=8,  textColor=GREY,   spaceAfter=10, alignment=TA_CENTER)
    s_h2      = style("RRH2",       fontSize=11, textColor=ACCENT,  spaceBefore=12, spaceAfter=4, fontName="Helvetica-Bold")
    s_body    = style("RRBody",     fontSize=10, leading=15, spaceAfter=6)
    s_note    = style("RRNote",     fontSize=9,  textColor=GREY,   leading=13, leftIndent=10)
    s_ref     = style("RRRef",      fontSize=9,  leading=13, leftIndent=10)
    s_excerpt = style("RRExcerpt",  fontSize=8,  textColor=GREY,   leftIndent=20, leading=12)
    s_disc    = style("RRDisc",     fontSize=7,  textColor=GREY,   alignment=TA_CENTER, spaceBefore=6)

    story = []

    # ── Header ──
    story += [
        Paragraph("Healdar", s_title),
        Paragraph("Health AI Regulatory Intelligence", s_tagline),
        Paragraph(f"Generated: {_timestamp()} &nbsp;|&nbsp; Jurisdiction: {jurisdiction.upper()}", s_meta),
        HRFlowable(width="100%", thickness=0.8, color=BORDER, spaceAfter=10),
    ]

    # ── Question ──
    story.append(Paragraph("Question", s_h2))
    # If original question was Arabic, show it as a note
    if question_original and question_original != question:
        story.append(Paragraph(f"Original: {question_original}", s_note))
        story.append(Paragraph(f"(English): {question}", s_body))
    else:
        story.append(Paragraph(question, s_body))

    # ── Answer ──
    story.append(Paragraph("Answer", s_h2))
    clean = _clean_citations(answer)

    for block in clean.split("\n\n"):
        lines = [l for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        bullet_pat   = re.compile(r'^[*\-–—•]\s+(.*)')
        numbered_pat = re.compile(r'^\d+[.)]\s+(.*)')

        if all(bullet_pat.match(l.lstrip()) for l in lines):
            items = [ListItem(Paragraph(bullet_pat.match(l.lstrip()).group(1), s_body)) for l in lines]
            story.append(ListFlowable(items, bulletType="bullet", leftIndent=15, spaceAfter=4))
        elif all(numbered_pat.match(l.lstrip()) for l in lines):
            items = [ListItem(Paragraph(numbered_pat.match(l.lstrip()).group(1), s_body)) for l in lines]
            story.append(ListFlowable(items, bulletType="1", leftIndent=15, spaceAfter=4))
        else:
            story.append(Paragraph(" ".join(lines), s_body))

    # ── References ──
    if sources:
        story += [
            Spacer(1, 0.2*cm),
            HRFlowable(width="100%", thickness=0.4, color=BORDER),
            Paragraph("References", s_h2),
        ]
        for i, src in enumerate(sources, 1):
            label = f"[{i}]  {src['filename']}  ·  {src['jurisdiction']}  ·  p.{src['page_number']}"
            story.append(Paragraph(label, s_ref))
            if src.get("text"):
                excerpt = src["text"][:220].strip()
                if len(src["text"]) > 220:
                    excerpt += "…"
                story.append(Paragraph(f'"{excerpt}"', s_excerpt))
            story.append(Spacer(1, 0.15*cm))

    # ── Disclaimer ──
    story += [
        Spacer(1, 0.4*cm),
        HRFlowable(width="100%", thickness=0.4, color=BORDER),
        Paragraph(
            "For informational purposes only. Always consult official regulatory bodies.",
            s_disc,
        ),
        Paragraph("Generated by Healdar · Developed by Mohammed R. S. Sunoqrot", s_disc),
    ]

    doc.build(story)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Word
# ---------------------------------------------------------------------------

def to_docx(
    question: str,
    answer: str,         # displayed answer (may be Arabic)
    sources: list[dict],
    jurisdiction: str,
    lang: str = "en",
) -> bytes:
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    ACCENT_RGB = RGBColor(0x0A, 0x66, 0xC2)
    GREY_RGB   = RGBColor(0x7A, 0x84, 0x99)
    RTL        = lang == "ar"
    align      = WD_ALIGN_PARAGRAPH.RIGHT if RTL else WD_ALIGN_PARAGRAPH.LEFT
    center     = WD_ALIGN_PARAGRAPH.CENTER

    doc = Document()

    # Page margins
    for sec in doc.sections:
        sec.top_margin    = Cm(2.5)
        sec.bottom_margin = Cm(2.5)
        sec.left_margin   = Cm(3)
        sec.right_margin  = Cm(3)

    def _add_rule(doc):
        """Insert a horizontal rule (paragraph border)."""
        p = doc.add_paragraph()
        pPr = p._p.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "4")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), "30363d")
        pBdr.append(bottom)
        pPr.append(pBdr)
        p.paragraph_format.space_after = Pt(6)
        return p

    def _set_rtl(para):
        pPr = para._p.get_or_add_pPr()
        bidi = OxmlElement("w:bidi")
        pPr.append(bidi)

    # ── Header ──
    title = doc.add_heading("Healdar", 0)
    title.alignment = center
    title.runs[0].font.color.rgb = ACCENT_RGB

    tagline = doc.add_paragraph("Health AI Regulatory Intelligence")
    tagline.alignment = center
    tagline.runs[0].font.color.rgb = GREY_RGB
    tagline.runs[0].font.size = Pt(11)

    meta = doc.add_paragraph(f"Generated: {_timestamp()}  |  Jurisdiction: {jurisdiction.upper()}")
    meta.alignment = center
    meta.runs[0].font.size = Pt(9)
    meta.runs[0].font.color.rgb = GREY_RGB

    _add_rule(doc)

    # ── Question ──
    h = doc.add_heading("Question", level=2)
    h.runs[0].font.color.rgb = ACCENT_RGB
    q_para = doc.add_paragraph(question)
    q_para.alignment = align
    if RTL:
        _set_rtl(q_para)

    doc.add_paragraph()

    # ── Answer ──
    h = doc.add_heading("Answer", level=2)
    h.runs[0].font.color.rgb = ACCENT_RGB

    clean = _clean_citations(answer)
    bullet_pat   = re.compile(r'^[*\-–—•]\s+(.*)')
    numbered_pat = re.compile(r'^\d+[.)]\s+(.*)')

    for block in clean.split("\n\n"):
        lines = [l for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        if all(bullet_pat.match(l.lstrip()) for l in lines):
            for line in lines:
                item = bullet_pat.match(line.lstrip()).group(1)
                p = doc.add_paragraph(item, style="List Bullet")
                p.alignment = align
                if RTL:
                    _set_rtl(p)
        elif all(numbered_pat.match(l.lstrip()) for l in lines):
            for line in lines:
                item = numbered_pat.match(line.lstrip()).group(1)
                p = doc.add_paragraph(item, style="List Number")
                p.alignment = align
                if RTL:
                    _set_rtl(p)
        else:
            p = doc.add_paragraph(" ".join(lines))
            p.alignment = align
            if RTL:
                _set_rtl(p)

    # ── References ──
    if sources:
        doc.add_paragraph()
        _add_rule(doc)
        h = doc.add_heading("References", level=2)
        h.runs[0].font.color.rgb = ACCENT_RGB
        for i, src in enumerate(sources, 1):
            ref = doc.add_paragraph()
            run_num = ref.add_run(f"[{i}]  ")
            run_num.bold = True
            ref.add_run(f"{src['filename']}  ·  {src['jurisdiction']}  ·  p.{src['page_number']}")
            if src.get("text"):
                excerpt = src["text"][:220].strip()
                if len(src["text"]) > 220:
                    excerpt += "…"
                exc_p = doc.add_paragraph(f'"{excerpt}"')
                exc_p.paragraph_format.left_indent = Cm(1.2)
                exc_p.runs[0].font.italic = True
                exc_p.runs[0].font.size   = Pt(9)
                exc_p.runs[0].font.color.rgb = GREY_RGB

    # ── Disclaimer ──
    doc.add_paragraph()
    _add_rule(doc)
    disc = doc.add_paragraph(
        "For informational purposes only. Always consult official regulatory bodies.\n"
        "Generated by Healdar  ·  Developed by Mohammed R. S. Sunoqrot"
    )
    disc.alignment = center
    disc.runs[0].font.size = Pt(8)
    disc.runs[0].font.color.rgb = GREY_RGB

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
