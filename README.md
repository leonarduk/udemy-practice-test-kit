# udemy-practice-test-kit

Shared tooling for Udemy practice-test question banks.

A course repo owns its **content** (`questions-master.md`) and its
**configuration** (`course.toml`). This package owns the **pipeline** that
turns one into Udemy's bulk-upload CSVs, and the **checks** that decide
whether the result is fit to upload.

## Why

Seven practice-test repos were built by forking each other. Two of them
(`java21-udemy-practice-tests`, `spring-professional-udemy-practice-tests`)
had byte-identical `test_qbank.py` and `generate_csvs.py`, and differed in
`qbank.py`/`validate.py` only by a docstring, an exam-count map, a domain-name
map and one subject-specific check.

Copy-forking is cheap to do. The bill arrives as **quirks that don't
propagate**: the Python bank was the only repo that knew Udemy parses Answer
Option cells as HTML, so `List<String>` in an option is silently dropped from
what the learner sees. The first time that check ran against the Spring bank
— as a shared check, from here — it found one.

`UDEMY-PLATFORM-NOTES.md` is the durable home for that class of knowledge.
Read it before authoring anything.

## Install

```bash
pip install "git+https://github.com/leonarduk/udemy-practice-test-kit@v1"
```

Zero runtime dependencies; Python 3.11+ (`tomllib`).

## Use

```bash
ptkit validate            # structural + item-quality checks
ptkit generate            # regenerate the per-exam CSVs
ptkit generate --check    # write nothing; non-zero exit if the CSVs are stale
ptkit new-course ../my-new-course
```

All commands find the nearest `course.toml` by walking up from the working
directory, the way `git` does.

## What goes where

| | Lives in | Example |
|---|---|---|
| Questions | course repo | `questions-master.md` |
| Paths, exam sizes, domains, thresholds | course repo | `course.toml` |
| Subject-specific checks | course repo | `tools/course_checks.py` |
| Parser, CSV projection, generic checks | **this package** | `ptkit/` |
| Platform quirks | **this package** | `UDEMY-PLATFORM-NOTES.md` |

The split rule: if it needs *subject* knowledge ("is JEP 453 final in Java
21?"), it belongs to the course. If it needs *platform* or *psychometric*
knowledge ("does Udemy render this?", "can a learner beat this by always
picking the longest option?"), it belongs here.

## course.toml

```toml
[course]
name = "Java SE 21 (1Z0-830) Practice Tests"
slug = "java21"

[layout]
kind = "exam-grouped"          # the "# Exam N / ## QNN" master layout
master = "questions-master.md"
output_dir = "."               # where the generated CSVs go
template = "PracticeTestBulkQuestionUploadTemplate_V2.2.csv"
csv_name = "practice-test-{exam}.csv"
option_letters = "ABCD"
require_domain_prefix = true   # every stem opens with "Domain N — Topic."
require_difficulty = false

[exams]
numbers = [1, 2, 3, 4, 5, 6]
counts = { 1 = 50, 2 = 50, 3 = 50, 4 = 50, 5 = 50, 6 = 50 }
free = []                      # exam numbers that are the free sample

[domains]
1 = "Handling Date, Time, Text, Numeric and Boolean Values"
# ...

[checks]
duplicate_threshold = 0.62
private_repos = ["some_private_upstream"]   # names that must not reach a learner
citation_owners = ["leonarduk"]             # strips "Source: <owner>/<repo> …" tails
key_distribution_band = [0.20, 0.30]
naive_strategy_band = [0.15, 0.35]
length_ratio_band = [0.90, 1.10]

# Cross-exam pairs reviewed and deliberately kept. A list of *reviewed* pairs,
# not a mute button: an unlisted pair above the threshold still warns, and a
# listed pair that drops below it is reported as stale.
[[checks.reviewed_pairs]]
left = "E1Q01"
right = "E1Q02"
reason = "different JLS rule behind a shared stem scaffold"
```

## Course-specific checks

Put them in `tools/course_checks.py` and expose a module-level `CHECKS` list.
Each function takes a `ptkit.checks.Context` (`.config`, `.questions`,
`.csv_rows`, `.raw_bodies`, `.report`, `.for_exam(n)`) and reports through
`ctx.report.fail` / `.warn` / `.ok`.

```python
def check_jep_numbers(ctx):
    ctx.report.heading("JEP numbers")
    ...

CHECKS = [check_jep_numbers]
```

They run between the structural checks and the item-quality ones.

## Failure vs warning

* `fail` — **structural**: would break the Udemy bulk upload or corrupt an
  exam. Blocks CI.
* `warn` — **item quality**: psychometric or hygiene findings, expected to
  improve over time rather than being a pass/fail gate today.

A check that cannot decide which of the two it is has not been thought
through yet.

## Layouts

Only `exam-grouped` is implemented, because it is the only one that has been
verified byte-for-byte against a real bank. The parser dispatches on the
layout name (`ptkit.parse.PARSERS`), so adding the domain-grouped layout used
by the risk-engineering bank is a self-contained change: write the parser,
register it, add the name to `config.LAYOUTS`.

## Tests

```bash
pip install -e . && python -m unittest discover -s tests
```

Nearly every test in `tests/test_text.py` corresponds to text that reached, or
nearly reached, a live course in a broken state. Read the comments before
changing a regex.
