"""Parse questions-master.md into Question objects.

questions-master.md is the durable, platform-independent source of truth for a
bank; the Udemy CSVs are a generated projection of it. Both `ptkit generate`
and `ptkit validate` parse through this module, so the two can never disagree
about what the bank contains.

Layouts
-------
"exam-grouped" (the layout every Oracle/Spring bank uses today):

    # Exam 1
    ## Q01
    Domain 3 - Overload resolution phases.
    ```java
    ...
    ```
    A. ...
    B. ...
    **Correct answer:** B
    **Explanation:** ...
    ---

"domain-grouped" (a bank transcribed module-by-module from a source that is
itself organized by domain, e.g. risk-eng-for-swe -- the domain is a heading
grouping a whole run of questions, rather than a line repeated in every
question's stem):

    # Exam 1
    ## Domain 5 — Trade Lifecycle & Settlement
    ### Q01
    ```java
    ...
    ```
    A. ...
    B. ...
    **Correct answer:** B
    **Explanation:** ...
    ---

Question numbers restart at 1 in each "## Domain" section, matching a source
transcribed one module at a time; parse_domain_grouped renumbers them
sequentially within the exam so every Question.qid stays unique.
"""

import re

from .model import ParseError, Question
from .text import strip_fences

# "Domain 3 (Overload resolution)." or "Domain 3 - Overload resolution
# phases." (em dash), at the very start of the stem. Some banks put it on its
# own line; others run it inline ahead of the question sentence.
#
# Both branches capture their topic text, but the two forms are used
# differently downstream (see clean_stem). The parenthetical (group 2) is a
# bare category label sitting in front of a real question sentence ("Domain 5
# (Collections). What happens when this runs?"), so it is dropped. The em-dash
# form (group 3) is often the ONLY prose the stem has -- whole exams have been
# authored where most questions are otherwise a bare code snippet with no
# framing at all -- so it is kept as the stem's opening line instead of being
# discarded along with the "Domain N" marker itself.
DOMAIN_PREFIX_RE = re.compile(
    r"^\s*Domain (\d+)\s*(?:\(([^)]*)\)|—[ \t]*([^\n]*))\s*[.—]?\s*"
)

EXAM_HEADING_RE = re.compile(r"^# Exam (\d+)\s*$", re.M)
QUESTION_HEADING_RE = re.compile(r"^## (Q\d+)\s*$", re.M)

# "## Domain 5 — Trade Lifecycle & Settlement", one level up from a
# domain-grouped bank's "### QNN" (exam-grouped's "## QNN" sits one level
# higher because it has no domain-heading layer between it and "# Exam N").
DOMAIN_HEADING_RE = re.compile(r"^## Domain (\d+)\s*—\s*(.*?)\s*$", re.M)
DOMAIN_QUESTION_HEADING_RE = re.compile(r"^### (Q\d+)\s*$", re.M)

DIFFICULTY_RE = re.compile(r"^\*\*Difficulty:\*\*\s*(\S+)\s*$", re.M)
DIFFICULTY_LEVELS = ("Easy", "Medium", "Hard")

# Runs to the '---' separator that ends the question, or to end of file. An
# explanation may span several paragraphs -- some carry a second one recording
# where the bank deliberately deviates from an upstream answer key -- so this
# must not stop at the first line break.
EXPLANATION_RE = re.compile(
    r"^\*\*Explanation:\*\*\s*(.*?)\s*(?:^---\s*$|\Z)", re.S | re.M
)


def answer_re(letters):
    return re.compile(rf"^\*\*Correct answer:\*\*\s*([{letters}])\s*$", re.M)


def option_re(letters):
    return re.compile(
        rf"^([{letters}])\.[ \t]+(.*?)"
        rf"(?=^[{letters}]\.[ \t]|^\*\*Correct answer:\*\*)",
        re.M | re.S,
    )


def clean_stem(raw, require_domain_prefix=True):
    """Strip the Domain prefix and code fences, returning (text, domain_number).

    The "Domain N" marker itself is always removed -- the digit populates the
    CSV's own Domain column instead. An em-dash topic sentence is kept as the
    stem's opening line, because it is often the question's only framing prose;
    without it a learner sees an unintroduced code snippet.

    Everything else -- blank lines, indentation inside snippets, Markdown
    emphasis -- is preserved as-is, so the CSV question text matches what the
    author wrote minus the parts Udemy cannot render.
    """
    match = DOMAIN_PREFIX_RE.match(raw)
    if not match:
        if require_domain_prefix:
            raise ParseError("every stem must carry a 'Domain N' prefix")
        return strip_fences(raw).strip(), None
    domain_number = int(match.group(1))
    raw = raw[match.end():]
    topic = (match.group(3) or "").strip()
    if topic:
        raw = f"{topic}\n{raw}"
    return strip_fences(raw).strip(), domain_number


