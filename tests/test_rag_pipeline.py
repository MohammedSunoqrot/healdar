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
        rag._call = mock.MagicMock(side_effect=list(chat_replies))
        return rag

    def test_off_topic_question_refused_without_planning(self):
        rag = self._rag(RetrievalResult([], quality="no_match", best_distance=0.8), [])
        answer = rag.ask("How do I bake sourdough bread?", "eu")
        self.assertTrue(answer.no_context)
        rag._call.assert_not_called()
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


class TestNamedJurisdiction(unittest.TestCase):
    """A question that names its jurisdiction is searched there, even in "All" mode."""

    def named(self, q):
        return HealdarRAG._named_jurisdictions(q)

    def test_eu_mdr(self):
        self.assertEqual(self.named("Suggest its classification under the EU MDR."), ["eu"])

    def test_saudi_regulator(self):
        self.assertEqual(self.named("How does SFDA regulate AI-based SaMD?"), ["sfda"])
        self.assertEqual(self.named("What do Saudi hospitals need?"), ["sfda"])

    def test_us_pathways(self):
        self.assertEqual(self.named("Is a 510(k) enough in the US?"), ["fda"])

    def test_comparison_names_both(self):
        self.assertEqual(self.named("Compare the FDA and the EU AI Act on this."), ["eu", "fda"])

    def test_general_question_names_none(self):
        self.assertEqual(self.named("What are post-market surveillance requirements for AI devices?"), [])

    def test_everyday_words_are_not_acronyms(self):
        self.assertEqual(self.named("Who should tell us what the rules are?"), [])

    def test_all_mode_narrows_to_the_named_jurisdiction(self):
        from unittest import mock
        rag = _bare_rag()
        rag.answer_model = "answer-model"
        rag._retriever = mock.MagicMock()
        rag._retriever.search.return_value = RetrievalResult([], quality="no_match")
        rag.ask("Which class is this retinal screening software under the EU MDR?", "all")
        self.assertEqual(rag._retriever.search.call_args[0][1], rp.JURISDICTION_MAP["eu"])

    def test_explicit_selection_is_not_overridden(self):
        from unittest import mock
        rag = _bare_rag()
        rag.answer_model = "answer-model"
        rag._retriever = mock.MagicMock()
        rag._retriever.search.return_value = RetrievalResult([], quality="no_match")
        rag.ask("How does this compare with the EU MDR?", "sfda")
        self.assertEqual(rag._retriever.search.call_args[0][1], rp.JURISDICTION_MAP["sfda"])


