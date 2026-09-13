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


class TestQueryExpansion(unittest.TestCase):
    """Acronyms in a question must reach documents that spell them out."""

    def test_query_compounds_kept_and_split(self):
        toks = retrieval.tokenize("AI-based MDS-G010", split_compounds=True)
        for t in ("ai-based", "ai", "based", "mds-g010"):
            self.assertIn(t, toks)

    def test_corpus_compounds_kept_whole(self):
        self.assertEqual(retrieval.tokenize("MDS-G010 AI-based"), ["mds-g010", "ai-based"])

    def test_acronyms_expanded(self):
        q = "How does SFDA regulate AI-based SaMD?"
        out = retrieval.expand_query(q)
        self.assertTrue(out.startswith(q))
        self.assertIn("artificial intelligence", out)
        self.assertIn("software as a medical device", out)

    def test_no_duplicate_when_already_spelled_out(self):
        q = "AI (artificial intelligence) in devices"
        self.assertEqual(retrieval.expand_query(q), q)

    def test_each_expansion_once(self):
        out = retrieval.expand_query("AI and more AI")
        self.assertEqual(out.count("artificial intelligence"), 1)

    def test_lowercase_words_untouched(self):
        q = "the said email is mild"
        self.assertEqual(retrieval.expand_query(q), q)

    def test_no_acronyms_unchanged(self):
        self.assertEqual(retrieval.expand_query("What is Annex VIII?"), "What is Annex VIII?")


class TestSearchMany(unittest.TestCase):
    """Planned queries add evidence; only the user's own question admits it."""

    @staticmethod
    def _p(cid, dist):
        return retrieval.Passage(chunk_id=cid, text=cid, filename=f"{cid}.pdf",
                                 jurisdiction="EU_MDCG", page_number=1, distance=dist)

    @staticmethod
    def _retriever(*results):
        from unittest import mock
        r = retrieval.Retriever(object(), hybrid=False)
        r.search = mock.MagicMock(side_effect=list(results))
        return r

    def test_refusal_decided_by_the_first_query(self):
        r = self._retriever(
            retrieval.RetrievalResult([], quality="no_match", best_distance=0.7),
            retrieval.RetrievalResult([self._p("rule11", 0.2)], best_distance=0.2),
        )
        out = r.search_many(["cooking recipes", "MDR Annex VIII Rule 11"])
        self.assertFalse(out)
        self.assertEqual(out.quality, "no_match")
        self.assertEqual(r.search.call_count, 1)

    def test_planned_evidence_is_fused_in(self):
        r = self._retriever(
            retrieval.RetrievalResult([self._p("faq", 0.45), self._p("rule11", 0.50)],
                                      quality="weak", best_distance=0.45),
            retrieval.RetrievalResult([self._p("rule11", 0.25), self._p("examples", 0.30)],
                                      best_distance=0.25),
        )
        out = r.search_many(["case question", "MDR Annex VIII Rule 11"], ["EU_MDCG"], top_k=3)
        ids = [p.chunk_id for p in out.passages]
        self.assertEqual(ids, ["faq", "rule11", "examples"])
        self.assertAlmostEqual(out.passages[1].distance, 0.25)   # best of both searches
        self.assertEqual(out.quality, "ok")

    def test_question_top_results_never_displaced(self):
        r = self._retriever(
            retrieval.RetrievalResult([self._p("a", 0.4), self._p("b", 0.4), self._p("c", 0.4)],
                                      best_distance=0.4),
            retrieval.RetrievalResult([self._p("x", 0.3), self._p("y", 0.3)], best_distance=0.3),
            retrieval.RetrievalResult([self._p("x", 0.3), self._p("y", 0.3)], best_distance=0.3),
        )
        out = r.search_many(["q", "plan 1", "plan 2"], ["EU_MDCG"], top_k=3)
        self.assertEqual([p.chunk_id for p in out.passages], ["a", "b", "x"])

    def test_each_planned_query_keeps_its_top_hit(self):
        # "common" is a half-match for two queries; "z1" is the one page the
        # third query was aimed at. Summed-rank fusion would pick "common".
        r = self._retriever(
            retrieval.RetrievalResult([self._p("a", 0.4), self._p("b", 0.4)], best_distance=0.4),
            retrieval.RetrievalResult([self._p("x1", 0.3), self._p("common", 0.3)], best_distance=0.3),
            retrieval.RetrievalResult([self._p("y1", 0.3), self._p("common", 0.3)], best_distance=0.3),
            retrieval.RetrievalResult([self._p("z1", 0.2)], best_distance=0.2),
        )
        out = r.search_many(["q", "p1", "p2", "p3"], ["EU_MDCG"], top_k=5)
        self.assertEqual([p.chunk_id for p in out.passages], ["a", "b", "x1", "y1", "z1"])
        self.assertAlmostEqual(out.best_distance, 0.2)

    def test_duplicate_and_blank_queries_searched_once(self):
        r = self._retriever(retrieval.RetrievalResult([self._p("a", 0.3)], best_distance=0.3))
        r.search_many(["q", " q ", ""])
        self.assertEqual(r.search.call_count, 1)


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
    """EU is ~47% of the corpus; it must not crowd out an 'all' answer."""

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


class TestGroupBalancing(unittest.TestCase):
    """Balancing caps a jurisdiction, not each regulator folder inside it."""

    def test_country_split_across_folders_shares_one_quota(self):
        # Three Saudi folders: without grouping each would get its own quota
        # and Saudi Arabia would take every slot.
        pool = [_passage(jx=j, page=i, distance=0.10 + i / 100)
                for i, j in enumerate(["KSA_SFDA", "KSA_SDAIA", "KSA_NHIC",
                                       "KSA_SFDA", "KSA_SDAIA", "KSA_NHIC"])]
        pool += [_passage(jx="USA_FDA", page=1, distance=0.45)]
        groups = {"KSA_SFDA": "sfda", "KSA_SDAIA": "sfda", "KSA_NHIC": "sfda",
                  "USA_FDA": "fda"}
        r = Retriever(StubCollection(pool), hybrid=False, group_of=groups)
        res = r.search("anything", [], top_k=3, balance=True)
        seen = [groups[p.jurisdiction] for p in res.passages]
        self.assertLessEqual(seen.count("sfda"), config.MAX_PER_JURISDICTION)
        self.assertIn("fda", seen)

    def test_ungrouped_tags_are_their_own_group(self):
        pool = [_passage(jx="A", page=i, distance=0.1) for i in range(4)]
        pool += [_passage(jx="B", page=1, distance=0.3)]
        r = Retriever(StubCollection(pool), hybrid=False)
        res = r.search("anything", [], top_k=3, balance=True)
        self.assertIn("B", [p.jurisdiction for p in res.passages])
