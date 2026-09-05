# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## What this is

Question bank and generated bulk-upload files for a Udemy practice-test course
targeting **TODO: exam name and code**. Read `HANDOVER.md` before making
changes.

## Source of truth and generated files

- `questions-master.md` is the source of truth. Edit questions here first.
- `practice-test-{1..6}.csv` are generated — never hand-edit, regenerate.
- `course.toml` is this bank's configuration: paths, exam sizes, domain names,
  check thresholds.
- The pipeline lives in the shared
  [udemy-practice-test-kit](https://github.com/leonarduk/udemy-practice-test-kit)
  package (`ptkit`), pinned in `requirements-dev.txt`. Do not vendor a copy of
  it into this repo — a fix that lands in one course repo and not the others
  is exactly the failure mode the kit exists to end.
- Subject-specific checks belong in `tools/course_checks.py` here. Generic
  ones (platform, psychometric) belong in the kit.

## Commands

```bash
pip install -r requirements-dev.txt
ptkit validate
ptkit generate
ptkit generate --check
```

CI runs `ptkit validate` and `ptkit generate --check`, plus `actionlint`.

## Authoring standard

See the header of `questions-master.md`. Option-length parity is a first-class
constraint while writing, not a cleanup pass — hand-authored questions drift
strongly towards the correct answer being the longest, most caveated option.

## Before authoring anything

Read the kit's `UDEMY-PLATFORM-NOTES.md`. It records how Udemy actually
renders these fields, including the two that most often break a shipped
course: the Question field is plain text (Markdown renders literally), and
Answer Option cells are parsed as HTML (a bare `<` silently eats the text
after it).
