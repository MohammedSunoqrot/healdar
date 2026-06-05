"""
Healdar Embedding Pipeline

Flow:
1. Load text chunks from data/chunks.json
2. Generate embeddings using HuggingFace all-MiniLM-L6-v2 (local, no API key)
3. Upsert chunks + embeddings into a persistent ChromaDB collection called 'regradar'
4. Print a per-jurisdiction summary

Re-running this script is safe: upsert overwrites existing records by ID.
"""

import json
import logging
from collections import defaultdict
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

# ---------------------------------------------------------------------------
# Paths — resolved relative to this script so the script can be run from anywhere
# ---------------------------------------------------------------------------
SCRIPT_DIR   = Path(__file__).resolve().parent        # src/
PROJECT_ROOT = SCRIPT_DIR.parent                      # Healdar/
CHUNKS_FILE  = PROJECT_ROOT / "data" / "processed" / "chunks.json"
VECTORSTORE  = PROJECT_ROOT / "data" / "processed" / "vectorstore"

COLLECTION_NAME  = "regradar"
EMBED_MODEL      = "all-MiniLM-L6-v2"
BATCH_SIZE       = 500   # number of chunks per upsert call

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
# Helpers
# ---------------------------------------------------------------------------

def make_chunk_id(meta: dict) -> str:
    """
    Build a deterministic, unique string ID for each chunk from its metadata.
    Using filename + page + chunk_index avoids collisions across files.
    """
    filename   = meta["filename"].replace(" ", "_")
    page       = meta["page_number"]
    chunk_idx  = meta["chunk_index"]
    return f"{filename}::p{page}::c{chunk_idx}"


def load_chunks(path: Path) -> list[dict]:
    """Load and validate the JSON chunks file."""
    if not path.exists():
        raise FileNotFoundError(
            f"chunks.json not found at {path}\n"
            "Run src/ingest.py first to generate it."
        )

    with path.open(encoding="utf-8") as fh:
        chunks = json.load(fh)

    if not isinstance(chunks, list) or not chunks:
        raise ValueError(f"Expected a non-empty list in {path}")

    logger.info(f"Loaded {len(chunks):,} chunks from {path}")
    return chunks


def batch(iterable: list, size: int):
    """Yield successive slices of `iterable` with length <= `size`."""
    for start in range(0, len(iterable), size):
        yield iterable[start : start + size]


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def embed() -> None:

    # 1. Load chunks
    chunks = load_chunks(CHUNKS_FILE)

    # 2. Set up ChromaDB persistent client
    #    PersistentClient writes the database to disk at VECTORSTORE.
    #    The directory is created automatically if it doesn't exist.
    VECTORSTORE.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(VECTORSTORE))
    logger.info(f"ChromaDB client ready at {VECTORSTORE}")

    # 3. Embedding function — runs locally via sentence-transformers
    ef = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    logger.info(f"Embedding function: {EMBED_MODEL}")

    # 4. Get or create the collection
    #    'cosine' distance is standard for sentence-transformer models.
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
    logger.info(f"Collection '{COLLECTION_NAME}' ready "
                f"(existing docs: {collection.count():,})")

    # 5. Prepare data for upsert
    ids        = []
    documents  = []
    metadatas  = []

    for chunk in chunks:
        meta = chunk["metadata"]

        ids.append(make_chunk_id(meta))
        documents.append(chunk["text"])

        # ChromaDB metadata values must be str / int / float / bool — no None
        metadatas.append({
            "jurisdiction": meta.get("jurisdiction", "unknown"),
            "filename":     meta.get("filename",     "unknown"),
            "page_number":  int(meta.get("page_number",  0)),
            "chunk_index":  int(meta.get("chunk_index",  0)),
        })

    # 6. Upsert in batches
    #    Using upsert (not add) so the script is idempotent on re-runs.
    total_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE
    logger.info(f"Upserting {len(chunks):,} chunks in {total_batches} batch(es) ...")

    for batch_num, (id_batch, doc_batch, meta_batch) in enumerate(
        zip(batch(ids, BATCH_SIZE),
            batch(documents, BATCH_SIZE),
            batch(metadatas, BATCH_SIZE)),
        start=1,
    ):
        try:
            collection.upsert(
                ids=id_batch,
                documents=doc_batch,
                metadatas=meta_batch,
            )
            logger.info(f"  Batch {batch_num}/{total_batches}: "
                        f"{len(id_batch)} chunks upserted")
        except Exception as exc:
            logger.error(f"  Batch {batch_num} failed: {exc}")
            raise

    # 7. Summary
    total_stored = collection.count()

    # Count chunks per jurisdiction from the loaded data
    by_jurisdiction: dict[str, int] = defaultdict(int)
    for m in metadatas:
        by_jurisdiction[m["jurisdiction"]] += 1

    print("\n" + "=" * 60)
    print("  EMBEDDING SUMMARY")
    print("=" * 60)
    print(f"  Model           : {EMBED_MODEL}")
    print(f"  Chunks embedded : {len(chunks):,}")
    print(f"  Docs in store   : {total_stored:,}  (collection total)")
    print(f"  Vectorstore     : {VECTORSTORE}")
    print()
    print(f"  {'Jurisdiction':<30} {'Chunks':>7}")
    print(f"  {'-'*30} {'-'*7}")
    for jurisdiction, count in sorted(by_jurisdiction.items()):
        print(f"  {jurisdiction:<30} {count:>7}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    embed()
