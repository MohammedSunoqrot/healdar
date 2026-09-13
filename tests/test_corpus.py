"""
Corpus integrity: the download manifest is the authoritative document list.

Guards a failure that happened during the v2 corpus refresh: the 2026 MDR
consolidation was downloaded alongside the superseded 2023 text, both were
ingested, and they then crowded each other in search results -- with the old
text citeable as if it were current. Anything ingested must be in the
manifest, so a leftover or hand-dropped file cannot slip in unnoticed.

These tests read chunks.json (committed), not data/raw_docs/ (gitignored), so
they run in CI.
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

import config

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "download_docs.py"


def _load_manifest():
    spec = importlib.util.spec_from_file_location("download_docs", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # Register before executing: the script declares @dataclass Doc under
    # `from __future__ import annotations`, and dataclasses resolves those
    # string annotations through sys.modules[cls.__module__].
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestManifest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.dd = _load_manifest()
        cls.manifest = {Path(d.dest).name for d in cls.dd.DOCS}
        chunks = json.loads(config.CHUNKS_FILE.read_text(encoding="utf-8"))
        cls.ingested = {c["metadata"]["filename"] for c in chunks}

    def test_every_ingested_document_is_in_the_manifest(self):
        stray = self.ingested - self.manifest
        self.assertEqual(
            stray, set(),
            f"ingested but not in scripts/download_docs.py: {sorted(stray)} -- "
            "a superseded version or a hand-dropped file?",
        )

    def test_manifest_destinations_are_unique(self):
        dests = [d.dest for d in self.dd.DOCS]
        dupes = {d for d in dests if dests.count(d) > 1}
        self.assertEqual(dupes, set())

    def test_every_manifest_entry_can_be_verified(self):
        """Each entry needs an identifier to check the PDF against."""
        missing = [d.dest for d in self.dd.DOCS if not d.expect]
        self.assertEqual(missing, [], "entries without an `expect` string")

    def test_only_one_consolidated_mdr(self):
        mdr = [n for n in self.ingested if n.startswith("EU_MDR_2017-745")]
        self.assertEqual(len(mdr), 1, f"superseded MDR text still ingested: {mdr}")


if __name__ == "__main__":
    unittest.main()
