"""
Tests for rag_pipeline.py.

Everything here is pure logic — no vector store, no embedding model, no network.
HealdarRAG instances are built with object.__new__ so __init__ never runs.
"""

import unittest

import groq

import config
import rag_pipeline as rp
from rag_pipeline import (
    JURISDICTION_MAP,
    HealdarRAG,
    ModelUnavailableError,
    RAGAnswer,
    RateLimitError,
    ServiceUnavailableError,
)
from retrieval import Passage, RetrievalResult


def _bare_rag() -> HealdarRAG:
    """A HealdarRAG with no __init__ — safe for testing pure helpers."""
    return object.__new__(HealdarRAG)


def _passage(text="body", fname="Doc.pdf", jx="SFDA", page=1, distance=0.3):
    return Passage(
        chunk_id=f"{fname}::p{page}::c0",
        text=text, filename=fname, jurisdiction=jx,
        page_number=page, distance=distance,
    )


class TestJurisdictionMap(unittest.TestCase):

    def test_all_key_exists_and_is_unfiltered(self):
        self.assertIn("all", JURISDICTION_MAP)
        self.assertEqual(JURISDICTION_MAP["all"], [])

    def test_required_aliases_present(self):
        for alias in ("eu", "sfda", "ksa", "qatar", "uae", "fda", "usa"):
            self.assertIn(alias, JURISDICTION_MAP, f"missing alias: {alias}")

    def test_non_all_aliases_have_values(self):
        for key, values in JURISDICTION_MAP.items():
            if key != "all":
                self.assertTrue(values, f"'{key}' maps to an empty list")

    def test_saudi_alias_covers_every_saudi_regulator(self):
        # SFDA regulates the device, SDAIA governs the data and the AI itself,
        # and NHIC sets health-information standards. The UI offers one "Saudi
        # Arabia" option, so it has to search all three -- it previously
        # searched only SFDA while the README advertised SDAIA coverage.
        self.assertEqual(
            set(JURISDICTION_MAP["sfda"]), {"KSA_SFDA", "KSA_SDAIA", "KSA_NHIC"}
        )

    def test_every_mapped_value_exists_in_the_corpus(self):
        """Guards against advertising a jurisdiction with no documents."""
        import json

        import config

        chunks = json.loads(config.CHUNKS_FILE.read_text(encoding="utf-8"))
        present = {c["metadata"]["jurisdiction"] for c in chunks}
        mapped = {v for values in JURISDICTION_MAP.values() for v in values}
        missing = mapped - present
        self.assertEqual(missing, set(), f"mapped but not ingested: {missing}")

    def test_every_corpus_jurisdiction_is_reachable(self):
        """A folder nobody can select is a document nobody can find."""
        import json

        import config

        chunks = json.loads(config.CHUNKS_FILE.read_text(encoding="utf-8"))
        present = {c["metadata"]["jurisdiction"] for c in chunks}
        mapped = {v for values in JURISDICTION_MAP.values() for v in values}
        self.assertEqual(present - mapped, set(),
                         f"ingested but unreachable: {present - mapped}")

    def test_ksa_and_sfda_are_equivalent(self):
        self.assertEqual(JURISDICTION_MAP["ksa"], JURISDICTION_MAP["sfda"])

    def test_multi_body_jurisdictions_cover_all_their_regulators(self):
        # Asserting an exact count here just breaks every time a regulator is
        # added; what matters is that each named body is actually present.
        self.assertLessEqual(
            {"UAE_DHA_Dubai", "UAE_DoH_AbuDhabi", "UAE_Federal"},
            set(JURISDICTION_MAP["uae"]),
        )
        self.assertLessEqual(
            {"Qatar_MCIT", "Qatar_MOPH", "Qatar_NCSA"},
            set(JURISDICTION_MAP["qatar"]),
        )


