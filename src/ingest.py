"""
Healdar Regulatory Document Ingestion Pipeline

Flow:
1. Discover all PDF files under data/raw_docs/ subfolders
2. Extract text from each PDF using PyMuPDF (fitz), with pypdf as fallback
3. Split text into chunks of 500 tokens with 50-token overlap (tiktoken cl100k_base)
4. Tag each chunk with metadata: filename, jurisdiction, page_number, chunk_index
5. Save all chunks to data/chunks.json
6. Print a per-jurisdiction summary
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# PDF extraction — prefer PyMuPDF (faster, more accurate), fall back to pypdf
# ---------------------------------------------------------------------------
try:
    import fitz  # PyMuPDF
    PDF_EXTRACTOR = "fitz"
except ImportError:
    try:
        from pypdf import PdfReader  # noqa: F401 -- availability check only
        PDF_EXTRACTOR = "pypdf"
    except ImportError:
        PDF_EXTRACTOR = None

if PDF_EXTRACTOR is None:
    raise RuntimeError("No PDF library found. Run: pip install PyMuPDF")

# ---------------------------------------------------------------------------
# Token-based text splitting
# ---------------------------------------------------------------------------
try:
    import tiktoken
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    _TOKENIZER = tiktoken.get_encoding("cl100k_base")

    def _token_len(text: str) -> int:
        return len(_TOKENIZER.encode(text))

    # chunk_size / chunk_overlap are measured in tokens via length_function
    _SPLITTER = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        length_function=_token_len,
        separators=["\n\n", "\n", " ", ""],
    )

except ImportError:
    # Character-based fallback: 1 token ≈ 4 chars
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    _SPLITTER = RecursiveCharacterTextSplitter(
        chunk_size=2000,   # ~500 tokens
        chunk_overlap=200,  # ~50 tokens
        separators=["\n\n", "\n", " ", ""],
    )

# ---------------------------------------------------------------------------
# Paths (shared with the rest of the app via config)
# ---------------------------------------------------------------------------
import config

RAW_DOCS_DIR = config.RAW_DOCS_DIR
OUTPUT_FILE = config.CHUNKS_FILE

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def _extract_fitz(pdf_path: Path) -> dict[int, str]:
    pages: dict[int, str] = {}
    with fitz.open(str(pdf_path)) as doc:
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text()
            if text.strip():
                pages[page_num] = text
    return pages


def _extract_pypdf(pdf_path: Path) -> dict[int, str]:
    from pypdf import PdfReader  # local: only needed as a fallback / for Arabic

    pages: dict[int, str] = {}
    for page_num, page in enumerate(PdfReader(str(pdf_path)).pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages[page_num] = text
    return pages


# ---------------------------------------------------------------------------
# Arabic extraction quality
#
# Some Arabic PDFs use fonts whose ligature glyphs (lam-alef, lam-meem, fa-ya,
# sheen-ra, ...) carry reversed ToUnicode mappings. PyMuPDF reproduces them
# faithfully, yielding text like "عىل" for "على", "يف" for "في" and "املعالجة"
# for "المعالجة" -- close enough to look Arabic, wrong enough that search and
# quotation both fail. pypdf decodes the same files correctly. Rather than
# guess per file, extract Arabic documents both ways and keep whichever reads
# as correct Arabic.
# ---------------------------------------------------------------------------
_ARABIC_LETTER = re.compile(r"[ء-ي]")
_AR_GOOD = {"على", "في", "إلى", "التي", "الذي", "هذا", "المادة", "البيانات"}
_AR_BAD = {"عىل", "يف", "إىل", "اليت"}
_AR_BAD_PREFIX = ("امل", "اإل", "اال")   # "الم", "الإ", "الا" with lam swapped


def arabic_share(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if _ARABIC_LETTER.match(c)) / len(letters)


def arabic_quality(text: str) -> int:
    """Correctly spelled high-frequency words minus tell-tale corrupted forms."""
    words = re.findall(r"[ء-ي]+", text)
    good = sum(1 for w in words if w in _AR_GOOD)
    bad = sum(1 for w in words if w in _AR_BAD or w.startswith(_AR_BAD_PREFIX))
    return good - bad


def extract_text_from_pdf(pdf_path: Path) -> dict[int, str]:
    """
    Return {page_number: text} for every non-empty page in the PDF.
    Page numbers are 1-indexed. Returns {} on failure.
    """
    page_texts: dict[int, str] = {}

    try:
        page_texts = (
            _extract_fitz(pdf_path) if PDF_EXTRACTOR == "fitz" else _extract_pypdf(pdf_path)
        )
    except Exception as exc:
        logger.error(f"  Could not extract text from {pdf_path.name}: {exc}")

    joined = "\n".join(page_texts.values())
    if PDF_EXTRACTOR == "fitz" and arabic_share(joined) > 0.3:
        try:
            alt = _extract_pypdf(pdf_path)
            alt_joined = "\n".join(alt.values())
            if arabic_quality(alt_joined) > arabic_quality(joined):
                logger.info(
                    f"  {pdf_path.name}: Arabic text reads correctly with pypdf "
                    f"(quality {arabic_quality(alt_joined)} vs {arabic_quality(joined)}) "
                    "-- using it"
                )
                page_texts = alt
        except Exception as exc:
            logger.warning(f"  {pdf_path.name}: pypdf fallback failed: {exc}")

    if not page_texts:
        logger.warning(f"  {pdf_path.name}: no extractable text (image-only PDF?)")

    return page_texts


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_page(text: str) -> list[str]:
    """Split a single page's text into token-sized chunks."""
    try:
        return _SPLITTER.split_text(text)
    except Exception as exc:
        logger.error(f"  Chunking error: {exc}")
        return []


# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------

def process_pdf(
    pdf_path: Path,
    jurisdiction: str,
) -> list[dict[str, Any]]:
    """
    Extract, chunk, and tag all text from one PDF.
    Returns a list of chunk dicts ready for JSON serialisation.
    """
    records: list[dict[str, Any]] = []

    page_texts = extract_text_from_pdf(pdf_path)
    if not page_texts:
        return records

    for page_num, text in page_texts.items():
        if len(text.strip()) < 20:   # skip near-empty pages
            continue

        for chunk_idx, chunk in enumerate(chunk_page(text)):
            records.append(
                {
                    "text": chunk,
                    "metadata": {
                        "filename": pdf_path.name,
                        "jurisdiction": jurisdiction,
                        "page_number": page_num,
                        "chunk_index": chunk_idx,
                    },
                }
            )

    return records


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def ingest() -> None:
    if not RAW_DOCS_DIR.exists():
        logger.error(f"raw_docs directory not found: {RAW_DOCS_DIR}")
        return

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    all_chunks: list[dict[str, Any]] = []

    # Statistics tracked per jurisdiction
    stats: dict[str, dict[str, int]] = {}
    total_pdfs = 0
    failed_pdfs = 0

    # Iterate over each jurisdiction subfolder (sorted for deterministic order)
    for jurisdiction_dir in sorted(RAW_DOCS_DIR.iterdir()):
        if not jurisdiction_dir.is_dir():
            continue

        jurisdiction = jurisdiction_dir.name

        # Collect unique PDF paths (avoids duplicates from overlapping globs)
        pdf_files = sorted(set(jurisdiction_dir.rglob("*.pdf")))

        if not pdf_files:
            logger.info(f"[{jurisdiction}] no PDFs found — skipping")
            continue

        logger.info(f"[{jurisdiction}] processing {len(pdf_files)} PDF(s)...")

        jurisdiction_chunks = 0
        jurisdiction_success = 0

        for pdf_path in pdf_files:
            total_pdfs += 1
            try:
                chunks = process_pdf(pdf_path, jurisdiction)
                if chunks:
                    all_chunks.extend(chunks)
                    jurisdiction_chunks += len(chunks)
                    jurisdiction_success += 1
                    logger.info(f"  + {pdf_path.name}: {len(chunks)} chunks")
                else:
                    failed_pdfs += 1
                    logger.warning(f"  - {pdf_path.name}: 0 chunks produced")
            except Exception as exc:
                failed_pdfs += 1
                logger.error(f"  ! {pdf_path.name}: unexpected error — {exc}")

        stats[jurisdiction] = {
            "pdfs_found": len(pdf_files),
            "pdfs_ok": jurisdiction_success,
            "chunks": jurisdiction_chunks,
        }

    # Save chunks to JSON
    logger.info(f"\nWriting {len(all_chunks)} chunks to {OUTPUT_FILE} ...")
    try:
        with OUTPUT_FILE.open("w", encoding="utf-8") as fh:
            json.dump(all_chunks, fh, ensure_ascii=False, indent=2)
        logger.info("Done.")
    except Exception as exc:
        logger.error(f"Failed to write output: {exc}")
        return

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 65)
    print("  INGEST SUMMARY")
    print("=" * 65)
    print(f"  PDFs processed : {total_pdfs}  ({total_pdfs - failed_pdfs} OK, {failed_pdfs} failed)")
    print(f"  Total chunks   : {len(all_chunks)}")
    print(f"  Output file    : {OUTPUT_FILE}")
    print()
    print(f"  {'Jurisdiction':<30} {'PDFs':>5}  {'Chunks':>7}")
    print(f"  {'-'*30} {'-'*5}  {'-'*7}")
    for jurisdiction, data in sorted(stats.items()):
        print(f"  {jurisdiction:<30} {data['pdfs_ok']:>5}  {data['chunks']:>7}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    ingest()