def _parse_question_fields(body, where, config, answer_pattern, option_pattern):
    """Extract options, answer, explanation and difficulty from one question body.

    This grammar is the same for every layout; only where the stem's domain
    comes from differs (an inline prefix vs. an enclosing heading), so each
    layout's own parser cleans `raw_stem` -- everything before the first
    option line -- itself.

    Returns (raw_stem, options, answer, explanation, difficulty).
    """
    letters = config.option_letters

    answer_match = answer_pattern.search(body)
    if not answer_match:
        raise ParseError(f"{where}: no '**Correct answer:** X' line")

    explanation_match = EXPLANATION_RE.search(body)
    if not explanation_match:
        raise ParseError(f"{where}: no '**Explanation:**' block")

    # Options run from the first "A. " line up to the answer line.
    options_region = body[:answer_match.start()]
    first_option = re.search(rf"^{letters[0]}\.[ \t]", options_region, re.M)
    if not first_option:
        raise ParseError(f"{where}: no '{letters[0]}. ' option line")

    options = {}
    for letter, option_text in option_pattern.findall(
        options_region[first_option.start():] + "**Correct answer:**"
    ):
        if letter in options:
            raise ParseError(f"{where}: duplicate option '{letter}'")
        options[letter] = option_text.strip()
    if sorted(options) != list(letters):
        raise ParseError(
            f"{where}: expected options {'-'.join(letters[::len(letters) - 1])}, "
            f"got {sorted(options)}"
        )

    difficulty = None
    difficulty_match = DIFFICULTY_RE.search(body)
    if difficulty_match:
        difficulty = difficulty_match.group(1)
        if difficulty not in DIFFICULTY_LEVELS:
            raise ParseError(
                f"{where}: Difficulty is {difficulty!r}, expected one of "
                f"{', '.join(DIFFICULTY_LEVELS)}"
            )
    elif config.require_difficulty:
        raise ParseError(f"{where}: no '**Difficulty:**' line")

    raw_stem = options_region[:first_option.start()]
    return (
        raw_stem, options, answer_match.group(1),
        explanation_match.group(1).strip(), difficulty,
    )


def parse_exam_grouped(text, config):
    """Parse the "# Exam N / ## QNN" layout into Questions, in document order."""
    answer_pattern = answer_re(config.option_letters)
    option_pattern = option_re(config.option_letters)

    parts = EXAM_HEADING_RE.split(text)[1:]
    if not parts:
        raise ParseError("no '# Exam N' headings found")

    questions = []
    for i in range(0, len(parts), 2):
        exam = int(parts[i])
        blocks = QUESTION_HEADING_RE.split(parts[i + 1])[1:]
        for j in range(0, len(blocks), 2):
            number = int(blocks[j][1:])
            body = blocks[j + 1]
            where = f"E{exam}Q{number:02d}"

            raw_stem, options, answer, explanation, difficulty = _parse_question_fields(
                body, where, config, answer_pattern, option_pattern
            )
            stem, domain_number = clean_stem(
                raw_stem, require_domain_prefix=config.require_domain_prefix,
            )
            if domain_number is not None and domain_number not in config.domain_names:
                raise ParseError(f"{where}: unknown domain number {domain_number}")
            domain = config.domain_names.get(domain_number, "")

            questions.append(Question(
                exam=exam,
                number=number,
                stem=stem,
                options=options,
                answer=answer,
                explanation=explanation,
                domain_number=domain_number,
                domain=domain,
                difficulty=difficulty,
            ))
    return questions


