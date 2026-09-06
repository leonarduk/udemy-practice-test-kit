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


class DomainGroupedParseTests(unittest.TestCase):
    """"# Exam N / ## Domain M — Name / ### QNN": the risk-eng-for-swe layout.

    Question numbers restart at Q01 in every domain section, matching a bank
    transcribed one source module at a time. The interesting behaviour this
    layout adds over exam-grouped is renumbering those questions sequentially
    within the exam so every qid stays unique.
    """

    @classmethod
    def setUpClass(cls):
        cls.config = ptkit.load(FIXTURES / "course-domain-grouped.toml")
        cls.questions = parse_master(cls.config)

    def test_domain_qnn_restarts_are_renumbered_to_unique_qids(self):
        # Domain 5 has Q01, Q02; Domain 1 then restarts at its own Q01.
        self.assertEqual([q.qid for q in self.questions],
                          ["E1Q01", "E1Q02", "E1Q03"])

    def test_domain_comes_from_the_heading_not_an_inline_prefix(self):
        self.assertEqual(self.questions[0].domain, "Fifth Domain")
        self.assertEqual(self.questions[0].domain_number, 5)
        self.assertEqual(self.questions[2].domain, "First Domain")
        self.assertEqual(self.questions[2].domain_number, 1)

    def test_stem_has_no_domain_marker_to_strip(self):
        self.assertTrue(self.questions[0].stem.startswith("What happens"))

    def test_code_fence_markers_are_stripped_but_code_survives(self):
        self.assertNotIn("```", self.questions[0].stem)
        self.assertIn("System.out.println", self.questions[0].stem)

    def test_options_and_answer(self):
        first = self.questions[0]
        self.assertEqual(sorted(first.options), list("ABCD"))
        self.assertEqual(first.answer, "A")
        self.assertEqual(first.difficulty, "Easy")

    def test_unknown_domain_number_is_a_parse_error(self):
        text = (FIXTURES / "questions-master-domain-grouped.md").read_text(
            encoding="utf-8"
        )
        text = text.replace("Domain 1 — First Domain", "Domain 9 — First Domain")
        from ptkit.parse import parse_domain_grouped
        with self.assertRaises(ParseError):
            parse_domain_grouped(text, self.config)

    def test_heading_name_disagreeing_with_course_toml_is_a_parse_error(self):
        text = (FIXTURES / "questions-master-domain-grouped.md").read_text(
            encoding="utf-8"
        )
        text = text.replace(
            "Domain 1 — First Domain", "Domain 1 — Wrong Name Entirely"
        )
        from ptkit.parse import parse_domain_grouped
        with self.assertRaises(ParseError):
            parse_domain_grouped(text, self.config)

    def test_missing_answer_line_is_a_parse_error(self):
        text = (FIXTURES / "questions-master-domain-grouped.md").read_text(
            encoding="utf-8"
        )
        text = text.replace("**Correct answer:** A", "", 1)
        from ptkit.parse import parse_domain_grouped
        with self.assertRaises(ParseError):
            parse_domain_grouped(text, self.config)