class TestArabicDetection(unittest.TestCase):
    """A ratio, not a single character — see _is_arabic."""

    def test_plain_english_is_not_arabic(self):
        self.assertFalse(HealdarRAG._is_arabic("What are the MDR requirements?"))

    def test_arabic_question_is_arabic(self):
        self.assertTrue(HealdarRAG._is_arabic("ما هي متطلبات الجهاز الطبي؟"))

    def test_one_arabic_word_in_english_does_not_flip_it(self):
        # The old "contains any Arabic character" check sent this whole query
        # through the translate-out-and-back pipeline.
        self.assertFalse(
            HealdarRAG._is_arabic("What does the term تقنية mean in the SFDA guidance?")
        )

    def test_mostly_arabic_with_english_terms_is_arabic(self):
        self.assertTrue(
            HealdarRAG._is_arabic("ما هي متطلبات SaMD في لائحة MDR الأوروبية؟")
        )

    def test_digits_and_punctuation_only_is_not_arabic(self):
        self.assertFalse(HealdarRAG._is_arabic("2017/745 -- 120?"))

    def test_empty_string_is_not_arabic(self):
        self.assertFalse(HealdarRAG._is_arabic(""))


class TestCoverageExtraction(unittest.TestCase):

    def test_full_marker_stripped(self):
        text, coverage = HealdarRAG._extract_coverage("The answer.\n\nCOVERAGE: full")
        self.assertEqual(coverage, "full")
        self.assertNotIn("COVERAGE", text)
        self.assertEqual(text, "The answer.")

    def test_partial_marker_detected(self):
        text, coverage = HealdarRAG._extract_coverage("Partial answer.\nCOVERAGE: partial")
        self.assertEqual(coverage, "partial")
        self.assertNotIn("COVERAGE", text)

    def test_none_counts_as_partial(self):
        _, coverage = HealdarRAG._extract_coverage("x\nCOVERAGE: none")
        self.assertEqual(coverage, "partial")

    def test_markdown_decorated_marker_still_matched(self):
        _, coverage = HealdarRAG._extract_coverage("x\n**COVERAGE: partial**")
        self.assertEqual(coverage, "partial")

    def test_missing_marker_defaults_to_full(self):
        text, coverage = HealdarRAG._extract_coverage("Just an answer.")
        self.assertEqual(coverage, "full")
        self.assertEqual(text, "Just an answer.")

    def test_case_insensitive(self):
        _, coverage = HealdarRAG._extract_coverage("x\ncoverage: partial")
        self.assertEqual(coverage, "partial")

    def test_body_text_is_preserved(self):
        body = "Line one.\n\n- bullet [Source 1]\n\nLine two."
        text, _ = HealdarRAG._extract_coverage(f"{body}\n\nCOVERAGE: full")
        self.assertEqual(text, body)


class TestMergeByPage(unittest.TestCase):
    """Same-page chunks become one source, so citation numbers stay aligned."""

    def test_same_page_chunks_merge(self):
        merged = HealdarRAG._merge_by_page([
            _passage(text="first half", page=4),
            _passage(text="second half", page=4),
        ])
        self.assertEqual(len(merged), 1)
        self.assertIn("first half", merged[0].text)
        self.assertIn("second half", merged[0].text)

    def test_different_pages_stay_separate(self):
        merged = HealdarRAG._merge_by_page([_passage(page=4), _passage(page=5)])
        self.assertEqual(len(merged), 2)

    def test_same_page_different_files_stay_separate(self):
        merged = HealdarRAG._merge_by_page([
            _passage(fname="A.pdf", page=1),
            _passage(fname="B.pdf", page=1),
        ])
        self.assertEqual(len(merged), 2)

    def test_merged_keeps_the_best_distance(self):
        merged = HealdarRAG._merge_by_page([
            _passage(text="a", page=1, distance=0.40),
            _passage(text="b", page=1, distance=0.15),
        ])
        self.assertAlmostEqual(merged[0].distance, 0.15)

    def test_duplicate_text_not_repeated(self):
        merged = HealdarRAG._merge_by_page([
            _passage(text="same", page=1), _passage(text="same", page=1),
        ])
        self.assertEqual(merged[0].text, "same")

    def test_order_is_preserved(self):
        merged = HealdarRAG._merge_by_page([
            _passage(fname="A.pdf"), _passage(fname="B.pdf"), _passage(fname="C.pdf"),
        ])
        self.assertEqual([p.filename for p in merged], ["A.pdf", "B.pdf", "C.pdf"])

    def test_inputs_are_not_mutated(self):
        original = _passage(text="one", page=1)
        HealdarRAG._merge_by_page([original, _passage(text="two", page=1)])
        self.assertEqual(original.text, "one")


