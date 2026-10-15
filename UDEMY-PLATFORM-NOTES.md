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

**Not established:** whether Udemy awards partial credit for a partly-right
multi-select answer, or scores it all-or-nothing. Item design that relies on
either (e.g. a "none of these" option that must be chosen alone) should be
checked on a draft practice test before a bank depends on it. Record the
answer here when someone does.
