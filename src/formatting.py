"""
Healdar -- answer formatting.

Language models write Markdown whether asked to or not: **bold**, ### headings,
pipe tables, `code`, horizontal rules. Rendered naively that shows up as raw
asterisks and pipes. This module parses an answer once into a small set of
blocks and inline segments, which the UI (HTML), the PDF exporter (reportlab
markup) and the Word exporter (python-docx runs) each render natively -- so no
Markdown punctuation ever reaches the reader, in any of the three.

Block kinds:  "p" paragraph lines | "h" heading | "ul" / "ol" list items |
              "table" rows of cells
Inline:       Segment(text, bold, italic, code)
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field

import config


@dataclass
class Segment:
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False


@dataclass
class Block:
    kind: str                                   # p | h | ul | ol | table
    lines: list[str] = field(default_factory=list)   # p/h: lines; ul/ol: items
    rows: list[list[str]] = field(default_factory=list)  # table only
    start: int = 1                                    # ol only: first number


# ---------------------------------------------------------------------------
# Block parsing
# ---------------------------------------------------------------------------

_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*$")
_BULLET = re.compile(r"^[*\-–—•]\s+(.*)$")
_NUMBERED = re.compile(r"^\d{1,3}[.)]\s+(.*)$")
_RULE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})$")
_TABLE_SEP = re.compile(r"^\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?$")
# A whole line that is only bold text reads as a sub-heading: "**Key points:**"
_BOLD_LINE = re.compile(r"^(?:\*\*|__)(.+?)(?:\*\*|__):?$")


def _is_table_row(line: str) -> bool:
    return line.startswith("|") and line.endswith("|") and line.count("|") >= 3


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_blocks(text: str) -> list[Block]:
    """Split answer text into renderable blocks."""
    blocks: list[Block] = []
    current: Block | None = None

    def flush() -> None:
        nonlocal current
        if current and (current.lines or current.rows):
            blocks.append(current)
        current = None

    in_code = False
    for raw in (text or "").replace("\r\n", "\n").split("\n"):
        # Blockquote markers ("> Software intended to ...") showed as a literal
        # ">"; the quote marks inside already say it is quoted text.
        line = re.sub(r"^(?:>\s?)+", "", raw.strip()).strip()

        # Code fences: keep the content, drop the fence.
        if line.startswith("```"):
            in_code = not in_code
            continue

        if not line:
            # Models put blank lines between list items. Ending the list there
            # restarted every numbered item at "1." -- keep the list open and
            # let the next non-item line close it.
            if not (current and current.kind in {"ul", "ol"}):
                flush()
            continue
        if _RULE.match(line):
            flush()
            continue

        if _is_table_row(line):
            if _TABLE_SEP.match(line):
                continue
            if not current or current.kind != "table":
                flush()
                current = Block("table")
            current.rows.append(_cells(line))
            continue

        heading = _HEADING.match(line)
        bold_line = _BOLD_LINE.match(line)
        if heading or (bold_line and not in_code):
            flush()
            blocks.append(Block("h", [(heading or bold_line).group(1).strip(" :")]))
            continue

        bullet = _BULLET.match(line)
        numbered = _NUMBERED.match(line)
        if bullet or numbered:
            kind = "ul" if bullet else "ol"
            if not current or current.kind != kind:
                flush()
                current = Block(kind)
                if numbered:
                    current.start = int(re.search(r"\d+", line).group())
            current.lines.append((bullet or numbered).group(1).strip())
            continue

        # Indented continuation of the previous list item.
        if current and current.kind in {"ul", "ol"} and raw[:1] in {" ", "\t"}:
            current.lines[-1] = f"{current.lines[-1]} {line}"
            continue

        if not current or current.kind != "p":
            flush()
            current = Block("p")
        current.lines.append(line)

    flush()
    return blocks


# ---------------------------------------------------------------------------
# Inline parsing
# ---------------------------------------------------------------------------

# Order matters: bold before italic, so "**x**" is not read as two italics.
_INLINE = re.compile(
    r"(?P<code>`[^`]+`)"
    r"|(?P<bold>\*\*(?=\S)(?:.+?)(?<=\S)\*\*|__(?=\S)(?:.+?)(?<=\S)__)"
    r"|(?P<italic>(?<![\w*])\*(?=\S)(?:[^*]+?)(?<=\S)\*(?![\w*]))"
)


def inline_segments(text: str) -> list[Segment]:
    """Split one line into plain / bold / italic / code segments."""
    out: list[Segment] = []
    pos = 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            out.append(Segment(text[pos:m.start()]))
        token = m.group(0)
        if m.group("code"):
            out.append(Segment(token[1:-1], code=True))
        elif m.group("bold"):
            out.append(Segment(token[2:-2], bold=True))
        else:
            out.append(Segment(token[1:-1], italic=True))
        pos = m.end()
    if pos < len(text):
        out.append(Segment(text[pos:]))
    # Any emphasis markers left unpaired are noise -- drop them.
    for seg in out:
        if not seg.code:
            seg.text = re.sub(r"\*{2,}|(?<!\w)__|__(?!\w)", "", seg.text)
    return [s for s in out if s.text]


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def _inline_html(line: str, cite) -> str:
    parts = []
    for seg in inline_segments(line):
        t = html.escape(seg.text)
        if cite:
            t = config.CITATION_RE.sub(cite, t)
        if seg.code:
            t = f"<code>{t}</code>"
        if seg.italic:
            t = f"<em>{t}</em>"
        if seg.bold:
            t = f"<strong>{t}</strong>"
        parts.append(t)
    return "".join(parts)


def to_html(text: str, cite=None) -> str:
    """
    Render answer text as safe HTML.

    `cite` is an optional re.sub callback applied to escaped text, used by the
    UI to turn [Source N] into footnote superscripts.
    """
    out: list[str] = []
    for b in parse_blocks(text):
        if b.kind == "h":
            out.append(f'<p class="ans-h">{_inline_html(b.lines[0], cite)}</p>')
        elif b.kind in {"ul", "ol"}:
            items = "".join(f"<li>{_inline_html(i, cite)}</li>" for i in b.lines)
            start = f' start="{b.start}"' if b.kind == "ol" and b.start != 1 else ""
            out.append(f"<{b.kind}{start}>{items}</{b.kind}>")
        elif b.kind == "table":
            head, *body = b.rows
            th = "".join(f"<th>{_inline_html(c, cite)}</th>" for c in head)
            trs = "".join(
                "<tr>" + "".join(f"<td>{_inline_html(c, cite)}</td>" for c in row) + "</tr>"
                for row in body
            )
            out.append(
                f'<div class="ans-table"><table><thead><tr>{th}</tr></thead>'
                f"<tbody>{trs}</tbody></table></div>"
            )
        else:
            out.append("<p>" + "<br>".join(_inline_html(ln, cite) for ln in b.lines) + "</p>")
    return "".join(out)


def to_plain(text: str) -> str:
    """Markdown-free text, for the clipboard and plain-text contexts."""
    lines: list[str] = []
    for b in parse_blocks(text):
        plain = lambda s: "".join(seg.text for seg in inline_segments(s))  # noqa: E731
        if b.kind == "h":
            lines.append(plain(b.lines[0]))
        elif b.kind == "ul":
            lines.extend(f"• {plain(i)}" for i in b.lines)
        elif b.kind == "ol":
            lines.extend(f"{n}. {plain(i)}" for n, i in enumerate(b.lines, b.start))
        elif b.kind == "table":
            lines.extend(" | ".join(plain(c) for c in row) for row in b.rows)
        else:
            lines.extend(plain(ln) for ln in b.lines)
        lines.append("")
    return "\n".join(lines).strip()


# Characters the PDF's standard Helvetica (WinAnsi) cannot draw. Models emit
# them constantly -- U+2011 non-breaking hyphen, U+202F narrow no-break space
# -- and each would otherwise print as a black box.
_PDF_MAP = {
    "‐": "-", "‑": "-", "‒": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", " ": " ", "​": "",
    "≤": "<=", "≥": ">=", "→": "->", "←": "<-",
    "≈": "~", "≠": "!=", "×": "x", "✓": "v", "✔": "v",
}


def pdf_safe(text: str) -> str:
    """Fold text to characters the built-in PDF font can render."""
    out = []
    for ch in text:
        ch = _PDF_MAP.get(ch, ch)
        try:
            ch.encode("cp1252")
            out.append(ch)
        except UnicodeEncodeError:
            folded = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode()
            out.append(folded)
    return "".join(out)


_ARABIC_LETTER = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_ANY_LETTER = re.compile(r"[^\W\d_]")


def is_rtl_text(text: str) -> bool:
    """
    Mostly Arabic? Layout follows the text itself, not the interface language:
    an Arabic question asked with the English interface got an Arabic answer
    laid out left to right. English terms and "[Source N]" tags inside an
    Arabic answer stay well under the threshold.
    """
    letters = _ANY_LETTER.findall(text or "")
    if not letters:
        return False
    return sum(1 for ch in letters if _ARABIC_LETTER.match(ch)) / len(letters) > 0.3


def is_pdf_renderable(text: str) -> bool:
    """False when most of the text would vanish in pdf_safe (e.g. Arabic)."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return True
    ok = sum(1 for c in letters if pdf_safe(c))
    return ok / len(letters) > 0.8


def to_reportlab(line: str) -> str:
    """One line as reportlab paragraph markup (<b>, <i>, Courier for code)."""
    parts = []
    for seg in inline_segments(line):
        t = html.escape(pdf_safe(seg.text), quote=False)
        if seg.code:
            t = f'<font face="Courier">{t}</font>'
        if seg.italic:
            t = f"<i>{t}</i>"
        if seg.bold:
            t = f"<b>{t}</b>"
        parts.append(t)
    return "".join(parts)
