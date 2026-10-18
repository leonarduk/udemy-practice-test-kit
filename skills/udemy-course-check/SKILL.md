---
name: udemy-course-check
description: Verify one of the user's Udemy courses end to end, read-only. Checks the course repo (scripts, samples, renders, listing text), then the live Udemy course against it (curriculum, videos, captions, quizzes, landing page, promotion and AI-disclosure rules, free previews, draft/live parity for practice tests), with an optional Whisper pronunciation pass for TTS narration. Use when the user types /udemy-course-check, or asks to "verify/check/audit the course", "is the course ready to submit/publish", "check it matches Udemy", or "what's wrong with course <id>", for a video course (video-course.toml, ptkit video) or a practice-test course (course.toml, ptkit).
user-invocable: true
---

# /udemy-course-check — verify a Udemy course, repo and live

The user builds Udemy courses from git repos with the shared kit
`udemy-practice-test-kit` (ptkit). There are two kinds:

- **Video course:** `video-course.toml`. Marp lectures (`lectures/*.md`) are
  rendered to `build/<stem>.mp4` and `.vtt` by `ptkit video build`. Samples are
  verified by `tools/verify_samples.py`. The listing lives in
  `platforms/udemy/course-listing.md`, the record in `platforms/udemy/STATUS.md`.
- **Practice-test course:** `course.toml`. `questions-master.md` is projected
  to `platforms/udemy/practice-test-N.csv` by `ptkit generate`.

This skill is **read-only**. It reports; it never edits the repo or Udemy.
Anything it finds that needs changing on Udemy (especially anything students
see, or submitting or publishing) goes back to the user as a proposal.

Every rule comes from a real upload or review. The background is in the kit's
`UDEMY-PLATFORM-NOTES.md`, and the bracketed numbers in the script output
point at its sections. Read the notes for any FAIL you don't understand.

## 1. Repo checks

From the course repo root (ask which repo if it's unclear; they live under
`D:\workspace\GitHub\`):

```bash
python ~/.claude/skills/udemy-course-check/scripts/check_repo.py --jdk-bin "C:/Program Files/Java/jdk-25/bin" --manifest "$TEMP/udemy-manifest.json"
```

- `--jdk-bin` puts the full JDK on PATH. Oracle's `javapath` shim has no
  `jar`, which some samples need. Use `--skip-samples` to skip them.
- The installed `ptkit` must match the repo's `requirements-dev.txt` pin,
  and the script checks this. Installing another repo's pin replaces it. To
  fix, run
  `pip install --force-reinstall --no-deps "git+https://github.com/leonarduk/udemy-practice-test-kit@<pin>"`.
  Process substitution (`-r <(...)`) doesn't work in this Windows shell.
- It prints PASS / WARN / FAIL lines and writes a manifest for step 2: the
  listing, the expected curriculum, and the per-lecture files with VTT cue
  counts, or per-exam keys.

**Video checks:**
- `ptkit video check` and `verify_samples.py` run clean.
- Every lecture has an mp4 and vtt newer than its source.
- Video length equals narration length (the old kit left a silent tail).
- Videos are at least 720p. Files over 10 MB are flagged, because Claude in
  Chrome's `file_upload` caps at 10 MB.
- No promotion outside the Bonus Lecture.
- Runtime is at least 30 min, and under 120 min if the course is free.
- Title is 60 characters or fewer, subtitle 120 or fewer, and lecture titles
  80 or fewer, all plain text.
- The listing description has the verbatim AI disclosure, no links, and no
  domain-like dotted names such as `java.lang.IO`.

**Practice-test checks:**
- `ptkit validate` and `ptkit generate --check` pass.
- There are 6 or fewer tests.
- No tag-shaped `<` appears in learner text.
- **Answer positions aren't predictable.** It warns when keys repeat with a
  short period (exams 4–6 of the Java 25 bank cycle A, B, C, D) or one letter
  holds more than 40%.

**Both kinds:** the installed ptkit must be the exact commit the repo pins.
Otherwise `generate --check` and the video checks report false failures, so
the script FAILs it first. Fix that and re-run before trusting anything else.

## 2. Live Udemy checks (Claude in Chrome)

1. Load the Chrome tools in one ToolSearch call (`tabs_context_mcp`,
   `tabs_create_mcp`, `navigate`, `javascript_tool`, `computer`, `find`).
   Make a new tab in the session's group.
2. Navigate to `https://www.udemy.com/instructor/courses/`. The user is
   normally signed in; if not, ask them to sign in. Find the course id, which
   STATUS.md or HANDOVER.md usually records.
3. Read `scripts/udemy_check.js`, and run it with `javascript_tool` as the
   file's text followed by
   `await udemyCheck(<courseId>, <manifest JSON pasted inline>)`.
   - For a large manifest, trim to the keys the check uses: `kind`,
     `listing`, `files` (or `exams`), and `runtime_seconds`.
   - If an evaluation runs past the tool's 45 s limit (caption fetches on a
     long course), run it without `await` into `window.__r`, then read
     `window.__r` in a second call.
   - Output with `=` or query-like strings can be blocked by the tool's
     filter. Return counts and short strings, not raw HTML.

