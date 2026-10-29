# Udemy practice-test platform notes

The single place where platform quirks are recorded. Every entry cost a real
course something. Before this file existed, each quirk was known in exactly
one repo — the one where it was discovered — and the other six shipped into
the same trap.

Add to this file whenever you learn something new about how Udemy actually
renders or imports a practice test, and say how it was confirmed.

---

## 1. The Question field is PLAIN TEXT on the bulk-upload path

Udemy's CSV importer does not render Markdown in the `Question` column. A
```` ```java ```` fence, a `backtick span`, or `**bold**` reaches the learner
as literal punctuation.

* **Consequence:** a whole practice test had to be deleted and re-uploaded
  after shipping with visible fence markers.
* **Handled by:** `ptkit.text.TextRenderer` strips fence marker lines,
  backticks and emphasis delimiters during CSV projection.
* **Guarded by:** the "Learner-facing text hygiene" check warns on any
  backtick that survives into a learner-facing column.

## 2. …but the per-question editor DOES render HTML

The same field, edited through Udemy's web per-question editor rather than
bulk upload, renders HTML. A `<pre class="prettyprint linenums">…</pre>` block
formats code correctly there — and renders as visible junk text if uploaded
through the CSV path instead.

* **Consequence:** these are two different formats for the same field. Do not
  move text between the two paths without re-checking it.
* **Confirmed:** by the Python bank, which drives the per-question editor
  from a `<pre>`-wrapped copy specifically because the CSV path cannot carry
  formatted code.

## 3. Answer Option cells ARE parsed as HTML, even on the CSV path

Unlike `Question`, the `Answer Option N` cells go through an HTML parser. A
bare `<`, `>` or `&` is treated as markup:

```
Both beans are injected into a List<PaymentGateway> automatically
                                      ^^^^^^^^^^^^^^^^
