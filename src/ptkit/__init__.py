"""Shared tooling for Udemy practice-test question banks.

A course repo owns its content (questions-master.md) and its configuration
(course.toml); this package owns the pipeline that turns one into Udemy's
bulk-upload CSVs and the checks that decide whether the result is fit to
upload. See README.md.
"""

from .config import COLUMNS, ConfigError, CourseConfig, load
from .csvout import is_current, normalise_newlines, render, to_row
from .model import ParseError, Question
from .parse import load_raw_bodies, parse_master
from .report import Report
from .text import TextRenderer

__version__ = "1.0.0"

__all__ = [
    "COLUMNS", "ConfigError", "CourseConfig", "ParseError", "Question",
    "Report", "TextRenderer", "is_current", "load", "load_raw_bodies",
    "normalise_newlines", "parse_master", "render", "to_row", "__version__",
]
