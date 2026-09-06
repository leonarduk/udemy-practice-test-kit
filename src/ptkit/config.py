"""Load a course's course.toml into a CourseConfig.

course.toml holds everything that genuinely differs between one practice-test
bank and the next: where the files live, how many exams there are and how long
each one is, the official domain list, and the tuning constants for the
quality checks. Anything that needs *code* to express -- a subject-specific
check such as Java's "is this JEP number finalized yet?" -- goes in the
course's own tools/course_checks.py instead. See README.md.
"""

import tomllib
from pathlib import Path

from .model import ParseError

CONFIG_NAME = "course.toml"

# The 17 columns of Udemy's PracticeTestBulkQuestionUploadTemplate_V2.2.csv,
# in order. The template's own instructions require unused columns to stay
# present, so Answer Option 5-6 (a course with fewer than 6 options) and any
# Explanation N a course doesn't author (see Question.option_explanations)
# are emitted empty rather than dropped. Not configurable: it is the
# platform's format, not the course's, and check_structure asserts the
# on-disk template still matches.
COLUMNS = [
    "Question", "Question Type",
    "Answer Option 1", "Explanation 1",
    "Answer Option 2", "Explanation 2",
    "Answer Option 3", "Explanation 3",
    "Answer Option 4", "Explanation 4",
    "Answer Option 5", "Explanation 5",
    "Answer Option 6", "Explanation 6",
    "Correct Answers", "Overall Explanation", "Domain",
]

# The parser dispatches on this name -- see parse.py's PARSERS and
# RAW_BODY_LOADERS. "exam-grouped" is every Oracle/Spring bank; "domain-grouped"
# is for a bank transcribed module-by-module from a domain-organized source
# (e.g. risk-eng-for-swe), where a heading groups a run of questions instead
# of "Domain N" being repeated inline in each one; "section-grouped" is for a
# bank authored as a flat list of named batches (no numbering convention at
# all), where [sections] maps each one onto the exam it belongs to and
# several batches may feed the same exam.
LAYOUTS = ("exam-grouped", "domain-grouped", "section-grouped")


class ConfigError(Exception):
    """course.toml is missing, malformed, or internally inconsistent."""


