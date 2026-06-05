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
from pathlib import Path
from typing import Dict, List, Any

# ---------------------------------------------------------------------------
# PDF extraction — prefer PyMuPDF (faster, more accurate), fall back to pypdf
# ---------------------------------------------------------------------------
try:
    import fitz  # PyMuPDF
    PDF_EXTRACTOR = "fitz"
except ImportError:
    try:
        from pypdf import PdfReader
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
# Resolve project root relative to this script's location
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent        # src/
PROJECT_ROOT = SCRIPT_DIR.parent                    # Healdar/
RAW_DOCS_DIR = PROJECT_ROOT / "data" / "raw_docs"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "chunks.json"

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

def extract_text_from_pdf(pdf_path: Path) -> Dict[int, str]:
    """
    Return {page_number: text} for every non-empty page in the PDF.
    Page numbers are 1-indexed. Returns {} on failure.
    """
    page_texts: Dict[int, str] = {}

    try:
        if PDF_EXTRACTOR == "fitz":
            doc = fitz.open(str(pdf_path))
            for page_num, page in enumerate(doc, start=1):
                text = page.get_text()
                if text.strip():
                    page_texts[page_num] = text
            doc.close()

        else:  # pypdf
            reader = PdfReader(str(pdf_path))
            for page_num, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    page_texts[page_num] = text

    except Exception as exc:
        logger.error(f"  Could not extract text from {pdf_path.name}: {exc}")

    if not page_texts:
        logger.warning(f"  {pdf_path.name}: no extractable text (image-only PDF?)")

    return page_texts


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_page(text: str) -> List[str]:
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
) -> List[Dict[str, Any]]:
    """
    Extract, chunk, and tag all text from one PDF.
    Returns a list of chunk dicts ready for JSON serialisation.
    """
    records: List[Dict[str, Any]] = []

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

    all_chunks: List[Dict[str, Any]] = []

    # Statistics tracked per jurisdiction
    stats: Dict[str, Dict[str, int]] = {}
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
