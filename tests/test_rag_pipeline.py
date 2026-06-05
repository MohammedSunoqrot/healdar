"""
Tests for rag_pipeline.py:
  - JURISDICTION_MAP data integrity
  - HealdarRAG._build_filter  (pure logic, no DB/model needed)
  - HealdarRAG._build_prompt  (pure logic, no DB/model needed)
  - RAGAnswer dataclass
"""

import sys
import unittest
from pathlib import Path

CODE_DIR = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(CODE_DIR))

from rag_pipeline import JURISDICTION_MAP, RAGAnswer, HealdarRAG


def _bare_rag() -> HealdarRAG:
    """Create a HealdarRAG instance without calling __init__ (no DB or model)."""
    return object.__new__(HealdarRAG)


class TestJurisdictionMap(unittest.TestCase):

    def test_all_key_exists(self):
        self.assertIn("all", JURISDICTION_MAP)

    def test_all_is_empty_list(self):
        self.assertEqual(JURISDICTION_MAP["all"], [])

    def test_required_aliases_present(self):
        for alias in ("eu", "sfda", "qatar", "uae", "fda"):
            self.assertIn(alias, JURISDICTION_MAP, f"Missing alias: {alias}")

    def test_non_all_aliases_have_values(self):
        for key, values in JURISDICTION_MAP.items():
            if key != "all":
                self.assertTrue(len(values) > 0, f"'{key}' maps to empty list")

    def test_uae_maps_to_three_bodies(self):
        self.assertEqual(len(JURISDICTION_MAP["uae"]), 3)

    def test_qatar_maps_to_three_bodies(self):
        self.assertEqual(len(JURISDICTION_MAP["qatar"]), 3)


class TestBuildFilter(unittest.TestCase):

    def setUp(self):
        self.rag = _bare_rag()

    def test_all_returns_none(self):
        self.assertIsNone(self.rag._build_filter("all"))

    def test_eu_single_value(self):
        f = self.rag._build_filter("eu")
        self.assertEqual(f, {"jurisdiction": "EU_MDR_MDCG"})

    def test_sfda_single_value(self):
        f = self.rag._build_filter("sfda")
        self.assertEqual(f, {"jurisdiction": "SFDA"})

    def test_fda_single_value(self):
        f = self.rag._build_filter("fda")
        self.assertEqual(f, {"jurisdiction": "USA_FDA"})

    def test_qatar_uses_dollar_in(self):
        f = self.rag._build_filter("qatar")
        self.assertIn("$in", f["jurisdiction"])
        self.assertIn("Qatar_MOPH", f["jurisdiction"]["$in"])
        self.assertIn("Qatar_MCIT", f["jurisdiction"]["$in"])
        self.assertIn("Qatar_NCSA", f["jurisdiction"]["$in"])

    def test_uae_uses_dollar_in(self):
        f = self.rag._build_filter("uae")
        self.assertIn("$in", f["jurisdiction"])
        self.assertIn("UAE_DoH_AbuDhabi", f["jurisdiction"]["$in"])

    def test_invalid_jurisdiction_raises(self):
        with self.assertRaises((KeyError, ValueError)):
            self.rag._build_filter("invalid_jx")


class TestBuildPrompt(unittest.TestCase):

    CHUNKS = [
        {"text": "Chunk alpha about AI regulation.", "filename": "DocA.pdf", "jurisdiction": "SFDA", "page_number": 1},
        {"text": "Chunk beta about post-market.",    "filename": "DocB.pdf", "jurisdiction": "EU_MDR_MDCG", "page_number": 5},
    ]
    QUESTION = "What are the requirements?"

    def setUp(self):
        self.rag = _bare_rag()

    def test_contains_source_tags(self):
        prompt = self.rag._build_prompt(self.QUESTION, self.CHUNKS)
        self.assertIn("[Source 1]", prompt)
        self.assertIn("[Source 2]", prompt)

    def test_no_filename_in_source_labels(self):
        prompt = self.rag._build_prompt(self.QUESTION, self.CHUNKS)
        # The label line should NOT contain raw filenames
        label_lines = [l for l in prompt.splitlines() if l.startswith("[Source")]
        for line in label_lines:
            self.assertNotIn(".pdf", line, "Filename leaked into source label")
            self.assertNotIn("|", line, "Pipe-separated metadata leaked into source label")

    def test_chunk_texts_present(self):
        prompt = self.rag._build_prompt(self.QUESTION, self.CHUNKS)
        self.assertIn("Chunk alpha about AI regulation.", prompt)
        self.assertIn("Chunk beta about post-market.", prompt)

    def test_question_present(self):
        prompt = self.rag._build_prompt(self.QUESTION, self.CHUNKS)
        self.assertIn(self.QUESTION, prompt)

    def test_prompt_ends_with_answer_marker(self):
        prompt = self.rag._build_prompt(self.QUESTION, self.CHUNKS)
        self.assertTrue(prompt.strip().endswith("ANSWER:"))

    def test_source_count_matches_chunks(self):
        import re
        prompt = self.rag._build_prompt(self.QUESTION, self.CHUNKS)
        # Count only inside the CONTEXT section, not the system instructions
        # (which also say "e.g. [Source 1] or [Source 2]" as examples)
        context_section = prompt.split("CONTEXT:")[1].split("QUESTION:")[0]
        tags = re.findall(r'\[Source \d+\]', context_section)
        self.assertEqual(len(tags), len(self.CHUNKS))


class TestRAGAnswer(unittest.TestCase):

    def test_default_no_context_false(self):
        ans = RAGAnswer(question="q", answer="a")
        self.assertFalse(ans.no_context)

    def test_default_sources_empty_list(self):
        ans = RAGAnswer(question="q", answer="a")
        self.assertEqual(ans.sources, [])

    def test_no_context_flag(self):
        ans = RAGAnswer(question="q", answer="a", no_context=True)
        self.assertTrue(ans.no_context)

    def test_sources_stored(self):
        src = [{"filename": "f.pdf", "jurisdiction": "SFDA", "page_number": 1}]
        ans = RAGAnswer(question="q", answer="a", sources=src)
        self.assertEqual(len(ans.sources), 1)
        self.assertEqual(ans.sources[0]["filename"], "f.pdf")


if __name__ == "__main__":
    unittest.main()