```

`<PaymentGateway>` is parsed as an unknown tag and **dropped**. The learner
sees "injected into a List automatically" — a different claim from the one
that was authored, and one that may now be true when the option was meant to
be false.

* **Escape as:** `&lt;` `&gt;` `&amp;`. A literal `<br>` is allowed and is
  the only tag that survives.
* **Guarded by:** `ptkit`'s "Answer Option HTML safety" check.
* **Discovered on:** the Python bank (`<class 'str'>` options vanishing).
  Found in the Spring bank the first time the shared check ran there.

**A lone `>` is not the same problem.** An unmatched `>` renders literally in
every browser, and Java/stream banks are full of `->` — in lambdas, and in
expected output like `Pa Pbb Pccc -> ccc`. The original check flagged `>` as
belt and braces; run against a Java bank that is four false alarms on one
question, and a check that cries wolf is one people learn to skip. Only `<`
is flagged now. The same reasoning applies to `&`: `P&L` and `a & b` render
as written, so only a `&` that actually forms an entity (`&nbsp;`) is
flagged.

## 3a. Which columns are HTML-parsed: all three, tested directly

**Settled by a live upload on 2026-10-15 (java21 bank, course 7327045).** An
earlier version of this section said `Question` was plain text, inferring it
from the Python bank's `<pre>` block showing up as junk. That inference was
wrong. Uploading the java21 bank's `practice-test-1.csv` into a fresh draft
practice test and reading back what Udemy stored
(`GET /api-2.0/quizzes/{id}/assessments/?draft=true`) gave:

| Column | Bulk-upload (CSV) path | Evidence (java21 Exam 1) |
|---|---|---|
| **Question** | **HTML-sanitised.** A tag-shaped `<Word>` is removed, while a `<` that can't start a tag survives (stored as `&lt;`). | Q35's `Set<Point> set = new HashSet<>();` was stored as `Set set = new HashSet&lt;&gt;();`, so `<Point>` vanished and `<>` survived. Q4's `i < 3` survived as `i &lt; 3`. |
| **Answer Option N** | **HTML.** Same behaviour. | The Python bank's issue #67 (`<class 'str'>` options losing their text), confirmed again on the Spring bank. |
| **Overall Explanation** | **HTML-sanitised.** Same behaviour. | Q33's `...remove on a List<Integer> is...` was stored as `...remove on a List is...`. Q34's `static <T> List<T> asList(T... a)` became `static  List asList(T... a)`. |

So the rule is the same in every learner-facing column: **a `<` followed by a
letter, `/`, `!` or `?` is eaten as a tag, along with everything up to the next
`>`.** `i < 3`, `x <= y` and `<>` render fine. `List<String>` silently becomes
`List`. That's a different claim, and sometimes it turns a false option or a
correct explanation into nonsense.

The Python bank's `<pre>` result is consistent with this. The sanitiser drops
the tags it doesn't allow and escapes or keeps the rest. It was never evidence
of plain text.

**Scale of the problem on a Java bank:** java21 has 68 stems and 12 explanations
with a tag-shaped `<` across its six exams, almost all of them generics.

**Fix:** escape `<` as `&lt;` in every learner-facing column, not just Answer
Options. Whether a CSV-supplied `&lt;` renders as `<` in Question and Overall
Explanation (as it does in Answer Options) is **not yet confirmed**. Check one
upload before relying on it, and record the result here.

**Leading indentation does not survive rendering either.** The same upload
stored Q3's 4-space indents verbatim inside `<p>...<br>    case ...</p>`. The
learner view renders the stem in a proportional font with `white-space:
normal`, which collapses them. So in the learner preview's practice mode, Q3's
`case` lines sit flush left. This was confirmed by inspecting the rendered element's
computed style and by screenshot. Preserving spaces in the CSV (kit `a152896`) is
still right, since the stored text is faithful, but it gains the learner
nothing unless the spaces become `&nbsp;` or the text gets `<pre>` formatting
via the per-question editor (§2).

## 4. Regenerating a CSV is not the same as updating the course

The generated CSVs are an input to Udemy, not a live view of it. Nothing a
learner sees changes until the file is re-uploaded.

For a wholesale change, re-upload. **For a handful of questions, edit them in
place via the per-question editor instead** — re-uploading resets the test's
duration, passing score and description, and renumbers the curriculum.

## 5. Practice-test-only courses cap at 6 practice tests

A course consisting solely of practice tests cannot hold more than six. A
seventh (e.g. a short diagnostic exam) can be generated and validated in the
repo but cannot be uploaded until the course gains non-practice-test content.

## 6. Row endings are CRLF; newlines inside a quoted field are LF

That is what the working uploaded files use, so `ptkit` writes exactly that:
`csv` module with `lineterminator="\r\n"`, `QUOTE_MINIMAL`, UTF-8 with no BOM.

Note that a `core.autocrlf` checkout — or an LF-normalising commit — rewrites
these files, so comparing a generated CSV to the one on disk must normalise
line endings. `ptkit generate --check` and the csv-sync validation check both
compare through `ptkit.csvout.normalise_newlines` so they can never disagree.

## 7. Unused template columns must stay present

Udemy's `PracticeTestBulkQuestionUploadTemplate_V2.2.csv` requires all 17
columns even when `Explanation 1-6` and `Answer Option 5-6` are empty. `ptkit`
emits them blank rather than dropping them, and the structure check asserts
the on-disk template header still matches what the kit expects — so a Udemy
template revision is caught rather than silently mis-mapped.

## 8. Multi-select: what the template confirms, and what it doesn't

`PracticeTestBulkQuestionUploadTemplate_V2.2.csv` itself carries a
multi-select example row: `Question Type = multi-select`, `Correct Answers =
"1,3,4"` (comma-separated, no spaces, quoted by the CSV writer), up to six
`Answer Option` columns. `ptkit` emits exactly that.

### 8a. A multi-select question needs at least two correct answers

Udemy **rejects the whole CSV** if any `multi-select` row keys fewer than two
answers; nothing is imported. The bulk-upload dialog reports:

```
multi-select question type must have minimum two correct answers. It is
invalid in rows 7, 13, 19, 22, 28, 34
```

(row numbers count data rows, header excluded).

* **Guarded by:** since ptkit 1.4.0 (PR #8), `ptkit validate` reports any
  multi-select question with fewer than two correct answers as a structural
  failure, naming the question and its key, so the CSV never reaches Udemy.

* **Consequence:** the ai-code-review bank's "which are defects?" questions
  keyed a single answer whenever a PR had one defect or none (approve only),
  36 of 72. The bank was redesigned so every question asks "which
  statements are true?" with options worded as a problem or as sound code,
  which always leaves at least two true.
* **A "none of these" option that must be chosen alone cannot be a
  multi-select key.**
* **Confirmed:** 2026-10-16, ai-code-review bank, course 7381469, first
  upload of `practice-test-1.csv` into an empty draft test.

### 8b. Multi-select is scored all or nothing

There is **no partial credit**. In the instructor preview, Exam mode:

* a question answered with one of its two correct options was marked
  **Incorrect** and scored 0;
* a question answered with exactly its three correct options was marked
  **Correct**, and the attempt scored 1/36 with nothing else answered.

* **Confirmed:** 2026-10-17, ai-code-review bank, course 7381469, test 1,
  two Exam-mode attempts read from the results and review pages.

## 9. Bulk-uploaded text with `**` shows literal asterisks

A `**` that survives into a CSV cell (Python's power operator here, not a
leftover bold marker) is stored as typed and renders as two asterisks in the
stem and in an option's explanation, with no bold. So a bank with real `**`
content needs nothing special; a leftover Markdown `**bold**` will show its
asterisks (see §1).

* **Confirmed:** 2026-10-17, ai-code-review bank, course 7381469, test 1
  Q28 (M1-E10): `(1 + rate / 12) ** 12 - 1` in the stem and `Decimal ** int`
  in an option explanation, read from the API, the rendered DOM and a
  screenshot of the review page.

## 10. A practice-test-only course cannot carry a downloadable file

Its curriculum offers only practice tests (no lectures, so no lecture
resources), course messages are plain text with a 1000-character limit, and
the course-level Bulk Uploader only stores files for lectures. A bank whose
questions depend on files (code to review) has to host them elsewhere and
link them. The course messages accept a link once Udemy's reminder that
"Links must be to free educational content that doesn't require students to
register" is acknowledged; the landing page forbids external links.

Practice mode's start page **does not show the practice test's
description**, only the question count and instructions; Exam mode shows it.
So a link that only lives in the test description is missed by learners who
start in Practice mode. Put it in the welcome message as well.

* **Confirmed:** 2026-10-16/17, course 7381469 (practice-test-only): the
  curriculum's add-item menu, the course messages page, and both mode start
  pages in the instructor preview. The exercise pack is hosted at
  `leonarduk/ai-code-review-exercises`.

## 11. Template V2.2 is still current (2026-10-16)

The bulk-upload dialog's "Download CSV template" link points at
`https://s.udemycdn.com/instructor/manage/PracticeTestBulkQuestionUploadTemplate_V2.2.csv`,
and its header is unchanged. Guessed newer names (V2.3 to V3.1) return 403.

