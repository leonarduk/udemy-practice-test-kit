"""Load a video course's video-course.toml into a VideoConfig.

Deliberately a separate file from a practice-test bank's course.toml: a video
course has no exams, domains or CSV template, and making one config describe
both would mean every field is optional and nothing is checked. A repo that
ships both a video course and a practice-test bank just has both files.
"""

import tomllib
from pathlib import Path

from ..config import ConfigError

CONFIG_NAME = "video-course.toml"

ENGINES = ("recorded", "azure", "silent")

# Removed in 1.5.0. edge-tts drives the Edge browser's Read Aloud service,
# which grants no right to publish its audio. Udemy Trust & Safety asks
# instructors of TTS courses to sign an affidavit that they hold the rights
# to the voice (UDEMY-PLATFORM-NOTES.md 23), and audio from that service
# can't back that up. Azure Speech is the licensed route to the same voices.
_REMOVED_ENGINES = {
    "edge": "engine \"edge\" was removed in ptkit 1.5.0: edge-tts uses the "
            "Edge browser's Read Aloud service, which gives no right to publish "
            "its audio, and Udemy asks TTS instructors to swear they hold that "
            "right (UDEMY-PLATFORM-NOTES.md 23). Use engine = \"azure\" -- the "
            "same voice names, licensed through an Azure Speech resource (the "
            "free tier covers a course) -- or \"recorded\"",
}


def find_config(start=None):
    """Walk up from `start` looking for video-course.toml, the way git does."""
    current = Path(start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    raise ConfigError(
        f"no {CONFIG_NAME} found in {current} or any parent directory -- "
        f"run this from inside a video course repo, or scaffold one with "
        f"`ptkit video new-course`"
    )


class VideoConfig:
    def __init__(self, path, data):
        self.path = Path(path).resolve()
        self.root = self.path.parent

        course = data.get("course", {})
        self.name = _require(course, "name", "course")
        self.slug = _require(course, "slug", "course")

        video = data.get("video", {})
        self.lectures_dir = self.root / video.get("lectures_dir", "lectures")
        # recordings/<lecture-stem>/slide-001.wav (or .m4a/.mp3/.flac), one
        # take per slide, for the "recorded" engine.
        self.recordings_dir = self.root / video.get("recordings_dir", "recordings")
        # Applied to recorded takes only (synthetic voices arrive level):
        # cut rumble below 80 Hz, then EBU R128 loudness to -19 LUFS, the
        # usual target for mono spoken word, so every take sits at the same
        # level however far the mic was. Set to "" to keep takes untouched.
        self.recording_filter = video.get(
            "recording_filter", "highpass=f=80,loudnorm=I=-19:TP=-1.5:LRA=11")
        self.build_dir = self.root / video.get("build_dir", "build")
        # Marp's default slide is 1280x720; scale 1.5 renders 1920x1080, the
        # resolution Udemy recommends. 720p is Udemy's floor, not the target.
        self.image_scale = float(video.get("image_scale", 1.5))
        self.fps = int(video.get("fps", 30))
        # Silence around each slide's narration. Without a lead-in the voice
        # starts on the same frame the slide appears, which reads as rushed;
        # the tail gives the learner a beat to look at the slide before it
        # changes. Values from listening to drafts, not from a spec.
        self.lead_in = float(video.get("lead_in", 0.4))
        self.tail = float(video.get("tail", 0.8))
        theme = video.get("theme")
        self.theme = self.root / theme if theme else None
        self.marp = video.get("marp", "npx --yes @marp-team/marp-cli@4.5.1")
        # Spoken-rate estimate for `ptkit video check` durations before any
        # audio exists. ~150 wpm is typical for instructional narration.
        self.words_per_minute = int(video.get("words_per_minute", 150))

        voice = data.get("voice", {})
        # "recorded" is the default because Udemy's reviewers have rejected
        # courses narrated entirely by text-to-speech (instructor forum
        # reports, 2023-2025; no official policy page found -- ask
        # policy@udemy.com before relying on synthetic narration). Azure is
        # for drafts and for small post-publication edits.
        self.engine = voice.get("engine", "recorded")
        if self.engine in _REMOVED_ENGINES:
            raise ConfigError(f"{self.path}: {_REMOVED_ENGINES[self.engine]}")
        if self.engine not in ENGINES:
            raise ConfigError(
                f"{self.path}: [voice] engine = {self.engine!r}; expected one "
                f"of {', '.join(ENGINES)}"
            )
        self.voice = voice.get("name", "en-GB-RyanNeural")
        self.language = voice.get("language", self.voice[:5])
        self.rate = voice.get("rate", "0%")
        # Not secrets: the key itself is only ever read from the environment
        # variable named here, so video-course.toml is safe to commit.
        self.region_env = voice.get("region_env", "AZURE_SPEECH_REGION")
        self.key_env = voice.get("key_env", "AZURE_SPEECH_KEY")

        pronounce = data.get("pronounce", {})
        for term, spoken in pronounce.items():
            if not isinstance(spoken, str) or not spoken.strip():
                raise ConfigError(
                    f"{self.path}: [pronounce] {term!r} needs a non-empty "
                    f"string saying how to read it aloud"
                )
        # Longest first, so "Java SE 25" wins over "Java" when both are listed.
        self.pronounce = dict(
            sorted(pronounce.items(), key=lambda item: -len(item[0]))
        )

    def lectures(self):
        """Lecture files in course order: the filename prefix is the order."""
        if not self.lectures_dir.is_dir():
            raise ConfigError(f"lectures directory {self.lectures_dir} does not exist")
        return sorted(self.lectures_dir.glob("*.md"))


def _require(table, key, section):
    value = table.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"[{section}] {key} is required")
    return value


def load(path=None):
    path = Path(path) if path else find_config()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    return VideoConfig(path, data)