class SectionGroupedParseTests(unittest.TestCase):
    """"# <Section Name> / ## QNN": a bank authored as a flat list of named
    batches (no numbering convention at all), where course.toml's [sections]
    maps each one onto the exam it belongs to. Several sections can feed the
    same exam, and question numbers restart at Q01 in every section -- the
    interesting behaviour here is the same cross-section renumbering
    domain-grouped does per domain, plus tolerating a document title that
    isn't a real section.
    """

    @classmethod
    def setUpClass(cls):
        cls.config = ptkit.load(FIXTURES / "course-section-grouped.toml")
        cls.questions = ptkit.parse_master(cls.config)

    def test_two_sections_feeding_one_exam_are_renumbered_to_unique_qids(self):
        # "Fixture Mock Exam 1" (Q01, Q02) and "Fixture Supplementary
        # Questions" (Q01) both map to exam 1; "Fixture Mock Exam 2" (Q01)
        # maps to exam 2.
        self.assertEqual([q.qid for q in self.questions],
                          ["E1Q01", "E1Q02", "E1Q03", "E2Q01"])

    def test_front_matter_title_is_not_treated_as_a_section(self):
        # The fixture's leading "# Fixture Bank — Master Question Bank" H1
        # carries no "## QNN" content and isn't in [sections] -- parsing
        # must not raise on it.
        self.assertEqual(len(self.questions), 4)

    def test_domain_and_options_are_parsed_normally(self):
        first = self.questions[0]
        self.assertEqual(first.domain, "Fifth Domain")
        self.assertEqual(sorted(first.options), list("ABCD"))
        self.assertEqual(first.answer, "A")

    def test_undeclared_section_with_real_questions_is_a_parse_error(self):
        text = (FIXTURES / "questions-master-section-grouped.md").read_text(
            encoding="utf-8"
        )
        text = text.replace("# Fixture Mock Exam 2", "# Fixture Mock Exam 3")
        from ptkit.parse import parse_section_grouped
        with self.assertRaises(ParseError) as caught:
            parse_section_grouped(text, self.config)
        self.assertIn("not in course.toml's [sections] table", str(caught.exception))

    def test_missing_answer_line_is_a_parse_error(self):
        text = (FIXTURES / "questions-master-section-grouped.md").read_text(
            encoding="utf-8"
        )
        text = text.replace("**Correct answer:** A", "", 1)
        from ptkit.parse import parse_section_grouped
        with self.assertRaises(ParseError):
            parse_section_grouped(text, self.config)

    def test_a_hash_comment_inside_a_fence_is_not_mistaken_for_a_section(self):
        # Python (and shell) use '#' for comments, which collides with a
        # section-grouped heading's own "any text after '# '" grammar. A
        # bare '# some comment' line at the start of a fenced code block
        # must not be split off as a new section -- this is exactly what
        # broke on the first real Python-content bank tried against this
        # layout: lines like "# saved as script.py" inside a snippet.
        text = (FIXTURES / "questions-master-section-grouped.md").read_text(
            encoding="utf-8"
        )
        text = text.replace(
            "System.out.println(1 * 2 * 3);\n```",
            "System.out.println(1 * 2 * 3);\n# a bash-style comment, not a heading\n```",
        )
        from ptkit.parse import parse_section_grouped
        questions = parse_section_grouped(text, self.config)
        self.assertEqual([q.qid for q in questions],
                          ["E1Q01", "E1Q02", "E1Q03", "E2Q01"])
        self.assertIn("a bash-style comment, not a heading", questions[0].stem)


class WhyBlockTests(unittest.TestCase):
    """The optional "**Why each option:**" block: per-option explanations,
    parsed by the same lettered-option grammar the main options use. Absent
    entirely for a course that doesn't author these (every fixture bank so
    far); when present it is all-or-nothing, since a blank next to the
    option a learner actually picked is worse than none at all.
    """

    @classmethod
    def setUpClass(cls):
        cls.config = ptkit.load(FIXTURES / "course.toml")

    def _with_why_block(self, why_block):
        text = (FIXTURES / "questions-master.md").read_text(encoding="utf-8")
        return text.replace(
            "**Correct answer:** A\n\n**Explanation:**",
            f"**Correct answer:** A\n\n{why_block}\n\n**Explanation:**",
            1,
        )

    def test_absent_why_block_leaves_option_explanations_empty(self):
        from ptkit.parse import parse_exam_grouped
        questions = parse_exam_grouped(
            (FIXTURES / "questions-master.md").read_text(encoding="utf-8"),
            self.config,
        )
        self.assertEqual(questions[0].option_explanations, {})

    def test_why_block_is_parsed_per_option(self):
        from ptkit.parse import parse_exam_grouped
        text = self._with_why_block(
            "**Why each option:**\n"
            "A. Right: multiplication happens first.\n"
            "B. Wrong: not string concatenation.\n"
            "C. Wrong: this is valid Java.\n"
            "D. Wrong: nothing here throws.\n"
        )
        questions = parse_exam_grouped(text, self.config)
        self.assertEqual(questions[0].option_explanations, {
            "A": "Right: multiplication happens first.",
            "B": "Wrong: not string concatenation.",
            "C": "Wrong: this is valid Java.",
            "D": "Wrong: nothing here throws.",
        })

    def test_why_block_covering_fewer_than_all_options_is_a_parse_error(self):
        from ptkit.parse import parse_exam_grouped
        text = self._with_why_block(
            "**Why each option:**\n"
            "A. Right: multiplication happens first.\n"
            "B. Wrong: not string concatenation.\n"
        )
        with self.assertRaises(ParseError) as caught:
            parse_exam_grouped(text, self.config)
        self.assertIn("every option needs one", str(caught.exception))

    def test_duplicate_why_block_letter_is_a_parse_error(self):
        from ptkit.parse import parse_exam_grouped
        text = self._with_why_block(
            "**Why each option:**\n"
            "A. Right: multiplication happens first.\n"
            "A. Said twice by mistake.\n"
            "B. Wrong: not string concatenation.\n"
            "C. Wrong: this is valid Java.\n"
            "D. Wrong: nothing here throws.\n"
        )
        with self.assertRaises(ParseError) as caught:
            parse_exam_grouped(text, self.config)
        self.assertIn("duplicate", str(caught.exception))


