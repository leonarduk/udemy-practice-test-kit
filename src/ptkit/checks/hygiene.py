"""Learner-facing text hygiene: does the shipped text render as intended?

Everything here is about the gap between what the author wrote in Markdown and
what Udemy actually puts in front of a learner. See UDEMY-PLATFORM-NOTES.md.
"""

import collections
import re

# Forms in which learner-facing text can leak a reference to a PRIVATE
# upstream repo: a generic "source repo" / "upstream source" mention, a
# "mock-exam(s)" path segment, and the "this module's own" / "tN-NN-..."
# module-doc patterns. Case-insensitive. Two patterns stay deliberately narrow
# to avoid catching legitimate exam prose: a bare "this module" also matches
# real content ("What does this module import declaration do?"), so it stays
# "this module's own"; "solution repo" isn't a trigger on its own for the same
# reason ("solution" alone is common exam vocabulary).
BASE_PRIVATE_REPO_PATTERNS = (
    r"this module's own",
    r"t\d-\d\d-[a-z-]+",
    r"\bsource repo\b",
    r"\bupstream source\b",
    r"mock-exams?[-/]",
)

# Udemy renders Answer Option cells as HTML, so a bare &, <, or > outside a
# literal <br> is parsed as markup and dropped or mangled rather than shown as
# text. An unescaped `<class 'str'>`-shaped answer simply vanishes from the
# option. Discovered on the Python bank; it applies to every bank, which is
# exactly why the check lives in the kit rather than in one course repo.
OPTION_BR = "<br>"
BARE_AMPERSAND_RE = re.compile(r"&(?!lt;|gt;|amp;)")


def build_private_repo_re(private_repos=()):
    patterns = list(BASE_PRIVATE_REPO_PATTERNS)
    patterns.extend(re.escape(name) for name in private_repos)
    return re.compile("|".join(patterns), re.I)


def learner_columns(config):
    return ["Question", "Overall Explanation"] + [
        f"Answer Option {i}" for i in range(1, len(config.option_letters) + 1)
    ]


def check_hygiene(ctx):
    report, config = ctx.report, ctx.config
    report.heading("Learner-facing text hygiene")
    private_repo_re = build_private_repo_re(config.private_repos)
    columns = learner_columns(config)
    backticked = collections.Counter()
    internal = []
    for exam, rows in ctx.csv_rows.items():
        for i, row in enumerate(rows, 1):
            for column in columns:
                if "`" in row[column]:
                    backticked[column] += 1
            blob = row["Question"] + row["Overall Explanation"]
            if private_repo_re.search(blob):
                internal.append(f"E{exam}Q{i:02d}")

    if backticked:
        for column, count in backticked.most_common():
            report.warn(f"{count} rows have Markdown backticks in {column!r} "
                        f"-- Udemy renders these literally")
    else:
        report.ok("no Markdown backticks in any learner-facing column")

    # A private-repo leak is structural, not a quality nit -- the repo is
    # private, so any surviving reference is a dead link/path a learner can
    # never follow. FAIL, unlike the backtick check above.
    if internal:
        report.fail(
            f"{len(internal)} explanations reference the private source repo: "
            f"{', '.join(internal[:8])}"
        )
    else:
        report.ok("no private-repo references in explanations")


def check_option_html(ctx):
    """Answer Option cells are rendered as HTML by Udemy's importer.

    Reported as a WARNING, not a failure, on purpose: it is newly shared
    across banks that were authored before anyone knew about it, so an
    existing bank can legitimately be non-clean while it is fixed question by
    question. It describes real breakage in the shipped product, though -- the
    offending text does not reach the learner -- so treat a finding here as a
    bug, not a nit.
    """
    report, config = ctx.report, ctx.config
    report.heading("Answer Option HTML safety")
    count = len(config.option_letters)
    offenders = []
    for exam, rows in ctx.csv_rows.items():
        for i, row in enumerate(rows, 1):
            for n in range(1, count + 1):
                text = row[f"Answer Option {n}"]
                if not text:
                    continue
                without_br = text.replace(OPTION_BR, "")
                if "<" in without_br or ">" in without_br:
                    offenders.append(f"E{exam}Q{i:02d} option {n}: unescaped < or >")
                elif BARE_AMPERSAND_RE.search(text):
                    offenders.append(f"E{exam}Q{i:02d} option {n}: unescaped &")
    if offenders:
        report.warn(
            f"{len(offenders)} answer option(s) contain unescaped HTML "
            f"characters -- Udemy parses these cells as HTML, so the "
            f"offending text is dropped or mangled for the learner:"
        )
        for offender in offenders[:15]:
            report.detail(f"  {offender}")
        if len(offenders) > 15:
            report.detail(f"  ... and {len(offenders) - 15} more")
    else:
        report.ok("no unescaped &, < or > in any answer option")
