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
pip install "git+https://github.com/leonarduk/udemy-practice-test-kit@<commit-sha>"
```

Zero runtime dependencies; Python 3.11+ (`tomllib`).

**Pin to an immutable ref.** A course bank that is live (or about to be) must
not have its CSV projection change because the kit moved underneath it. A
commit SHA is the safest pin — unlike a tag, it cannot be repointed. Bump it
deliberately, and re-run `ptkit generate --check` in the course repo when you
do: if the CSVs go stale, the kit changed the projection and the course needs
regenerating and re-uploading to Udemy.

## Versioning

`ptkit.__version__` (in `src/ptkit/__init__.py`) is the only version number;
`pyproject.toml` reads it. **Bump it in every PR that changes behaviour**:
the minor version when the CSV projection or a check's verdict changes, the
patch version for anything else. `ptkit --version` prints the installed one.

The bump is not cosmetic. `pip install -r requirements-dev.txt` compares
*versions*, not commits: a course that moves its pin to a new SHA while the
version is unchanged gets "Requirement already satisfied" and silently keeps
the old kit wherever an earlier install survives, such as a self-hosted
runner or a developer's environment. That is exactly how java21 moved its pin
past the whitespace-collapse fix (`a152896`) and CI kept regenerating
collapsed CSVs until the runner was made to `--force-reinstall`. The
scaffolded `ci.yml` force-reinstalls for that reason; a version bump is what
fixes the same trap everywhere else.

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
# shuffle_options = true                        # see "Answer-option shuffle"
# shuffle_seed = "my-course/2026-09"             # required if shuffle_options is set

[exams]
numbers = [1, 2, 3, 4, 5, 6]
counts = { 1 = 50, 2 = 50, 3 = 50, 4 = 50, 5 = 50, 6 = 50 }
free = []                      # exam numbers that are the free sample
complete = [1, 2]              # exams declared FINISHED -- see below
# slugs = { 1 = "pcep-30" }    # optional: {exam} in csv_name uses this
                                # string instead of the bare number, for a
                                # bank whose established CSV names aren't
                                # numbered -- an exam with no entry here
                                # just uses its own number, as above

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
# strip_verified_asides = true  # see "Verified-aside stripping" below

# Cross-exam pairs reviewed and deliberately kept. A list of *reviewed* pairs,
# not a mute button: an unlisted pair above the threshold still warns, and a
# listed pair that drops below it is reported as stale.
[[checks.reviewed_pairs]]
left = "E1Q01"
right = "E1Q02"
reason = "different JLS rule behind a shared stem scaffold"
```

## The completion ratchet

`[exams] complete` lists the exams declared finished. It exists because the
question-count check is useless as a CI gate while a bank is being authored:
an exam nobody has written yet is not a regression, but it is
indistinguishable from one if "fewer than the target" always fails — so the
build stays red for the entire authoring phase, and a real regression is
invisible exactly when the gate would be worth having.

* an exam **not** listed may have fewer than its target — reported as
  `....` pending, not a failure;
* an exam **listed** must have *exactly* its target — a finished exam losing
  questions is a regression and fails;
* **more** than the target always fails, listed or not: that can only be a
  numbering or duplication mistake;
* a CSV whose row count disagrees with `questions-master.md` always fails, at
  any stage — the CSV is a projection of the master and desync is never
  acceptable.

One-way by policy: add an exam the moment it reaches its full count, in the
same commit that completes it, and never remove one — removing it silently
lowers the bar on content already held to it.

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

The parser dispatches on `[layout] kind` (`ptkit.parse.PARSERS`), so a new
master-file grammar is a self-contained addition: write the parser, register
it, add the name to `config.LAYOUTS`.

- `exam-grouped`: `# Exam N` / `## QNN`. Every Oracle/Spring bank. Each
  question's stem carries an inline `Domain N` prefix.
- `domain-grouped`: `# Exam N` / `## Domain M — Name` / `### QNN`. For a bank
  transcribed module-by-module from a domain-organized source (e.g.
  risk-eng-for-swe) — the domain is a heading grouping a run of questions,
  not a line repeated in each one. Question numbers restart at `### Q01` in
  every domain section, matching each source module's own numbering; the
  parser renumbers them sequentially within the exam so every `Question.qid`
  stays unique.
