"""Parser tests: the Domain prefix, option extraction, and error reporting."""

import unittest
from pathlib import Path

import ptkit
from ptkit.model import ParseError
from ptkit.parse import clean_stem, parse_master

FIXTURES = Path(__file__).parent / "fixtures"


class DomainPrefixTests(unittest.TestCase):
    """The "Domain N" prefix line feeds two different outputs.

    The digit always populates the CSV's own Domain column and never survives
    into the learner-facing stem. What happens to the *topic text* after it
    differs by form, and that difference is deliberate:

      * The parenthetical form is a category label in front of a real question
        sentence ("Domain 5 (Collections). What happens when this runs?"), so
        the label is redundant and is dropped.
      * The em-dash form is often the question's only prose ("Domain 5 -
        Duplicate elements in `Set.of`." on its own line, followed by nothing
        but a code block). Dropping it too -- which is what the parser used to
        do -- shipped 32 of one exam's 50 questions to Udemy as an
        unintroduced snippet, so it is kept as the stem's opening line.
    """

    def test_domain_marker_number_is_extracted(self):
        stem, domain_number = clean_stem(
            "Domain 5 — Some topic.\n\nWhat happens when this runs?"
        )
        self.assertEqual(domain_number, 5)

    def test_parenthetical_topic_label_is_dropped(self):
        stem, _ = clean_stem("Domain 5 (Collections). What happens when this runs?")
        self.assertTrue(stem.startswith("What happens"))
        self.assertNotIn("Collections)", stem)

    def test_em_dash_topic_sentence_is_kept_as_the_opening_line(self):
        stem, _ = clean_stem("Domain 5 — Collections deep dive.\n\nWhat happens?")
        self.assertTrue(stem.startswith("Collections deep dive"))

    def test_code_fence_markers_are_stripped_but_code_survives(self):
        stem, _ = clean_stem(
            "Domain 1 — T.\n\n```java\nint x = 1;\n```\n\nWhat prints?"
        )
        self.assertNotIn("```", stem)
        self.assertIn("int x = 1;", stem)

    def test_missing_prefix_is_a_parse_error_when_required(self):
        with self.assertRaises(ParseError):
            clean_stem("What happens when this runs?")

    def test_missing_prefix_is_allowed_when_the_course_opts_out(self):
        stem, domain_number = clean_stem(
            "What happens when this runs?", require_domain_prefix=False
        )
        self.assertEqual(stem, "What happens when this runs?")
        self.assertIsNone(domain_number)


class ParseMasterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = ptkit.load(FIXTURES / "course.toml")
        cls.questions = parse_master(cls.config)

    def test_parses_every_question_in_document_order(self):
        self.assertEqual([q.qid for q in self.questions],
                         ["E1Q01", "E1Q02", "E2Q01"])

    def test_no_stem_leaks_the_domain_marker(self):
        for q in self.questions:
            self.assertNotIn("Domain ", q.stem.split("\n")[0], q.qid)

    def test_domain_name_is_resolved_from_the_course_table(self):
        self.assertEqual(self.questions[0].domain, "Fifth Domain")
        self.assertEqual(self.questions[1].domain, "First Domain")

    def test_options_and_answer(self):
        first = self.questions[0]
        self.assertEqual(sorted(first.options), list("ABCD"))
        self.assertEqual(first.answer, "A")
        self.assertEqual(first.correct_index, 1)
        self.assertEqual(len(first.distractors), 3)

    def test_unknown_domain_number_is_a_parse_error(self):
        bad = FIXTURES / "questions-master.md"
        text = bad.read_text(encoding="utf-8").replace("Domain 5 (", "Domain 9 (")
        with self.assertRaises(ParseError):
            from ptkit.parse import parse_exam_grouped
            parse_exam_grouped(text, self.config)

    def test_missing_answer_line_is_a_parse_error(self):
        text = (FIXTURES / "questions-master.md").read_text(encoding="utf-8")
        text = text.replace("**Correct answer:** A", "", 1)
        from ptkit.parse import parse_exam_grouped
        with self.assertRaises(ParseError):
            parse_exam_grouped(text, self.config)


if __name__ == "__main__":
    unittest.main()
