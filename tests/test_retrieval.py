"""
Tests for retrieval.py — the fusion, gating and balancing logic.

These use a stub collection rather than the real vector store, so they run in
milliseconds and do not need the embedding model or committed index.
"""

import unittest

import config
import retrieval
from retrieval import Passage, Retriever


def _passage(jx="SFDA", page=1, distance=0.3, fname=None, **kw):
    return Passage(
        chunk_id=f"{fname or jx}::p{page}::c0",
        text=f"text {jx} {page}",
        filename=fname or f"{jx}_doc.pdf",
        jurisdiction=jx,
        page_number=page,
        distance=distance,
        **kw,
    )


class StubCollection:
    """Minimal stand-in for a Chroma collection."""

    def __init__(self, passages):
        self._passages = passages

    def query(self, query_texts, n_results, include, where=None):
        picked = self._passages
        if where:
            jx = where.get("jurisdiction")
            allowed = jx.get("$in") if isinstance(jx, dict) else [jx]
            picked = [p for p in picked if p.jurisdiction in allowed]
        picked = sorted(picked, key=lambda p: p.distance)[:n_results]
        return {
            "documents": [[p.text for p in picked]],
            "metadatas": [[{
                "filename": p.filename,
                "jurisdiction": p.jurisdiction,
                "page_number": p.page_number,
                "chunk_index": p.chunk_index,
            } for p in picked]],
            "distances": [[p.distance for p in picked]],
        }


class TestTokenize(unittest.TestCase):

    def test_lowercases(self):
        self.assertEqual(retrieval.tokenize("Article"), ["article"])

    def test_keeps_hyphenated_document_codes(self):
        self.assertIn("mds-g010", retrieval.tokenize("See MDS-G010 for guidance"))

    def test_keeps_slashed_regulation_numbers(self):
        self.assertIn("2017/745", retrieval.tokenize("Regulation (EU) 2017/745"))

    def test_splits_on_punctuation(self):
        self.assertEqual(
            retrieval.tokenize("Annex VIII, Rule 11."),
            ["annex", "viii", "rule", "11"],
        )

    def test_empty_string(self):
        self.assertEqual(retrieval.tokenize(""), [])


class TestRelevanceGate(unittest.TestCase):
    """Off-topic questions must return nothing, not five weak passages."""

    def test_irrelevant_results_are_dropped(self):
        far = [_passage(distance=0.9), _passage(page=2, distance=0.95)]
        r = Retriever(StubCollection(far), hybrid=False)
        res = r.search("anything", [])
        self.assertEqual(len(res.passages), 0)
        self.assertEqual(res.quality, "no_match")

    def test_relevant_results_are_kept(self):
        near = [_passage(distance=0.2), _passage(page=2, distance=0.25)]
        r = Retriever(StubCollection(near), hybrid=False)
        res = r.search("anything", [])
        self.assertEqual(len(res.passages), 2)
        self.assertEqual(res.quality, "ok")

    def test_borderline_results_flagged_weak(self):
        borderline = config.WEAK_DISTANCE + 0.01
        self.assertLess(borderline, config.MAX_DISTANCE)
        r = Retriever(StubCollection([_passage(distance=borderline)]), hybrid=False)
        res = r.search("anything", [])
        self.assertEqual(len(res.passages), 1)
        self.assertEqual(res.quality, "weak")

    def test_mixed_drops_only_the_far_ones(self):
        mixed = [_passage(distance=0.2), _passage(page=2, distance=0.95)]
        r = Retriever(StubCollection(mixed), hybrid=False)
        res = r.search("anything", [])
        self.assertEqual(len(res.passages), 1)
        self.assertLessEqual(res.passages[0].distance, config.MAX_DISTANCE)

    def test_best_distance_reported_even_when_nothing_passes(self):
        r = Retriever(StubCollection([_passage(distance=0.88)]), hybrid=False)
        res = r.search("anything", [])
        self.assertAlmostEqual(res.best_distance, 0.88)

    def test_result_is_falsy_when_empty(self):
        r = Retriever(StubCollection([_passage(distance=0.99)]), hybrid=False)
        self.assertFalse(r.search("anything", []))


