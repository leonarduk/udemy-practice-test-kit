"""Lecture Markdown -> slide PNGs (Marp) + narration WAVs -> MP4 + VTT.

Timing is decided in Python, not by ffmpeg: one WAV for the whole lecture is
assembled sample-exactly from (lead-in silence + slide audio + tail silence)
per slide, and each slide image is shown for exactly that span. Encoding the
slides as separate clips and concatenating them was the obvious alternative,
but each AAC segment carries its own encoder priming, which adds small gaps
that accumulate into audible drift against the captions over a long lecture.
"""

import shlex
import shutil
import subprocess
import wave
from pathlib import Path

from ..config import ConfigError
from . import captions, speech
from .lecture import parse_lecture


def run(command, **kwargs):
    executable = shutil.which(command[0])
    if executable is None:
        raise ConfigError(f"`{command[0]}` is not on PATH -- needed to build video")
    result = subprocess.run([executable, *command[1:]], capture_output=True,
                            text=True, **kwargs)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout).strip().splitlines()[-15:]
        raise ConfigError(f"{command[0]} failed:\n  " + "\n  ".join(tail))
    return result


def render_slides(lecture, config, out_dir):
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)  # stale PNGs from a longer earlier draft
    out_dir.mkdir(parents=True)
    command = [
        *shlex.split(config.marp), str(lecture.path),
        "--images", "png",
        "--image-scale", str(config.image_scale),
        "--allow-local-files",
        "-o", str(out_dir / "slide.png"),
    ]
    if config.theme:
        command += ["--theme-set", str(config.theme)]
    run(command, cwd=config.root)
    images = sorted(out_dir.glob("slide*.png"))
    if len(images) != len(lecture.slides):
        raise ConfigError(
            f"{lecture.path.name}: Marp rendered {len(images)} slides but the "
            f"script has {len(lecture.slides)} -- run `ptkit video check`; a "
            f"`---` directly under a line of text is a heading, not a break"
        )
    return images


def build_lecture(path, config, log=print):
    lecture = parse_lecture(path)
    stem = lecture.stem
    work = config.build_dir / stem
    cache = config.build_dir / "audio-cache"
    log(f"{stem}: {len(lecture.slides)} slides")

    images = render_slides(lecture, config, work / "slides")

    clips = []
    fresh = 0
    for slide in lecture.slides:
        if not slide.narration:
            raise ConfigError(f"{path.name} slide {slide.number}: no narration")
        audio, created = speech.synthesise(slide, config, cache, stem)
        fresh += created
        clips.append(audio)
    log(f"  audio: {fresh} synthesised ({config.engine}), "
        f"{len(clips) - fresh} from cache")

    lecture_wav = work / "narration.wav"
    spans, cues = _assemble_audio(lecture, clips, config, lecture_wav)

    concat = work / "images.txt"
    entries = []
    for image, seconds in zip(images, spans):
        entries += [f"file '{image.resolve().as_posix()}'", f"duration {seconds:.3f}"]
    # The concat demuxer ignores the last entry's duration unless the file is
    # listed once more after it.
    entries.append(f"file '{images[-1].resolve().as_posix()}'")
    concat.write_text("\n".join(entries) + "\n", encoding="utf-8")

    mp4 = config.build_dir / f"{stem}.mp4"
    total = sum(spans)
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat),
        "-i", str(lecture_wav),
        "-vf", f"fps={config.fps},scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
        "-c:v", "libx264", "-tune", "stillimage", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-ac", "2",
        # -shortest alone leaves the still-image stream running ~2.5 s past
        # the audio (the repeated last concat entry), so cap it explicitly.
        "-shortest", "-t", f"{total:.3f}", "-movflags", "+faststart",
        str(mp4),
    ])
    vtt = config.build_dir / f"{stem}.vtt"
    vtt.write_text(captions.to_vtt(cues), encoding="utf-8")
    log(f"  wrote {mp4.name} ({total / 60:.1f} min) and {vtt.name}")
    return mp4, total


def _assemble_audio(lecture, clips, config, out_path):
    """Concatenate per-slide WAVs with lead/tail silence; return spans and cues."""
    spans = []
    cues = []
    clock = 0.0
    with wave.open(str(out_path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(speech.SAMPLE_RATE)
        for slide, clip in zip(lecture.slides, clips):
            with wave.open(str(clip), "rb") as audio:
                if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (
                        1, 2, speech.SAMPLE_RATE):
                    raise ConfigError(
                        f"{clip}: expected 48 kHz 16-bit mono; delete it from "
                        f"the audio cache and rebuild"
                    )
                frames = audio.readframes(audio.getnframes())
                seconds = audio.getnframes() / speech.SAMPLE_RATE
            lead = _silence(config.lead_in)
            tail = _silence(config.tail)
            out.writeframes(lead + frames + tail)
            cues += captions.cues_for_slide(slide, clock + config.lead_in, seconds)
            span = (len(lead) + len(frames) + len(tail)) / 2 / speech.SAMPLE_RATE
            spans.append(span)
            clock += span
    return spans, cues


def _silence(seconds):
    return b"\x00\x00" * int(seconds * speech.SAMPLE_RATE)
