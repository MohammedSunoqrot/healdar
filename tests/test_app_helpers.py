"""
Tests for pure-Python helper functions in app.py.
Streamlit is mocked at the module level so no Streamlit runtime is needed.
"""

import unittest

# sys.path and the streamlit stub are set up in conftest.py.
import app
import config


class TestPrettifyFilename(unittest.TestCase):

    def test_removes_extension(self):
        self.assertEqual(app.prettify_filename("document.pdf"), "document")

    def test_replaces_underscores(self):
        result = app.prettify_filename("SFDA_MDS-G010_AI-ML_Medical_Devices_Guidance_2023.pdf")
        self.assertEqual(result, "SFDA MDS-G010 AI-ML Medical Devices Guidance 2023")

    def test_eu_filename(self):
        result = app.prettify_filename("EU_AI_Act_2024-1689.pdf")
        self.assertEqual(result, "EU AI Act 2024-1689")

    def test_no_underscores(self):
        result = app.prettify_filename("plain.pdf")
        self.assertEqual(result, "plain")

    def test_no_extension_chars_leaked(self):
        result = app.prettify_filename("some_doc.pdf")
        self.assertNotIn(".pdf", result)

    def test_uae_filename(self):
        result = app.prettify_filename("UAE_DoH_Responsible_AI_Standard_V1_2025.pdf")
        self.assertEqual(result, "UAE DoH Responsible AI Standard V1 2025")


class TestJxColor(unittest.TestCase):

    def test_eu_color(self):
        self.assertEqual(app.jx_color("EU_MDCG"), "#003399")

    def test_sfda_color(self):
        self.assertEqual(app.jx_color("KSA_SFDA"), "#00843D")

    def test_uae_dha_color(self):
        self.assertEqual(app.jx_color("UAE_DHA_Dubai"), "#CC0001")

    def test_uae_doh_color(self):
        self.assertEqual(app.jx_color("UAE_DoH_AbuDhabi"), "#CC0001")

    def test_qatar_color(self):
        self.assertEqual(app.jx_color("Qatar_MOPH"), "#8D1B3D")

    def test_fda_color(self):
        self.assertEqual(app.jx_color("USA_FDA"), "#1A1A6E")

    def test_unknown_returns_default(self):
        # Unknown jurisdictions fall back to the "all" grey
        self.assertEqual(app.jx_color("UNKNOWN_BODY"), "#555B6E")


class TestTextToHtml(unittest.TestCase):

    def test_single_paragraph(self):
        result = app.text_to_html("Hello World")
        self.assertIn("<p>Hello World</p>", result)

    def test_double_newline_splits_paragraphs(self):
        result = app.text_to_html("Para 1\n\nPara 2")
        self.assertIn("<p>Para 1</p>", result)
        self.assertIn("<p>Para 2</p>", result)

    def test_single_newline_becomes_br(self):
        result = app.text_to_html("Line 1\nLine 2")
        self.assertIn("<br>", result)

    def test_html_chars_escaped(self):
        result = app.text_to_html("<b>bold</b> & more")
        self.assertNotIn("<b>", result)
        self.assertIn("&lt;b&gt;", result)
        self.assertIn("&amp;", result)

    def test_empty_string(self):
        result = app.text_to_html("")
        self.assertEqual(result, "")

    def test_only_whitespace_excluded(self):
        result = app.text_to_html("   \n\n   ")
        self.assertEqual(result, "")


