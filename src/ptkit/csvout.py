"""Project a parsed bank onto Udemy's 17-column bulk-upload CSV.

The CSVs are a generated artefact. Edit questions-master.md and regenerate,
never the other way round -- and remember the regenerated files still have to
be re-uploaded to Udemy before learners see the change.
"""

import csv
import io

from .config import COLUMNS
from .text import TextRenderer


def to_row(question, render_text, domain_names=None):
    """Project a Question onto the 17-column Udemy template.

    `render_text` is a TextRenderer -- the Markdown-to-plain-text pass that
    Udemy's non-rendering fields require.

    `domain_names` optionally overrides the Domain column's language (pass a
    translated table keyed by question.domain_number). Falls back to
    question.domain (its parse-time name) when omitted, or for a Question
    built without a domain_number, e.g. a test fixture constructed directly.
    """
    if domain_names is not None and question.domain_number in domain_names:
        domain = domain_names[question.domain_number]
    else:
        domain = question.domain

    row = {column: "" for column in COLUMNS}
    row.update({
        "Question": render_text(question.stem),
        "Question Type": "multiple-choice",
        "Correct Answers": str(question.correct_index),
        "Overall Explanation": render_text(question.explanation),
        "Domain": domain,
    })
    for index, letter in enumerate(sorted(question.options), start=1):
        row[f"Answer Option {index}"] = render_text(question.options[letter])
    return row


def render(questions, exam, config, domain_names=None):
    """Render one exam's questions as CSV text, matching Udemy's template.

    Format notes, all of which matter for byte-identical output:
      * rows terminated with CRLF, but newlines *inside* a quoted field stay
        bare LF -- that is what the uploaded files use
      * QUOTE_MINIMAL, so 'multiple-choice' is unquoted while a multi-line
        question is quoted
      * UTF-8 with no BOM
    """
    render_text = TextRenderer(config.citation_owners)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=COLUMNS, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL
    )
    writer.writeheader()
    for question in questions:
        if question.exam == exam:
            writer.writerow(to_row(question, render_text, domain_names=domain_names))
    return buffer.getvalue()


def normalise_newlines(text):
    """Compare CSVs by content, not by line ending.

    core.autocrlf rewrites these files on checkout, so a raw byte compare
    reports a fresh Windows clone -- or, as it turns out, an LF-normalised
    commit -- as out of sync when the content is in fact identical. Both
    `ptkit generate --check` and the csv-sync validation check compare through
    this, so the two commands can never contradict each other about whether
    the CSVs are current.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def is_current(config, questions, exam, domain_names=None):
    """True if the on-disk CSV for `exam` matches what the generator produces."""
    path = config.csv_path(exam)
    if not path.exists():
        return False
    generated = render(questions, exam, config, domain_names=domain_names)
    on_disk = path.read_bytes().decode("utf-8")
    return normalise_newlines(generated) == normalise_newlines(on_disk)
