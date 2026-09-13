"""
Healdar export -- PDF and Word reports from a RAGAnswer.

Both formats render the answer through formatting.parse_blocks, so headings,
lists, tables and emphasis come out as real document structure instead of
literal Markdown punctuation.

PDF  : reportlab with the built-in Helvetica. It cannot draw Arabic, so the
       PDF carries the English answer, and Arabic source excerpts are noted
       rather than printed as rows of empty boxes.
Word : python-docx with full Unicode -- carries the answer in the language
       it was shown in, right-to-left where needed.

Sources are passed as (index, source) pairs. The index is the number the
answer cites -- an earlier version renumbered the cited sources from 1, so an
answer citing [2] and [4] got a reference list labelled [1] and [2].
"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import config
import formatting

ACCENT_HEX = "#3B5BDB"
GREY_HEX = "#6B7489"
RULE_HEX = "#C9D0DD"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _clean_citations(text: str) -> str:
    """[Source N] -> [N], matching the numbering of the reference list."""
    return config.CITATION_RE.sub(r"[\1]", text)


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _file_date() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M")


def _doc_name(filename: str) -> str:
    return Path(filename).stem.replace("_", " ")


def _indexed(sources) -> list[tuple[int, dict]]:
    """Accept [(n, src), ...] or a plain [src, ...] (numbered from 1)."""
    out = []
    for i, item in enumerate(sources or [], start=1):
        if isinstance(item, tuple) and len(item) == 2:
            out.append((int(item[0]), item[1]))
        else:
            out.append((i, item))
    return out


def _excerpt(text: str, limit: int = 260) -> str:
    text = " ".join((text or "").split())
    return text[:limit].rstrip() + ("…" if len(text) > limit else "")


_FOOTER = (
    "For informational purposes only. Always consult the official regulatory "
    "documents and bodies."
)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def to_pdf(
    question: str,
    answer: str,                 # English answer (the built-in font is Latin-only)
    sources,
    jurisdiction: str,
    question_original: str = "",
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        HRFlowable,
        ListFlowable,
        ListItem,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    accent, grey, rule = (colors.HexColor(c) for c in (ACCENT_HEX, GREY_HEX, RULE_HEX))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=2.2 * cm, leftMargin=2.2 * cm,
        topMargin=2 * cm, bottomMargin=2.2 * cm,
        title="Healdar report", author="Healdar",
    )
    base = getSampleStyleSheet()["Normal"]

    def style(name, **kw):
        return ParagraphStyle(name, parent=base, **kw)

    s_title = style("T", fontSize=22, textColor=accent, alignment=TA_CENTER,
                    fontName="Helvetica-Bold", spaceAfter=4, leading=26)
    s_meta = style("M", fontSize=8, textColor=grey, alignment=TA_CENTER, spaceAfter=10)
    s_h2 = style("H2", fontSize=12, textColor=accent, fontName="Helvetica-Bold",
                 spaceBefore=12, spaceAfter=5)
    s_h3 = style("H3", fontSize=10.5, fontName="Helvetica-Bold", spaceBefore=8, spaceAfter=3)
    s_body = style("B", fontSize=10, leading=15, spaceAfter=6)
    s_cell = style("C", fontSize=8.5, leading=11)
    s_note = style("N", fontSize=9, textColor=grey, leading=13)
    s_ref = style("R", fontSize=9, leading=13, spaceBefore=3)
    s_exc = style("E", fontSize=8, textColor=grey, leftIndent=14, leading=11)
    s_disc = style("D", fontSize=7.5, textColor=grey, alignment=TA_CENTER, spaceBefore=4)

    def rl(text: str) -> str:
        return formatting.to_reportlab(text)

    story = [
        Paragraph("Healdar", s_title),
        Paragraph(
            f"Health AI Regulatory Intelligence &nbsp;|&nbsp; Generated {_timestamp()} "
            f"&nbsp;|&nbsp; {rl(jurisdiction)} &nbsp;|&nbsp; v{config.APP_VERSION}",
            s_meta,
        ),
        HRFlowable(width="100%", thickness=0.8, color=rule, spaceAfter=8),
        Paragraph("Question", s_h2),
    ]

    if (question_original and question_original != question
            and formatting.is_pdf_renderable(question_original)):
        story.append(Paragraph(rl(question_original), s_body))
        story.append(Paragraph(f"(English) {rl(question)}", s_note))
    else:
        story.append(Paragraph(rl(question), s_body))
        if question_original and question_original != question:
            story.append(Paragraph("Asked in Arabic; shown in English translation.", s_note))

    story.append(Paragraph("Answer", s_h2))
    for block in formatting.parse_blocks(_clean_citations(answer)):
        if block.kind == "h":
            story.append(Paragraph(rl(block.lines[0]), s_h3))
        elif block.kind in {"ul", "ol"}:
            items = [ListItem(Paragraph(rl(i), s_body), leftIndent=12) for i in block.lines]
            story.append(ListFlowable(
                items, bulletType="bullet" if block.kind == "ul" else "1",
                leftIndent=14, bulletFontSize=8 if block.kind == "ul" else 10,
                start=block.start if block.kind == "ol" else None,
            ))
        elif block.kind == "table":
            width = doc.width / max(1, max(len(r) for r in block.rows))
            data = [[Paragraph(rl(c), s_cell) for c in row] for row in block.rows]
            tbl = Table(data, colWidths=[width] * len(data[0]), repeatRows=1)
            tbl.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.4, rule),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF1F8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story += [tbl, Spacer(1, 6)]
        else:
            story.append(Paragraph("<br/>".join(rl(ln) for ln in block.lines), s_body))

    indexed = _indexed(sources)
    if indexed:
        story += [Spacer(1, 6), HRFlowable(width="100%", thickness=0.4, color=rule),
                  Paragraph("References", s_h2)]
        for n, src in indexed:
            label = (f"<b>[{n}]</b> {rl(_doc_name(src['filename']))} &nbsp;·&nbsp; "
                     f"{rl(str(src.get('jurisdiction', '')))} &nbsp;·&nbsp; p.{src.get('page_number', '')}")
            story.append(Paragraph(label, s_ref))
            text = src.get("text") or ""
            if text and formatting.is_pdf_renderable(text):
                story.append(Paragraph(f"“{rl(_excerpt(text))}”", s_exc))
            elif text:
                story.append(Paragraph(
                    "Source text is in Arabic -- see the Word export for the original.", s_exc))

    story += [
        Spacer(1, 10), HRFlowable(width="100%", thickness=0.4, color=rule),
        Paragraph(_FOOTER, s_disc),
        Paragraph(f"Generated by Healdar v{config.APP_VERSION} ({config.RELEASE_DATE}) "
                  "· Developed by Mohammed R. S. Sunoqrot", s_disc),
    ]
    doc.build(story)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Word
# ---------------------------------------------------------------------------

def to_docx(
    question: str,
    answer: str,              # the answer as displayed (may be Arabic)
    sources,
    jurisdiction: str,
    lang: str = "en",
) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    accent = RGBColor(0x3B, 0x5B, 0xDB)
    grey = RGBColor(0x6B, 0x74, 0x89)
    rtl = lang == "ar"
    align = WD_ALIGN_PARAGRAPH.RIGHT if rtl else WD_ALIGN_PARAGRAPH.LEFT
    center = WD_ALIGN_PARAGRAPH.CENTER

    doc = Document()
    for sec in doc.sections:
        sec.top_margin = sec.bottom_margin = Cm(2.3)
        sec.left_margin = sec.right_margin = Cm(2.6)

    def set_rtl(par):
        if rtl:
            par._p.get_or_add_pPr().append(OxmlElement("w:bidi"))
            par.alignment = align

    def add_rule():
        p = doc.add_paragraph()
        ppr = p._p.get_or_add_pPr()
        border = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        for k, v in (("w:val", "single"), ("w:sz", "4"), ("w:space", "1"), ("w:color", "C9D0DD")):
            bottom.set(qn(k), v)
        border.append(bottom)
        ppr.append(border)

    def add_runs(par, line: str):
        for seg in formatting.inline_segments(line):
            run = par.add_run(seg.text)
            run.bold = seg.bold or None
            run.italic = seg.italic or None
            if seg.code:
                run.font.name = "Consolas"
            if rtl:
                run._r.get_or_add_rPr().append(OxmlElement("w:rtl"))

    def heading(text: str, level: int = 2):
        h = doc.add_heading(text, level=level)
        for r in h.runs:
            r.font.color.rgb = accent
        set_rtl(h)

    title = doc.add_heading("Healdar", 0)
    title.alignment = center
    for r in title.runs:
        r.font.color.rgb = accent
    meta = doc.add_paragraph(
        f"Health AI Regulatory Intelligence  |  Generated {_timestamp()}  |  "
        f"{jurisdiction}  |  v{config.APP_VERSION}"
    )
    meta.alignment = center
    meta.runs[0].font.size = Pt(9)
    meta.runs[0].font.color.rgb = grey
    add_rule()

    heading("السؤال" if rtl else "Question")
    q = doc.add_paragraph()
    add_runs(q, question)
    set_rtl(q)

    heading("الإجابة" if rtl else "Answer")
    for block in formatting.parse_blocks(_clean_citations(answer)):
        if block.kind == "h":
            p = doc.add_paragraph()
            add_runs(p, block.lines[0])
            for r in p.runs:
                r.bold = True
            set_rtl(p)
        elif block.kind in {"ul", "ol"}:
            for item in block.lines:
                p = doc.add_paragraph(style="List Bullet" if block.kind == "ul" else "List Number")
                add_runs(p, item)
                set_rtl(p)
        elif block.kind == "table":
            ncols = max(len(r) for r in block.rows)
            table = doc.add_table(rows=0, cols=ncols)
            table.style = "Table Grid"
            for r_i, row in enumerate(block.rows):
                cells = table.add_row().cells
                for c_i, text in enumerate(row[:ncols]):
                    par = cells[c_i].paragraphs[0]
                    add_runs(par, text)
                    if r_i == 0:
                        for run in par.runs:
                            run.bold = True
            doc.add_paragraph()
        else:
            p = doc.add_paragraph()
            for i, line in enumerate(block.lines):
                if i:
                    p.add_run().add_break()
                add_runs(p, line)
            set_rtl(p)

    indexed = _indexed(sources)
    if indexed:
        add_rule()
        heading("المصادر" if rtl else "References")
        for n, src in indexed:
            ref = doc.add_paragraph()
            ref.add_run(f"[{n}]  ").bold = True
            ref.add_run(f"{_doc_name(src['filename'])}  ·  {src.get('jurisdiction', '')}  ·  "
                        f"p.{src.get('page_number', '')}")
            if src.get("text"):
                exc = doc.add_paragraph(f"“{_excerpt(src['text'])}”")
                exc.paragraph_format.left_indent = Cm(1.0)
                exc.runs[0].italic = True
                exc.runs[0].font.size = Pt(9)
                exc.runs[0].font.color.rgb = grey

    add_rule()
    disc = doc.add_paragraph(
        f"{_FOOTER}\nGenerated by Healdar v{config.APP_VERSION} ({config.RELEASE_DATE})"
        "  ·  Developed by Mohammed R. S. Sunoqrot"
    )
    disc.alignment = center
    disc.runs[0].font.size = Pt(8)
    disc.runs[0].font.color.rgb = grey

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