class TestBuildPrompt(unittest.TestCase):

    PASSAGES = [
        _passage(text="Chunk alpha about AI regulation.", fname="DocA.pdf", jx="SFDA"),
        _passage(text="Chunk beta about post-market.", fname="DocB.pdf",
                 jx="EU_MDR_MDCG", page=5),
    ]
    QUESTION = "What are the requirements?"

    def setUp(self):
        self.rag = _bare_rag()
        self.prompt = self.rag._build_prompt(self.QUESTION, self.PASSAGES)

    def test_contains_numbered_source_tags(self):
        self.assertIn("[Source 1]", self.prompt)
        self.assertIn("[Source 2]", self.prompt)

    def test_no_filename_in_source_labels(self):
        for line in self.prompt.splitlines():
            if line.startswith("[Source"):
                self.assertNotIn(".pdf", line)
                self.assertNotIn("|", line)

    def test_chunk_texts_present(self):
        self.assertIn("Chunk alpha about AI regulation.", self.prompt)
        self.assertIn("Chunk beta about post-market.", self.prompt)

    def test_question_present(self):
        self.assertIn(self.QUESTION, self.prompt)

    def test_ends_with_answer_marker(self):
        self.assertTrue(self.prompt.strip().endswith("ANSWER:"))

    def test_source_count_matches_passages(self):
        context = self.prompt.split("CONTEXT:")[1].split("QUESTION:")[0]
        tags = config.CITATION_RE.findall(context)
        self.assertEqual(len(tags), len(self.PASSAGES))

    def test_requests_a_coverage_marker(self):
        self.assertIn("COVERAGE", self.prompt)

    def test_history_included_when_given(self):
        prompt = self.rag._build_prompt(
            self.QUESTION, self.PASSAGES,
            history=[{"question_en": "earlier q", "answer_en": "earlier a"}],
        )
        self.assertIn("earlier q", prompt)
        self.assertIn("CONVERSATION HISTORY", prompt)

    def test_history_absent_when_not_given(self):
        self.assertNotIn("CONVERSATION HISTORY", self.prompt)


class TestReformulationHeuristic(unittest.TestCase):

    def test_pronoun_triggers_reformulation(self):
        self.assertTrue(HealdarRAG._needs_reformulation("What about it?"))

    def test_what_about_triggers_reformulation(self):
        self.assertTrue(HealdarRAG._needs_reformulation("What about the UAE?"))

    def test_self_contained_short_question_does_not(self):
        # Short but complete: rewriting it against stale history makes
        # retrieval worse and costs an extra round trip.
        self.assertFalse(
            HealdarRAG._needs_reformulation("SFDA post-market surveillance rules?")
        )

    def test_long_standalone_question_does_not(self):
        self.assertFalse(HealdarRAG._needs_reformulation(
            "What are the FDA requirements for a predetermined change control plan?"
        ))

    def test_very_short_fragment_does(self):
        self.assertTrue(HealdarRAG._needs_reformulation("and Qatar"))


