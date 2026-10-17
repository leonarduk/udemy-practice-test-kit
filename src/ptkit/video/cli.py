"""`ptkit video ...` subcommands."""

import shutil
import sys
from pathlib import Path

from ..report import Report
from . import build as build_module
from . import checks
from . import config as config_module
from .lecture import parse_lecture


def _load(args):
    config = config_module.load(args.video_config)
    if getattr(args, "engine", None):
        config.engine = args.engine
    return config


def _select(config, names):
    lectures = config.lectures()
    if not names:
        return lectures
    chosen = []
    for name in names:
        matches = [p for p in lectures if p.stem == name or p.stem.startswith(name)]
        if len(matches) != 1:
            raise config_module.ConfigError(
                f"{name!r} matches {len(matches)} lectures in "
                f"{config.lectures_dir.name}/ -- use more of the filename"
            )
        chosen.append(matches[0])
    return chosen


def cmd_check(args):
    config = _load(args)
    report = Report()
    print(f"{config.name} (voice: {config.engine})")
    checks.run(config, report)
    return report.summary()


def cmd_build(args):
    config = _load(args)
    # Never spend TTS quota or render on a script check would fail.
    report = Report()
    checks.run(config, report)
    if report.failures:
        print("\nFix the failures above before building.", file=sys.stderr)
        return 1
    print()
    total = 0.0
    for path in _select(config, args.lectures):
        _, seconds = build_module.build_lecture(path, config)
        total += seconds
    print(f"\nBuilt {total / 60:.1f} min of video into "
          f"{config.build_dir.relative_to(config.root)}/")
    if config.engine == "silent":
        print("Engine was 'silent': the MP4s have no voice -- for checking "
              "slides and timing only.")
    return 0


def cmd_script(args):
    """Print a lecture's narration slide by slide -- the reading script."""
    config = _load(args)
    for path in _select(config, args.lectures):
        lecture = parse_lecture(path)
        print(f"# {lecture.stem} -- {lecture.title}\n")
        for slide in lecture.slides:
            print(f"[slide-{slide.number:03d}]  (line {slide.line})")
            print(slide.narration or "(no narration)")
            print()
    return 0


def cmd_new_course(args):
    target = Path(args.directory).resolve()
    if target.exists() and any(target.iterdir()):
        print(f"{target} exists and is not empty", file=sys.stderr)
        return 1
    source = Path(__file__).parent / "scaffold"
    shutil.copytree(source, target, dirs_exist_ok=True)
    # Shipped undotted for the same packaging reason as the bank scaffold.
    flattened = target / "github-workflows"
    if flattened.is_dir():
        workflows = target / ".github" / "workflows"
        workflows.mkdir(parents=True, exist_ok=True)
        for item in flattened.iterdir():
            shutil.move(str(item), workflows / item.name)
        flattened.rmdir()
    if (target / "gitignore").is_file():
        (target / "gitignore").rename(target / ".gitignore")
    print(f"Scaffolded {target}")
    print("\nNext:")
    print("  1. Fill in video-course.toml (name, slug, voice).")
    print("  2. Write lectures/NN-NN-topic.md -- slides with the script as notes.")
    print("  3. `ptkit video check`, then `ptkit video build --engine silent` to preview.")
    print("  4. Record (or synthesise) the narration and `ptkit video build`.")
    return 0


def add_parser(sub):
    video = sub.add_parser("video", help="build video lectures from slides + script")
    video.add_argument("--video-config", help="path to video-course.toml (default: nearest)")
    vsub = video.add_subparsers(dest="video_command", required=True)

    check = vsub.add_parser("check", help="check every lecture's slides and script")
    check.add_argument("--engine", choices=config_module.ENGINES)
    check.set_defaults(func=cmd_check)

    build = vsub.add_parser("build", help="render lectures to MP4 + VTT")
    build.add_argument("lectures", nargs="*", help="lecture filename stems or prefixes (default: all)")
    build.add_argument("--engine", choices=config_module.ENGINES,
                       help="override [voice] engine; 'silent' previews timing for free")
    build.set_defaults(func=cmd_build)

    script = vsub.add_parser("script", help="print the narration to read aloud")
    script.add_argument("lectures", nargs="*")
    script.set_defaults(func=cmd_script)

    new_course = vsub.add_parser("new-course", help="scaffold a new video course repo")
    new_course.add_argument("directory")
    new_course.set_defaults(func=cmd_new_course)
