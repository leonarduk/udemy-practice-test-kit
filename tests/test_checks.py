"""Check tests: the scorers, the keep-list, and the HTML-safety detector."""

import io
import shutil
import tempfile
import unittest
from pathlib import Path

import ptkit
from ptkit import checks as checks_pkg
from ptkit.checks.hygiene import build_private_repo_re, check_option_html
from ptkit.checks.quality import check_duplicates, naive_length_score
from ptkit.checks.structure import check_explanations_present, check_structure
from ptkit.model import Question
from ptkit.report import Report

FIXTURES = Path(__file__).parent / "fixtures"


def build_course(tmp, **toml_overrides):
    """Copy the fixture course into `tmp` and generate its CSVs."""
    shutil.copytree(FIXTURES, tmp, dirs_exist_ok=True)
    if toml_overrides:
        text = (tmp / "course.toml").read_text(encoding="utf-8")
        for old, new in toml_overrides.items():
            text = text.replace(old, new)
        (tmp / "course.toml").write_text(text, encoding="utf-8")
    config = ptkit.load(tmp / "course.toml")
    questions = ptkit.parse_master(config)
    for exam in config.exams:
        config.csv_path(exam).write_bytes(
            ptkit.render(questions, exam, config).encode("utf-8")
        )
    return config, questions


class CourseFixtureTestCase(unittest.TestCase):
    toml_overrides = {}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.config, self.questions = build_course(self.tmp, **self.toml_overrides)
        self.report = Report(stream=io.StringIO())
        self.ctx = checks_pkg.Context(self.config, self.questions, self.report)

    def tearDown(self):
        self._tmp.cleanup()


class OptionHtmlSafetyTests(CourseFixtureTestCase):
    """Udemy renders Answer Option cells as HTML, so `List<String>` in an
    option is parsed as an unknown tag and dropped -- the learner sees "a List
    of names", which is a different (and possibly correct-looking) statement.

    This check was written for the Python bank and lived only there. Moving it
    into the kit is the whole point of the kit: it found a real
    `List<PaymentGateway>` option in the Spring bank on its first run.
    """

    def test_angle_brackets_in_an_option_are_flagged(self):
        check_option_html(self.ctx)
        self.assertEqual(len(self.report.warnings), 1)
        self.assertIn("unescaped HTML", self.report.warnings[0])

    def test_escaped_option_is_clean(self):
        path = self.config.csv_path(2)
        path.write_bytes(
            path.read_bytes().replace(b"List<String>", b"List&lt;String&gt;")
        )
        self.ctx._csv_rows = None
        check_option_html(self.ctx)
        self.assertEqual(self.report.warnings, [])

    def test_literal_br_tag_is_allowed(self):
        path = self.config.csv_path(2)
        path.write_bytes(path.read_bytes().replace(b"List<String>", b"one<br>two"))
        self.ctx._csv_rows = None
        check_option_html(self.ctx)
        self.assertEqual(self.report.warnings, [])

    def test_bare_ampersand_is_flagged_but_an_entity_is_not(self):
        path = self.config.csv_path(2)
        path.write_bytes(path.read_bytes().replace(b"List<String>", b"a &amp; b"))
        self.ctx._csv_rows = None
        check_option_html(self.ctx)
        self.assertEqual(self.report.warnings, [])

        path.write_bytes(path.read_bytes().replace(b"a &amp; b", b"a & b"))
        self.ctx._csv_rows = None
        report = Report(stream=io.StringIO())
        check_option_html(checks_pkg.Context(self.config, self.questions, report))
        self.assertEqual(len(report.warnings), 1)


class ExplanationPresenceTests(CourseFixtureTestCase):
    def test_non_blank_explanations_pass(self):
        check_explanations_present(self.ctx)
        self.assertEqual(self.report.failures, [])

    def test_blank_explanation_is_a_structural_failure(self):
        path = self.config.csv_path(2)
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace("Only one of these compiles.", ""), encoding="utf-8"
        )
        self.ctx._csv_rows = None
        check_explanations_present(self.ctx)
        self.assertEqual(len(self.report.failures), 1)
        self.assertIn("blank Overall Explanation", self.report.failures[0])


