"""The check registry.

A check is a function taking a Context and reporting through ctx.report. They
run in three phases:

  structural   things that would break the Udemy upload -- must run first, so
               a malformed bank fails loudly before the quality checks try to
               do statistics on it
  course       whatever the course repo registers in tools/course_checks.py
               (e.g. Java's "is this JEP number finalized?"); subject-specific
               knowledge belongs to the course, not the kit
  quality      psychometric and hygiene findings, which warn rather than fail

Course repos extend the registry by defining a module-level `CHECKS` list of
functions in tools/course_checks.py -- see README.md.
"""

import csv

from . import hygiene, quality, structure


class Context:
    """Everything a check might need, parsed once and shared by all of them."""

    def __init__(self, config, questions, report):
        self.config = config
        self.questions = questions
        self.report = report
        self._csv_rows = None
        self._raw_bodies = None

    @property
    def csv_rows(self):
        """exam -> list of dict rows, read from the generated CSVs on disk.

        A missing CSV is a structural failure recorded once, here, rather than
        by every check that wanted to read it.
        """
        if self._csv_rows is None:
            rows = {}
            for exam in self.config.exams:
                path = self.config.csv_path(exam)
                if not path.exists():
                    self.report.fail(f"{path.name} is missing")
                    continue
                with path.open(encoding="utf-8", newline="") as handle:
                    rows[exam] = list(csv.DictReader(handle))
            self._csv_rows = rows
        return self._csv_rows

    @property
    def raw_bodies(self):
        """qid -> raw pre-fence-stripping Markdown, for code-only comparison."""
        if self._raw_bodies is None:
            from ..parse import load_raw_bodies
            self._raw_bodies = load_raw_bodies(self.config)
        return self._raw_bodies

    def for_exam(self, exam):
        return [q for q in self.questions if q.exam == exam]


STRUCTURAL_CHECKS = [
    structure.check_structure,
    structure.check_explanations_present,
    structure.check_csvs_current,
]

QUALITY_CHECKS = [
    quality.check_key_distribution,
    quality.check_option_lengths,
    quality.check_naive_strategies,
    quality.check_duplicates,
    structure.check_identical_options,
    hygiene.check_option_html,
    hygiene.check_hygiene,
]


def run(config, questions, report, course_checks=()):
    ctx = Context(config, questions, report)
    for check in [*STRUCTURAL_CHECKS, *course_checks, *QUALITY_CHECKS]:
        check(ctx)
    return ctx
