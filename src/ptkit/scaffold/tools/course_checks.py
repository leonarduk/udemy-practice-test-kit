"""Course-specific checks.

The shared pipeline and the generic item-quality checks live in
udemy-practice-test-kit (ptkit). This file is the escape hatch for checks that
need SUBJECT knowledge the kit has no business carrying -- for example, "which
JEP numbers may legitimately be cited as final for the release this exam
covers?", or "does every explanation cite a real reference-documentation
section?".

`ptkit validate` imports the module-level CHECKS list and runs each function
against a ptkit.checks.Context, between the structural checks and the
item-quality ones.

A Context gives you:
    ctx.config      the CourseConfig from course.toml
    ctx.questions   every parsed Question, in document order
    ctx.csv_rows    exam -> list of dict rows read from the generated CSVs
    ctx.raw_bodies  qid -> raw pre-fence-stripping Markdown
    ctx.for_exam(n) the questions belonging to one exam
    ctx.report      .heading() / .fail() / .warn() / .ok() / .detail()

Use fail() only for something that would break the upload or corrupt an exam;
use warn() for quality findings that should improve over time.

Delete this file if the course has no subject-specific checks.
"""


def check_citations(ctx):
    """Example: every explanation should cite a checkable source."""
    ctx.report.heading("Citations")
    missing = [q.qid for q in ctx.questions if "TODO-citation-marker" in q.explanation]
    if missing:
        ctx.report.warn(
            f"{len(missing)} explanation(s) have no citation: "
            f"{', '.join(missing[:8])}"
        )
    else:
        ctx.report.ok("every explanation cites a source")


CHECKS = [check_citations]