class PrivateRepoPatternTests(unittest.TestCase):
    def test_course_configured_repo_name_is_matched(self):
        pattern = build_private_repo_re(["java_25_cert"])
        self.assertTrue(pattern.search("see leonarduk/java_25_cert for details"))

    def test_a_course_without_a_private_upstream_does_not_inherit_one(self):
        pattern = build_private_repo_re([])
        self.assertIsNone(pattern.search("see leonarduk/java_25_cert for details"))

    def test_generic_patterns_apply_to_every_course(self):
        pattern = build_private_repo_re([])
        for leak in ("this module's own README", "the source repo",
                     "the upstream source", "mock-exams/foo", "t1-01-launch"):
            self.assertIsNotNone(pattern.search(leak), leak)

    def test_module_import_declaration_prose_is_not_flagged(self):
        # A bare "this module" also matches real exam content ("What does this
        # module import declaration do?"), which is why the pattern stays
        # narrowed to "this module's own".
        pattern = build_private_repo_re([])
        self.assertIsNone(
            pattern.search("What does this module import declaration do?")
        )


class NaiveLengthScoreTests(unittest.TestCase):
    """Ties MUST be scored fractionally rather than as a hit.

    A question whose options are all the same length leaks nothing -- the
    heuristic degenerates to a coin flip and pays exactly the chance rate.
    Counting such a question as "the key is the shortest" AND "the key is the
    longest" at once was how one exam came to report 48% shortest-is-correct
    off only 9 genuinely short keys.
    """

    @staticmethod
    def bank(correct_length, distractor_length, count=8):
        return [
            Question(
                exam=1, number=i,
                stem="stem",
                options={
                    "A": "x" * correct_length,
                    "B": "y" * distractor_length,
                    "C": "z" * distractor_length,
                    "D": "w" * distractor_length,
                },
                answer="A", explanation="e", domain="d",
            )
            for i in range(1, count + 1)
        ]

    def test_ties_are_scored_at_the_chance_rate(self):
        questions = self.bank(100, 100)
        self.assertAlmostEqual(naive_length_score(questions, min), 0.25)
        self.assertAlmostEqual(naive_length_score(questions, max), 0.25)

    def test_unique_extreme_key_scores_full(self):
        # A key that is genuinely always the shortest pays 100%, which is the
        # tell the check exists to catch.
        self.assertAlmostEqual(naive_length_score(self.bank(50, 200), min), 1.0)
        self.assertAlmostEqual(naive_length_score(self.bank(200, 50), max), 1.0)

    def test_key_at_the_opposite_extreme_scores_zero(self):
        self.assertAlmostEqual(naive_length_score(self.bank(50, 200), max), 0.0)


class DuplicateKeepListTests(CourseFixtureTestCase):
    """The keep-list is a list of *reviewed* pairs, not a mute button."""

    def near_duplicate_bank(self):
        stem = "Domain 1 — T.\n\nWhat does this print? int x = 1; System.out.println(x);"
        return [
            Question(exam=e, number=1, stem=stem,
                     options={k: k * 4 for k in "ABCD"},
                     answer="A", explanation="e", domain="First Domain")
            for e in (1, 2)
        ]

    def run_duplicates(self, questions):
        report = Report(stream=io.StringIO())
        ctx = checks_pkg.Context(self.config, questions, report)
        ctx._raw_bodies = {q.qid: "" for q in questions}
        check_duplicates(ctx)
        return report

    def test_unreviewed_pair_above_threshold_warns(self):
        report = self.run_duplicates(self.near_duplicate_bank())
        self.assertTrue(
            any("unreviewed near-duplicate" in w for w in report.warnings)
        )

    def test_keep_listed_pair_is_not_reported_as_unreviewed(self):
        self.config.reviewed_pairs = {("E1Q01", "E2Q01"): "different trap"}
        report = self.run_duplicates(self.near_duplicate_bank())
        self.assertFalse(
            any("unreviewed near-duplicate" in w for w in report.warnings)
        )

    def test_stale_entry_below_threshold_is_reported(self):
        self.config.reviewed_pairs = {("E1Q01", "E1Q02"): "reviewed long ago"}
        report = self.run_duplicates(self.questions)
        self.assertTrue(
            any("stale exemption" in w for w in report.warnings), report.warnings
        )

    def test_entry_naming_a_removed_question_is_reported(self):
        self.config.reviewed_pairs = {("E1Q01", "E9Q99"): "reviewed long ago"}
        report = self.run_duplicates(self.questions)
        self.assertTrue(
            any("no longer exists" in w for w in report.warnings), report.warnings
        )


