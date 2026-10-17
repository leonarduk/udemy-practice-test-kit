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
