"""Item-quality checks: is this bank actually testing knowledge?

These warn rather than fail. They exist because a practice-test bank can be
perfectly well-formed and still be beatable without knowing the subject --
by always picking C, or always picking the longest option.
"""

import collections
import difflib
import re


def check_key_distribution(ctx):
    report, config = ctx.report, ctx.config
    report.heading("Answer key distribution")
    low_share, high_share = config.key_distribution_band
    for exam in config.exams:
        subset_size = config.exam_question_counts[exam]
        counts = collections.Counter(q.answer for q in ctx.for_exam(exam))
        if not counts:
            # This exam hasn't been authored yet (the bank is still being
            # built up) -- nothing to score, so skip rather than divide by
            # zero / max() an empty Counter.
            continue
        letters = config.option_letters
        spread = "  ".join(f"{k}={counts.get(k, 0):2d}" for k in letters)
        worst_letter, worst_count = max(counts.items(), key=lambda kv: kv[1])
        line = (f"exam {exam}: {spread}   best single-letter guess = "
                f"{worst_count / subset_size:.0%} ({worst_letter})")
        high = subset_size * high_share
        low = subset_size * low_share
        if worst_count > high or min(counts.get(k, 0) for k in letters) < low:
            report.warn(line + f"   [target: every letter {low:.0f}-{high:.0f}]")
        else:
            report.ok(line)


def naive_length_score(subset, extreme):
    """Expected score for a learner who always picks the longest (or shortest)
    option, breaking ties at random. `extreme` is `max` or `min`.

    Ties MUST be scored fractionally rather than as a hit. A question whose
    options are all the same length leaks nothing -- the heuristic degenerates
    to a coin flip and pays exactly the chance rate. Counting such a question
    as "the correct answer is the shortest" (and, for an n-way tie,
    simultaneously as "the correct answer is the longest") was how one exam
    came to report 48% shortest-is-correct off only 9 genuinely short keys, 15
    of the 24 being ties: one question's four options are `5`/`3`/`4`/`9`, all
    one character, and another's are `3 1`/`1 3`/`1 2`/`3 2`. Both are ideal
    items by this measure and both were being counted as offences in both
    directions at once.
    """
    total = 0.0
    for question in subset:
        lengths = {k: len(v) for k, v in question.options.items()}
        target = extreme(lengths.values())
        tied = [k for k, n in lengths.items() if n == target]
        if question.answer in tied:
            total += 1 / len(tied)
    return total / len(subset)


def check_option_lengths(ctx):
    report, config = ctx.report, ctx.config
    report.heading("Option length parity")
    low, high = config.naive_strategy_band
    ratio_low, ratio_high = config.length_ratio_band
    for exam in config.exams:
        subset = ctx.for_exam(exam)
        if not subset:
            continue
        # Both directions matter. A correct answer that is reliably the
        # SHORTEST option is exactly as exploitable as one that is reliably
        # the longest, and a one-sided "ratio <= 1.15" target actively invites
        # overcorrection -- shortening every correct answer scores well on it
        # while creating the mirror-image tell.
        shortest = naive_length_score(subset, min)
        longest = naive_length_score(subset, max)
        # Reported for context only, NOT thresholded -- it counts just the
        # unambiguous cases, where the key is strictly shorter than every
        # distractor, so it reads far lower than the tie-inflated count this
        # check used to threshold on.
        strictly_shortest = sum(
            1 for q in subset
            if len(q.options[q.answer]) < min(len(t) for t in q.distractors)
        )
        distractor_count = len(config.option_letters) - 1
        mean_correct = sum(len(q.options[q.answer]) for q in subset) / len(subset)
        mean_distractor = sum(
            sum(len(t) for t in q.distractors) / distractor_count for q in subset
        ) / len(subset)
        ratio = mean_correct / mean_distractor if mean_distractor else 0
        line = (f"exam {exam}: always-shortest scores {shortest:.0%}, "
                f"always-longest scores {longest:.0%}, "
                f"correct {mean_correct:.0f} chars "
                f"vs distractor {mean_distractor:.0f} ({ratio:.2f}x)"
                f"   [{strictly_shortest}/{len(subset)} keys strictly shortest]")
        # Symmetric band around the chance rate: a key that is reliably NEVER
        # the shortest is an inverse tell -- eliminating the shortest option
        # lifts a guesser above chance just as reliably as picking it does.
        off_target = (
            not low <= shortest <= high
            or not low <= longest <= high
            or not ratio_low <= ratio <= ratio_high
        )
        if off_target:
            report.warn(
                line + f"   [target: both strategies {low:.0%}-{high:.0%}, "
                f"ratio {ratio_low:.2f}-{ratio_high:.2f}x]"
            )
        else:
            report.ok(line)


def check_naive_strategies(ctx):
    report, config = ctx.report, ctx.config
    chance = 1 / len(config.option_letters)
    report.heading(f"Naive strategy scores (should all be near {chance:.0%})")
    for exam in config.exams:
        subset = ctx.for_exam(exam)
        if not subset:
            continue
        best_letter = max(
            (sum(1 for q in subset if q.answer == letter) / len(subset), letter)
            for letter in config.option_letters
        )
        # Shares the parity check's scorer so the two sections can never
        # disagree about the same strategy. Comparing option TEXT against
        # `max(..., key=len)` -- the obvious way to write this -- silently
        # breaks ties by document order rather than scoring them.
        longest = naive_length_score(subset, max)
        line = (f"exam {exam}: always-{best_letter[1]} scores {best_letter[0]:.0%}, "
                f"always-longest scores {longest:.0%}")
        if best_letter[0] > chance * 1.28 or longest > config.naive_strategy_band[1]:
            report.warn(line)
        else:
            report.ok(line)