class TestFollowUps(unittest.TestCase):
    """Follow-ups: rewritten to stand alone, and built on the pages already cited."""

    HISTORY = [{
        "question_en": "Suggest the class of my retinal screening software under the EU MDR.",
        "answer_en": "Most likely Class IIb under Rule 11 [Source 2]. It is software [Source 1].",
        "sources": [
            {"filename": "FAQ.pdf", "jurisdiction": "EU_MDCG", "page_number": 5,
             "text": "faq text", "relevance": 0.5},
            {"filename": "MDCG_2019-11.pdf", "jurisdiction": "EU_MDCG", "page_number": 18,
             "text": "Rule 11 text", "relevance": 0.7},
            {"filename": "Uncited.pdf", "jurisdiction": "EU_MDCG", "page_number": 3,
             "text": "uncited", "relevance": 0.6},
        ],
    }]
    STANDALONE = "Why would the retinal software be Class IIb rather than IIa under the EU MDR?"

    def test_parse_plan_takes_question_and_queries(self):
        raw = f"QUESTION: {self.STANDALONE}\nRule 11 serious deterioration\nMDCG 2019-11 examples"
        q, planned = HealdarRAG._parse_followup_plan(raw, "why IIb?")
        self.assertEqual(q, self.STANDALONE)
        self.assertEqual(planned, ["Rule 11 serious deterioration", "MDCG 2019-11 examples"])

    def test_parse_plan_without_question_line_keeps_the_original(self):
        q, planned = HealdarRAG._parse_followup_plan("Rule 11 criteria", "why IIb?")
        self.assertEqual(q, "why IIb?")
        self.assertEqual(planned, ["Rule 11 criteria"])

    def test_parse_plan_accepts_markup(self):
        q, _ = HealdarRAG._parse_followup_plan("**QUESTION:** Is it Class III?", "and III?")
        self.assertEqual(q, "Is it Class III?")

    def test_parse_plan_strips_markdown_from_the_question(self):
        q, _ = HealdarRAG._parse_followup_plan(
            "QUESTION: How would a **definitive diagnosis** change it?", "and if?")
        self.assertEqual(q, "How would a definitive diagnosis change it?")

    def test_carried_passages_are_the_cited_ones(self):
        carried = HealdarRAG._carried_passages(self.HISTORY, [])
        self.assertEqual([p.filename for p in carried], ["MDCG_2019-11.pdf", "FAQ.pdf"])
        self.assertAlmostEqual(carried[0].distance, 0.3)

    def test_carried_passages_respect_the_jurisdiction(self):
        self.assertEqual(HealdarRAG._carried_passages(self.HISTORY, ["KSA_SFDA"]), [])

    def test_extract_followups(self):
        text = ("Answer body [Source 1].\n\nFOLLOW-UPS:\n- What if it acts autonomously?\n"
                "- How does SFDA classify it? [Source 2]\n")
        body, followups = HealdarRAG._extract_followups(text)
        self.assertEqual(body, "Answer body [Source 1].")
        self.assertEqual(followups, ["What if it acts autonomously?", "How does SFDA classify it?"])

    def test_extract_followups_with_markup_and_a_cap(self):
        text = ("Body.\n**Suggested follow-ups:**\n1. First question here?\n"
                "2. Second question here?\n3. Third question here?\n4. Fourth question here?")
        body, followups = HealdarRAG._extract_followups(text)
        self.assertEqual(body, "Body.")
        self.assertEqual(len(followups), 3)

    def test_body_mentioning_follow_up_is_untouched(self):
        text = "Follow-up monitoring is required after market entry [Source 1]."
        self.assertEqual(HealdarRAG._extract_followups(text), (text, []))

    def test_extract_followups_as_gpt_oss_writes_them(self):
        # Seen live: a non-breaking hyphen, doubled bullets, a rule above.
        text = ("Body [Source 1].\n\n---\n\nFOLLOW‑UPS:\n"
                "- - What if it is coupled with a pump?\n- - Which PMS duties apply?\n")
        body, followups = HealdarRAG._extract_followups(text)
        self.assertEqual(body, "Body [Source 1].")
        self.assertEqual(followups, ["What if it is coupled with a pump?", "Which PMS duties apply?"])

    def test_extract_followups_bold_heading_without_colon(self):
        body, followups = HealdarRAG._extract_followups("Body.\n\n**FOLLOW-UPS**\n- Is it Class III then?")
        self.assertEqual((body, followups), ("Body.", ["Is it Class III then?"]))

    def test_followups_carry_no_markdown(self):
        # Seen live (Arabic): "... **screening** ..." on a button label.
        _, followups = HealdarRAG._extract_followups(
            "Body.\nFOLLOW-UPS:\n- How does **screening** change the class?")
        self.assertEqual(followups, ["How does screening change the class?"])

    def test_history_keeps_the_conclusion_of_a_long_answer(self):
        long_answer = "Rule 11 analysis step. " * 300 + "Conclusion: most likely Class IIb."
        prompt = _bare_rag()._build_prompt(
            "why?", TestBuildPrompt.PASSAGES,
            history=[{"question_en": "Which class?", "answer_en": long_answer}],
        )
        self.assertIn("most likely Class IIb", prompt)
        self.assertLess(len(prompt), len(long_answer))

    def test_history_in_prompt_drops_old_citation_numbers(self):
        prompt = _bare_rag()._build_prompt("why IIb?", TestBuildPrompt.PASSAGES,
                                           history=self.HISTORY, search_question=self.STANDALONE)
        history_part = prompt.split("CONTEXT:")[0]
        self.assertIn("Most likely Class IIb under Rule 11.", history_part)
        self.assertNotIn("[Source 2]", history_part)
        self.assertIn(f"(In full: {self.STANDALONE})", prompt)

    def _rag(self, chat_replies, first):
        from unittest import mock
        rag = _bare_rag()
        rag.answer_model = "answer-model"
        rag._retriever = mock.MagicMock()
        rag._retriever.search.return_value = first
        rag._retriever.search_many.return_value = RetrievalResult(
            [_passage(text="Rule 11 exceptions", fname="MDCG_2019-11.pdf", jx="EU_MDCG", page=19)]
        )
        rag._call = mock.MagicMock(side_effect=list(chat_replies))
        return rag

    def test_follow_up_end_to_end(self):
        rag = self._rag(
            [f"QUESTION: {self.STANDALONE}\nRule 11 serious deterioration",
             "A missed referral can cause serious deterioration [Source 1].\n"
             "FOLLOW-UPS:\n- What evidence does a Class IIb device need?\nCOVERAGE: full"],
            RetrievalResult([_passage(text="faq", jx="EU_MDCG")]),
        )
        answer = rag.ask("why IIb and not IIa?", "all", history=self.HISTORY)
        search_args = rag._retriever.search.call_args[0]
        self.assertEqual(search_args[0], self.STANDALONE)                 # gate judges the rewrite
        self.assertEqual(search_args[1], rp.JURISDICTION_MAP["eu"])      # ... which names the EU
        self.assertEqual(answer.search_question, self.STANDALONE)
        self.assertEqual(answer.followups, ["What evidence does a Class IIb device need?"])
        self.assertEqual((answer.sources[0]["filename"], answer.sources[0]["page_number"]),
                         ("MDCG_2019-11.pdf", 18))                         # carried forward, first
        self.assertEqual(rag._call.call_count, 2)                          # plan + answer only

    def test_off_topic_follow_up_still_refused(self):
        rag = self._rag(["QUESTION: How do I bake sourdough bread?"],
                        RetrievalResult([], quality="no_match"))
        answer = rag.ask("how do I bake sourdough bread?", "all", history=self.HISTORY)
        self.assertTrue(answer.no_context)
        rag._retriever.search_many.assert_not_called()
        self.assertEqual(rag._call.call_count, 1)


