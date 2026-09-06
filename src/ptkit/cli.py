"""`ptkit` command line: validate, generate, new-course.

Every command resolves the course from the nearest course.toml, so they work
from anywhere inside a course repo.
"""

import argparse
import importlib.util
import shutil
import sys
from pathlib import Path

from . import checks as checks_pkg
from . import config as config_module
from .config import ConfigError
from .csvout import normalise_newlines, render
from .model import ParseError
from .parse import parse_master
from .report import Report

COURSE_CHECKS_PATH = Path("tools") / "course_checks.py"


def load_course_checks(config):
    """Import the course's own tools/course_checks.py, if it has one.

    Subject-specific knowledge -- "is this JEP number finalized in the release
    this exam covers?" -- belongs to the course, not the kit. The module
    exposes a module-level `CHECKS` list of functions taking a Context.
    """
    path = config.root / COURSE_CHECKS_PATH
    if not path.is_file():
        return []
    spec = importlib.util.spec_from_file_location(f"{config.slug}_course_checks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    course_checks = getattr(module, "CHECKS", None)
    if course_checks is None:
        raise ConfigError(
            f"{path} defines no module-level CHECKS list -- it should be a "
            f"list of functions taking a ptkit.checks.Context"
        )
    return list(course_checks)


def cmd_validate(args):
    config = config_module.load(args.config)
    questions = parse_master(config)
    report = Report()
    print(f"{config.name}\nparsed {len(questions)} questions from "
          f"{config.master.relative_to(config.root)}")
    checks_pkg.run(config, questions, report, course_checks=load_course_checks(config))
    return report.summary()


def cmd_generate(args):
    config = config_module.load(args.config)
    questions = parse_master(
        config, path=Path(args.master) if args.master else None,
        shuffle=not args.no_shuffle,
    )
    print(f"parsed {len(questions)} questions from "
          f"{args.master or config.master.relative_to(config.root)}")

    config.output_dir.mkdir(parents=True, exist_ok=True)
    stale = []
    for exam in config.exams:
        path = config.csv_path(exam)
        rendered = render(questions, exam, config)
        encoded = rendered.encode("utf-8")
        count = sum(1 for q in questions if q.exam == exam)

        if args.check:
            existing = path.read_text(encoding="utf-8") if path.exists() else ""
            # Line-ending agnostic, exactly like the csv-sync validation
            # check: core.autocrlf and LF-normalised commits both otherwise
            # report an identical file as stale.
            if normalise_newlines(existing) == normalise_newlines(rendered):
                print(f"  {path.name}: matches ({count} questions)")
            else:
                stale.append(path.name)
                print(f"  {path.name}: DIFFERS (on disk {len(existing)} chars, "
                      f"generated {len(rendered)})")
        else:
            path.write_bytes(encoded)
            print(f"  wrote {path.name} ({count} questions, {len(encoded)} bytes)")

    if stale:
        print(f"\n{len(stale)} file(s) differ from {config.master.name}: "
              f"{', '.join(stale)}")
        print("Run `ptkit generate` without --check to regenerate.")
        return 1
    if args.check:
        print(f"\nAll CSVs are up to date with {config.master.name}.")
    else:
        print("\nRegenerated. These must be re-uploaded to Udemy before "
              "learners see the change.")
    return 0


def cmd_new_course(args):
    """Scaffold a new course repo: the pipeline, CI, and the working rules.

    The tooling was never the slow part of starting a course -- re-deriving
    the authoring standard and the platform gotchas was. This copies both.
    """
    target = Path(args.directory).resolve()
    if target.exists() and any(target.iterdir()):
        print(f"{target} exists and is not empty", file=sys.stderr)
        return 1
    source = Path(__file__).parent / "scaffold"
    shutil.copytree(source, target, dirs_exist_ok=True)
    # .github would be swallowed by packaging tools if shipped under its real
    # name, so the scaffold stores it flattened and it is unpacked here.
    flattened = target / "github-workflows"
    if flattened.is_dir():
        workflows = target / ".github" / "workflows"
        workflows.mkdir(parents=True, exist_ok=True)
        for item in flattened.iterdir():
            shutil.move(str(item), workflows / item.name)
        flattened.rmdir()
    # Same problem: a leading dot would hide the file from packaging tools,
    # so the scaffold ships it undotted.
    gitignore = target / "gitignore"
    if gitignore.is_file():
        gitignore.rename(target / ".gitignore")
    print(f"Scaffolded {target}")
    print("\nNext:")
    print("  1. Fill in course.toml (name, slug, exam counts, domain names).")
    print("  2. Copy Udemy's PracticeTestBulkQuestionUploadTemplate_V2.2.csv in.")
    print("  3. Write questions into questions-master.md.")
    print("  4. `ptkit generate && ptkit validate`")
    print("\nRead UDEMY-PLATFORM-NOTES.md before authoring -- it is the list "
          "of platform quirks that have already cost a live course.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ptkit", description=__doc__.splitlines()[0]
    )
    parser.add_argument("--config", help="path to course.toml (default: nearest)")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="check the bank and its CSVs")
    validate.set_defaults(func=cmd_validate)

    generate = sub.add_parser("generate", help="regenerate the per-exam CSVs")
    generate.add_argument("--check", action="store_true",
                          help="write nothing; exit non-zero if the CSVs are stale")
    generate.add_argument("--master", help="override the source Markdown file")
    generate.add_argument("--no-shuffle", action="store_true",
                          help="skip [layout] shuffle_options; emit the "
                               "authored option order for hand-diffing")
    generate.set_defaults(func=cmd_generate)

    new_course = sub.add_parser("new-course", help="scaffold a new course repo")
    new_course.add_argument("directory")
    new_course.set_defaults(func=cmd_new_course)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, ParseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
