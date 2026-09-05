# TODO: Course Title — Master Question Bank

The durable, platform-independent source of truth for every question. The
per-exam CSVs are a GENERATED projection of this file — never hand-edit them,
regenerate with `ptkit generate`.

## Authoring standard

1. Every stem opens with a `Domain N — Topic.` line. The digit populates the
   CSV's Domain column; the marker never reaches the learner. The topic
   sentence after an em dash IS kept as the stem's opening line, because for a
   code-snippet question it is the only framing prose there is.
2. Every factual claim must be verified before it is written up — for a code
   question, by actually compiling and running the snippet, not by reasoning
   about it.
3. Every explanation cites something checkable: a spec section, a JEP number,
   a javadoc member, or a named documentation section.
4. **Option-length parity is an authoring constraint, not a cleanup pass.**
   The correct answer must not be reliably the longest or the shortest option
   — a learner who always picks the longest should score at chance.
   `ptkit validate` measures this; don't let it accumulate.
5. Spread the answer key evenly across A–D within each exam.
6. Answer options are rendered as HTML by Udemy. Escape `<`, `>` and `&` as
   `&lt;`, `&gt;`, `&amp;` — see UDEMY-PLATFORM-NOTES.md in the kit.

---

# Exam 1

## Q01

Domain 1 — TODO topic.

```text
TODO: snippet, if this is a code question
```

TODO: the question sentence.

A. TODO first option
B. TODO second option
C. TODO third option
D. TODO fourth option

**Correct answer:** A

**Explanation:** TODO — why A is right, why the others are wrong, and the
citation that backs it.

---