class TestDailyLimitFallback(unittest.TestCase):
    """A used-up daily allowance reroutes to the backup model instead of failing."""

    TPD = ("Error code: 429 - Rate limit reached for model `openai/gpt-oss-120b` in "
           "organization `org_x` service tier `on_demand` on tokens per day (TPD): Limit "
           "200000, Used 199653, Requested 4627. Please try again in 30m48.96s.")
    TPM = ("Rate limit reached for model `openai/gpt-oss-120b` on tokens per minute (TPM): "
           "Limit 8000, Used 4222, Requested 4482. Please try again in 5.28s.")

    def test_daily_limit_is_recognised(self):
        err = rp._rate_limit_from(self.TPD)
        self.assertTrue(err.daily)
        self.assertAlmostEqual(err.retry_after, 30 * 60 + 48.96, places=1)

    def test_minute_limit_is_not_daily(self):
        err = rp._rate_limit_from(self.TPM)
        self.assertFalse(err.daily)
        self.assertAlmostEqual(err.retry_after, 5.28, places=2)

    @staticmethod
    def _rag(*effects):
        from unittest import mock
        rag = _bare_rag()
        rag._call = mock.MagicMock(side_effect=list(effects))
        return rag

    def test_daily_limit_reroutes_to_the_backup(self):
        rag = self._rag(rp.RateLimitError("x", daily=True), "backup answer")
        text, used = rag._complete(model=config.GROQ_MODEL_LARGE, content="q",
                                   temperature=0, max_tokens=100)
        self.assertEqual((text, used), ("backup answer", config.GROQ_MODEL_FALLBACK))
        kwargs = rag._call.call_args.kwargs
        self.assertEqual(kwargs["model"], config.GROQ_MODEL_FALLBACK)
        self.assertEqual(kwargs["reasoning_effort"], "low")
        self.assertGreater(kwargs["max_tokens"], 100)

    def test_minute_limit_is_not_rerouted(self):
        rag = self._rag(rp.RateLimitError("x", daily=False))
        with self.assertRaises(rp.RateLimitError):
            rag._complete(model=config.GROQ_MODEL_LARGE, content="q", temperature=0, max_tokens=100)
        self.assertEqual(rag._call.call_count, 1)

    def test_backup_can_be_turned_off(self):
        from unittest import mock
        rag = self._rag(rp.RateLimitError("x", daily=True))
        with mock.patch.object(config, "GROQ_MODEL_FALLBACK", ""), \
                self.assertRaises(rp.RateLimitError):
            rag._complete(model=config.GROQ_MODEL_LARGE, content="q", temperature=0, max_tokens=100)

    def test_answer_records_the_backup_model(self):
        from unittest import mock
        rag = _bare_rag()
        rag.answer_model = config.GROQ_MODEL_LARGE
        rag._retriever = mock.MagicMock()
        found = RetrievalResult([_passage(text="Rule 11 text", jx="EU_MDCG")])
        rag._retriever.search.return_value = found
        rag._retriever.search_many.return_value = found
        rag._call = mock.MagicMock(side_effect=[
            "Rule 11 software classification",             # planner, main model
            rp.RateLimitError("x", daily=True),            # answer, main model: used up
            "Class IIa [Source 1].\nCOVERAGE: full",       # answer, backup model
        ])
        answer = rag.ask("Which class is my software under the EU MDR?", "eu")
        self.assertEqual(answer.model, config.GROQ_MODEL_FALLBACK)
        self.assertIn("Class IIa", answer.answer)


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
        # "(Source 2)" is converted on purpose (test_parenthesised_citations).
        text = "See [1] and 【note】 and (see Annex VIII)."
        self.assertEqual(rp.canonical_citations(text), text)

    def test_parenthesised_citations(self):
        # Seen live: "(Source 4)" left the answer with no reference list.
        self.assertEqual(rp.canonical_citations("is Class IIa (Source 4)."),
                         "is Class IIa [Source 4].")
        self.assertEqual(rp.canonical_citations("(Sources 1, 3)"), "[Source 1][Source 3]")

    def test_bare_mentions_are_linked_not_dropped(self):
        # Seen live: "Source 6 lists two exceptions" and "(Source 1 §1.4)"
        # showed as plain text with no reference behind them.
        self.assertEqual(rp.canonical_citations("Source 6 lists two exceptions."),
                         "Source [Source 6] lists two exceptions.")
        self.assertEqual(rp.canonical_citations("(Source 1 §1.4)"), "(Source [Source 1] §1.4)")
        self.assertEqual(rp.canonical_citations("(Source 1 describes the rule)"),
                         "(Source [Source 1] describes the rule)")

    def test_linking_is_idempotent(self):
        once = rp.canonical_citations("Source 6 lists [Source 2].")
        self.assertEqual(once, "Source [Source 6] lists [Source 2].")
        self.assertEqual(rp.canonical_citations(once), once)

    def test_shared_regex_matches_all_styles(self):
        found = config.CITATION_RE.findall("[Source 1] 【Source 2】 ［Source 3］")
        self.assertEqual(found, ["1", "2", "3"])


if __name__ == "__main__":
    unittest.main()
