"""CSV projection tests: column layout, stripping, and staleness comparison."""

import csv
import io
import unittest
from pathlib import Path

import ptkit
from ptkit.config import COLUMNS
from ptkit.csvout import normalise_newlines, render, to_row
from ptkit.model import Question
from ptkit.text import TextRenderer

FIXTURES = Path(__file__).parent / "fixtures"


class ToRowTests(unittest.TestCase):
    def setUp(self):
        self.render_text = TextRenderer()
        self.question = Question(
            exam=1, number=99,
            stem="Does `Foo` compile? *Assume* nothing.",
            options={
                "A": "`true`",
                "B": "`false` — verified separately.",
                "C": "It *does not* compile.",
                "D": "Plain text.",
            },
            answer="A",
            explanation="`Foo` compiles fine. Verified with javac: output was fine.",
            domain="Applying Object-Oriented Principles",
        )

    def test_applies_stripping_to_all_learner_columns(self):
        row = to_row(self.question, self.render_text)
        self.assertEqual(row["Question"], "Does Foo compile? Assume nothing.")
        self.assertEqual(row["Answer Option 1"], "true")
        self.assertEqual(row["Answer Option 2"], "false — verified separately.")
        self.assertEqual(row["Answer Option 3"], "It does not compile.")
        self.assertEqual(row["Overall Explanation"], "Foo compiles fine.")

    def test_emits_every_template_column_including_the_unused_ones(self):
        # Udemy's template instructions require unused columns to stay
        # present, so Explanation 1-6 and Answer Option 5-6 are emitted empty
        # rather than dropped.
        row = to_row(self.question, self.render_text)
        self.assertEqual(sorted(row), sorted(COLUMNS))
        self.assertEqual(row["Answer Option 5"], "")
        self.assertEqual(row["Explanation 1"], "")

    def test_domain_names_override_translates_only_the_domain_column(self):
        self.question.domain_number = 3
        row = to_row(self.question, self.render_text, domain_names={3: "Traduzido"})
        self.assertEqual(row["Domain"], "Traduzido")
        self.assertEqual(row["Question"], "Does Foo compile? Assume nothing.")

    def test_domain_names_override_falls_back_for_an_untagged_question(self):
        row = to_row(self.question, self.render_text, domain_names={3: "Traduzido"})
        self.assertEqual(row["Domain"], "Applying Object-Oriented Principles")

    def test_option_explanations_populate_the_matching_explanation_column(self):
        self.question.option_explanations = {
            "A": "Right: `true` — verified separately.",
            "B": "Wrong: never `false`.",
            "C": "Wrong: it compiles.",
            "D": "Wrong: not plain text.",
        }
        row = to_row(self.question, self.render_text)
        self.assertEqual(row["Explanation 1"], "Right: true — verified separately.")
        self.assertEqual(row["Explanation 2"], "Wrong: never false.")
        self.assertEqual(row["Explanation 3"], "Wrong: it compiles.")
        self.assertEqual(row["Explanation 4"], "Wrong: not plain text.")


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = ptkit.load(FIXTURES / "course.toml")
        cls.questions = ptkit.parse_master(cls.config)

    def test_header_matches_the_udemy_template(self):
        with (FIXTURES / "PracticeTestBulkQuestionUploadTemplate_V2.2.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            template_header = next(csv.reader(handle))
        self.assertEqual(template_header, COLUMNS)

    def test_rows_are_crlf_terminated_but_embedded_newlines_stay_lf(self):
        text = render(self.questions, 1, self.config)
        self.assertTrue(text.startswith("Question,Question Type"))
        self.assertIn("\r\n", text)
        # The code snippet inside a quoted Question field keeps bare LF.
        body = text.split("\r\n", 1)[1]
        self.assertIn("\n", body.replace("\r\n", ""))

    def test_only_the_requested_exam_is_rendered(self):
        rows = list(csv.DictReader(io.StringIO(render(self.questions, 2, self.config))))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Domain"], "Fifth Domain")

    def test_question_type_and_answer_index(self):
        rows = list(csv.DictReader(io.StringIO(render(self.questions, 1, self.config))))
        self.assertEqual({r["Question Type"] for r in rows}, {"multiple-choice"})
        self.assertEqual([r["Correct Answers"] for r in rows], ["1", "2"])


class NewlineComparisonTests(unittest.TestCase):
    """`ptkit generate --check` and the csv-sync check compare through the
    same normaliser, so the two commands can never contradict each other
    about whether the CSVs are current. Before the kit they did: validate.py
    normalised line endings and generate_csvs.py --check compared raw bytes,
    so an LF-normalised commit was simultaneously "in sync" and "DIFFERS".
    """

    def test_crlf_checkout_is_not_reported_as_stale(self):
        generated = "a,b\r\nc,d\r\n"
        on_disk = "a,b\nc,d\n"
        self.assertEqual(normalise_newlines(generated), normalise_newlines(on_disk))

    def test_real_content_drift_is_still_caught(self):
        self.assertNotEqual(
            normalise_newlines("a,b\r\nc,d\r\n"),
            normalise_newlines("a,b\nc,DIFFERENT\n"),
        )


if __name__ == "__main__":
    unittest.main()