def parse_domain_grouped(text, config):
    """Parse the "# Exam N / ## Domain M — Name / ### QNN" layout into Questions.

    Question numbers restart at "### Q01" in every domain section -- the
    convention a bank transcribed one source module at a time naturally
    falls into, since each module has its own internal numbering. Renumbered
    sequentially within the exam here (in document order, across domain
    boundaries) so every Question.qid is still unique; the visible "Q01" is
    a per-domain label, not read back as the model's `number`.
    """
    answer_pattern = answer_re(config.option_letters)
    option_pattern = option_re(config.option_letters)

    parts = EXAM_HEADING_RE.split(text)[1:]
    if not parts:
        raise ParseError("no '# Exam N' headings found")

    questions = []
    for i in range(0, len(parts), 2):
        exam = int(parts[i])
        domain_parts = DOMAIN_HEADING_RE.split(parts[i + 1])[1:]
        if not domain_parts:
            raise ParseError(f"E{exam}: no '## Domain N — Name' headings found")

        running_number = 0
        for k in range(0, len(domain_parts), 3):
            domain_number = int(domain_parts[k])
            heading_name = domain_parts[k + 1].strip()
            domain_body = domain_parts[k + 2]
            if domain_number not in config.domain_names:
                raise ParseError(
                    f"E{exam} Domain {domain_number}: unknown domain number"
                )
            domain = config.domain_names[domain_number]
            if heading_name and heading_name != domain:
                raise ParseError(
                    f"E{exam} Domain {domain_number}: heading says "
                    f"{heading_name!r}, course.toml [domains] says {domain!r}"
                )

            blocks = DOMAIN_QUESTION_HEADING_RE.split(domain_body)[1:]
            if not blocks:
                raise ParseError(
                    f"E{exam} Domain {domain_number}: no '### QNN' headings found"
                )
            for j in range(0, len(blocks), 2):
                label = blocks[j]
                body = blocks[j + 1]
                where = f"E{exam} Domain {domain_number} {label}"

                raw_stem, options, answer, explanation, difficulty = _parse_question_fields(
                    body, where, config, answer_pattern, option_pattern
                )
                running_number += 1

                questions.append(Question(
                    exam=exam,
                    number=running_number,
                    stem=strip_fences(raw_stem).strip(),
                    options=options,
                    answer=answer,
                    explanation=explanation,
                    domain_number=domain_number,
                    domain=domain,
                    difficulty=difficulty,
                ))
    return questions


PARSERS = {
    "exam-grouped": parse_exam_grouped,
    "domain-grouped": parse_domain_grouped,
}


def parse_master(config, path=None):
    """Parse the course's master Markdown file into a list of Question."""
    source = path or config.master
    text = source.read_text(encoding="utf-8") if hasattr(source, "read_text") \
        else open(source, encoding="utf-8").read()
    return PARSERS[config.layout](text, config)


def _raw_bodies_exam_grouped(text):
    bodies = {}
    parts = EXAM_HEADING_RE.split(text)[1:]
    for i in range(0, len(parts), 2):
        exam = int(parts[i])
        blocks = QUESTION_HEADING_RE.split(parts[i + 1])[1:]
        for j in range(0, len(blocks), 2):
            number = int(blocks[j][1:])
            bodies[f"E{exam}Q{number:02d}"] = blocks[j + 1]
    return bodies


def _raw_bodies_domain_grouped(text):
    bodies = {}
    parts = EXAM_HEADING_RE.split(text)[1:]
    for i in range(0, len(parts), 2):
        exam = int(parts[i])
        domain_parts = DOMAIN_HEADING_RE.split(parts[i + 1])[1:]
        running_number = 0
        for k in range(0, len(domain_parts), 3):
            blocks = DOMAIN_QUESTION_HEADING_RE.split(domain_parts[k + 2])[1:]
            for j in range(0, len(blocks), 2):
                running_number += 1
                bodies[f"E{exam}Q{running_number:02d}"] = blocks[j + 1]
    return bodies


RAW_BODY_LOADERS = {
    "exam-grouped": _raw_bodies_exam_grouped,
    "domain-grouped": _raw_bodies_domain_grouped,
}


def load_raw_bodies(config, path=None):
    """qid -> raw (pre-fence-stripping) Markdown body, for code-only comparison.

    parse_master drops the fence marker lines but keeps the code content inline
    in Question.stem with no delimiter, so comparing *just the code* (as
    opposed to the whole stem, prose included) needs its own pass over the raw
    file. Mirrors the layout's own parser's heading traversal, minus the
    grammar validation -- this must find exactly the same qids parse_master
    does, or the two would silently talk past each other.
    """
    source = path or config.master
    text = source.read_text(encoding="utf-8") if hasattr(source, "read_text") \
        else open(source, encoding="utf-8").read()
    return RAW_BODY_LOADERS[config.layout](text)
