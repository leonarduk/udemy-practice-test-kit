"""Narration text -> SSML -> WAV, with a content-addressed cache.

Engines:

  recorded  Your own takes, one file per slide, in
          recordings/<lecture>/slide-NNN.{wav,m4a,mp3,flac}. Converted to
          48 kHz mono and loudness-normalised by ffmpeg. The default -- see
          VideoConfig.engine for why.
  azure   Azure Neural TTS over its REST endpoint, using only urllib -- the kit
          stays zero-dependency, so no Azure SDK. Reads the key and region
          from environment variables named in video-course.toml; the key is
          never written to disk or printed.
  silent  Silence of the estimated spoken length. For previewing slide
          timing, captions and the full build before spending any TTS quota,
          and for tests and CI, which have no key.

The cache key is the SHA-256 of (engine, voice, rate, SSML). Editing one
slide's script re-synthesises that slide only, and a rebuild with no script
changes makes no network calls at all.
"""

import hashlib
import os
import re
import struct
import urllib.error
import urllib.request
import wave
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from ..config import ConfigError

SAMPLE_RATE = 48000
# 48 kHz 16-bit mono PCM: lossless in, so the only lossy step is ffmpeg's
# single AAC encode at the end. Udemy re-encodes uploads anyway.
AZURE_FORMAT = "riff-48khz-16bit-mono-pcm"

_PAUSE = re.compile(r"\[pause\s+(\d+(?:\.\d+)?)\s*(ms|s)\]", re.IGNORECASE)


def to_ssml(narration, config):
    """Build the SSML document for one slide's narration.

    Pronunciations are applied as <sub alias>, which tells the engine what to
    say while leaving the written term intact -- captions are generated from
    the narration, not the SSML, so they keep "1Z0-831" rather than its
    spelled-out form.
    """
    parts = []
    position = 0
    for match in _PAUSE.finditer(narration):
        parts.append(_with_pronunciations(narration[position:match.start()], config))
        amount, unit = match.groups()
        millis = float(amount) * (1 if unit.lower() == "ms" else 1000)
        parts.append(f'<break time="{int(millis)}ms"/>')
        position = match.end()
    parts.append(_with_pronunciations(narration[position:], config))
    body = " ".join(" ".join(parts).split())
    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xml:lang={quoteattr(config.language)}>'
        f'<voice name={quoteattr(config.voice)}>'
        f'<prosody rate={quoteattr(config.rate)}>{body}</prosody>'
        f'</voice></speak>'
    )


def _with_pronunciations(text, config):
    if not config.pronounce:
        return escape(text)
    pattern = re.compile(
        "|".join(
            # Word-ish boundaries, so "JEP" does not fire inside "JEPs" unless
            # "JEPs" is itself listed (longest-first makes that win).
            rf"(?<![\w-]){re.escape(term)}(?![\w-])"
            for term in config.pronounce
        )
    )
    out = []
    position = 0
    for match in pattern.finditer(text):
        out.append(escape(text[position:match.start()]))
        term = match.group(0)
        out.append(f"<sub alias={quoteattr(config.pronounce[term])}>{escape(term)}</sub>")
        position = match.end()
    out.append(escape(text[position:]))
    return "".join(out)


def cache_key(ssml, config):
    material = "\n".join([config.engine, config.voice, config.rate, ssml])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


RECORDING_SUFFIXES = (".wav", ".m4a", ".mp3", ".flac")


def recording_for(config, lecture_stem, slide_number):
    """The take for this slide, or None if it has not been recorded yet."""
    folder = config.recordings_dir / lecture_stem
    for suffix in RECORDING_SUFFIXES:
        candidate = folder / f"slide-{slide_number:03d}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def synthesise(slide, config, cache_dir, lecture_stem):
    """Return (WAV path, newly made?) for this slide's narration, cached by content."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    if config.engine == "recorded":
        return _recorded(slide, config, cache_dir, lecture_stem)
    ssml = to_ssml(slide.narration, config)
    path = cache_dir / f"{cache_key(ssml, config)}.wav"
    if path.exists():
        return path, False
    if config.engine == "silent":
        seconds = slide.word_count * 60 / config.words_per_minute + slide.pauses_seconds()
        write_silence(path, max(seconds, 0.5))
    elif config.engine == "azure":
        _azure(ssml, config, path)
    else:  # VideoConfig already rejects unknown engines; belt and braces
        raise ConfigError(f"unknown engine {config.engine!r}")
    return path, True


def _recorded(slide, config, cache_dir, lecture_stem):
    source = recording_for(config, lecture_stem, slide.number)
    if source is None:
        raise ConfigError(
            f"no recording for {lecture_stem} slide {slide.number}: expected "
            f"{config.recordings_dir.name}/{lecture_stem}/slide-{slide.number:03d}.wav "
            f"(`ptkit video script {lecture_stem}` prints what to read)"
        )
    digest = hashlib.sha256(source.read_bytes())
    digest.update(config.recording_filter.encode("utf-8"))
    path = cache_dir / f"rec-{digest.hexdigest()[:24]}.wav"
    if path.exists():
        return path, False
    from .build import run  # build imports this module; avoid the cycle
    partial = path.with_name(path.stem + ".partial.wav")
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source)]
    if config.recording_filter:
        command += ["-af", config.recording_filter]
    command += ["-ac", "1", "-ar", str(SAMPLE_RATE), "-sample_fmt", "s16", str(partial)]
    run(command)
    partial.replace(path)
    return path, True


def write_silence(path, seconds):
    frames = int(seconds * SAMPLE_RATE)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(struct.pack("<h", 0) * frames)


def wav_seconds(path):
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def _azure(ssml, config, path):
    key = os.environ.get(config.key_env)
    region = os.environ.get(config.region_env)
    if not key or not region:
        raise ConfigError(
            f"Azure TTS needs the {config.key_env} and {config.region_env} "
            f"environment variables (your Speech resource's key and region, "
            f"e.g. uksouth). Or run with --engine silent to build without "
            f"voice."
        )
    request = urllib.request.Request(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        data=ssml.encode("utf-8"),
        method="POST",
        headers={
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": AZURE_FORMAT,
            "User-Agent": "udemy-practice-test-kit",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            audio = response.read()
    except urllib.error.HTTPError as exc:
        # The body is Azure's error text; it never contains the key.
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise ConfigError(f"Azure TTS returned HTTP {exc.code}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise ConfigError(f"could not reach Azure TTS in region {region!r}: {exc.reason}") from exc
    # Write via a temp name so an interrupted download never poisons the cache.
    partial = path.with_suffix(".partial")
    partial.write_bytes(audio)
    partial.replace(path)