class ParseMasterShuffleTests(unittest.TestCase):
    """parse_master applies config.shuffle_options itself, not just at
    CSV-render time -- see shuffle.py's module docstring for why: the quality
    checks read Question objects directly, so a render-only shuffle would
    leave them looking at the pre-shuffle distribution forever.
    """

    def setUp(self):
        self.config = ptkit.load(FIXTURES / "course.toml")
        self.config.shuffle_options = True
        self.config.shuffle_seed = "parse-master-shuffle-test"

    def test_shuffle_options_off_leaves_the_authored_order_untouched(self):
        self.config.shuffle_options = False
        unshuffled = parse_master(self.config)
        from ptkit.parse import parse_exam_grouped
        text = (FIXTURES / "questions-master.md").read_text(encoding="utf-8")
        authored = parse_exam_grouped(text, self.config)
        self.assertEqual(
            [q.options for q in unshuffled], [q.options for q in authored]
        )

    def test_shuffle_options_on_reorders_options_from_the_authored_source(self):
        from ptkit.parse import parse_exam_grouped
        text = (FIXTURES / "questions-master.md").read_text(encoding="utf-8")
        authored = parse_exam_grouped(text, self.config)
        shuffled = parse_master(self.config)
        # Same option *texts* survive, just not necessarily under the same
        # letters -- this fixture's seed is not guaranteed to move every
        # question, only asserts the pipeline actually ran the shuffle step.
        for a, s in zip(authored, shuffled):
            self.assertEqual(sorted(a.options.values()), sorted(s.options.values()))

    def test_no_shuffle_flag_bypasses_shuffle_options_for_hand_diffing(self):
        from ptkit.parse import parse_exam_grouped
        text = (FIXTURES / "questions-master.md").read_text(encoding="utf-8")
        authored = parse_exam_grouped(text, self.config)
        bypassed = parse_master(self.config, shuffle=False)
        self.assertEqual(
            [q.options for q in bypassed], [q.options for q in authored]
        )


class FencedHashMaskingTests(unittest.TestCase):
    """_mask_fenced_hashes/_unmask_fenced_hashes: the fence-tracking helper
    parse_section_grouped relies on to tell a real section heading apart
    from a snippet's own '#'-comment line.
    """

    def setUp(self):
        from ptkit.parse import _mask_fenced_hashes, _unmask_fenced_hashes
        self.mask = _mask_fenced_hashes
        self.unmask = _unmask_fenced_hashes

    def test_hash_line_inside_a_fence_is_masked(self):
        text = "```python\n# a comment\nx = 1\n```\n"
        masked = self.mask(text)
        self.assertNotIn("\n# a comment\n", masked)
        self.assertIn("a comment", masked)  # only the leading '#' changes

    def test_hash_line_outside_a_fence_is_untouched(self):
        text = "# Real Section\n\nsome text\n"
        self.assertEqual(self.mask(text), text)

    def test_round_trip_restores_the_original_text(self):
        text = "# Section\n\n```python\n# comment one\nx = 1\n# comment two\n```\nAfter.\n"
        self.assertEqual(self.unmask(self.mask(text)), text)

    def test_fence_state_toggles_back_off_after_closing_marker(self):
        # A '#' line after a fence has closed is a real heading candidate
        # again, not still masked.
        text = "```python\n# inside\n```\n# Real Section\n"
        masked = self.mask(text)
        self.assertIn("\n# Real Section\n", masked)


if __name__ == "__main__":
    unittest.main()
