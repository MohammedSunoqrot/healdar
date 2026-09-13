"""
Tests for ingest.py:
  - chunk_page (token-based text splitting)
  - extract_text_from_pdf (error handling for bad paths)
  - prettify_filename (via Path.stem)
"""

import unittest
from pathlib import Path

import config
import ingest

# Sample PDFs are not committed (data/raw_docs/ is gitignored), so the tests
# that need one skip when it is absent.
SAMPLE_PDF = config.RAW_DOCS_DIR / "SFDA" / "SFDA_MDS-G025_AI_Guidance_2025.pdf"


class TestChunkPage(unittest.TestCase):

    def test_short_text_returns_one_chunk(self):
        result = ingest.chunk_page("Short regulatory text.")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

    def test_long_text_returns_multiple_chunks(self):
        # ~2000-word text should split into multiple 500-token chunks
        long_text = "This is a regulatory requirement. " * 200
        result = ingest.chunk_page(long_text)
        self.assertGreater(len(result), 1)

    def test_chunks_are_non_empty_strings(self):
        result = ingest.chunk_page("Article 1. All AI systems shall comply. " * 50)
        for chunk in result:
            self.assertIsInstance(chunk, str)
            self.assertTrue(len(chunk.strip()) > 0)

    def test_empty_string_returns_empty(self):
        result = ingest.chunk_page("")
        self.assertEqual(result, [])

    def test_whitespace_only_returns_empty(self):
        result = ingest.chunk_page("   \n\n   ")
        self.assertEqual(result, [])

    def test_chunks_together_cover_original_content(self):
        text = "Word " * 300
        chunks = ingest.chunk_page(text)
        combined = " ".join(chunks)
        # Every unique word from the original should appear somewhere
        for word in text.split()[:10]:
            self.assertIn(word, combined)


class TestExtractTextFromPdf(unittest.TestCase):

    def test_nonexistent_file_returns_empty(self):
        result = ingest.extract_text_from_pdf(Path("/nonexistent/path/fake.pdf"))
        self.assertEqual(result, {})

    def test_returns_dict(self):
        result = ingest.extract_text_from_pdf(Path("/nonexistent/path/fake.pdf"))
        self.assertIsInstance(result, dict)

    def test_real_pdf_returns_pages(self):
        # Use an actual PDF from the project to test real extraction
        pdf_path = SAMPLE_PDF
        if not pdf_path.exists():
            self.skipTest("Sample PDF not available")
        result = ingest.extract_text_from_pdf(pdf_path)
        self.assertIsInstance(result, dict)
        self.assertGreater(len(result), 0)
        # All keys should be positive page numbers
        for page_num in result:
            self.assertGreater(page_num, 0)
        # All values should be non-empty strings
        for text in result.values():
            self.assertIsInstance(text, str)
            self.assertTrue(len(text.strip()) > 0)


class TestProcessPdf(unittest.TestCase):

    def test_missing_file_returns_empty_list(self):
        result = ingest.process_pdf(Path("/does/not/exist.pdf"), "TEST_JX")
        self.assertEqual(result, [])

    def test_chunk_record_structure(self):
        pdf_path = SAMPLE_PDF
        if not pdf_path.exists():
            self.skipTest("Sample PDF not available")
        records = ingest.process_pdf(pdf_path, "SFDA")
        self.assertGreater(len(records), 0)
        first = records[0]
        # Each record must have text and metadata keys
        self.assertIn("text", first)
        self.assertIn("metadata", first)
        meta = first["metadata"]
        self.assertIn("filename",     meta)
        self.assertIn("jurisdiction", meta)
        self.assertIn("page_number",  meta)
        self.assertIn("chunk_index",  meta)
        self.assertEqual(meta["jurisdiction"], "SFDA")

    def test_jurisdiction_tag_propagated(self):
        pdf_path = SAMPLE_PDF
        if not pdf_path.exists():
            self.skipTest("Sample PDF not available")
        records = ingest.process_pdf(pdf_path, "SFDA")
        for r in records:
            self.assertEqual(r["metadata"]["jurisdiction"], "SFDA")


if __name__ == "__main__":
    unittest.main()


class TestArabicExtractionQuality(unittest.TestCase):
    """
    Some Arabic PDFs extract with swapped ligature pairs under PyMuPDF
    ("عىل" for "على", "املعالجة" for "المعالجة"). ingest scores both
    extractors and keeps the one that reads as correct Arabic.
    """

    GOOD = "نص المادة على البيانات في هذا القانون التي تنظم المعالجة"
    BAD = "نص املادة عىل البيانات يف هذا القانون اليت تنظم املعالجة"

    def test_correct_text_scores_higher(self):
        self.assertGreater(ingest.arabic_quality(self.GOOD), ingest.arabic_quality(self.BAD))

    def test_corrupted_text_scores_negative(self):
        self.assertLess(ingest.arabic_quality(self.BAD), 0)

    def test_arabic_share(self):
        self.assertGreater(ingest.arabic_share(self.GOOD), 0.9)
        self.assertEqual(ingest.arabic_share("Plain English text"), 0.0)

    def test_english_has_no_arabic_quality_signal(self):
        self.assertEqual(ingest.arabic_quality("Plain English text only"), 0)
