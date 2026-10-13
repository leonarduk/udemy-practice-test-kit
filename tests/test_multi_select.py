"""Multi-select questions: "**Correct answers:** A, C" end to end.

A multi-select is its own Udemy question type ("multi-select", key written
"1,3,4" as in Udemy's own template example), not a single-choice question
with a list of one -- so "**Correct answers:** D" (plural, one letter) must
stay multi-select, and "**Correct answer:** A, C" (singular, two) is an
authoring mistake, not a silent upgrade.
"""

import csv
import io
import shutil
import tempfile
import types
import unittest
from pathlib import Path

import ptkit
from ptkit import checks as checks_pkg
from ptkit.model import ParseError, Question
from ptkit.report import Report
from ptkit.shuffle import shuffle_questions

FIXTURES = Path(__file__).parent / "fixtures"

MULTI_QUESTION = """
## Q03

Domain 1 — Which statements are true?

A. first true
B. false one
C. second true
D. false two

**Correct answers:** A, C

**Explanation:** A and C hold.

---
"""


def write_course(tmp, extra_question, counts="{ 1 = 3, 2 = 1 }"):
    shutil.copytree(FIXTURES, tmp, dirs_exist_ok=True)
    toml = (tmp / "course.toml").read_text(encoding="utf-8")
    (tmp / "course.toml").write_text(
        toml.replace("counts = { 1 = 2, 2 = 1 }", f"counts = {counts}"),
        encoding="utf-8",
    )
    master = (tmp / "questions-master.md").read_text(encoding="utf-8")
    head, exam2 = master.split("# Exam 2")
    (tmp / "questions-master.md").write_text(
        head.rstrip() + "\n" + extra_question + "\n# Exam 2" + exam2,
        encoding="utf-8",
    )
    return ptkit.load(tmp / "course.toml")


class MultiSelectTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class ParseTests(MultiSelectTestCase):
    def test_plural_answer_line_makes_a_multi_select_question(self):
        config = write_course(self.tmp, MULTI_QUESTION)
        question = ptkit.parse_master(config)[2]
        self.assertTrue(question.multi)
        self.assertEqual(question.answers, ("A", "C"))
        self.assertEqual(question.correct_indices, (1, 3))
        self.assertEqual(question.distractors, ["false one", "false two"])

    def test_plural_with_one_letter_stays_multi_select(self):
        config = write_course(
            self.tmp, MULTI_QUESTION.replace("A, C", "D")
        )
        question = ptkit.parse_master(config)[2]
        self.assertTrue(question.multi)
        self.assertEqual(question.answers, ("D",))

    def test_singular_answer_line_with_two_letters_is_a_parse_error(self):
        config = write_course(
            self.tmp, MULTI_QUESTION.replace("Correct answers:", "Correct answer:")
        )
        with self.assertRaises(ParseError) as caught:
            ptkit.parse_master(config)
        self.assertIn("Correct answers:", str(caught.exception))

    def test_a_repeated_letter_is_a_parse_error(self):
        config = write_course(self.tmp, MULTI_QUESTION.replace("A, C", "A, A"))
        with self.assertRaises(ParseError):
            ptkit.parse_master(config)

    def test_single_choice_questions_are_unchanged(self):
        config = write_course(self.tmp, MULTI_QUESTION)
        question = ptkit.parse_master(config)[0]
        self.assertFalse(question.multi)
        self.assertEqual(question.answer, "A")
        self.assertEqual(question.correct_index, 1)


class CsvTests(MultiSelectTestCase):
    def test_row_uses_udemys_multi_select_type_and_key_format(self):
        config = write_course(self.tmp, MULTI_QUESTION)
        questions = ptkit.parse_master(config)
        rows = list(csv.DictReader(io.StringIO(ptkit.render(questions, 1, config))))
        self.assertEqual(rows[2]["Question Type"], "multi-select")
        self.assertEqual(rows[2]["Correct Answers"], "1,3")
        self.assertEqual(rows[0]["Question Type"], "multiple-choice")

    def test_a_bank_with_multi_select_has_no_structural_failures(self):
        config = write_course(self.tmp, MULTI_QUESTION)
        questions = ptkit.parse_master(config)
        for exam in config.exams:
            config.csv_path(exam).write_bytes(
                ptkit.render(questions, exam, config).encode("utf-8")
            )
        report = Report(stream=io.StringIO())
        checks_pkg.run(config, questions, report)
        self.assertEqual(report.failures, [])

    def test_a_malformed_multi_select_key_in_the_csv_fails(self):
        config = write_course(self.tmp, MULTI_QUESTION)
        questions = ptkit.parse_master(config)
        for exam in config.exams:
            config.csv_path(exam).write_bytes(
                ptkit.render(questions, exam, config).encode("utf-8")
            )
        path = config.csv_path(1)
        path.write_text(
            path.read_text(encoding="utf-8").replace('"1,3"', '"1,1"'),
            encoding="utf-8",
        )
        report = Report(stream=io.StringIO())
        checks_pkg.run(config, questions, report)
        self.assertTrue(
            any("Correct Answers" in f for f in report.failures), report.failures
        )


class ShuffleTests(unittest.TestCase):
    def make(self, stem):
        return Question(
            exam=1, number=1, stem=stem,
            options={l: f"{stem} {l}" for l in "ABCDEF"},
            answer=None, answers=["B", "E"],
            explanation="x", domain="D",
            option_explanations={l: f"why {stem} {l}" for l in "ABCDEF"},
        )

    def test_correct_answers_and_explanations_travel_with_their_options(self):
        config = types.SimpleNamespace(shuffle_seed="s", option_letters="ABCDEF")
        moved = 0
        for i in range(20):
            original = self.make(f"Q{i}")
            [shuffled] = shuffle_questions([original], config)
            self.assertTrue(shuffled.multi)
            self.assertEqual(
                sorted(shuffled.options[a] for a in shuffled.answers),
                [f"Q{i} B", f"Q{i} E"],
            )
            for letter, text in shuffled.options.items():
                self.assertEqual(
                    shuffled.option_explanations[letter], "why " + text
                )
            moved += shuffled.answers != ("B", "E")
        self.assertGreater(moved, 10)


class KeyCardinalityTests(unittest.TestCase):
    def run_check(self, cardinalities):
        questions = [
            Question(exam=1, number=i, stem=f"s{i}",
                     options={l: l for l in "ABCD"}, answer=None,
                     answers=list("ABCD"[:n]), explanation="e", domain="d")
            for i, n in enumerate(cardinalities, 1)
        ]
        config = types.SimpleNamespace(exams=(1,))
        report = Report(stream=io.StringIO())
        ctx = types.SimpleNamespace(config=config, questions=questions,
                                    report=report,
                                    for_exam=lambda e: questions)
        from ptkit.checks.quality import check_multi_select_keys
        check_multi_select_keys(ctx)
        return report

    def test_uniform_cardinality_across_five_questions_warns(self):
        self.assertTrue(self.run_check([2, 2, 2, 2, 2]).warnings)

    def test_varied_cardinality_is_ok(self):
        self.assertFalse(self.run_check([1, 2, 3, 2, 1]).warnings)


if __name__ == "__main__":
    unittest.main()