def normalise_stem(text):
    text = re.sub(r"Domain \d+[^\n]*", "", text)
    return re.sub(r"[`*\s]+", " ", text).strip().lower()


# Matches a fenced code block in the RAW (pre-fence-stripping) Markdown.
CODE_FENCE_RE = re.compile(r"```\w*\n(.*?)```", re.S)


def normalise_code(raw_body):
    """Concatenated, whitespace-collapsed text of every fenced code block."""
    code = "\n".join(CODE_FENCE_RE.findall(raw_body))
    return re.sub(r"\s+", " ", code).strip().lower()


def check_duplicates(ctx):
    report, config = ctx.report, ctx.config
    threshold = config.duplicate_threshold
    report.heading(f"Cross-exam duplicates (threshold {threshold})")
    raw_bodies = ctx.raw_bodies
    normalised = [
        (q, normalise_stem(q.stem), normalise_code(raw_bodies.get(q.qid, "")))
        for q in ctx.questions
    ]
    pairs = []       # cross-exam: reviewable, warn-only
    same_exam = []   # same exam: a promised-distinct-question count violation
    for i, (left, left_stem, left_code) in enumerate(normalised):
        for right, right_stem, right_code in normalised[i + 1:]:
            # autojunk=False matters here: the default heuristic treats the
            # repeated "A./B./C./D." markers as junk and reports spurious low
            # similarity for questions that are in fact near-identical.
            stem_ratio = difflib.SequenceMatcher(
                None, left_stem, right_stem, autojunk=False
            ).ratio()
            code_ratio = 0.0
            if left_code and right_code:
                code_ratio = difflib.SequenceMatcher(
                    None, left_code, right_code, autojunk=False
                ).ratio()
            ratio = max(stem_ratio, code_ratio)
            if ratio > threshold:
                bucket = same_exam if left.exam == right.exam else pairs
                bucket.append((ratio, left.qid, right.qid))
    pairs.sort(reverse=True)
    same_exam.sort(reverse=True)

    reviewed = config.reviewed_reason
    same_exam_flagged = [p for p in same_exam if reviewed(p[1], p[2]) is None]
    same_exam_kept = [p for p in same_exam if reviewed(p[1], p[2]) is not None]

    if same_exam_flagged:
        report.fail(
            f"{len(same_exam_flagged)} unreviewed near-duplicate pair(s) "
            f"WITHIN the same exam -- that exam may not actually have as "
            f"many distinct questions as its question count implies:"
        )
        for ratio, left, right in same_exam_flagged:
            report.detail(f"  {ratio:.2f}  {left} <-> {right}")
    else:
        report.ok("no unreviewed near-duplicate pairs within any single exam")
    if same_exam_kept:
        report.detail(
            f"{len(same_exam_kept)} reviewed same-exam pair(s) deliberately "
            f"kept -- same template, different question, by design:"
        )
        for ratio, left, right in same_exam_kept:
            report.detail(f"  {ratio:.2f}  {left} <-> {right}"
                          f"  -- {reviewed(left, right)}")

    flagged = [p for p in pairs if reviewed(p[1], p[2]) is None]
    kept = [p for p in pairs if reviewed(p[1], p[2]) is not None]

    if flagged:
        involved = {qid for _, a, b in flagged for qid in (a, b)}
        report.warn(
            f"{len(flagged)} unreviewed near-duplicate pairs across "
            f"{len(involved)} of {len(ctx.questions)} questions "
            f"({len(involved) / len(ctx.questions):.0%})"
        )
        for ratio, left, right in flagged[:15]:
            report.detail(f"  {ratio:.2f}  {left} <-> {right}")
        if len(flagged) > 15:
            report.detail(f"  ... and {len(flagged) - 15} more")
    else:
        report.ok("no unreviewed cross-exam stem/code pairs above threshold")

    if kept:
        report.detail(f"{len(kept)} reviewed pair(s) deliberately kept:")
        for ratio, left, right in kept:
            report.detail(f"  {ratio:.2f}  {left} <-> {right}"
                          f"  -- {reviewed(left, right)}")

    # A keep-list entry that no longer scores above the threshold is stale:
    # drop it, so it can't silently absorb a genuinely new duplicate later.
    all_pairs = pairs + same_exam
    scored = {(a, b) for _, a, b in all_pairs} | {(b, a) for _, a, b in all_pairs}
    known = {q.qid for q in ctx.questions}
    for entry in config.reviewed_pairs:
        left, right = entry
        missing = [qid for qid in entry if qid not in known]
        if missing:
            report.warn(
                f"reviewed_pairs entry {left} <-> {right} names "
                f"{', '.join(missing)}, which no longer exists -- "
                f"remove or update the entry"
            )
        elif entry not in scored:
            report.warn(
                f"reviewed_pairs entry {left} <-> {right} now scores below "
                f"{threshold} -- remove the stale exemption"
            )
