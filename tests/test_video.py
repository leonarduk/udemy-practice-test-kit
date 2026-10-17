"""ptkit video: lecture parsing, SSML, captions, checks, and (opt-in) a build."""

import io
import os
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

from ptkit.model import ParseError
from ptkit.report import Report
from ptkit.video import captions, checks, speech
from ptkit.video.config import ConfigError, VideoConfig
from ptkit.video.lecture import is_directive, parse_lecture

SCAFFOLD = Path(__file__).parent.parent / "src" / "ptkit" / "video" / "scaffold"


def config(root, **voice):
    data = {"course": {"name": "C", "slug": "c"}, "voice": {"engine": "silent", **voice}}
    if "pronounce" in voice:
        data["pronounce"] = voice.pop("pronounce")
        data["voice"].pop("pronounce")
    return VideoConfig(Path(root) / "video-course.toml", data)


def lecture(tmp, body, name="01-01-test.md"):
    folder = Path(tmp) / "lectures"
    folder.mkdir(exist_ok=True)
    path = folder / name
    path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return path


TWO_SLIDES = """
    ---
    marp: true
    paginate: true
    ---

    <!-- _class: lead -->

    # Title

    <!-- Hello and welcome. -->

    ---

    ```java
    String s = \"\"\"
    ---
    \"\"\";
    ```

    <!--
    A text block.
    [pause 500ms]
    That dash line is inside the fence.
    -->
"""


class LectureTests(unittest.TestCase):
    def test_slides_split_and_directives_are_not_narration(self):
        with tempfile.TemporaryDirectory() as tmp:
            parsed = parse_lecture(lecture(tmp, TWO_SLIDES))
        self.assertEqual(len(parsed.slides), 2)
        self.assertEqual(parsed.slides[0].narration, "Hello and welcome.")
        self.assertEqual(parsed.title, "Title")
        self.assertIn("[pause 500ms]", parsed.slides[1].narration)
        self.assertEqual(parsed.slides[1].spoken_text,
                         "A text block. That dash line is inside the fence.")
        self.assertAlmostEqual(parsed.slides[1].pauses_seconds(), 0.5)

    def test_dashes_under_text_are_a_heading_not_a_break(self):
        body = """
            ---
            marp: true
            ---

            # One
            Some text
            ---
            <!-- narration -->
        """
        with tempfile.TemporaryDirectory() as tmp:
            parsed = parse_lecture(lecture(tmp, body))
        self.assertEqual(len(parsed.slides), 1)
        self.assertEqual(parsed.slides[0].setext_risk, [7])

    def test_missing_marp_front_matter_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ParseError):
                parse_lecture(lecture(tmp, "# no front matter\n"))

    def test_directive_detection(self):
        self.assertTrue(is_directive(" _class: lead "))
        self.assertTrue(is_directive("paginate: true\nfooter: x"))
        self.assertFalse(is_directive("Note: this is narration"))
        self.assertFalse(is_directive("class: lead\nand then some words"))