---

# Video courses

Sections 12 onward come from the first video course uploaded with
`ptkit video` output: java25-whats-new-course, course 7385221, 2026-10-17.
Everything was driven through Claude in Chrome.

## 12. Caption upload rejects a .vtt sent as `application/octet-stream`

The Captions tab signs each upload with `POST /api-2.0/s3-upload-signatures/`,
and the policy carries the file's MIME type. With `Content-Type:
application/octet-stream` the signer answers **400 `{"results":["Invalid
input."]}`**. The page only shows "An error occurred uploading your file.
Please try again later." With `text/vtt` it answers 200, the file goes to S3,
and `POST /api-2.0/courses/{id}/assets/{asset}/draft-captions/` creates the
caption.

* **When it bites:** browser automation that hands the page a file without
  a type. Claude in Chrome's `file_upload` does this for `.vtt`. A Windows
  machine with no `.vtt` MIME mapping may do the same through the normal file
  picker (not tested).
* **Workaround used:** before the first upload on each page load, override
  `File.prototype.type` in the page so a `.vtt` reports `text/vtt`. The bytes
  are unchanged.
* **After a failed attempt, the uploader sends nothing more** until the
  page is reloaded: later file selections fire no network request at all.
  Reload, then retry.
* **Confirmed:** by capturing the XHR bodies and responses for the failing
  and the working attempt (lecture 1), then 27 uploads on one page load.

## 13. Captions: video first, then about 12 minutes of processing

A caption can only be uploaded for a lecture that has a video asset; the
Captions tab lists only those lectures. A caption uploaded while the video
was still processing was accepted. A 93-second 1080p MP4 took about 12
minutes to go from asset `status` 0 to 1; later ones were faster. The
caption language defaults to the course locale (English (UK) here).

Udemy stores the uploaded VTT with **CRLF** line endings and names it
`<lecture-slug>.autogenerated.vtt`, but its `source` is `manual`, and the
cues are the uploaded ones. So compare cue text, not bytes. Checked for all
27 uploads by fetching each caption's URL and comparing cue count and first
cue with the local file.

## 14. "java.lang.IO" in the description is refused as an external link

The landing-page description editor reads a dotted name ending in a real TLD
as a URL. "java.lang.IO" blocked the save with "External links are not
allowed here. Please remove the link java.lang.IO to proceed." Rewording to
"the new IO class in java.lang" fixed it. Expect the same for other
`*.io`/`*.ai`/`*.dev`-shaped names. A description pasted as HTML (a paste
event with `text/html`) keeps real `<ul><li>` bullets and `<strong>`.

## 15. The curriculum API: what the editor itself calls

The editor uses `/api-2.0/users/me/taught-courses/{course}/...`. The
intuitive `/api-2.0/courses/{course}/chapters/{id}/` returns 404 for writes.

* Rename: `PATCH .../taught-courses/{course}/chapters/{id}/` or
  `.../lectures/{id}/` with `{"title": ...}`. `{"is_free": true}` on a lecture
  marks it as a free preview.
* Create: `POST .../taught-courses/{course}/lectures/` or `.../chapters/`
  with `{"title": ...}`. New items are unplaced until the order is saved.
* Order: `PUT /api-2.0/courses/{course}/instructor-curriculum-items/` with
  `{"items": "<JSON string of [{id, class, is_published}]>"}`. The value is a
  string containing JSON, not a nested array.
* Read back: `GET /api-2.0/courses/{course}/instructor-curriculum-items/?page_size=200&fields[lecture]=title,asset,is_free&fields[asset]=title,status,length,captions`.

Headers: `X-CSRFToken` from the `csrftoken` cookie, plus
`X-Requested-With: XMLHttpRequest`. Confirmed by capturing the editor's own
requests, then building 8 sections and 26 lectures this way. They were
verified after a reload.

Like practice-test routes, `/instructor/course/{id}/manage/basics/` and
`/course/draft/{id}/learn/lecture/{id}` redirect when opened directly. Click
the sidebar link, or use the Preview menu's "As Student" link (it has
`?instructorPreviewMode=student_v4`).

## 16. Free courses: the Pricing tab's own rules

The Pricing tab now sets a "backup price" for the Deals programme. "Free" is
one of its tiers. The tab itself says a free course "must have a total video
length of less than 2 hours and can not have practice tests", and that
switching between free and paid more than once limits promotional
announcements. So a free course cannot take a practice test, and a
practice-test-only course cannot be free.

## 17. Lecture descriptions strip links; use External Resources

`PATCH .../taught-courses/{course}/lectures/{id}/` with a `description`
containing `<a href="...">` returns 200, but the stored description has the
`<a>` removed and only its text left. This happened with and without
`target`/`rel`, and to links to the instructor's own Udemy courses in the
Bonus Lecture. So a Bonus Lecture that promotes other courses needs its
links as **External Resources**. The editor makes these with two calls:
`POST /api-2.0/users/me/external-link-assets/` `{title, url}` (201, returns
an asset id), then `POST .../taught-courses/{course}/lectures/{id}/assets/`
`{asset_id, type: "supplementary"}`. Confirmed on course 7385221: 5 links,
read back as `supplementary_assets` of type `ExternalLink`.

Replacing a lecture's video (Edit Content → Replace) creates a new asset,
and the caption stays with the old asset. Upload the caption again
afterwards.

## 18. Replacing lecture videos left every lecture marked as a free preview

After all 28 lecture videos of a free course were replaced (Edit Content →
Replace), `is_free` read back as `true` on all 28 lectures. Before, only the
2 chosen previews had it. The cause was not isolated: it may be the replace
flow, or Udemy's handling of free courses. Either way, after any video
replacement, re-read `is_free` from `instructor-curriculum-items` and reset
it with `PATCH .../taught-courses/{course}/lectures/{id}/` `{"is_free": false}`.
Each replacement makes a new asset, so its captions have to be uploaded
again too (§17). Confirmed on course 7385221, 2026-10-17, by reading
`is_free` back before and after.

## 19. Lecture quizzes: the editor's API, and code blocks that render

A course quiz (not a practice test) is two kinds of call:

* Quiz: `POST /api-2.0/courses/{course}/quizzes/`
  `{"title", "description": "", "type": "simple-quiz"}` (201, returns the id).
  It is unplaced until the curriculum order is saved (§15), with
  `{"id", "class": "quiz", "is_published": true}` in the `items` list.
* Question: `POST /api-2.0/quizzes/{quiz}/assessments/` with
  `assessment_type: "multiple-choice"`, `question` (HTML), and these as JSON
  *strings*: `answers` (list of HTML), `feedbacks` (one per answer; the
  "Explain why this is or isn't the best answer" text), `correct_response`
  (e.g. `"[\"b\"]"`). Also send `related_lecture: ""`, `explanation: ""`,
  `section: ""` and `section_name_map: "[]"`.
  `DELETE .../assessments/{id}/` removes one.

Unlike the practice-test CSV path (§1-3), the question HTML is stored
exactly as sent. `<pre class="prettyprint linenums">` with `&lt;`/`&gt;`
escaping keeps its line breaks, and in the student player it renders as a
highlighted code block with line numbers. Confirmed on course 7385221: 33
questions read back identical to what was sent, and section 2 Q1 checked in
the student preview, 2026-10-17.

## 20. Publishing practice-test edits requires a message to learners

On a published practice test, "Publish changes" opens a **required** "Send
update message to learners" dialog. "Send and publish changes" stays
disabled until the message box has text. Existing students see the message
on their practice-test results page. A "Send as educational announcement"
checkbox (limited, e.g. "4 out of 4 left this month") also sends it by
email and the notification bell. Leave it unticked unless that's wanted.
Because this message reaches students, agree its wording with the owner
before publishing.

Also: the first "Save question" on a published test creates a whole new
draft (`POST /api-2.0/courses/{id}/quizzes/` `{quiz_id, draft_action:
"create"}`) with new assessment ids, then updates the edited question in
it. The edited field is stored as editor HTML (`<p>…</p>`), not the
CSV-imported plain text.

* **Confirmed:** java25 practice tests, course 7306443, Mock Exam 6,
  2026-10-17, by capturing the editor's requests and reading live and draft
  back before and after publishing.

## 21. The Captions tab uploads one file at a time; extra files are dropped

On the Captions tab, each lecture has its own upload input. If you hand a
second lecture's `.vtt` to its input while the first is still uploading, the
second is silently dropped: no error, no caption, and the tab looks normal.
Wait until each caption shows (the tab's "Uploaded / A few seconds ago", or
the lecture's asset `captions` in the curriculum API) before sending the
next one. Uploads sent one at a time all succeeded on the same page load.

* **Confirmed:** course 7385513 (What's New in Python 3.14), 2026-10-17.
  23 captions sent back to back in three bursts left only the first of each
  burst (lectures 3, 7 and 16) captioned. After a reload and the §12 MIME
  patch, the other 19 were sent one at a time, each checked through the
  API, and all 19 took.

## 22. Course messages: a synthetic paste is not saved

The landing-page description accepts HTML pasted by a synthetic paste event
(§14), and it's saved. The Course messages tab's two editors (Welcome,
Congratulations) do not save it: the text appeared in both editors, Save
was clicked, and after a reload both were empty. Type the messages in, or
use the editor by hand.

* **Confirmed:** course 7385513, 2026-10-17, by reloading the tab after
  Save. Keyboard input was tried next but didn't reach the editors while
  the Chrome window was minimised (screenshots also timed out then), so
  whether typed text saves is not yet tested here; the Java 25 course's
  messages were set by hand.

## 21. Quality review: AI disclosure first, and no course lists in lecture descriptions

First quality review of a TTS-narrated video course (course 7385221,
2026-10-18) came back "Needs fixes" with two required items:

* **AI disclosure, verbatim, at the very top of the description.** Any use
  of AI (here, TTS narration) needs the exact sentence "This course
  contains the use of artificial intelligence." as the first thing in the
  course description. A line further down that says "the voice-over is
  AI-generated" was **not** enough. The Help Center link in the feedback
  (`/hc/en-us/articles/33490280024087`) now redirects; the wording came
  from that article's quoted text and the Udemy staff community post
  "AI Policy Clarification…" (2025-11-06), which agree. Put it in the
  listing template from day one.
* **No list of your other courses in a lecture description, even in the
  Bonus Lecture.** The reviewer asked for the Bonus Lecture description
  that named five other courses to be removed. The same lecture's External
  Resource links to those courses, and a video slide naming them, were
  not flagged. Keep promotion to resources and the video.
* **Recommended (not required) "Audio Quality":** the TTS was judged
  "sufficient to match with Udemy's Audio Standards", with a warning that
  audio reported as robotic or mispronounced can be re-reviewed by Trust
  and Safety. The Whisper-transcription pronunciation pass (see the java25
  course STATUS.md) is the defence.
* Fixes are then marked "Mark as fixed" per item on
  `/manage/feedback/course` before "Resubmit for review".

## 23. Trust & Safety TTS affidavit: you must hold the rights to the voice

On 2026-10-27 Udemy Trust & Safety emailed the owner: one or more courses
"may feature voices or images of third parties that are inconsistent with
information submitted in your instructor profile". Udemy accepts TTS and AI
narration, but the instructor must sign an affidavit, within 14 days,
confirming they "possess the necessary rights" to it, or the courses risk
being disabled and the account actioned. Editing a course to remove content
before signing is allowed on request. (The email said a form was attached;
none was. Ask for it through the instructor messages or a support ticket,
not a link in an email.)

What it means for the kit:

* **The affidavit asks about rights, not price.** The earlier stance, "edge
  is fine for a free course, switch to azure before charging", was wrong.
  edge-tts drives the Edge browser's Read Aloud service, a consumer feature
  with no grant to publish its audio. A free Udemy course still runs on a
  commercial platform, and its Bonus Lecture sells the paid courses. So the
  kit dropped the `edge` engine in 1.5.0 and refuses a config that names it.
* **Azure Speech is the licensed route to the same voices** (`engine =
  "azure"`, same `en-GB-RyanNeural`). Its free tier (0.5M neural characters a
  month at the time of writing) covers a one-hour course, about 55k
  characters. Check Microsoft's current terms rather than this note.
* **Promo videos too.** Each course's vendored `tools/promo_video/build.py`
  (and the practice-test repos' `promo/build.py`) called edge-tts directly.
  They now call Azure's REST endpoint with the same key and region variables.
  The `udemy-course-check` skill fails any repo with `import edge_tts` or an
  `edge-tts` requirement anywhere outside `.venv`/`build`.
* **Use a stock synthetic voice, never one imitating a real person**, and
  keep the AI disclosure (section 21). Consider saying in the instructor bio
  that courses use AI text-to-speech narration, since the trigger was a
  mismatch with the profile.
* **Re-voicing is a rebuild and re-upload:** `ptkit video build` with the
  azure engine (the cache key includes the engine, so every slide is
  re-synthesised), then replace each lecture's video and captions, and the
  promo video. Watch for section 18: replacing videos marks every lecture as
  a free preview.

## 24. A practice test inside a video course, through the API

A practice test can be added to a video course's curriculum with the same
call as a lecture quiz (section 19), with `type: "practice-test"`:
`POST /api-2.0/courses/{course}/quizzes/` `{title, description, type:
"practice-test", duration, pass_percent}`. `duration` is required, in
**seconds**: without it the call returns **400 `{"duration":["duration
cannot be null"]}`**. `pass_percent` is a whole number. The new test comes
back `is_published: true` and unplaced, so save the curriculum order
(section 15) with `{"id", "class": "quiz", "is_published": true}` where it
belongs.

The CSV then goes in through the test's own editor (the "+" by Questions,
then Bulk upload). Uploading into the empty test kept the duration, pass
mark and description set at creation, unlike a re-upload (section 4).
Afterwards live and `?draft=true` assessments were identical.

* **Confirmed:** course 7403093 (Where AI Agents Run), 2026-10-29: test
  8011363 read back with `duration` 1800 and `pass_percent` 70 after a
  23-question upload; keys matched the CSV.

## 25. A new course starts free, in English (US), with a placeholder section

The create wizard (`/course/create/1` to `4`: type, working title,
category, time commitment) makes a Draft with one "Introduction" section
holding one empty "Introduction" lecture. Rename those two (section 15)
rather than creating new ones, or they stay in the curriculum. The course
starts **free** (`is_paid: false`, price "Free"), in locale **en_US**, so
captions uploaded before any change are stored as `en_US`. A paid course
with a practice test has to have its price set before submission (section
16).

Lecture videos went up through the curriculum editor: "Add Content", then
"Video", then Claude in Chrome's `file_upload` on the lecture's
`input[name=asset]`. Thirteen files of 3 to 10 MB were sent one after
another, about 5 seconds apart, and every one attached to the right
lecture. All 13 finished processing within about 20 minutes, and captions
uploaded while they were processing were accepted (as in section 13).

* **Confirmed:** course 7403093, 2026-10-29, by reading
  `instructor-curriculum-items` and the course fields before and after.