def find_config(start=None):
    """Walk up from `start` looking for course.toml.

    Lets `ptkit validate` work from anywhere inside a course repo, the way git
    does, instead of only from the repo root.
    """
    current = Path(start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    raise ConfigError(
        f"no {CONFIG_NAME} found in {current} or any parent directory -- "
        f"run this from inside a course repo, or scaffold one with "
        f"`ptkit new-course`"
    )


class CourseConfig:
    def __init__(self, path, data):
        self.path = Path(path).resolve()
        self.root = self.path.parent
        self._data = data

        course = self._table("course")
        self.name = self._require(course, "name", "course", str)
        self.slug = self._require(course, "slug", "course", str)

        layout = self._table("layout")
        self.layout = layout.get("kind", "exam-grouped")
        if self.layout not in LAYOUTS:
            raise ConfigError(
                f"[layout] kind = {self.layout!r} is not one of {LAYOUTS}"
            )
        self.master = self.root / layout.get("master", "questions-master.md")
        self.output_dir = self.root / layout.get("output_dir", ".")
        self.template = self.output_dir / layout.get(
            "template", "PracticeTestBulkQuestionUploadTemplate_V2.2.csv"
        )
        self.csv_name = layout.get("csv_name", "practice-test-{exam}.csv")
        if "{exam}" not in self.csv_name:
            raise ConfigError("[layout] csv_name must contain '{exam}'")
        self.option_letters = layout.get("option_letters", "ABCD")
        if len(self.option_letters) < 2:
            raise ConfigError("[layout] option_letters needs at least 2 letters")
        self.require_domain_prefix = layout.get("require_domain_prefix", True)
        self.require_difficulty = layout.get("require_difficulty", False)
        # Deterministic answer-option shuffle (see shuffle.py) -- off by
        # default, since it changes which letter is "correct" for every
        # question and so is only safe to turn on for a bank that has never
        # been uploaded, or that is being deliberately re-keyed. shuffle_seed
        # is part of the bank's identity once enabled: changing it reshuffles
        # every question, so treat it like a schema field, not a tuning knob.
        self.shuffle_options = layout.get("shuffle_options", False)
        self.shuffle_seed = layout.get("shuffle_seed")
        if self.shuffle_options and not self.shuffle_seed:
            raise ConfigError(
                "[layout] shuffle_options = true needs a non-empty shuffle_seed"
            )

        exams = self._table("exams")
        numbers = exams.get("numbers")
        if not numbers:
            raise ConfigError("[exams] numbers must list at least one exam")
        self.exams = tuple(int(n) for n in numbers)
        # Optional human-readable filename slug per exam (e.g. exam 1 ->
        # "pcep-30"), for a bank whose established CSV names are strings, not
        # bare numbers -- csv_path() below substitutes it into csv_name's
        # {exam} placeholder in place of the number. An exam with no entry
        # here just uses its own number, which is the entire behavior for
        # every course that doesn't set this table at all.
        raw_slugs = exams.get("slugs", {})
        self.exam_slugs = {int(k): str(v) for k, v in raw_slugs.items()}
        unknown_slug_exams = sorted(set(self.exam_slugs) - set(self.exams))
        if unknown_slug_exams:
            raise ConfigError(
                f"[exams] slugs names exam(s) "
                f"{', '.join(map(str, unknown_slug_exams))} that are not "
                f"in numbers"
            )
        raw_counts = exams.get("counts", {})
        self.exam_question_counts = {int(k): int(v) for k, v in raw_counts.items()}
        missing = [e for e in self.exams if e not in self.exam_question_counts]
        if missing:
            raise ConfigError(
                f"[exams] counts is missing an entry for exam(s) "
                f"{', '.join(map(str, missing))}"
            )
        # Exam-level, not question-level: the real free/paid boundary in these
        # banks is "which whole practice test is the free sample", and no bank
        # tags individual questions. An exporter targeting a PUBLIC
        # destination must filter through is_public_safe() rather than
        # reimplementing the distinction.
        self.free_exams = {int(n) for n in exams.get("free", [])}
        # Exams declared finished. A one-way ratchet, and the single reason it
        # exists is that the question-count checks are useless as a CI gate
        # while a bank is being authored: an exam that has not been written
        # yet is not a regression, but it is indistinguishable from one if
        # "fewer than the target" always fails. Every exam listed here must
        # have exactly its full count -- a finished exam losing questions IS a
        # regression and fails the build -- while an exam not listed may have
        # fewer, reported as progress rather than as a defect.
        #
        # Add an exam the moment it reaches its full count, in the same commit
        # that completes it. Never remove one: that silently lowers the bar on
        # content already held to it. Having too MANY questions always fails,
        # listed or not, since that can only be a numbering mistake.
        self.complete_exams = frozenset(int(n) for n in exams.get("complete", []))
        unknown = sorted(self.complete_exams - set(self.exams))
        if unknown:
            raise ConfigError(
                f"[exams] complete lists exam(s) {', '.join(map(str, unknown))} "
                f"that are not in numbers"
            )

        domains = self._table("domains", required=False)
        self.domain_names = {int(k): str(v) for k, v in domains.items()}
        if not self.domain_names:
            raise ConfigError("[domains] must map at least one domain number to a name")

        # Only meaningful for "section-grouped" -- see parse.py's
        # parse_section_grouped. Maps a master-file section heading's exact
        # text onto the exam number it belongs to; several sections may map
        # to the same exam.
        sections = self._table("sections", required=False)
        self.sections = {str(k): int(v) for k, v in sections.items()}
        if self.layout == "section-grouped" and not self.sections:
            raise ConfigError(
                "[layout] kind = \"section-grouped\" needs a non-empty "
                "[sections] table mapping section names to exam numbers"
            )
        unknown_section_exams = sorted(set(self.sections.values()) - set(self.exams))
        if unknown_section_exams:
            raise ConfigError(
                f"[sections] maps to exam(s) "
                f"{', '.join(map(str, unknown_section_exams))} that are not "
                f"in [exams] numbers"
            )

        checks = self._table("checks", required=False)
        self.duplicate_threshold = float(checks.get("duplicate_threshold", 0.62))
        self.private_repos = tuple(checks.get("private_repos", []))
        self.citation_owners = tuple(checks.get("citation_owners", ["leonarduk"]))
        # Off switch for TextRenderer's "Verified ..." aside-stripping (see
        # its own docstring) -- default True keeps every existing adopter's
        # behavior unchanged; a course whose explanations use "Verified by
        # running it: ..." as the substantive evidence, not a discardable
        # tail, sets this false so that sentence survives into the CSV.
        self.strip_verified_asides = bool(checks.get("strip_verified_asides", True))
        self.key_distribution_band = tuple(
            checks.get("key_distribution_band", [0.20, 0.30])
        )
        self.naive_strategy_band = tuple(
            checks.get("naive_strategy_band", [0.15, 0.35])
        )
        self.length_ratio_band = tuple(checks.get("length_ratio_band", [0.90, 1.10]))
        self.reviewed_pairs = self._reviewed_pairs(checks)

    # -- helpers ---------------------------------------------------------

    def _table(self, name, required=True):
        table = self._data.get(name)
        if table is None:
            if required:
                raise ConfigError(f"{self.path.name} has no [{name}] table")
            return {}
        if not isinstance(table, dict):
            raise ConfigError(f"[{name}] must be a table")
        return table

    @staticmethod
    def _require(table, key, table_name, kind):
        value = table.get(key)
        if not isinstance(value, kind) or (kind is str and not value.strip()):
            raise ConfigError(f"[{table_name}] {key} is required")
        return value

    def _reviewed_pairs(self, checks):
        """[[checks.reviewed_pairs]] entries -> {(left, right): reason}.

        A list of *reviewed* pairs, not a mute button: an unlisted pair above
        the threshold still warns, and a listed pair that drops below it is
        reported as stale so it gets removed rather than quietly masking a
        future regression. Every entry must carry the reason it was kept.
        """
        pairs = {}
        for entry in checks.get("reviewed_pairs", []):
            try:
                left, right, reason = entry["left"], entry["right"], entry["reason"]
            except (KeyError, TypeError):
                raise ConfigError(
                    "each [[checks.reviewed_pairs]] entry needs left, right "
                    "and reason keys"
                ) from None
            if not reason.strip():
                raise ConfigError(
                    f"[[checks.reviewed_pairs]] {left} <-> {right} has an "
                    f"empty reason -- record why the pair was kept"
                )
            pairs[(left, right)] = reason
        return pairs

    # -- derived ---------------------------------------------------------

    def csv_path(self, exam):
        return self.output_dir / self.csv_name.format(
            exam=self.exam_slugs.get(exam, exam)
        )

    def tier_of(self, exam):
        """"free" for a free-tier exam, "paid" otherwise."""
        return "free" if exam in self.free_exams else "paid"

    def is_public_safe(self, question):
        """True if `question` may be included in a public-facing export.

        A future exporter targeting a public destination (as opposed to the
        Udemy CSVs, which are a private paid-product delivery pipeline) should
        filter through this rather than reimplementing the free/paid split.
        """
        return self.tier_of(question.exam) == "free"

    def is_complete(self, exam):
        """True if `exam` is declared finished -- see complete_exams."""
        return exam in self.complete_exams

    def bank_is_complete(self):
        """True once every exam is declared finished."""
        return all(self.is_complete(exam) for exam in self.exams)

    @property
    def total_questions(self):
        return sum(self.exam_question_counts[e] for e in self.exams)

    def reviewed_reason(self, left, right):
        """Why this pair was deliberately kept, or None if it wasn't reviewed."""
        return (self.reviewed_pairs.get((left, right))
                or self.reviewed_pairs.get((right, left)))


def load(path=None):
    """Load a CourseConfig from `path`, or from the nearest course.toml."""
    config_path = Path(path) if path else find_config()
    if config_path.is_dir():
        config_path = config_path / CONFIG_NAME
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"{config_path} does not exist") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{config_path} is not valid TOML: {exc}") from None
    return CourseConfig(config_path, data)


__all__ = ["COLUMNS", "ConfigError", "CourseConfig", "ParseError", "find_config", "load"]
