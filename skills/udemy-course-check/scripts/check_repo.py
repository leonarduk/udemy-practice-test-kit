"""Read-only checks of a Udemy course repo, plus a manifest for the live-course check.

Usage (from the course repo root):
    python check_repo.py [--jdk-bin DIR] [--skip-samples] [--manifest OUT.json]

Detects the course type:
  video          video-course.toml (ptkit video: lectures/*.md -> build/*.mp4 + .vtt)
  practice-test  course.toml (ptkit: questions-master.md -> practice-test-N.csv)

Prints one line per check: PASS / WARN / FAIL, then a summary. Exit code 1 if
any FAIL. Writes nothing in the repo; the manifest goes where --manifest says
(default: a temp file, path printed).

Every rule here was learned from a real upload; see udemy-practice-test-kit's
UDEMY-PLATFORM-NOTES.md (section numbers in brackets).
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

AI_DISCLOSURE = "This course contains the use of artificial intelligence."  # [21]
TLD_LIKE = re.compile(r"\b[a-z][\w]*(?:\.[a-z][\w]*)*\.(io|ai|dev|app|co|me|so|sh|ly|tv|xyz)\b", re.I)  # [14]
results = []


def report(level, name, detail=""):
    results.append((level, name, detail))
    print(f"{level:4}  {name}" + (f" -- {detail}" if detail else ""), flush=True)


def run(cmd, **kw):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=kw.pop("timeout", 1800), **kw)
    except FileNotFoundError as exc:
        return subprocess.CompletedProcess(cmd, 127, "", str(exc))
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, "", "timed out")


# ---------------------------------------------------------------- listing --

def section(text, heading):
    """Body of a '### heading' (or '## heading') section of course-listing.md."""
    m = re.search(rf"^#{{2,3}} {re.escape(heading)}[^\n]*\n(.*?)(?=^#{{2,3}} |\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else None


def check_listing(root, kind):
    listing = root / "platforms" / "udemy" / "course-listing.md"
    if not listing.exists():
        report("WARN", "course-listing.md", "not found; landing-page checks skipped")
        return {}
    text = listing.read_text(encoding="utf-8")
    out = {}
    title = section(text, "Title")
    if title:
        t = title.splitlines()[0].strip()
        out["title"] = t
        report("PASS" if len(t) <= 60 else "FAIL", "title <= 60 chars", f"{len(t)}: {t}")
    sub = section(text, "Subtitle")
    if sub:
        s = sub.splitlines()[0].strip()
        out["subtitle"] = s
        report("PASS" if len(s) <= 120 else "FAIL", "subtitle <= 120 chars", f"{len(s)}")
    desc = section(text, "Description")
    if desc is not None:
        body = re.sub(r"^.*?(?=^\S)", "", desc, flags=re.S)  # drop leading notes/indented blocks
        words = len(re.findall(r"\w+", desc))
        report("PASS" if words >= 200 else "WARN", "description >= 200 words", str(words))
        uses_ai = re.search(r"AI-generated|text-to-speech|\bTTS\b|artificial intelligence", text, re.I)
        if uses_ai:
            report("PASS" if AI_DISCLOSURE in desc else "FAIL", "AI disclosure in listing description [21]",
                   "must be the first paragraph, verbatim: " + AI_DISCLOSURE)
        # Ignore quoted text: the listing's own notes quote names *not* to use.
        unquoted = re.sub(r'"[^"\n]*"', "", desc)
        bad = sorted({m.group(0) for m in TLD_LIKE.finditer(unquoted) if "udemy" not in m.group(0).lower()})
        report("WARN" if bad else "PASS", "no domain-like dotted names in description [14]", ", ".join(bad))
        report("FAIL" if re.search(r"https?://|udemy\.com/course", desc) else "PASS", "no links in description")
    table = re.findall(r"^\|\s*(.+?)\s*\|\s*([0-9]{2}-[0-9]{2}-[\w-]+)?\s*\|", text, re.M)
    curriculum = []
    for title_cell, stem in table:
        title_cell = title_cell.strip()
        if re.match(r"\*\*Section \d+: (.+)\*\*", title_cell):
            curriculum.append({"class": "chapter", "title": re.match(r"\*\*Section \d+: (.+)\*\*", title_cell).group(1)})
        elif stem:
            curriculum.append({"class": "lecture", "title": title_cell, "stem": stem})
    if curriculum:
        out["curriculum"] = curriculum
        lectures = [c for c in curriculum if c["class"] == "lecture"]
        long = [c["title"] for c in lectures if len(c["title"]) > 80]
        ticks = [c["title"] for c in lectures if "`" in c["title"] or "**" in c["title"]]
        report("FAIL" if long else "PASS", "lecture titles <= 80 chars", "; ".join(long))
        report("FAIL" if ticks else "PASS", "lecture titles are plain text", "; ".join(ticks))
        if kind == "video":
            last = lectures[-1]["title"] if lectures else ""
            report("PASS" if last == "Bonus Lecture" else "WARN", "last lecture titled exactly 'Bonus Lecture'", last)
    m = re.search(r"free preview[^\n]*", text, re.I)
    out["free_preview_note"] = m.group(0) if m else ""
    return out


# ------------------------------------------------------------------ video --

def vtt_cues(path):
    t = path.read_text(encoding="utf-8").replace("\r", "")
    return re.findall(r"-->[^\n]*\n([^\n]+)", t)


def ffprobe_lengths(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration,height",
             "-of", "json", str(path)], timeout=60)
    if r.returncode:
        return None
    streams = json.loads(r.stdout).get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    a = next((s for s in streams if s.get("codec_type") == "audio"), {})
    return float(v.get("duration", 0)), float(a.get("duration", 0)), int(v.get("height", 0))


def check_video(root, args, manifest):
    cfg = tomllib.loads((root / "video-course.toml").read_text(encoding="utf-8"))
    r = run(["ptkit", "video", "check"], cwd=root)
    tail = (r.stdout or r.stderr).strip().splitlines()[-2:] if (r.stdout or r.stderr) else ["no output"]
    report("PASS" if r.returncode == 0 and "0 structural" in (r.stdout or "") else "FAIL", "ptkit video check", " / ".join(tail))

    if not args.skip_samples and (root / "tools" / "verify_samples.py").exists():
        env = dict(os.environ)
        if args.jdk_bin:
            env["PATH"] = args.jdk_bin + os.pathsep + env["PATH"]
        r = run([sys.executable, "tools/verify_samples.py"], cwd=root, env=env)
        last = (r.stdout.strip().splitlines() or ["?"])[-1]
        report("PASS" if r.returncode == 0 else "FAIL", "verify_samples.py", last)

    engine = cfg.get("voice", {}).get("engine", "recorded")
    if engine == "edge":
        report("FAIL", "narration engine 'edge'",
               "edge-tts audio carries no right to publish, and Udemy asks TTS instructors to "
               "sign that they hold it [23] -- switch to azure and rebuild every lecture and the promo")
    elif engine == "azure":
        report("WARN", "narration engine 'azure' (synthetic voice)",
               "needs the AI disclosure [21]; run the pronunciation pass before upload")

    lectures_dir = root / cfg.get("video", {}).get("lectures_dir", "lectures")
    build = root / cfg.get("video", {}).get("build_dir", "build")
    lectures = sorted(lectures_dir.glob("*.md"))
    newest_input = max([(root / "video-course.toml").stat().st_mtime] + [p.stat().st_mtime for p in lectures])
    files, total, missing, stale, drift, small, big = [], 0.0, [], [], [], [], []
    promo_hits = []
    for md in lectures:
        stem = md.stem
        mp4, vtt = build / f"{stem}.mp4", build / f"{stem}.vtt"
        if not (mp4.exists() and vtt.exists()):
            missing.append(stem)
            continue
        if mp4.stat().st_mtime < md.stat().st_mtime:
            stale.append(stem)
        lengths = ffprobe_lengths(mp4)
        if lengths:
            v, a, h = lengths
            total += a
            if abs(v - a) > 0.3:
                drift.append(f"{stem} video {v:.1f}s vs audio {a:.1f}s")
            if h and h < 720:
                small.append(f"{stem} {h}p")
        if mp4.stat().st_size > 10 * 1024 * 1024:
            big.append(f"{stem} {mp4.stat().st_size / 1048576:.1f} MB")
        cues = vtt_cues(vtt)
        files.append({"stem": stem, "mp4": mp4.name, "vtt": vtt.name, "cues": len(cues),
                      "first_cue": cues[0] if cues else "",
                      "sha256": hashlib.sha256(mp4.read_bytes()).hexdigest()})
        text = md.read_text(encoding="utf-8")
        if "bonus" not in stem.lower() and re.search(r"udemy\.com/course|my other courses|practice tests? course", text, re.I):
            promo_hits.append(stem)
    report("FAIL" if missing else "PASS", "every lecture rendered (mp4 + vtt)", ", ".join(missing))
    report("WARN" if stale else "PASS", "renders newer than their lecture source", ", ".join(stale) +
           (" (git checkouts also touch mtimes: rebuild only if the lecture text changed since the render)" if stale else ""))
    report("FAIL" if drift else "PASS", "video length matches narration (no silent tail)", "; ".join(drift))
    report("FAIL" if small else "PASS", "resolution >= 720p", ", ".join(small))
    report("WARN" if big else "PASS", "files under 10 MB (browser-automation upload cap)", ", ".join(big))
    report("WARN" if promo_hits else "PASS", "no promotion outside the Bonus Lecture", ", ".join(promo_hits))
    mins = total / 60
    report("PASS" if mins >= 30 else "FAIL", "runtime >= 30 min (Udemy minimum)", f"{mins:.1f} min")
    report("PASS" if mins < 120 else "WARN", "runtime < 120 min (needed only if the course is free)", f"{mins:.1f} min")
    manifest["kind"] = "video"
    manifest["files"] = files
    manifest["runtime_seconds"] = round(total)
    manifest["newest_input_mtime"] = newest_input


# --------------------------------------------------------- practice tests --

def check_practice(root, manifest):
    r = run(["ptkit", "validate"], cwd=root)
    tail = " / ".join((r.stdout or "").strip().splitlines()[-2:])
    report("PASS" if "0 structural" in (r.stdout or "") else "FAIL", "ptkit validate", tail)
    r = run(["ptkit", "generate", "--check"], cwd=root)
    report("PASS" if r.returncode == 0 else "FAIL", "ptkit generate --check (CSVs current)", (r.stdout or r.stderr).strip()[-120:])
    cfg = tomllib.loads((root / "course.toml").read_text(encoding="utf-8"))
    out_dir = root / cfg.get("layout", {}).get("output_dir", ".")
    pattern = cfg.get("layout", {}).get("csv_name", "practice-test-{exam}.csv")
    exams = []
    import csv
    for n in cfg.get("exams", {}).get("numbers", []):
        p = out_dir / pattern.format(exam=n)
        if not p.exists():
            report("FAIL", f"CSV for exam {n}", f"{p.name} missing")
            continue
        rows = list(csv.DictReader(p.open(encoding="utf-8", newline="")))
        tagged = [i + 1 for i, row in enumerate(rows)
                  if re.search(r"<[A-Za-z/!?]", " ".join(v for k, v in row.items() if k and ("Question" in k or "Answer" in k or "Explanation" in k)))]
        report("WARN" if tagged else "PASS", f"exam {n}: no tag-shaped '<' in learner text [3a]", f"rows {tagged[:10]}")
        keys = [row.get("Correct Answers", "") for row in rows]
        single = [k for k in keys if k and "," not in k]
        key_pattern = ""
        for period in (2, 3, 4, 5):
            same = sum(1 for i in range(period, len(single)) if single[i] == single[i - period])
            if len(single) > period * 3 and same / (len(single) - period) >= 0.8:
                key_pattern = f"keys repeat with period {period} ({same}/{len(single) - period} positions)"
                break
        counts = {k: single.count(k) for k in sorted(set(single))}
        skew = single and max(counts.values()) / len(single) > 0.4
        report("WARN" if key_pattern or skew else "PASS", f"exam {n}: answer positions not predictable",
               key_pattern or (f"skewed: {counts}" if skew else f"spread {counts}"))
        exams.append({"exam": n, "questions": len(rows),
                      "keys": [row.get("Correct Answers", "") for row in rows],
                      "stems": [re.sub(r"\s+", " ", row.get("Question", ""))[:80] for row in rows]})
    report("PASS" if len(exams) <= 6 else "FAIL", "at most 6 practice tests [5]", str(len(exams)))
    manifest["kind"] = "practice-test"
    manifest["exams"] = exams


EDGE_TTS = re.compile(r"^\s*(?:import edge_tts|from edge_tts|edge-tts\b)", re.MULTILINE)
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "build", "out", "__pycache__"}


def check_voice_rights(root):
    """No edge-tts anywhere, promo builders included [23].

    Its audio carries no right to publish, and Udemy asks TTS instructors to
    sign that they hold that right, so a promo voiced with it is as exposed
    as a lecture.
    """
    hits = []
    for path in root.rglob("*"):
        if SKIP_DIRS.intersection(path.relative_to(root).parts) or not path.is_file():
            continue
        if path.suffix == ".py" or (path.suffix == ".txt" and path.name.startswith("requirements")):
            if EDGE_TTS.search(path.read_text(encoding="utf-8", errors="replace")):
                hits.append(str(path.relative_to(root)))
    report("FAIL" if hits else "PASS", "no edge-tts narration, promo included [23]", ", ".join(hits))


def check_kit_pin(root):
    """Installed ptkit must be the commit requirements-dev.txt pins, or results mislead."""
    req = root / "requirements-dev.txt"
    if not req.exists():
        return
    m = re.search(r"udemy-practice-test-kit@([0-9a-f]{7,40})", req.read_text(encoding="utf-8"))
    if not m:
        return
    pin = m.group(1)
    try:
        from importlib import metadata
        info = json.loads(metadata.distribution("udemy-practice-test-kit").read_text("direct_url.json") or "{}")
        installed = info.get("vcs_info", {}).get("commit_id") or info.get("url", "")
    except Exception as exc:  # not installed, or installed from a local path
        installed = f"unknown ({exc.__class__.__name__})"
    same = isinstance(installed, str) and (installed.startswith(pin) or pin.startswith(installed[:7]))
    report("PASS" if same else "FAIL", "installed ptkit is the repo's pinned commit",
           f"pin {pin[:10]}, installed {str(installed)[:40]}" +
           ("" if same else " -- pip install --force-reinstall --no-deps -r requirements-dev.txt, then re-run"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jdk-bin", help="JDK bin directory to put first on PATH for verify_samples.py")
    ap.add_argument("--skip-samples", action="store_true")
    ap.add_argument("--manifest", help="where to write the manifest JSON")
    args = ap.parse_args()
    root = Path.cwd()
    if (root / "video-course.toml").exists():
        kind = "video"
    elif (root / "course.toml").exists():
        kind = "practice-test"
    else:
        sys.exit("No video-course.toml or course.toml here: run from a course repo root.")
    print(f"Course repo: {root}  ({kind})\n")
    manifest = {"repo": str(root)}
    check_kit_pin(root)
    check_voice_rights(root)
    manifest["listing"] = check_listing(root, kind)
    if kind == "video":
        if not shutil.which("ffprobe"):
            report("FAIL", "ffprobe on PATH", "needed for length checks")
        check_video(root, args, manifest)
    else:
        check_practice(root, manifest)
    out = Path(args.manifest) if args.manifest else Path(tempfile.gettempdir()) / f"udemy-course-manifest-{root.name}.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    fails = sum(1 for r in results if r[0] == "FAIL")
    warns = sum(1 for r in results if r[0] == "WARN")
    print(f"\n{fails} FAIL, {warns} WARN, {len(results) - fails - warns} PASS")
    print(f"manifest: {out}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