class CompletionRatchetTests(CourseFixtureTestCase):
    """`[exams] complete` is a one-way ratchet.

    Without it the question-count check is useless as a CI gate while a bank
    is being authored: an unwritten exam is not a regression, but it is
    indistinguishable from one if "fewer than the target" always fails, and
    the build stays red for the entire authoring phase — at which point a
    real regression is invisible. Ported from the java21 bank, which hit
    exactly this and solved it there first.

    The fixture bank has exam 1 with 2 questions and exam 2 with 1.
    """

    def failures_for(self, **overrides):
        with tempfile.TemporaryDirectory() as tmp:
            config, questions = build_course(Path(tmp), **overrides)
            report = Report(stream=io.StringIO())
            ctx = checks_pkg.Context(config, questions, report)
            check_structure(ctx)
            return report.failures

    def test_unauthored_exam_is_not_a_failure(self):
        # Nothing declared complete: both exams fall short of a raised target
        # and neither is a defect.
        self.assertEqual(
            self.failures_for(**{"counts = { 1 = 2, 2 = 1 }":
                                 "counts = { 1 = 50, 2 = 50 }"}),
            [],
        )

    def test_completed_exam_losing_a_question_still_fails(self):
        failures = self.failures_for(**{
            "counts = { 1 = 2, 2 = 1 }": "counts = { 1 = 3, 2 = 1 }",
            'free = [2]': 'free = [2]\ncomplete = [1]',
        })
        self.assertTrue(any("declared complete" in f for f in failures), failures)

    def test_declaring_an_unfinished_exam_complete_fails(self):
        # The rule that makes the ratchet safe: the relaxed path cannot be
        # reached by over-claiming.
        failures = self.failures_for(**{
            "counts = { 1 = 2, 2 = 1 }": "counts = { 1 = 50, 2 = 1 }",
            'free = [2]': 'free = [2]\ncomplete = [1]',
        })
        self.assertTrue(any("declared complete" in f for f in failures), failures)

    def test_too_many_questions_fails_even_when_not_complete(self):
        failures = self.failures_for(**{
            "counts = { 1 = 2, 2 = 1 }": "counts = { 1 = 1, 2 = 1 }",
        })
        self.assertTrue(
            any("has 2 questions, expected 1" in f for f in failures), failures
        )

    def test_a_complete_and_correct_exam_passes(self):
        self.assertEqual(
            self.failures_for(**{'free = [2]': 'free = [2]\ncomplete = [1, 2]'}), []
        )

    def test_csv_out_of_sync_with_master_always_fails(self):
        # Desync between the CSV and the master is never acceptable, at any
        # stage of authoring — the CSV is a projection of the master.
        path = self.config.csv_path(1)
        lines = path.read_bytes().split(b"\r\n")
        path.write_bytes(b"\r\n".join(lines[:-2] + [b""]))  # drop a row
        self.ctx._csv_rows = None
        check_structure(self.ctx)
        self.assertTrue(
            any("regenerate" in f for f in self.report.failures), self.report.failures
        )


class EndToEndTests(CourseFixtureTestCase):
    def test_a_freshly_generated_bank_has_no_structural_failures(self):
        checks_pkg.run(self.config, self.questions, self.report)
        self.assertEqual(self.report.failures, [])

    def test_a_stale_csv_is_reported(self):
        path = self.config.csv_path(1)
        path.write_text(
            path.read_text(encoding="utf-8").replace("It prints 6", "It prints 7"),
            encoding="utf-8",
        )
        checks_pkg.run(self.config, self.questions, self.report)
        self.assertTrue(any("differ from" in w for w in self.report.warnings))

    def test_course_checks_run_and_can_fail_the_build(self):
        def always_fails(ctx):
            ctx.report.heading("Course check")
            ctx.report.fail("subject-specific rule violated")

        checks_pkg.run(self.config, self.questions, self.report,
                       course_checks=[always_fails])
        self.assertIn("subject-specific rule violated", self.report.failures)


if __name__ == "__main__":
    unittest.main()
