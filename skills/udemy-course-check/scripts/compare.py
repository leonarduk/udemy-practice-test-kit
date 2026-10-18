"""Diff each lecture's narration against its Whisper transcript.

Usage: python compare.py STT_DIR [stem-prefix ...]   (run from the course root)
Prints every span where the words differ, with a little context, so each
one can be judged: Whisper spelling/number style, or a real mispronunciation.
"""
import difflib
import re
import sys
from pathlib import Path

from ptkit.video.lecture import parse_lecture

stt = Path(sys.argv[1])
prefixes = sys.argv[2:]


def words(text):
    text = re.sub(r"\[pause[^\]]*\]", " ", text)
    return re.findall(r"[a-z0-9]+", text.lower().replace("'", ""))


for lecture in sorted(Path("lectures").glob("*.md")):
    if prefixes and not lecture.stem.startswith(tuple(prefixes)):
        continue
    said = " ".join(s.narration for s in parse_lecture(lecture).slides)
    heard_file = stt / f"{lecture.stem}.txt"
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
