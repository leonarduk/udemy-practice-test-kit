"""Deterministic answer-option shuffle.

A bank authored straight through tends to put the correct answer in the same
slot far too often -- one bank had option B correct in 73% of its questions,
which passed its own 70% pass mark by answering "B" to everything without
reading a single question. check_key_distribution/check_naive_strategies (see
checks/quality.py) detect this; this module is the fix, applied once, at
parse time, so every check and every generated CSV sees the same corrected
distribution -- there is no separate "pre-shuffle" and "post-shuffle" view of
a course's own questions.

Ported from spring-boot-ai-udemy-practice-tests/tools/generate_csv.py, the
bank that hit this first, generalized to the kit's option_letters. Multi-
select (more than one correct answer) is out of scope: Question models
exactly one correct answer, and nothing that generates one exists yet.
"""

import collections
import hashlib

from .model import Question


def _byte_stream(seed_text):
    """An endless, deterministic byte stream derived from seed_text.

    SHA-256 rather than the `random` module on purpose: `ptkit generate
    --check` diffs the regenerated CSVs against the committed ones
    byte-for-byte, so the permutation has to be identical on every Python
    that ever runs this. `random.shuffle`'s internals are explicitly not
    covered by Python's reproducibility guarantee; a hash is.
    """
    counter = 0
    while True:
        block = hashlib.sha256(f"{seed_text}:{counter}".encode("utf-8")).digest()
        yield from block
        counter += 1


def _below(stream, bound):
    """A uniform integer in [0, bound) drawn from a byte stream.

    Rejection sampling, not `byte % bound`, which would skew low values
    whenever bound does not divide 256 -- exactly the kind of quiet bias this
    whole module exists to remove. bound is at most a course's option count
    or exam size, comfortably under 256.
    """
    if bound <= 1:
        return 0
    if bound > 256:
        raise ValueError(f"_below only supports bound <= 256, got {bound}")
    limit = 256 - (256 % bound)
    for byte in stream:
        if byte < limit:
            return byte % bound
    raise AssertionError("byte stream ended")  # pragma: no cover -- it cannot


def deterministic_permutation(seed_text, n):
    """A permutation of range(n), fixed by seed_text. Fisher-Yates."""
    order = list(range(n))
    stream = _byte_stream(seed_text)
    for i in range(n - 1, 0, -1):
        j = _below(stream, i + 1)
        order[i], order[j] = order[j], order[i]
    return order


def _question_seed(seed, exam, question_text):
    """Seed one question's own permutation off its stem TEXT, not its
    position, so inserting or deleting a question does not reshuffle its
    neighbours' options (and a content edit changes as little else in the
    regenerated CSV as possible)."""
    digest = hashlib.sha256(question_text.encode("utf-8")).hexdigest()
    return f"{seed}:exam{exam}:{digest}"


def _balanced_slots(seed, exam, n_questions, n_options):
    """Which option slot each question's correct answer should land in.

    A per-question shuffle alone only evens the key out on average -- over a
    few dozen questions it can still leave one letter well ahead. This deals
    the slots out as a balanced multiset instead (counts differ by at most
    one), then permutes THAT list so the result is balanced without being a
    visible A,B,C,D,A,B,C,D cycle, which would just replace one tell with
    another.
    """
    slots = [i % n_options for i in range(n_questions)]
    order = deterministic_permutation(
        f"{seed}:exam{exam}:slots{n_options}", n_questions
    )
    return [slots[i] for i in order]


def _shuffle_one(question, letters, target_slot, seed):
    """Rebuild one question with its options (and any per-option
    explanations) permuted so the correct answer sits at `target_slot`,
    everything else in a per-question-deterministic order."""
    n = len(letters)
    correct = letters.index(question.answer)
    distractors = [i for i in range(n) if i != correct]
    order = deterministic_permutation(
        _question_seed(seed, question.exam, question.stem), len(distractors)
    )
    new_from_old = [None] * n
    new_from_old[target_slot] = correct
    free_slots = [i for i in range(n) if i != target_slot]
    for slot, distractor_index in zip(free_slots, order):
        new_from_old[slot] = distractors[distractor_index]

    old_texts = [question.options[letters[i]] for i in range(n)]
    old_whys = {
        letters[i]: question.option_explanations.get(letters[i], "")
        for i in range(n)
    }
    new_options = {letters[new]: old_texts[old] for new, old in enumerate(new_from_old)}
    new_whys = {
        letters[new]: old_whys[letters[old]] for new, old in enumerate(new_from_old)
    }

    return Question(
        exam=question.exam,
        number=question.number,
        stem=question.stem,
        options=new_options,
        answer=letters[target_slot],
        explanation=question.explanation,
        domain=question.domain,
        domain_number=question.domain_number,
        difficulty=question.difficulty,
        option_explanations=new_whys if question.option_explanations else {},
    )


def shuffle_questions(questions, config):
    """Return `questions` with every question's answer options reordered.

    Deterministic in (config.shuffle_seed, exam number, question stem) --
    regenerating without any content change reproduces byte-identical
    output. Balances the correct-answer slot within each exam, bucketed by
    option count (relevant only if a course ever mixes 4- and 5-option
    questions in one exam; every adopter today uses a fixed count).

    Applied once, in parse_master, before any check or CSV render sees the
    questions -- see this module's docstring for why.
    """
    letters = config.option_letters
    by_exam = collections.defaultdict(list)
    for position, question in enumerate(questions):
        by_exam[question.exam].append(position)

    shuffled = list(questions)
    for exam, positions in by_exam.items():
        buckets = collections.defaultdict(list)
        for position in positions:
            buckets[len(questions[position].options)].append(position)

        for n_options, bucket_positions in sorted(buckets.items()):
            slots = _balanced_slots(
                config.shuffle_seed, exam, len(bucket_positions), n_options
            )
            for position, slot in zip(bucket_positions, slots):
                shuffled[position] = _shuffle_one(
                    questions[position], letters[:n_options], slot,
                    config.shuffle_seed,
                )
    return shuffled
