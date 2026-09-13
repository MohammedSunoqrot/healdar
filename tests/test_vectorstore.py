"""
Tests for vectorstore.py — chunk ids, LFS pointer detection, chunk loading.

The LFS-pointer tests guard a failure that actually shipped: the committed
Chroma index contained a 131-byte Git LFS stub instead of the real HNSW
metadata, so the store opened, reported 1978 documents, and then threw on
every query — which the old pipeline reported to users as "no relevant
information found".
"""

import json
import tempfile
import unittest
from pathlib import Path

import vectorstore
from vectorstore import VectorStoreError, is_lfs_pointer, make_chunk_id


class TestMakeChunkId(unittest.TestCase):

    def test_basic_id(self):
        meta = {"filename": "doc.pdf", "page_number": 1, "chunk_index": 0}
        self.assertEqual(make_chunk_id(meta), "doc.pdf::p1::c0")

    def test_spaces_replaced(self):
        meta = {"filename": "my file.pdf", "page_number": 2, "chunk_index": 3}
        result = make_chunk_id(meta)
        self.assertNotIn(" ", result)
        self.assertIn("my_file.pdf", result)

    def test_page_and_chunk_encoded(self):
        result = make_chunk_id({"filename": "x.pdf", "page_number": 10, "chunk_index": 5})
        self.assertIn("p10", result)
        self.assertIn("c5", result)

    def test_different_files_differ(self):
        a = make_chunk_id({"filename": "a.pdf", "page_number": 1, "chunk_index": 0})
        b = make_chunk_id({"filename": "b.pdf", "page_number": 1, "chunk_index": 0})
        self.assertNotEqual(a, b)

    def test_different_pages_differ(self):
        a = make_chunk_id({"filename": "a.pdf", "page_number": 1, "chunk_index": 0})
        b = make_chunk_id({"filename": "a.pdf", "page_number": 2, "chunk_index": 0})
        self.assertNotEqual(a, b)

    def test_is_deterministic(self):
        meta = {"filename": "f.pdf", "page_number": 7, "chunk_index": 2}
        self.assertEqual(make_chunk_id(meta), make_chunk_id(dict(meta)))

    def test_matches_retriever_id_scheme(self):
        """Dense and lexical hits must agree on ids or fusion silently fails."""
        from retrieval import Retriever
        meta = {"filename": "my file.pdf", "page_number": 3, "chunk_index": 1}
        self.assertEqual(make_chunk_id(meta), Retriever._meta_id(meta))


class TestLfsPointerDetection(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, data: bytes) -> Path:
        p = self.dir / name
        p.write_bytes(data)
        return p

    POINTER = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:43fba30deefcfb7f8f05b39f7be04f291daf8c70a6d149ea\n"
        b"size 107948\n"
    )

    def test_detects_a_pointer(self):
        self.assertTrue(is_lfs_pointer(self._write("index.pickle", self.POINTER)))

    def test_real_binary_is_not_a_pointer(self):
        self.assertFalse(is_lfs_pointer(self._write("data.bin", b"\x80\x04\x95" * 100)))

    def test_large_file_short_circuits(self):
        self.assertFalse(is_lfs_pointer(self._write("big.bin", b"x" * 2048)))

    def test_missing_file_is_not_a_pointer(self):
        self.assertFalse(is_lfs_pointer(self.dir / "nope.bin"))

    def test_empty_file_is_not_a_pointer(self):
        self.assertFalse(is_lfs_pointer(self._write("empty.bin", b"")))

    def test_find_pointers_walks_recursively(self):
        (self.dir / "seg").mkdir()
        (self.dir / "seg" / "index.pickle").write_bytes(self.POINTER)
        (self.dir / "seg" / "real.bin").write_bytes(b"\x00" * 4096)
        found = vectorstore.find_lfs_pointers(self.dir)
        self.assertEqual([p.name for p in found], ["index.pickle"])

    def test_find_pointers_on_missing_dir(self):
        self.assertEqual(vectorstore.find_lfs_pointers(self.dir / "gone"), [])


class TestLoadChunks(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_raises(self):
        with self.assertRaises(VectorStoreError):
            vectorstore.load_chunks(self.dir / "nope.json")

    def test_empty_list_raises(self):
        p = self.dir / "chunks.json"
        p.write_text("[]", encoding="utf-8")
        with self.assertRaises(VectorStoreError):
            vectorstore.load_chunks(p)

    def test_pointer_file_raises_with_actionable_message(self):
        p = self.dir / "chunks.json"
        p.write_bytes(TestLfsPointerDetection.POINTER)
        with self.assertRaises(VectorStoreError) as ctx:
            vectorstore.load_chunks(p)
        self.assertIn("git lfs pull", str(ctx.exception))

    def test_valid_file_loads(self):
        p = self.dir / "chunks.json"
        payload = [{"text": "t", "metadata": {
            "filename": "a.pdf", "jurisdiction": "SFDA",
            "page_number": 1, "chunk_index": 0}}]
        p.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(len(vectorstore.load_chunks(p)), 1)


class TestSummarise(unittest.TestCase):

    def test_counts_per_jurisdiction(self):
        chunks = [
            {"metadata": {"jurisdiction": "SFDA"}},
            {"metadata": {"jurisdiction": "SFDA"}},
            {"metadata": {"jurisdiction": "USA_FDA"}},
        ]
        self.assertEqual(vectorstore.summarise(chunks), {"SFDA": 2, "USA_FDA": 1})

    def test_empty(self):
        self.assertEqual(vectorstore.summarise([]), {})


if __name__ == "__main__":
    unittest.main()