class TestSourceStripHtml(unittest.TestCase):

    SOURCES = [
        {"filename": "Doc_A.pdf", "jurisdiction": "KSA_SFDA",       "page_number": 1, "text": "text a"},
        {"filename": "Doc_B.pdf", "jurisdiction": "EU_MDCG", "page_number": 2, "text": "text b"},
        {"filename": "Doc_C.pdf", "jurisdiction": "USA_FDA",     "page_number": 3, "text": "text c"},
        {"filename": "Doc_D.pdf", "jurisdiction": "KSA_SFDA",        "page_number": 4, "text": "text d"},
    ]

    def test_empty_sources_returns_empty(self):
        self.assertEqual(app.source_strip_html([], "en", "test"), "")

    def test_all_sources_shown(self):
        indexed = [(i, s) for i, s in enumerate(self.SOURCES, start=1)]
        result = app.source_strip_html(indexed, "en", "card1")
        for n in range(1, 5):
            self.assertIn(f"[{n}]", result)

    def test_excerpt_ids_unique_per_card(self):
        indexed = [(1, self.SOURCES[0])]
        html_a = app.source_strip_html(indexed, "en", "cardA")
        html_b = app.source_strip_html(indexed, "en", "cardB")
        self.assertIn("rref-cardA-1", html_a)
        self.assertIn("rref-cardB-1", html_b)
        self.assertNotIn("rref-cardB-1", html_a)

    def test_jurisdiction_color_on_dot(self):
        indexed = [(1, self.SOURCES[0])]   # SFDA → #00843D
        result = app.source_strip_html(indexed, "en", "c")
        self.assertIn("#00843D", result)

    def test_original_source_numbers_preserved(self):
        # Non-contiguous indices must be rendered as-is
        indexed = [(3, self.SOURCES[0]), (5, self.SOURCES[1])]
        result = app.source_strip_html(indexed, "en", "c")
        self.assertIn("[3]", result)
        self.assertIn("[5]", result)
        self.assertNotIn("[1]", result)
        self.assertNotIn("[2]", result)

    def test_excerpt_text_in_output(self):
        indexed = [(1, self.SOURCES[0])]
        result = app.source_strip_html(indexed, "en", "c")
        self.assertIn("text a", result)

    def test_excerpt_hidden_by_default(self):
        indexed = [(1, self.SOURCES[0])]
        result = app.source_strip_html(indexed, "en", "c")
        self.assertIn("ref-excerpt", result)
        self.assertNotIn('class="ref-excerpt open"', result)

    def test_references_title_english(self):
        indexed = [(1, self.SOURCES[0])]
        result = app.source_strip_html(indexed, "en", "c")
        self.assertIn("References", result)

    def test_references_title_arabic(self):
        indexed = [(1, self.SOURCES[0])]
        result = app.source_strip_html(indexed, "ar", "c")
        self.assertIn("المصادر", result)


class TestTextToHtmlFootnotes(unittest.TestCase):

    def test_source_tag_becomes_superscript(self):
        result = app.text_to_html("See [Source 1] for details.")
        self.assertIn('<sup class="fn-ref"', result)
        self.assertIn("[1]", result)
        self.assertNotIn("[Source 1]", result)

    def test_tooltip_added_when_provided(self):
        result = app.text_to_html("See [Source 2].", {2: "Doc B · p.5"})
        self.assertIn('title="Doc B', result)

    def test_no_tooltip_when_not_provided(self):
        result = app.text_to_html("See [Source 1].")
        self.assertNotIn("title=", result)

    def test_multiple_sources_converted(self):
        result = app.text_to_html("[Source 1] and [Source 3].")
        self.assertIn("[1]", result)
        self.assertIn("[3]", result)
        self.assertNotIn("[Source", result)


class TestCitationParsing(unittest.TestCase):
    """The one shared pattern used by the pipeline, the UI and both exporters."""

    PATTERN = config.CITATION_RE

    def test_single_citation(self):
        nums = {int(n) for n in self.PATTERN.findall("[Source 1] explains this.")}
        self.assertEqual(nums, {1})

    def test_multiple_citations(self):
        nums = {int(n) for n in self.PATTERN.findall("[Source 2] and [Source 4] agree.")}
        self.assertEqual(nums, {2, 4})

    def test_no_citation(self):
        nums = {int(n) for n in self.PATTERN.findall("No references here.")}
        self.assertEqual(nums, set())

    def test_case_insensitive(self):
        nums = {int(n) for n in self.PATTERN.findall("[source 3] is cited.")}
        self.assertEqual(nums, {3})

    def test_duplicate_citation_counted_once(self):
        nums = {int(n) for n in self.PATTERN.findall("[Source 1] and [Source 1] again.")}
        self.assertEqual(nums, {1})


from rag_pipeline import RAGAnswer


def _make_result(q_en="q", a_en="a"):
    return RAGAnswer(question="q", answer="a", question_en=q_en, answer_en=a_en)