class TestGroqErrorMapping(unittest.TestCase):
    """Typed SDK exceptions, not string matching on the message."""

    @staticmethod
    def _response(status):
        import httpx
        return httpx.Response(
            status_code=status, request=httpx.Request("POST", "https://api.groq.com")
        )

    def test_rate_limit_maps_to_rate_limit_error(self):
        exc = groq.RateLimitError("slow down", response=self._response(429), body=None)
        self.assertIsInstance(rp._wrap_groq_error(exc), RateLimitError)

    def test_connection_error_maps_to_service_unavailable(self):
        import httpx
        exc = groq.APIConnectionError(
            request=httpx.Request("POST", "https://api.groq.com")
        )
        self.assertIsInstance(rp._wrap_groq_error(exc), ServiceUnavailableError)

    def test_404_maps_to_model_unavailable(self):
        exc = groq.NotFoundError(
            "model does not exist", response=self._response(404), body=None
        )
        self.assertIsInstance(rp._wrap_groq_error(exc), ModelUnavailableError)

    def test_500_maps_to_service_unavailable(self):
        exc = groq.InternalServerError(
            "boom", response=self._response(500), body=None
        )
        self.assertIsInstance(rp._wrap_groq_error(exc), ServiceUnavailableError)

    def test_unknown_error_passes_through(self):
        exc = ValueError("something else")
        self.assertIs(rp._wrap_groq_error(exc), exc)


class TestRAGAnswer(unittest.TestCase):

    def test_defaults(self):
        ans = RAGAnswer(question="q", answer="a")
        self.assertFalse(ans.no_context)
        self.assertEqual(ans.sources, [])
        self.assertEqual(ans.quality, "ok")
        self.assertEqual(ans.coverage, "full")

    def test_sources_stored(self):
        src = [{"filename": "f.pdf", "jurisdiction": "SFDA", "page_number": 1}]
        ans = RAGAnswer(question="q", answer="a", sources=src)
        self.assertEqual(ans.sources[0]["filename"], "f.pdf")

    def test_is_weak_on_weak_quality(self):
        self.assertTrue(RAGAnswer(question="q", answer="a", quality="weak").is_weak)

    def test_is_weak_on_partial_coverage(self):
        self.assertTrue(RAGAnswer(question="q", answer="a", coverage="partial").is_weak)

    def test_not_weak_by_default(self):
        self.assertFalse(RAGAnswer(question="q", answer="a").is_weak)


class TestAskValidation(unittest.TestCase):

    def test_unknown_jurisdiction_raises_value_error(self):
        with self.assertRaises(ValueError):
            _bare_rag().ask("q", jurisdiction="atlantis")


class TestQueryPlanning(unittest.TestCase):
    """Case-style questions get searches that name the rule deciding them."""

    def test_parse_strips_numbering_and_bullets(self):
        raw = "1. MDR Annex VIII Rule 11\n- MDCG 2019-11 software classification\n* Rule 11 examples"
        self.assertEqual(
            HealdarRAG._parse_planned(raw, "q"),
            ["MDR Annex VIII Rule 11", "MDCG 2019-11 software classification", "Rule 11 examples"],
        )

    def test_parse_drops_duplicates_blanks_and_the_question(self):
        raw = "Which class?\n\nRule 11\nRule 11\n"
        self.assertEqual(HealdarRAG._parse_planned(raw, "Which class?"), ["Rule 11"])

    def test_parse_caps_the_number_of_queries(self):
        raw = "\n".join(f"query number {i}" for i in range(10))
        self.assertEqual(len(HealdarRAG._parse_planned(raw, "q")), config.PLANNED_QUERIES)

    def test_planner_failure_falls_back_to_the_question_alone(self):
        from unittest import mock
        rag = _bare_rag()
        rag._chat = mock.MagicMock(side_effect=RuntimeError("groq down"))
        self.assertEqual(rag._plan_queries("q"), [])

    def test_planning_can_be_disabled(self):
        from unittest import mock
        rag = _bare_rag()
        rag._chat = mock.MagicMock(return_value="Rule 11")
        with mock.patch.object(config, "QUERY_PLANNING", False):
            self.assertEqual(rag._plan_queries("q"), [])
        rag._chat.assert_not_called()

    def test_planner_is_told_the_jurisdiction(self):
        from unittest import mock
        rag = _bare_rag()
        rag._chat = mock.MagicMock(return_value="Rule 11 software classification")
        self.assertEqual(rag._plan_queries("Which class?", "eu"),
                         ["Rule 11 software classification"])
        kwargs = rag._chat.call_args.kwargs
        self.assertIn("(jurisdiction: EU)", kwargs["content"])
        self.assertEqual(kwargs["model"], config.GROQ_MODEL_PLANNER)