class SsmlTests(unittest.TestCase):
    def test_pronunciations_pauses_and_escaping(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config(tmp, pronounce={"1Z0-831": "one Z zero eight three one"})
        ssml = speech.to_ssml("Pass 1Z0-831 & relax [pause 1s] <now>.", cfg)
        self.assertIn('<sub alias="one Z zero eight three one">1Z0-831</sub>', ssml)
        self.assertIn('<break time="1000ms"/>', ssml)
        self.assertIn("&amp; relax", ssml)
        self.assertIn("&lt;now&gt;", ssml)

    def test_cache_key_changes_with_voice(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = config(tmp, name="en-GB-RyanNeural")
            b = config(tmp, name="en-GB-SoniaNeural")
        self.assertNotEqual(speech.cache_key("<speak/>", a), speech.cache_key("<speak/>", b))

    def test_edge_chunks_substitute_pronunciations_and_split_on_pauses(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config(tmp, engine="edge",
                         pronounce={"1Z0-831": "one Z zero eight three one", "JEP": "jep"})
        chunks = speech.edge_chunks("Pass 1Z0-831 & relax. [pause 600ms] JEPs and JEP 512.", cfg)
        self.assertEqual(chunks, [
            ("say", "Pass one Z zero eight three one & relax."),
            ("pause", 0.6),
            ("say", "JEPs and jep 512."),
        ])

    def test_edge_rate_is_signed(self):
        self.assertEqual(speech.edge_rate("0%"), "+0%")
        self.assertEqual(speech.edge_rate("-5%"), "-5%")

    def test_unknown_engine_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigError):
                config(tmp, engine="nope")


class CaptionTests(unittest.TestCase):
    def test_cues_fill_the_audio_and_skip_pauses(self):
        with tempfile.TemporaryDirectory() as tmp:
            slide = parse_lecture(lecture(tmp, TWO_SLIDES)).slides[1]
        cues = captions.cues_for_slide(slide, start=10.0, audio_seconds=4.5)
        self.assertEqual([c[2] for c in cues],
                         ["A text block.", "That dash line is inside the fence."])
        self.assertAlmostEqual(cues[0][0], 10.0)
        self.assertAlmostEqual(cues[-1][1], 14.5)
        self.assertAlmostEqual(cues[1][0] - cues[0][1], 0.5)  # the pause

    def test_long_sentences_are_split(self):
        text = "word " * 60
        for chunk in captions._chunks(text):
            self.assertLessEqual(len(chunk), captions.MAX_CUE_CHARS)

    def test_vtt_format(self):
        vtt = captions.to_vtt([(0.0, 61.25, "Hi")])
        self.assertIn("00:00:00.000 --> 00:01:01.250", vtt)
        self.assertTrue(vtt.startswith("WEBVTT"))


class CheckTests(unittest.TestCase):
    def run_checks(self, body):
        with tempfile.TemporaryDirectory() as tmp:
            lecture(tmp, body)
            report = Report(stream=io.StringIO())
            checks.run(config(tmp), report)
            return report

    def test_clean_lecture_passes(self):
        report = self.run_checks(TWO_SLIDES)
        self.assertEqual(report.failures, [])
        self.assertEqual(report.warnings, [])

    def test_missing_narration_fails_and_code_warns(self):
        body = """
            ---
            marp: true
            ---

            # Silent slide

            ---

            # Code

            <!-- Write var _ = list.get(0); and JEP-456 too. -->
        """
        report = self.run_checks(body)
        self.assertEqual(len(report.failures), 1)
        self.assertIn("no narration", report.failures[0])
        joined = " ".join(report.warnings)
        self.assertIn("_", joined)
        self.assertIn("JEP-456", joined)

    def test_scaffold_lecture_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(SCAFFOLD, tmp, dirs_exist_ok=True)
            from ptkit.video.config import load
            cfg = load(Path(tmp) / "video-course.toml")
            report = Report(stream=io.StringIO())
            checks.run(cfg, report)
        self.assertEqual(report.failures, [])
        self.assertEqual(report.warnings, [])


@unittest.skipUnless(
    os.environ.get("PTKIT_VIDEO_E2E") and shutil.which("ffmpeg") and shutil.which("npx"),
    "set PTKIT_VIDEO_E2E=1 with ffmpeg, Node and Chrome/Edge to run a real build",
)
class BuildTests(unittest.TestCase):
    def test_silent_build_produces_mp4_and_vtt(self):
        from ptkit.video.build import build_lecture
        with tempfile.TemporaryDirectory() as tmp:
            path = lecture(tmp, TWO_SLIDES)
            cfg = config(tmp)
            mp4, seconds = build_lecture(path, cfg, log=lambda *_: None)
            self.assertTrue(mp4.is_file())
            self.assertGreater(mp4.stat().st_size, 1000)
            self.assertTrue(mp4.with_suffix(".vtt").is_file())
            self.assertGreater(seconds, 2)


if __name__ == "__main__":
    unittest.main()