**Video checks:**
- Title and subtitle match the listing.
- The description opens with the AI disclosure, has no `<a>` links, and has
  real bullets.
- The image is set, and the promo video is reported.
- The editor checklist is complete.
- The curriculum matches the listing table in order, with "Bonus Lecture" last.
- Every lecture has a processed video whose file name matches the build, and
  an English caption matching the local VTT (cue count and first cue; Udemy
  stores captions with CRLF line endings).
- Runtime is at least 30 min, and under 2 h if free.
- Only a few lectures are free previews; replacing videos once set all 28.
- No promotional lecture descriptions, and the Bonus Lecture's description is
  empty: the reviewer made us remove a course list there.
- External links appear only on the Bonus Lecture.
- Every quiz has questions.

**Practice-test checks:**
- One test per exam.
- For each test, live and `?draft=true` are identical; a divergent draft is
  dangerous to publish.
- Question count and answer keys match the CSVs.

Then look at the course's **feedback page** (`/manage/feedback/course`, reached
from the sidebar link, since direct navigation often redirects). If the status
is "Needs fixes", quote the required and recommended items.

## 3. Pronunciation pass (TTS-narrated video courses)

Udemy accepts TTS audio, but its review warns that mispronunciations can
trigger a Trust and Safety re-review. Run this before submitting, and after
any narration change:

```bash
pip install faster-whisper          # once; model small.en downloads on first use
python ~/.claude/skills/udemy-course-check/scripts/transcribe.py "$TEMP/stt" build/*.mp4
python ~/.claude/skills/udemy-course-check/scripts/compare.py "$TEMP/stt" > "$TEMP/diffs.txt"
```

- `transcribe.py` decodes the audio with ffmpeg itself, because PyAV is broken
  on this machine.
- `compare.py` prints every word-level difference between the narration and
  what Whisper heard.
- Most differences are Whisper's spelling (US vs UK, digits, a dropped "dot").
  Flag only real mishearings of technical terms, such as `openjdk` heard as
  "arpenge" or `awt` heard as "aut". The fix is a `[pronounce]` entry in
  `video-course.toml`, then rebuilding that lecture. Propose it; don't apply
  it in this skill.

## 4. Report

Give the user one table per area: repo, live course, pronunciation. Show FAIL
first, then WARN, with the reason and the fix for each, citing the
platform-notes section where there is one. Then:

- **Status:** the course's Udemy status, and any open reviewer feedback.
- **Proposed fixes:** split into repo changes (a PR) and Udemy changes. Udemy
  changes need the user's go-ahead before anything students see changes,
  including publishing practice-test edits, which sends a learner message.
- **Not checked:** say what you couldn't verify, for example Oracle's exam
  objectives when its site is down, or captions when an asset is still
  processing.

Never mark the course "ready" if any FAIL remains. Don't call a WARN harmless
without saying why.
