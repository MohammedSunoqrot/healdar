"""PDF exports: an Arabic answer is typeset in Arabic, not swapped for English."""

import unittest
from unittest import mock

import export
import formatting

SRC_EN = {"filename": "EU_MDCG_2019-11_Software.pdf", "jurisdiction": "EU_MDCG",
          "page_number": 18,
          "text": "Software intended to provide information which is used to take decisions "
                  "with diagnosis or therapeutic purposes is classified as class IIa."}
SRC_AR = {"filename": "UAE_Federal_PDPL_Decree_Law_45_2021_AR.pdf", "jurisdiction": "UAE_Federal",
          "page_number": 12,
          "text": "يجب على المتحكم اتخاذ التدابير اللازمة لحماية البيانات الشخصية."}
AR_ANSWER = ("البرنامج هو برمجية جهاز طبي وفق MDR [Source 1].\n\n"
             "- يُصنَّف من الفئة Class IIa وفق القاعدة 11.\n"
             "- يخضع لتقييم المطابقة من جهة مُخطَرة.")


class TestArabicPdf(unittest.TestCase):

    def setUp(self):
        if not export.arabic_pdf_available():
            self.skipTest("Arabic PDF support is not installed")

    def test_arabic_answer_is_typeset_in_arabic(self):
        pdf = export.to_pdf("ما تصنيف البرنامج؟", AR_ANSWER, [(1, SRC_EN)], "EU",
                            question_en="What is the class?", answer_en="Class IIa [Source 1].")
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn(b"PlexSansArabic", pdf)

    def test_english_answer_needs_no_arabic_font(self):
        pdf = export.to_pdf("What is the class?", "Class IIa [Source 1].", [(1, SRC_EN)], "EU")
        self.assertNotIn(b"PlexSansArabic", pdf)

    def test_arabic_excerpt_in_an_english_report(self):
        # Used to print "see the Word export" instead of the source text.
        pdf = export.to_pdf("What does the UAE law require?",
                            "Controllers must protect personal data [Source 1].",
                            [(1, SRC_AR)], "UAE")
        self.assertIn(b"PlexSansArabic", pdf)

    def test_arabic_table_renders(self):
        answer = "| البند | الفئة |\n|---|---|\n| البرنامج | Class IIa |"
        self.assertTrue(export.to_pdf("سؤال", answer, [], "EU").startswith(b"%PDF"))

    def test_lines_fit_the_column(self):
        from reportlab.pdfbase.pdfmetrics import stringWidth
        lines = export.rtl_lines("حماية البيانات الشخصية " * 30, export.AR_FONT, 10, 200)
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(stringWidth(line, export.AR_FONT, 10), 200)

    def test_brackets_are_mirrored(self):
        # Seen in the first Arabic PDF: "(MDSW)" printed as ")MDSW(".
        line = export.rtl_lines("جهاز طبي (MDSW) لأنه", export.AR_FONT, 10, 500)[0]
        self.assertIn("(MDSW)", line)

    def test_citation_brackets_stay_whole(self):
        # Seen with the older ordering: "MDR [1]." printed as "1] MDR]."
        for text, expected in (("من MDR [1].", "[1]"),
                               ("الفئة IIb (القاعدة 11) وفق [Source 3].", "[Source 3]"),
                               ("وفق المادة 2(1) من MDR", "(1)")):
            line = export.rtl_lines(text, export.AR_FONT, 10, 800)[0]
            self.assertIn(expected, line, text)

    def test_ordering_degrades_instead_of_failing(self):
        with mock.patch.object(export, "_levels", side_effect=ValueError("format changed")):
            lines = export.rtl_lines("جهاز طبي (MDSW) لأنه", export.AR_FONT, 10, 500)
        self.assertEqual(len(lines), 1)


class TestPdfFallback(unittest.TestCase):

    def test_english_version_when_the_font_is_missing(self):
        with mock.patch.object(export, "arabic_pdf_available", return_value=False):
            pdf = export.to_pdf("ما تصنيف البرنامج؟", AR_ANSWER, [(1, SRC_EN)], "EU",
                                question_en="What is the class?",
                                answer_en="Class IIa [Source 1].")
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertNotIn(b"PlexSansArabic", pdf)


class TestTextDirection(unittest.TestCase):

    def test_arabic_answer_with_english_terms_is_rtl(self):
        self.assertTrue(formatting.is_rtl_text(AR_ANSWER))

    def test_english_answer_quoting_arabic_is_ltr(self):
        self.assertFalse(formatting.is_rtl_text("The UAE law (قانون) requires consent [Source 2]."))

    def test_empty_is_ltr(self):
        self.assertFalse(formatting.is_rtl_text(""))


if __name__ == "__main__":
    unittest.main()
