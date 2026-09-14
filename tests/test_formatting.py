"""
Tests for formatting.py -- no Markdown punctuation may reach the reader.

Models emit **bold**, ### headings and pipe tables even when told not to; the
previous renderer escaped them and displayed the raw asterisks and pipes.
"""

import re
import unittest

import formatting as fmt


def _cite(m):
    return f'<sup class="fn-ref">[{m.group(1)}]</sup>'


class TestHtml(unittest.TestCase):

    def test_bold_is_rendered_not_shown(self):
        out = fmt.to_html("This is **important** text.")
        self.assertIn("<strong>important</strong>", out)
        self.assertNotIn("**", out)

    def test_heading_hashes_removed(self):
        out = fmt.to_html("### Key requirements\nBody text.")
        self.assertIn('class="ans-h"', out)
        self.assertNotIn("#", out)

    def test_bold_only_line_becomes_heading(self):
        out = fmt.to_html("**SFDA core requirements:**\n\n- one\n- two")
        self.assertIn('<p class="ans-h">SFDA core requirements</p>', out)
        self.assertNotIn("**", out)

    def test_table_rendered_without_pipes(self):
        out = fmt.to_html("| Body | Rule |\n|---|---|\n| SFDA | MDS-G010 |")
        self.assertIn("<table>", out)
        self.assertIn("<th>Body</th>", out)
        self.assertIn("<td>MDS-G010</td>", out)
        self.assertNotIn("|", out)
        self.assertNotIn("---", out)

    def test_bullets_and_numbers(self):
        out = fmt.to_html("- a\n- b\n\n1. x\n2) y")
        self.assertIn("<ul><li>a</li><li>b</li></ul>", out)
        self.assertIn("<ol><li>x</li><li>y</li></ol>", out)

    def test_bullet_with_bold_lead(self):
        out = fmt.to_html("1. **Intended use** – determines status [Source 2]", cite=_cite)
        self.assertIn("<strong>Intended use</strong>", out)
        self.assertIn('<sup class="fn-ref">[2]</sup>', out)
        self.assertNotIn("**", out)

    def test_unpaired_asterisks_dropped(self):
        out = fmt.to_html("The SFDA states that **“If the device”")
        self.assertNotIn("**", out)

    def test_italic(self):
        self.assertIn("<em>must</em>", fmt.to_html("It *must* comply."))

    def test_underscores_in_identifiers_untouched(self):
        self.assertIn("MDS_G23_file", fmt.to_html("See MDS_G23_file for details."))

    def test_inline_code(self):
        out = fmt.to_html("Use `CITE1REF` tokens.")
        self.assertIn("<code>CITE1REF</code>", out)
        self.assertNotIn("`", out)

    def test_horizontal_rule_dropped(self):
        out = fmt.to_html("Para one\n\n---\n\nPara two")
        self.assertNotIn("---", out)
        self.assertEqual(out.count("<p>"), 2)

    def test_code_fence_dropped_content_kept(self):
        out = fmt.to_html("```\nplain content\n```")
        self.assertIn("plain content", out)
        self.assertNotIn("```", out)

    def test_indented_continuation_joins_list_item(self):
        out = fmt.to_html("- first item\n  continues here\n- second")
        self.assertIn("<li>first item continues here</li>", out)

    def test_html_is_escaped(self):
        out = fmt.to_html("<script>alert(1)</script> & more")
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)
        self.assertIn("&amp;", out)

    def test_single_newline_is_line_break(self):
        self.assertIn("<br>", fmt.to_html("Line 1\nLine 2"))

    def test_empty(self):
        self.assertEqual(fmt.to_html(""), "")
        self.assertEqual(fmt.to_html("  \n\n "), "")


class TestPlain(unittest.TestCase):

    def test_plain_has_no_markdown(self):
        text = "### Head\n**Bold** lead\n\n- one\n- **two**\n\n| a | b |\n|---|---|\n| 1 | 2 |"
        out = fmt.to_plain(text)
        self.assertNotIn("**", out)
        self.assertNotIn("#", out)
        self.assertNotRegex(out, r"^\|", "table pipes at line start")
        self.assertIn("• one", out)
        self.assertIn("• two", out)
        self.assertIn("a | b", out)


class TestPdfSafety(unittest.TestCase):

    def test_non_breaking_hyphen_folded(self):
        self.assertEqual(fmt.pdf_safe("post‑market"), "post-market")

    def test_narrow_space_folded(self):
        self.assertEqual(fmt.pdf_safe("section 5.4"), "section 5.4")

    def test_math_symbols(self):
        self.assertEqual(fmt.pdf_safe("≤ 5"), "<= 5")

    def test_winansi_kept(self):
        self.assertEqual(fmt.pdf_safe("“quoted” – …"), "“quoted” – …")

    def test_arabic_not_renderable(self):
        self.assertFalse(fmt.is_pdf_renderable("حماية البيانات الشخصية"))

    def test_english_renderable(self):
        self.assertTrue(fmt.is_pdf_renderable("Personal data protection"))

    def test_reportlab_escapes_and_bolds(self):
        out = fmt.to_reportlab("R&D **must** use < 5")
        self.assertIn("R&amp;D", out)
        self.assertIn("<b>must</b>", out)
        self.assertIn("&lt; 5", out)
        self.assertIsNone(re.search(r"\*\*", out))


class TestBlockquotes(unittest.TestCase):
    """Seen live: a quoted rule rendered with a literal ">" in front of it."""

    def test_quote_marker_dropped(self):
        out = fmt.to_html("> “Software intended to provide information” is class IIa.")
        self.assertNotIn("&gt;", out)
        self.assertIn("Software intended to provide information", out)

    def test_nested_marker_dropped_in_plain_text(self):
        self.assertEqual(fmt.to_plain(">> quoted rule"), "quoted rule")


class TestListContinuity(unittest.TestCase):
    """Blank lines between items used to restart every numbered item at 1."""

    def test_numbered_list_survives_blank_lines(self):
        out = fmt.to_html("1. first\n\n2. second\n\n3. third")
        self.assertEqual(out.count("<ol"), 1)
        self.assertEqual(out.count("<li>"), 3)

    def test_bullets_survive_blank_lines(self):
        out = fmt.to_html("- a\n\n- b")
        self.assertEqual(out.count("<ul>"), 1)

    def test_paragraph_after_list_closes_it(self):
        out = fmt.to_html("1. first\n\nClosing paragraph.")
        self.assertIn("</ol><p>Closing paragraph.</p>", out)

    def test_numbering_resumes_after_interruption(self):
        out = fmt.to_html("1. first\n- aside\n2. second")
        self.assertIn('<ol start="2">', out)

    def test_plain_numbering_uses_start(self):
        self.assertIn("3. third", fmt.to_plain("3. third"))


if __name__ == "__main__":
    unittest.main()
