# CLAUDE.md

## What this is

Source for a Udemy **video** course. `lectures/*.md` are the source of truth;
`build/` is generated and gitignored. The pipeline is the shared kit
(`ptkit video`), pinned in `requirements-dev.txt` -- do not vendor it.

## Lecture format

- One file per lecture, `NN-NN-short-topic.md` (section-lecture); the
  filename order is the course order.
- Marp front matter with `marp: true` and `theme: course`.
- Slides separated by `---` **with a blank line above it** (under a line of
  text it is a heading underline, not a slide break).
- Each slide's narration is an HTML comment on that slide. Directive comments
  (`<!-- _class: lead -->`) are not narration.
- `[pause 600ms]` inside narration inserts a pause.

## Script standard

- Write for the ear: short sentences, "you", one idea per slide.
- Never put code in the narration -- the slide shows the code; the narration
  says what it means. `ptkit video check` warns on code characters.
- Add mangle-prone terms (exam codes, JEP numbers) to `[pronounce]`.
- About 60-90 seconds of narration per slide at most; 3-10 minutes per
  lecture.
- Every technical claim must be checked against the JDK/spec it concerns;
  compile and run every code sample on the target JDK before it goes on a
  slide.

## Commands

```bash
ptkit video check
ptkit video build --engine silent
ptkit video build
```
