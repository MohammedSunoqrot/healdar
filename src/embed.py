"""
Healdar embedding pipeline — chunks.json -> ChromaDB.

  python src/embed.py            # upsert (idempotent)
  python src/embed.py --rebuild  # delete the store first, then build

The actual work lives in vectorstore.build(), which the app also calls to
repair an unusable index at startup. Keeping one build path means a store
rebuilt automatically is identical to one built here.
"""

import argparse
import logging

import config
import vectorstore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Healdar vector store.")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="delete the existing store before building",
    )
    args = parser.parse_args()

    chunks = vectorstore.load_chunks()
    logger.info("Loaded %d chunks from %s", len(chunks), config.CHUNKS_FILE)

    collection = vectorstore.build(chunks, wipe=args.rebuild, progress=True)
    by_jurisdiction = vectorstore.summarise(chunks)

    print("\n" + "=" * 60)
    print("  EMBEDDING SUMMARY")
    print("=" * 60)
    print(f"  Model           : {config.EMBED_MODEL}")
    print(f"  Chunks embedded : {len(chunks):,}")
    print(f"  Docs in store   : {collection.count():,}")
    print(f"  Vector store    : {config.VECTORSTORE}")
    print()
    print(f"  {'Jurisdiction':<30} {'Chunks':>7}")
    print(f"  {'-' * 30} {'-' * 7}")
    for jurisdiction, count in sorted(by_jurisdiction.items()):
        print(f"  {jurisdiction:<30} {count:>7}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
