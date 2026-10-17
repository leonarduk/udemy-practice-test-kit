"""`ptkit video check`: is every lecture's script fit to synthesise?

Runs with no network, no Marp and no ffmpeg, so it is the CI gate and the
fast inner loop while writing. Same severities as the bank checks (see
ptkit.report): fail = the build would break or ship something wrong; warn =
it will build but probably sound or read badly; pending = not written yet.
"""

import re

from ..model import ParseError
from .lecture import parse_lecture
from .speech import recording_for

# Characters a TTS engine reads literally ("open brace") or skips, either of
# which mangles a sentence. Code belongs on the slide; the narration says
# what it means. Underscore is here because Java 22's `_` is a topic of its
# own -- narrate it as "underscore" (or add it to [pronounce]).
_CODE_CHARS = re.compile(r"[`{}\[\];<>=_]|\(\)|->|::")
# Mixed letter/number codes ("1Z0-831", "JDK-8313290") that engines spell out
# unpredictably. Plain acronyms (JDK, API) read fine and are not flagged.
_CODE_TERM = re.compile(r"(?<![\w-])(?=[A-Za-z0-9-]*\d)(?=[A-Za-z0-9-]*[A-Za-z])[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+(?![\w-])")
_PAUSE = re.compile(r"\[pause\s+[^\]]*\]", re.IGNORECASE)

# A static slide narrated for longer than this loses the learner; split it or
# reveal it in steps. Instructional-design rule of thumb, not a Udemy rule.
MAX_SLIDE_SECONDS = 90
# Udemy's own guidance favours lectures of a few minutes; past this a lecture
# is usually two topics that should be two lectures.
MAX_LECTURE_MINUTES = 15
# Udemy's published minimum for a paid course is 30 minutes of video across
# at least 5 lectures (Udemy staff answers in the instructor community; the
# official Teaching Center wording may move -- re-check before publishing).
MIN_COURSE_MINUTES = 30
MIN_LECTURES = 5


def estimate_seconds(slide, config):
    return (slide.word_count * 60 / config.words_per_minute
            + slide.pauses_seconds() + config.lead_in + config.tail)


def run(config, report):
    paths = config.lectures()
    total_seconds = 0.0
    lectures = 0
    report.heading(f"Lectures in {config.lectures_dir.relative_to(config.root)}")
    if not paths:
        report.pending("no lectures written yet")
    for path in paths:
        try:
            lecture = parse_lecture(path)
        except ParseError as exc:
            report.fail(str(exc))
            continue
        lectures += 1
        seconds = _check_lecture(lecture, config, report)
        total_seconds += seconds

    report.heading("Course")
    minutes = total_seconds / 60
    summary = f"{lectures} lectures, ~{minutes:.0f} min estimated"
    if lectures >= MIN_LECTURES and minutes >= MIN_COURSE_MINUTES:
        report.ok(summary)
    else:
        report.pending(f"{summary}; Udemy's paid-course minimum is "
                       f"{MIN_LECTURES} lectures and {MIN_COURSE_MINUTES} min")
    return report


def _check_lecture(lecture, config, report):
    name = lecture.path.name
    problems = 0
    seconds = 0.0
    unknown_terms = set()
    for slide in lecture.slides:
        where = f"{name} slide {slide.number} (line {slide.line})"
        for line in slide.setext_risk:
            problems += 1
            report.fail(f"{name} line {line}: `---` directly under text is a "
                        f"heading underline, not a slide break -- add a blank "
                        f"line above it")
        if not slide.body and not slide.narration:
            problems += 1
            report.fail(f"{where}: empty slide -- Marp renders it blank")
            continue
        if not slide.narration:
            problems += 1
            report.fail(f"{where}: no narration (add an HTML comment)")
            continue
        spoken = _PAUSE.sub(" ", slide.narration)
        code = sorted(set(_CODE_CHARS.findall(spoken)))
        if code:
            problems += 1
            report.warn(f"{where}: narration contains {' '.join(code)} -- "
                        f"the voice will read or drop these; say it in words")
        for term in _CODE_TERM.findall(spoken):
            if term not in config.pronounce:
                unknown_terms.add(term)
        slide_seconds = estimate_seconds(slide, config)
        if slide_seconds > MAX_SLIDE_SECONDS:
            problems += 1
            report.warn(f"{where}: ~{slide_seconds:.0f}s on one slide -- "
                        f"split it or reveal it in steps")
        seconds += slide_seconds
    for term in sorted(unknown_terms):
        problems += 1
        report.warn(f"{name}: {term!r} has no [pronounce] entry -- engines "
                    f"spell codes like this out unpredictably")
    if config.engine == "recorded":
        missing = [s.number for s in lecture.slides
                   if s.narration and recording_for(config, lecture.stem, s.number) is None]
        if missing:
            report.pending(f"{name}: {len(missing)} of {len(lecture.slides)} "
                           f"slides not recorded yet")
    if seconds / 60 > MAX_LECTURE_MINUTES:
        problems += 1
        report.warn(f"{name}: ~{seconds / 60:.0f} min -- consider splitting")
    if not problems:
        report.ok(f"{name}: {len(lecture.slides)} slides, ~{seconds / 60:.1f} min "
                  f"-- {lecture.title}")
    return seconds
