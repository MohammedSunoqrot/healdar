"""
Healdar — vector store lifecycle.

The Chroma index is a build artefact, not a source of truth: chunks.json is.
This module opens the index, proves it actually works, and rebuilds it from
chunks.json when it does not.

Why the paranoia: the committed index is tracked with Git LFS. A clone without
"git lfs pull", a Docker COPY of pointer files, or a Chroma version bump all
leave a store that opens fine and reports the right document count, but throws
on the first query. The previous version caught that exception and returned an
empty result list, so every question was answered "no relevant information
found" -- a silent, total failure that looked like a content gap.
"""

from __future__ import annotations

import json
import logging
import shutil
from collections import defaultdict
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

import config

logger = logging.getLogger(__name__)

_LFS_POINTER_PREFIX = b"version https://git-lfs"
BATCH_SIZE = 500


class VectorStoreError(RuntimeError):
    """The index is unusable and could not be rebuilt."""


# ---------------------------------------------------------------------------
# Integrity checks
# ---------------------------------------------------------------------------

def is_lfs_pointer(path: Path) -> bool:
    """True if path is a Git LFS pointer stub rather than the real content."""
    try:
        if path.stat().st_size > 1024:      # real binaries are far larger
            return False
        with path.open("rb") as fh:
            return fh.read(len(_LFS_POINTER_PREFIX)) == _LFS_POINTER_PREFIX
    except OSError:
        return False


def find_lfs_pointers(root: Path) -> list[Path]:
    """Return every Git LFS pointer stub under root."""
    if not root.exists():
        return []
    return [p for p in root.rglob("*") if p.is_file() and is_lfs_pointer(p)]


def make_chunk_id(meta: dict) -> str:
    """Deterministic unique id for a chunk: filename + page + chunk index."""
    filename = str(meta["filename"]).replace(" ", "_")
    return f"{filename}::p{meta['page_number']}::c{meta['chunk_index']}"


def load_chunks(path: Path | None = None) -> list[dict]:
    """Load and validate chunks.json."""
    path = path or config.CHUNKS_FILE
    if not path.exists():
        raise VectorStoreError(
            f"chunks.json not found at {path}. Run 'python src/ingest.py' first."
        )
    if is_lfs_pointer(path):
        raise VectorStoreError(
            f"{path} is a Git LFS pointer, not real content. Run 'git lfs pull'."
        )
    with path.open(encoding="utf-8") as fh:
        chunks = json.load(fh)
    if not isinstance(chunks, list) or not chunks:
        raise VectorStoreError(f"Expected a non-empty list in {path}")
    return chunks


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(
    chunks: list[dict] | None = None,
    *,
    wipe: bool = False,
    progress: bool = False,
):
    """
    (Re)build the Chroma collection from chunks.json.

    Uses upsert, so re-running is idempotent. Pass wipe=True to delete an
    existing store first -- needed when the on-disk index is corrupt.
    """
    chunks = chunks if chunks is not None else load_chunks()

    if wipe and config.VECTORSTORE.exists():
        logger.warning("Removing unusable vector store at %s", config.VECTORSTORE)
        shutil.rmtree(config.VECTORSTORE, ignore_errors=True)

    config.VECTORSTORE.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(config.VECTORSTORE))
    ef = SentenceTransformerEmbeddingFunction(model_name=config.EMBED_MODEL)
    collection = client.get_or_create_collection(
        name=config.COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    ids, documents, metadatas = [], [], []
    for chunk in chunks:
        meta = chunk["metadata"]
        ids.append(make_chunk_id(meta))
        documents.append(chunk["text"])
        # Chroma metadata values must be str / int / float / bool -- never None.
        metadatas.append({
            "jurisdiction": str(meta.get("jurisdiction", "unknown")),
            "filename":     str(meta.get("filename", "unknown")),
            "page_number":  int(meta.get("page_number", 0)),
            "chunk_index":  int(meta.get("chunk_index", 0)),
        })

    total_batches = (len(ids) + BATCH_SIZE - 1) // BATCH_SIZE
    logger.info("Embedding %d chunks in %d batch(es)...", len(ids), total_batches)
    for n, start in enumerate(range(0, len(ids), BATCH_SIZE), start=1):
        stop = start + BATCH_SIZE
        collection.upsert(
            ids=ids[start:stop],
            documents=documents[start:stop],
            metadatas=metadatas[start:stop],
        )
        if progress:
            print(f"  batch {n}/{total_batches}: {len(ids[start:stop])} chunks")

    return collection


def summarise(chunks: list[dict]) -> dict[str, int]:
    """Chunk count per jurisdiction, for build summaries."""
    counts: dict[str, int] = defaultdict(int)
    for c in chunks:
        counts[c["metadata"].get("jurisdiction", "unknown")] += 1
    return dict(counts)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def _smoke_test(collection) -> None:
    """
    Prove the index actually answers a query.

    collection.count() reads SQLite and succeeds even when the HNSW segment is
    corrupt, so counting is not enough -- we have to issue a real query.
    """
    collection.query(query_texts=["test"], n_results=1, include=["distances"])


def load_collection(allow_rebuild: bool | None = None):
    """
    Open the vector store, verifying it works. Rebuild from chunks.json when it
    does not (and rebuilding is permitted).

    Raises VectorStoreError with an actionable message if it cannot be used.
    """
    allow_rebuild = (
        config.AUTO_REBUILD_VECTORSTORE if allow_rebuild is None else allow_rebuild
    )
    ef = SentenceTransformerEmbeddingFunction(model_name=config.EMBED_MODEL)

    def _open():
        client = chromadb.PersistentClient(path=str(config.VECTORSTORE))
        collection = client.get_collection(
            name=config.COLLECTION_NAME, embedding_function=ef
        )
        if collection.count() == 0:
            raise VectorStoreError("Vector store is empty.")
        _smoke_test(collection)
        return collection

    reason: str | None = None
    pointers = find_lfs_pointers(config.VECTORSTORE)

    if not (config.VECTORSTORE / "chroma.sqlite3").exists():
        reason = f"No vector store at {config.VECTORSTORE}"
    elif pointers:
        names = ", ".join(p.name for p in pointers[:3])
        reason = f"Git LFS pointer files instead of real data ({names})"
    else:
        try:
            return _open()
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"

    logger.warning("Vector store unusable -- %s", reason)

    if not allow_rebuild:
        raise VectorStoreError(
            f"Vector store unusable ({reason}). Run 'git lfs pull', or rebuild "
            "with 'python src/embed.py', or set HEALDAR_AUTO_REBUILD=1."
        )

    logger.warning("Rebuilding the index from %s -- this takes a minute.",
                   config.CHUNKS_FILE.name)
    build(wipe=True)
    try:
        return _open()
    except Exception as exc:
        raise VectorStoreError(
            f"Rebuilt the vector store but it is still unusable: {exc}"
        ) from exc