class TestJurisdictionFilter(unittest.TestCase):

    def test_single_value_filter(self):
        self.assertEqual(Retriever._where(["SFDA"]), {"jurisdiction": "SFDA"})

    def test_multi_value_uses_dollar_in(self):
        where = Retriever._where(["SFDA", "KSA_SDAIA"])
        self.assertEqual(where["jurisdiction"]["$in"], ["SFDA", "KSA_SDAIA"])

    def test_empty_means_no_filter(self):
        self.assertIsNone(Retriever._where([]))

    def test_filter_is_applied(self):
        pool = [_passage(jx="SFDA", distance=0.2), _passage(jx="USA_FDA", distance=0.1)]
        r = Retriever(StubCollection(pool), hybrid=False)
        res = r.search("anything", ["SFDA"])
        self.assertTrue(all(p.jurisdiction == "SFDA" for p in res.passages))


class TestBalancing(unittest.TestCase):
    """EU is ~49% of the corpus; it must not crowd out an 'all' answer."""

    def test_weaker_jurisdiction_still_gets_a_slot(self):
        """A dominant corpus must not shut a smaller one out entirely."""
        pool = [_passage(jx="EU_MDR_MDCG", page=i, distance=0.10 + i / 100)
                for i in range(6)]
        pool += [_passage(jx="SFDA", page=1, distance=0.40)]
        r = Retriever(StubCollection(pool), hybrid=False)
        res = r.search("anything", [], top_k=5, balance=True)
        # Without balancing, all five slots would go to the six closer EU hits.
        self.assertIn("SFDA", [p.jurisdiction for p in res.passages])

    def test_every_jurisdiction_gets_its_turn_before_any_seconds(self):
        pool = [_passage(jx="EU_MDR_MDCG", page=i, distance=0.10 + i / 100)
                for i in range(6)]
        pool += [_passage(jx="SFDA", page=1, distance=0.40)]
        pool += [_passage(jx="USA_FDA", page=1, distance=0.45)]
        r = Retriever(StubCollection(pool), hybrid=False)
        res = r.search("anything", [], top_k=4, balance=True)
        seen = [p.jurisdiction for p in res.passages]
        self.assertLessEqual(seen.count("EU_MDR_MDCG"), config.MAX_PER_JURISDICTION)
        self.assertIn("SFDA", seen)
        self.assertIn("USA_FDA", seen)

    def test_cap_is_soft_rather_than_wasting_slots(self):
        """With only one jurisdiction available, fill the slots anyway."""
        pool = [_passage(jx="EU_MDR_MDCG", page=i, distance=0.10 + i / 100)
                for i in range(6)]
        pool += [_passage(jx="SFDA", page=1, distance=0.40)]
        r = Retriever(StubCollection(pool), hybrid=False)
        res = r.search("anything", [], top_k=5, balance=True)
        self.assertEqual(len(res.passages), 5)

    def test_backfills_when_cap_leaves_room(self):
        # Only one jurisdiction available — the cap must not starve the result.
        pool = [_passage(jx="EU_MDR_MDCG", page=i, distance=0.10 + i / 100)
                for i in range(6)]
        r = Retriever(StubCollection(pool), hybrid=False)
        res = r.search("anything", [], top_k=5, balance=True)
        self.assertEqual(len(res.passages), 5)

    def test_single_jurisdiction_search_is_not_balanced(self):
        pool = [_passage(jx="SFDA", page=i, distance=0.10 + i / 100) for i in range(5)]
        r = Retriever(StubCollection(pool), hybrid=False)
        res = r.search("anything", ["SFDA"], top_k=5)
        self.assertEqual(len(res.passages), 5)

    def test_respects_top_k(self):
        pool = [_passage(jx=f"JX{i}", page=1, distance=0.1) for i in range(10)]
        r = Retriever(StubCollection(pool), hybrid=False)
        self.assertEqual(len(r.search("q", [], top_k=3).passages), 3)


class TestPassage(unittest.TestCase):

    def test_relevance_is_inverse_of_distance(self):
        self.assertAlmostEqual(_passage(distance=0.25).relevance, 0.75)

    def test_relevance_clamped_to_zero(self):
        self.assertEqual(_passage(distance=1.8).relevance, 0.0)

    def test_source_dict_has_ui_keys(self):
        d = _passage().to_source_dict()
        for key in ("filename", "jurisdiction", "page_number", "text", "relevance"):
            self.assertIn(key, d)


if __name__ == "__main__":
    unittest.main()
