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
