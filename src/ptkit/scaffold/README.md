# TODO: Course Title — Practice Test Question Bank

Question bank and generated bulk-upload files for a Udemy practice-test course
targeting **TODO: exam name and code**.

Target: 6 mock exams of TODO questions each, covering all TODO official exam
domains.

## Source of truth and generated files

- `questions-master.md` is the durable, platform-independent source of truth.
  Edit questions here first.
- `practice-test-{1..6}.csv` are **generated** — never hand-edit them,
  regenerate instead.
- `course.toml` holds everything specific to this bank: paths, exam sizes,
  domain names, check thresholds.
- The pipeline itself lives in
  [udemy-practice-test-kit](https://github.com/leonarduk/udemy-practice-test-kit).
  Read its `UDEMY-PLATFORM-NOTES.md` before authoring — it is the list of
  platform quirks that have already cost a live course.

## Commands

```bash
pip install -r requirements-dev.txt

ptkit validate          # structural + item-quality checks
ptkit generate          # regenerate the per-exam CSVs
ptkit generate --check  # write nothing; non-zero exit if the CSVs are stale
```

Regenerating a CSV does **not** update the live course — it has to be
re-uploaded. For a handful of questions, edit them in place via Udemy's
per-question editor instead; re-uploading resets the test's duration, passing
score and description.
