"""course.toml loading: defaults, derived values, and the error messages."""

import tempfile
import textwrap
import unittest
from pathlib import Path

import ptkit
from ptkit.config import ConfigError, CourseConfig, find_config, load

FIXTURES = Path(__file__).parent / "fixtures"

MINIMAL = """
[course]
name = "X"
slug = "x"
[layout]
[exams]
numbers = [1]
counts = { 1 = 2 }
[domains]
1 = "D"
"""


def write(tmp, text):
    path = Path(tmp) / "course.toml"
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


class LoadTests(unittest.TestCase):
    def test_fixture_course_loads(self):
        config = load(FIXTURES / "course.toml")
        self.assertEqual(config.slug, "fixture")
        self.assertEqual(config.exams, (1, 2))
        self.assertEqual(config.total_questions, 3)
        self.assertEqual(config.domain_names[5], "Fifth Domain")

    def test_defaults_fill_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load(write(tmp, MINIMAL))
            self.assertEqual(config.layout, "exam-grouped")
            self.assertEqual(config.option_letters, "ABCD")
            self.assertTrue(config.require_domain_prefix)
            self.assertFalse(config.require_difficulty)
            self.assertEqual(config.duplicate_threshold, 0.62)
            self.assertEqual(config.master.name, "questions-master.md")
            self.assertEqual(config.csv_path(1).name, "practice-test-1.csv")

    def test_find_config_walks_up_like_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, MINIMAL)
            nested = Path(tmp) / "a" / "b"
            nested.mkdir(parents=True)
            self.assertEqual(find_config(nested), Path(tmp).resolve() / "course.toml")

    def test_missing_config_names_the_scaffold_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError) as caught:
                find_config(tmp)
        self.assertIn("ptkit new-course", str(caught.exception))


class TierTests(unittest.TestCase):
    """Exam-level, not question-level: no bank tags individual questions, and
    the real boundary is "which whole practice test is the free sample".
    """

    def setUp(self):
        self.config = load(FIXTURES / "course.toml")
        self.questions = ptkit.parse_master(self.config)

    def test_tier_of(self):
        self.assertEqual(self.config.tier_of(1), "paid")
        self.assertEqual(self.config.tier_of(2), "free")

    def test_is_public_safe_filters_to_the_free_exam(self):
        safe = [q.qid for q in self.questions if self.config.is_public_safe(q)]
        self.assertEqual(safe, ["E2Q01"])


class ValidationTests(unittest.TestCase):
    def assert_config_error(self, body, fragment):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError) as caught:
                load(write(tmp, body))
        self.assertIn(fragment, str(caught.exception))

    def test_unknown_layout_is_rejected(self):
        self.assert_config_error(
            MINIMAL.replace("[layout]", '[layout]\nkind = "freeform"'),
            "not one of",
        )

    def test_counts_must_cover_every_exam(self):
        self.assert_config_error(
            MINIMAL.replace("numbers = [1]", "numbers = [1, 2]"),
            "missing an entry for exam(s) 2",
        )

    def test_csv_name_must_be_parameterised(self):
        self.assert_config_error(
            MINIMAL.replace("[layout]", '[layout]\ncsv_name = "out.csv"'),
            "must contain '{exam}'",
        )

    def test_domains_are_required(self):
        self.assert_config_error(
            MINIMAL.replace('[domains]\n1 = "D"', ""),
            "at least one domain",
        )

    def test_reviewed_pair_needs_a_reason(self):
        self.assert_config_error(
            MINIMAL + '\n[[checks.reviewed_pairs]]\nleft = "E1Q01"\n'
                      'right = "E1Q02"\nreason = "  "\n',
            "empty reason",
        )

    def test_reviewed_pair_is_matched_in_either_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load(write(
                tmp,
                MINIMAL + '\n[[checks.reviewed_pairs]]\nleft = "E1Q01"\n'
                          'right = "E1Q02"\nreason = "same scaffold"\n',
            ))
        self.assertEqual(config.reviewed_reason("E1Q02", "E1Q01"), "same scaffold")
        self.assertIsNone(config.reviewed_reason("E1Q03", "E1Q04"))

    def test_bad_toml_names_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError) as caught:
                load(write(tmp, "[course\nname = 'x'"))
        self.assertIn("not valid TOML", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
