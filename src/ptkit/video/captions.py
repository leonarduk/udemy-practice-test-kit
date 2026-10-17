"""WebVTT captions generated from the script, not from speech recognition.

Udemy's auto-captions mishear exactly the terms a technical course is about
("1Z0-831", "JEP 513", "var underscore"). We already have the exact words and
each slide's exact start time and audio length, so the only estimate left is
where each sentence falls *within* a slide: time is shared out in proportion
to character count, with [pause] markers taking their stated length. Good
enough for captions, which only need to be on screen while the words are said.
"""

import re

from .lecture import _PAUSE

# Two lines of ~42 characters is the usual broadcast caption limit.
MAX_CUE_CHARS = 84


def cues_for_slide(slide, start, audio_seconds, spans=None):
    """(start, end, text) cues for one slide whose audio begins at `start`.

    `spans`, when the engine knows them (edge), are the [start, end] seconds
    of real speech for each text segment between [pause] markers, measured
    from the start of the slide's audio. Each segment's cues are then timed
    within its own speech, so the engine's silent padding around every chunk
    can't push the captions ahead of the voice.
    """
    if spans:
        texts = [chunks for chunks in
                 (_chunks(text) for text in _PAUSE.split(slide.narration)[::3])
                 if chunks]
        if len(texts) == len(spans):
            return _cues_in_spans(texts, spans, start)
    segments = []  # (text, None) or (None, pause_seconds)
    position = 0
    for match in _PAUSE.finditer(slide.narration):
        segments.append((slide.narration[position:match.start()], None))
        amount, unit = match.groups()
        segments.append((None, float(amount) / (1000 if unit.lower() == "ms" else 1)))
        position = match.end()
    segments.append((slide.narration[position:], None))

    pieces = []
    for text, pause in segments:
        if pause is not None:
            pieces.append((None, pause))
        else:
            pieces.extend((chunk, None) for chunk in _chunks(text))

    speech_chars = sum(len(text) for text, _ in pieces if text)
    pause_total = sum(pause for _, pause in pieces if pause)
    speaking = max(audio_seconds - pause_total, 0.1)
    cues = []
    clock = start
    for text, pause in pieces:
        if pause is not None:
            clock += pause
            continue
        length = speaking * len(text) / speech_chars if speech_chars else 0
        cues.append((clock, clock + length, text))
        clock += length
    return cues


def _cues_in_spans(texts, spans, start):
    cues = []
    for chunks, (begin, end) in zip(texts, spans):
        chars = sum(len(chunk) for chunk in chunks)
        clock = start + begin
        for chunk in chunks:
            length = (end - begin) * len(chunk) / chars
            cues.append((clock, clock + length, chunk))
            clock += length
    return cues


def _chunks(text):
    """Sentences, with any sentence too long for one cue split at a comma or word."""
    text = " ".join(text.split())
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out = []
    for sentence in sentences:
        while len(sentence) > MAX_CUE_CHARS:
            cut = sentence.rfind(", ", 0, MAX_CUE_CHARS)
            cut = cut + 1 if cut > MAX_CUE_CHARS // 3 else sentence.rfind(" ", 0, MAX_CUE_CHARS)
            if cut <= 0:
                cut = MAX_CUE_CHARS
            out.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            out.append(sentence)
    return out


def timestamp(seconds):
    millis = int(round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def to_vtt(cues):
    lines = ["WEBVTT", ""]
    for index, (start, end, text) in enumerate(cues, 1):
        lines += [str(index), f"{timestamp(start)} --> {timestamp(end)}", text, ""]
    return "\n".join(lines)
