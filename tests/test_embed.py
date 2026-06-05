"""
Tests for embed.py utility functions:
  - make_chunk_id
  - batch
"""

import sys
import unittest
from pathlib import Path

CODE_DIR = Path(__file__).parent.parent / "code"
sys.path.insert(0, str(CODE_DIR))

from embed import batch, make_chunk_id


class TestMakeChunkId(unittest.TestCase):

    def test_basic_id(self):
        meta = {"filename": "doc.pdf", "page_number": 1, "chunk_index": 0}
        self.assertEqual(make_chunk_id(meta), "doc.pdf::p1::c0")

    def test_spaces_in_filename_replaced(self):
        meta = {"filename": "my file.pdf", "page_number": 2, "chunk_index": 3}
        result = make_chunk_id(meta)
        self.assertNotIn(" ", result)
        self.assertIn("my_file.pdf", result)

    def test_page_and_chunk_in_id(self):
        meta = {"filename": "x.pdf", "page_number": 10, "chunk_index": 5}
        result = make_chunk_id(meta)
        self.assertIn("p10", result)
        self.assertIn("c5", result)

    def test_different_files_produce_different_ids(self):
        m1 = {"filename": "a.pdf", "page_number": 1, "chunk_index": 0}
        m2 = {"filename": "b.pdf", "page_number": 1, "chunk_index": 0}
        self.assertNotEqual(make_chunk_id(m1), make_chunk_id(m2))

    def test_same_file_different_page_different_id(self):
        m1 = {"filename": "a.pdf", "page_number": 1, "chunk_index": 0}
        m2 = {"filename": "a.pdf", "page_number": 2, "chunk_index": 0}
        self.assertNotEqual(make_chunk_id(m1), make_chunk_id(m2))

    def test_id_is_string(self):
        meta = {"filename": "f.pdf", "page_number": 1, "chunk_index": 0}
        self.assertIsInstance(make_chunk_id(meta), str)


class TestBatch(unittest.TestCase):

    def test_even_split(self):
        result = list(batch([1, 2, 3, 4], 2))
        self.assertEqual(result, [[1, 2], [3, 4]])

    def test_uneven_split(self):
        result = list(batch([1, 2, 3, 4, 5], 2))
        self.assertEqual(result, [[1, 2], [3, 4], [5]])

    def test_batch_larger_than_list(self):
        result = list(batch([1, 2, 3], 10))
        self.assertEqual(result, [[1, 2, 3]])

    def test_empty_list(self):
        result = list(batch([], 3))
        self.assertEqual(result, [])

    def test_batch_size_one(self):
        result = list(batch([10, 20, 30], 1))
        self.assertEqual(result, [[10], [20], [30]])

    def test_preserves_order(self):
        items = list(range(7))
        batches = list(batch(items, 3))
        reconstructed = [x for b in batches for x in b]
        self.assertEqual(reconstructed, items)


if __name__ == "__main__":
    unittest.main()
