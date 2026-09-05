"""Structural checks: things that would break the Udemy bulk upload."""

import collections
import csv

from ..config import COLUMNS
from ..csvout import is_current


def check_structure(ctx):
    report, config = ctx.report, ctx.config
    report.heading("Structure")

    per_exam = collections.Counter(q.exam for q in ctx.questions)
    for exam in config.exams:
        expected = config.exam_question_counts[exam]
        if per_exam[exam] != expected:
            report.fail(
                f"exam {exam} has {per_exam[exam]} questions, expected {expected}"
            )
    if len(ctx.questions) != config.total_questions:
        report.fail(
            f"{len(ctx.questions)} questions in total, "
            f"expected {config.total_questions}"
        )
    else:
        counts = ", ".join(
            f"{exam}={config.exam_question_counts[exam]}" for exam in config.exams
        )
        report.ok(f"{config.total_questions} questions ({counts})")

    # The parser already rejects a question without exactly the configured
    # option letters and one correct answer, so reaching here means the
    # Markdown side is well formed.
    report.ok(
        f"every question has options "
        f"{config.option_letters[0]}-{config.option_letters[-1]} "
        f"and exactly one correct answer"
    )

    if not config.template.exists():
        report.fail(f"{config.template.name} is missing -- cannot verify the "
                    f"CSV column layout against Udemy's own template")
    else:
        with config.template.open(encoding="utf-8", newline="") as handle:
            template_header = next(csv.reader(handle))
        if template_header != COLUMNS:
            report.fail(
                "ptkit's COLUMNS no longer matches the Udemy template header "
                "-- Udemy has revised the template; the kit needs updating"
            )
        else:
            report.ok(f"template header matches ptkit COLUMNS "
                      f"({len(COLUMNS)} columns)")

    valid_indices = {str(i) for i in range(1, len(config.option_letters) + 1)}
    domain_values = set(config.domain_names.values())
    row_failures = 0
    for exam, rows in ctx.csv_rows.items():
        name = config.csv_path(exam).name
        expected = config.exam_question_counts[exam]
        if len(rows) != expected:
            report.fail(f"{name} has {len(rows)} rows, expected {expected}")
        if rows and list(rows[0].keys()) != COLUMNS:
            report.fail(f"{name} header does not match the template")
            continue
        for i, row in enumerate(rows, 1):
            where = f"{name} row {i}"
            if len(row) != len(COLUMNS):
                report.fail(f"{where}: {len(row)} columns, expected {len(COLUMNS)}")
                row_failures += 1
            if row["Question Type"] != "multiple-choice":
                report.fail(f"{where}: Question Type is {row['Question Type']!r}")
                row_failures += 1
            if row["Correct Answers"] not in valid_indices:
                report.fail(f"{where}: Correct Answers is {row['Correct Answers']!r}")
                row_failures += 1
            if row["Domain"] not in domain_values:
                report.fail(f"{where}: unknown Domain {row['Domain']!r}")
                row_failures += 1
    if not row_failures:
        report.ok(f"all CSV rows: {len(COLUMNS)} columns, multiple-choice, "
                  f"valid answer index and domain")


def check_explanations_present(ctx):
    """A blank explanation breaks the product outright.

    This is a paid practice-test course whose entire value is the
    explanations, so an empty one is a structural FAIL, not a quality warning.
    "Maintainer-note-only" isn't independently detectable in general, but the
    private-repo detector in hygiene.py catches the concrete form it took once
    (a question leaking an internal file path) as a second line of defence.
    """
    ctx.report.heading("Explanations present")
    blank = []
    for exam, rows in ctx.csv_rows.items():
        for i, row in enumerate(rows, 1):
            if not row["Overall Explanation"].strip():
                blank.append(f"E{exam}Q{i:02d}")
    if blank:
        ctx.report.fail(
            f"{len(blank)} question(s) have a blank Overall Explanation: "
            f"{', '.join(blank)}"
        )
    else:
        ctx.report.ok("every row has a non-empty Overall Explanation")


def check_identical_options(ctx):
    """Two options can render as the same literal string in the shipped CSV
    even though they differ in questions-master.md -- e.g. differing only in a
    run of internal spaces, which the learner-text renderer collapses. A
    student then sees two identical choices, which is either confusing (both
    wrong) or actively penalizes a correct answer (if one of the identical
    pair is the correct one). Structural: it breaks the question as shipped.
    """
    ctx.report.heading("Identical options after learner-text normalization")
    count = len(ctx.config.option_letters)
    broken = []
    for exam, rows in ctx.csv_rows.items():
        for i, row in enumerate(rows, 1):
            texts = [row[f"Answer Option {n}"] for n in range(1, count + 1)]
            if len(set(texts)) < len(texts):
                broken.append(f"E{exam}Q{i:02d}")
    if broken:
        ctx.report.fail(
            f"{len(broken)} question(s) have two options that render as "
            f"identical text to the learner: {', '.join(broken)}"
        )
    else:
        ctx.report.ok(
            f"every question's {count} options render as {count} distinct strings"
        )


def check_csvs_current(ctx):
    ctx.report.heading("CSVs in sync with questions-master.md")
    stale = []
    for exam in ctx.config.exams:
        if exam not in ctx.csv_rows:
            continue
        if not is_current(ctx.config, ctx.questions, exam):
            stale.append(exam)
    if stale:
        ctx.report.warn(
            f"exam(s) {', '.join(map(str, stale))} differ from "
            f"{ctx.config.master.name} -- run `ptkit generate`"
        )
    else:
        ctx.report.ok("all CSVs match what the generator produces")