- `section-grouped`: `# <Section Name>` / `## QNN`, no numbering convention
  at all. For a bank authored as a flat list of named batches, where several
  batches feed the same output exam (e.g. three "Mock Exam" sections plus a
  later "Supplementary Questions" batch, all in `practice-test-1.csv`) — a
  shape `exam-grouped`'s "# Exam N" can't express, since two sections feeding
  the same exam don't share a naming pattern. `[sections]` in `course.toml`
  maps each section's exact heading text onto the exam number it belongs to.
  Question numbers restart at `## Q01` in every section; the parser
  renumbers them sequentially within the *target* exam, the same way
  `domain-grouped` does per domain. A `# ...` heading matches any text
  (there's no "Exam N" pattern to require), so a document's own front-matter
  title is tolerated: a heading with no `## QNN` questions under it is
  skipped as front matter unless it's declared in `[sections]`, in which
  case an empty declared section is treated as the real problem it is.

## Per-option explanations

An optional `**Why each option:**` block, sitting between the correct-answer
line and `**Explanation:**`, saying why *each* option is right or wrong —
not just the one overall explanation:

```
**Correct answer:** B

**Why each option:**
A. Wrong: this compiles, so it does not throw at build time.
B. Right: `byte` wraps around at 127 per JLS 15.14.2.
C. Wrong: nothing here fails to compile.
D. Wrong: this is the un-wrapped value, not what actually prints.

**Explanation:** `byte` wraps around at 127 per JLS 15.14.2.
```

Maps onto the CSV's `Explanation 1`-`4` columns, which Udemy shows beside
each option when a learner reviews their attempt — this is where a practice
test does most of its teaching, telling someone why the distractor they
picked was wrong rather than only what the right answer was.

All-or-nothing: a course that doesn't author these just omits the block
entirely (`Question.option_explanations` is then `{}` and every `Explanation
N` column stays blank, same as before this feature existed). If the block is
present, every option needs an entry — a half-filled block is a parse error,
since a blank next to the option a learner actually chose is worse than none
at all.

## Multi-select questions

Write the answer line in the plural to make a question multi-select:

```
**Correct answers:** A, C
```

The plural is what declares the type, so `**Correct answers:** D` -- one key,
presented as multi-select -- parses and stays multi-select, but `ptkit
validate` fails it: Udemy rejects the whole bulk-upload CSV if any
multi-select question keys fewer than two answers (UDEMY-PLATFORM-NOTES.md
8a), so a "which of these are defects?" question whose only right answer is
"none of them" cannot be multi-select. Word the options so at least two are
always true (e.g. "which statements are true?"). `**Correct answer:** A, C`
(singular, two letters) is a parse error rather than a silent upgrade.

The CSV row gets `Question Type = multi-select` and `Correct Answers = "1,3"`,
the format Udemy's own V2.2 template example uses. Single-answer heuristics
(key distribution, option-length parity, naive strategies) skip multi-select
questions -- there is no single key to pick by position or length -- and
`check_multi_select_keys` warns instead when every multi-select question in
an exam keys the same number of options. The shuffle permutes a multi-select
question's options per question, without slot balancing. Set
`option_letters = "ABCDEF"` to use all six of Udemy's option columns.

## Answer-option shuffle

`[layout] shuffle_options = true` (with a required `shuffle_seed`) reorders
each question's answer options deterministically at parse time, before any
check or CSV render sees the questions. It exists because a bank authored
straight through tends to put the correct answer in the same slot far too
often — one bank had option B correct in 73% of its questions, comfortably
above its own 70% pass mark, so answering "B" to everything passed without
reading a single question. `check_key_distribution` / `check_naive_strategies`
(`checks/quality.py`) detect this; shuffling is the fix.

The permutation is a pure function of `(shuffle_seed, exam number, question
stem text)` — regenerating without any content change reproduces
byte-identical CSVs, and editing one question's stem does not reshuffle its
neighbours' options. Per-option explanations (see above) are permuted
together with the options they describe, so an explanation always travels
with the answer it's talking about. `ptkit generate --no-shuffle` emits the
authored order instead, for hand-diffing against `questions-master.md`.

Off by default: turning it on re-keys every question in the bank, so it is
only safe for a course that has never been uploaded, or that is being
deliberately re-keyed on purpose. Once enabled, `shuffle_seed` is part of the
bank's identity — changing it reshuffles everything, so treat it like a
schema field, not a tuning knob.

## Verified-aside stripping

`TextRenderer` drops a "Verified ..." (or "Matches this module's own ...
README") sentence as a discardable aside — built for a course whose
explanations already state the answer in full and then append a short,
redundant verification note ("... wraps to -128. Verified: prints -128.").

That assumption isn't universal. A course whose explanations use "Verified
by running it: `<the actual observed behaviour>`" as the substantive
evidence — the one place a specific concrete detail is stated, not a restated
aside — needs `[checks] strip_verified_asides = false`, or the sentence
carrying the real content is deleted, not just a redundant tail. Default
`true` keeps every existing adopter's output unchanged.

## Video courses

`ptkit video` builds Udemy lecture videos from Marp Markdown. A video course
repo owns its lectures and `video-course.toml`; the kit owns the pipeline --
the same split as the practice-test side.

```bash
ptkit video new-course ../my-video-course
ptkit video check                    # script problems, durations, recordings left
ptkit video build --engine silent    # free preview: slides + timing, no voice
ptkit video script 01-01             # reading script, slide by slide
ptkit video build                    # build/<lecture>.mp4 + build/<lecture>.vtt
```

**One file per lecture.** Slides are separated by `---`; each slide's
narration is its HTML comment (Marp's presenter-notes convention, so the
Marp VS Code preview shows the script as notes). Directive comments such as
`<!-- _class: lead -->` are not narration. `[pause 600ms]` inserts a pause.

**Voice engines** (`[voice] engine`, or `--engine` per run):

| Engine | What | Use for |
|---|---|---|
| `recorded` (default) | your takes in `recordings/<lecture>/slide-NNN.{wav,m4a,mp3,flac}`, high-passed and loudness-normalised to -19 LUFS | the published course |
| `azure` | Azure Neural TTS over REST (stdlib `urllib`; key/region from `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION`) | drafts; small fixes after publishing |
| `edge` | the same neural voices via the optional `edge-tts` package (7.3.1+), which uses the Edge browser's read-aloud service: no key. Pronunciations are substituted into the text and `[pause]` markers become silence between chunks. Not a licensed TTS product -- check its terms before paid use | keyless drafts; courses that accept that trade-off |
| `silent` | silence of the estimated length | previewing slides, pacing and captions for free; CI |

`recorded` is the default because Udemy's reviewers have rejected courses
narrated entirely by text-to-speech, and staff have said TTS may be used for
edits but not to replace the instructor. This comes from instructor-community
threads (2023-2025), not an official policy page -- ask policy@udemy.com
before relying on synthetic narration for a whole course.

**Timing is exact, not re-derived.** One WAV per lecture is assembled
sample-exactly in Python (lead-in + slide audio + tail per slide) and each
slide image is held for exactly that span, then ffmpeg encodes once. Clip-by-
clip encoding and concatenation was rejected: each AAC segment's encoder
priming adds a small gap, and over a long lecture they drift audibly against
the captions.

**Captions come from the script**, not speech recognition, so exam codes and
API names are spelled right. Sentence timing within a slide is shared out by
character count. With the `edge` engine it is shared out within each chunk's
measured speech: edge-tts pads every chunk between `[pause]` markers with
about 0.6 s of silence before and 0.7 s after, which otherwise put captions
up to ~2.7 s ahead of the voice (kit 1.4.2). Terms the voice mangles go in `[pronounce]` (applied as SSML
`<sub alias>`), which changes the speech and leaves the captions alone.

**Caching.** Synthesised audio is keyed by (engine, voice, rate, SSML) and
recorded takes by file content + filter, under `build/audio-cache/`. A
rebuild only re-synthesises slides whose script changed -- it does not spend
TTS quota twice.

Needs Node (Marp runs via `npx`, pinned to `@marp-team/marp-cli@4.5.1`),
Chrome or Edge (Marp's PNG renderer), and ffmpeg. `ptkit video check` needs
none of them, which is why it is the CI gate. The real build test runs with
`PTKIT_VIDEO_E2E=1`.

## Tests

```bash
pip install -e . && python -m unittest discover -s tests
```

Nearly every test in `tests/test_text.py` corresponds to text that reached, or
nearly reached, a live course in a broken state. Read the comments before
changing a regex.
