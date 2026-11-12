"""Diff each lecture's narration against its Whisper transcript.

Usage: python compare.py STT_DIR [stem-prefix ...]   (run from the course root)
       [--lectures-dir DIR | --video-config video-course.de.toml]
Prints every span where the words differ, with a little context, so each
one can be judged: Whisper spelling/number style, or a real mispronunciation.

Lectures come from --lectures-dir, else from [video].lectures_dir in
--video-config, else from lectures/.
"""
import argparse
import difflib
import re
import tomllib
from pathlib import Path

from ptkit.video.lecture import parse_lecture

parser = argparse.ArgumentParser(description="Diff lecture narration against Whisper transcripts.")
parser.add_argument("stt", type=Path, metavar="STT_DIR")
parser.add_argument("prefixes", nargs="*", metavar="stem-prefix")
source = parser.add_mutually_exclusive_group()
source.add_argument("--lectures-dir", type=Path, help="lecture Markdown folder (default: lectures)")
source.add_argument("--video-config", type=Path,
                    help="read [video].lectures_dir from this video-course TOML")
args = parser.parse_args()

if args.lectures_dir:
    lectures_dir = args.lectures_dir
elif args.video_config:
    data = tomllib.loads(args.video_config.read_text(encoding="utf-8"))
    lectures_dir = args.video_config.parent / data.get("video", {}).get("lectures_dir", "lectures")
else:
    lectures_dir = Path("lectures")
if not lectures_dir.is_dir():
    parser.error(f"lectures directory {lectures_dir} does not exist")


def words(text):
    text = re.sub(r"\[pause[^\]]*\]", " ", text)
    # Unicode letters and digits, so umlauts and ß stay inside their word.
    return re.findall(r"[^\W_]+", text.lower().replace("'", ""))


for lecture in sorted(lectures_dir.glob("*.md")):
    if args.prefixes and not lecture.stem.startswith(tuple(args.prefixes)):
        continue
    said = " ".join(s.narration for s in parse_lecture(lecture).slides)
    heard_file = args.stt / f"{lecture.stem}.txt"
    if not heard_file.exists():
        print(f"## {lecture.stem}: no transcript")
        continue
    heard = re.sub(r"^\[[^\]]*\]\s*", "", heard_file.read_text(encoding="utf-8"), flags=re.M)
    a, b = words(said), words(heard)
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    diffs = [op for op in matcher.get_opcodes() if op[0] != "equal"]
    print(f"## {lecture.stem}: {len(diffs)} diff(s), match {matcher.ratio():.3f}")
    for tag, i1, i2, j1, j2 in diffs:
        ctx = " ".join(a[max(0, i1 - 4):i1])
        print(f"   [{ctx}] script: {' '.join(a[i1:i2]) or '-'}  |  heard: {' '.join(b[j1:j2]) or '-'}")