class TestAskWithPlanning(unittest.TestCase):
    """End to end through ask(), with retrieval and Groq mocked."""

    def _rag(self, first, chat_replies):
        from unittest import mock
        rag = _bare_rag()
        rag.answer_model = "answer-model"
        rag._retriever = mock.MagicMock()
        rag._retriever.search.return_value = first
        rag._retriever.search_many.return_value = RetrievalResult(
            [_passage(text="Rule 11 text", fname="MDCG_2019-11.pdf", jx="EU_MDCG")]
        )
        rag._chat = mock.MagicMock(side_effect=list(chat_replies))
        return rag

    def test_off_topic_question_refused_without_planning(self):
        rag = self._rag(RetrievalResult([], quality="no_match", best_distance=0.8), [])
        answer = rag.ask("How do I bake sourdough bread?", "eu")
        self.assertTrue(answer.no_context)
        rag._chat.assert_not_called()
        rag._retriever.search_many.assert_not_called()

    def test_planned_queries_join_the_search(self):
        rag = self._rag(
            RetrievalResult([_passage(text="FAQ text", jx="EU_MDCG")], quality="weak"),
            ["MDR Annex VIII Rule 11 software", "Most likely Class IIa [Source 1].\nCOVERAGE: full"],
        )
        answer = rag.ask("Which class is my retinal screening software?", "eu")
        queries = rag._retriever.search_many.call_args[0][0]
        self.assertEqual(queries, ["Which class is my retinal screening software?",
                                   "MDR Annex VIII Rule 11 software"])
        self.assertEqual(answer.sources[0]["filename"], "MDCG_2019-11.pdf")
        self.assertEqual(answer.coverage, "full")


class TestPromptAllowsReasoning(unittest.TestCase):
    """The model should apply the rules it is given, not refuse to conclude."""

    def test_invites_applying_rules_to_a_case(self):
        prompt = _bare_rag()._build_prompt("Which class?", TestBuildPrompt.PASSAGES)
        self.assertIn("apply the rules in the passages", prompt)
        self.assertIn("must come from them, with a citation", prompt)
        self.assertNotIn("using ONLY the CONTEXT", prompt)


class TestCanonicalCitations(unittest.TestCase):
    """gpt-oss writes 【Source 2】; everything downstream expects [Source 2]."""

    def test_lenticular_brackets(self):
        self.assertEqual(rp.canonical_citations("x 【Source 2】."), "x [Source 2].")

    def test_fullwidth_brackets(self):
        self.assertEqual(rp.canonical_citations("［Source 3］"), "[Source 3]")

    def test_grouped_citation_keeps_every_number(self):
        self.assertEqual(rp.canonical_citations("[Source 1, Source 3]"),
                         "[Source 1][Source 3]")

    def test_grouped_bare_numbers(self):
        self.assertEqual(rp.canonical_citations("【Source 1, 4】"),
                         "[Source 1][Source 4]")

    def test_trailing_detail_dropped(self):
        self.assertEqual(rp.canonical_citations("[Source 2: doc_2023.pdf | p.5]"),
                         "[Source 2]")

    def test_dagger_line_refs(self):
        self.assertEqual(rp.canonical_citations("【Source 1†L10-L12】"),
                         "[Source 1]")

    def test_other_brackets_untouched(self):
        text = "See [1] and 【note】 and (Source 2)."
        self.assertEqual(rp.canonical_citations(text), text)

    def test_shared_regex_matches_all_styles(self):
        found = config.CITATION_RE.findall("[Source 1] 【Source 2】 ［Source 3］")
        self.assertEqual(found, ["1", "2", "3"])


if __name__ == "__main__":
    unittest.main()