class TestBuildHistoryContext(unittest.TestCase):
    """Tests for app.build_history_context."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _single(q_en="q", a_en="a"):
        """Return a single-mode history entry dict."""
        return {"mode": "single", "result": _make_result(q_en=q_en, a_en=a_en)}

    @staticmethod
    def _compare():
        """Return a compare-mode history entry dict (no 'result' key)."""
        return {
            "mode": "compare",
            "result_l": _make_result(),
            "result_r": _make_result(),
        }

    # ------------------------------------------------------------------
    # Test cases
    # ------------------------------------------------------------------

    def test_empty_history_returns_none(self):
        self.assertIsNone(app.build_history_context([]))

    def test_single_valid_entry_returns_list_of_one(self):
        history = [self._single(q_en="what is MDR?", a_en="MDR is a regulation.")]
        result = app.build_history_context(history)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)

    def test_only_compare_entries_returns_none(self):
        history = [self._compare(), self._compare()]
        self.assertIsNone(app.build_history_context(history))

    def test_mix_of_single_and_compare_returns_only_single(self):
        history = [
            self._single(q_en="q1", a_en="a1"),
            self._compare(),
            self._single(q_en="q2", a_en="a2"),
        ]
        result = app.build_history_context(history)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)

    def test_more_than_three_single_entries_returns_last_three(self):
        history = [
            self._single(q_en=f"q{i}", a_en=f"a{i}")
            for i in range(1, 6)   # 5 valid single entries
        ]
        result = app.build_history_context(history)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 3)

    def test_entry_with_empty_question_en_is_skipped(self):
        history = [self._single(q_en="", a_en="some answer")]
        self.assertIsNone(app.build_history_context(history))

    def test_entry_with_empty_answer_en_is_skipped(self):
        history = [self._single(q_en="some question", a_en="")]
        self.assertIsNone(app.build_history_context(history))

    def test_returned_dicts_have_expected_keys(self):
        history = [self._single(q_en="q?", a_en="a!")]
        result = app.build_history_context(history)
        self.assertIsNotNone(result)
        self.assertIn("question_en", result[0])
        self.assertIn("answer_en", result[0])

    def test_returned_dicts_contain_correct_values(self):
        history = [self._single(q_en="what is SFDA?", a_en="SFDA is the Saudi regulator.")]
        result = app.build_history_context(history)
        self.assertIsNotNone(result)
        self.assertEqual(result[0]["question_en"], "what is SFDA?")
        self.assertEqual(result[0]["answer_en"], "SFDA is the Saudi regulator.")

    def test_last_three_entries_are_kept_in_order(self):
        # Build 5 entries; we expect the last 3 (indices 2-4) to be returned in order.
        history = [
            self._single(q_en=f"q{i}", a_en=f"a{i}")
            for i in range(5)
        ]
        result = app.build_history_context(history)
        self.assertIsNotNone(result)
        self.assertEqual([r["question_en"] for r in result], ["q2", "q3", "q4"])


class TestConversationHelpers(unittest.TestCase):
    """What a follow-up carries, and what the reader is shown about it."""

    def test_history_passes_sources_for_carrying_forward(self):
        result = _make_result(q_en="q", a_en="a [Source 1]")
        result.sources = [{"filename": "A.pdf"}]
        ctx = app.build_history_context([{"mode": "single", "result": result}])
        self.assertEqual(ctx[0]["sources"], [{"filename": "A.pdf"}])

    def test_rewritten_follow_up_is_shown(self):
        r = RAGAnswer(question="why IIb?", answer="a", question_en="why IIb?",
                      search_question="Why would the retinal software be Class IIb?")
        self.assertEqual(app.understood_as(r), "Why would the retinal software be Class IIb?")

    def test_unchanged_question_shows_nothing(self):
        r = RAGAnswer(question="What is MDR?", answer="a", question_en="What is MDR?",
                      search_question="what is MDR?")
        self.assertEqual(app.understood_as(r), "")

    def test_results_saved_before_the_field_existed(self):
        self.assertEqual(app.understood_as(RAGAnswer(question="q", answer="a")), "")


class TestNonAsciiCitationBrackets(unittest.TestCase):
    """Answers stored before canonicalisation still render and resolve."""

    SOURCES = [{"filename": "A.pdf", "jurisdiction": "KSA_SFDA", "page_number": 1, "text": "a"},
               {"filename": "B.pdf", "jurisdiction": "KSA_SFDA", "page_number": 2, "text": "b"}]

    def test_lenticular_citation_becomes_superscript(self):
        out = app.text_to_html("Scope applies 【Source 2】.")
        self.assertIn('<sup class="fn-ref"', out)
        self.assertNotIn("【", out)

    def test_lenticular_citation_resolves_to_source(self):
        picked = app.select_cited_sources("x 【Source 2】", self.SOURCES)
        self.assertEqual([i for i, _ in picked], [2])


if __name__ == "__main__":
    unittest.main()


class TestSelectCitedSources(unittest.TestCase):
    """
    Regression cover for the citation-misalignment bug.

    render_answer used to deduplicate result.sources by (filename, page) and
    re-number from 1 at display time. The prompt had already numbered the
    passages, so any dedupe shifted every later reference by one and dropped
    the highest-numbered citation entirely — a reader clicking [3] got the
    text the model had cited as [4].
    """

    SOURCES = [
        {"filename": "A.pdf", "jurisdiction": "KSA_SFDA",        "page_number": 1, "text": "a"},
        {"filename": "B.pdf", "jurisdiction": "EU_MDCG", "page_number": 2, "text": "b"},
        {"filename": "C.pdf", "jurisdiction": "USA_FDA",     "page_number": 3, "text": "c"},
        {"filename": "D.pdf", "jurisdiction": "KSA_SFDA",        "page_number": 4, "text": "d"},
        {"filename": "E.pdf", "jurisdiction": "Qatar_MOPH",  "page_number": 5, "text": "e"},
    ]

    def test_citation_maps_to_the_same_index_the_model_saw(self):
        picked = app.select_cited_sources("See [Source 3].", self.SOURCES)
        self.assertEqual(len(picked), 1)
        idx, src = picked[0]
        self.assertEqual(idx, 3)
        self.assertEqual(src["filename"], "C.pdf")

    def test_last_source_is_not_dropped(self):
        # The old dedupe-and-renumber path lost this one whenever any two
        # retrieved chunks shared a page.
        picked = app.select_cited_sources("See [Source 5].", self.SOURCES)
        self.assertEqual([i for i, _ in picked], [5])
        self.assertEqual(picked[0][1]["filename"], "E.pdf")

    def test_same_page_entries_do_not_shift_numbering(self):
        sources = [
            {"filename": "A.pdf", "jurisdiction": "KSA_SFDA", "page_number": 1, "text": "a"},
            {"filename": "A.pdf", "jurisdiction": "KSA_SFDA", "page_number": 1, "text": "a2"},
            {"filename": "B.pdf", "jurisdiction": "KSA_SFDA", "page_number": 9, "text": "b"},
        ]
        picked = app.select_cited_sources("[Source 3]", sources)
        self.assertEqual(picked[0][0], 3)
        self.assertEqual(picked[0][1]["filename"], "B.pdf")

    def test_multiple_citations_preserve_order(self):
        picked = app.select_cited_sources("[Source 4] then [Source 2].", self.SOURCES)
        self.assertEqual([i for i, _ in picked], [2, 4])

    def test_uncited_sources_are_omitted(self):
        picked = app.select_cited_sources("[Source 1]", self.SOURCES)
        self.assertEqual(len(picked), 1)

    def test_no_citations_returns_nothing(self):
        self.assertEqual(app.select_cited_sources("No references.", self.SOURCES), [])

    def test_repeated_citation_listed_once(self):
        picked = app.select_cited_sources("[Source 2] and [Source 2]", self.SOURCES)
        self.assertEqual(len(picked), 1)

    def test_legacy_verbose_tag_still_parsed(self):
        picked = app.select_cited_sources(
            "[Source 2: B.pdf | EU | p.2]", self.SOURCES
        )
        self.assertEqual([i for i, _ in picked], [2])

    def test_out_of_range_citation_falls_back_to_all_sources(self):
        # Rather than silently showing nothing, surface everything.
        picked = app.select_cited_sources("[Source 9]", self.SOURCES)
        self.assertEqual(len(picked), len(self.SOURCES))

    def test_empty_sources_is_safe(self):
        self.assertEqual(app.select_cited_sources("[Source 1]", []), [])
