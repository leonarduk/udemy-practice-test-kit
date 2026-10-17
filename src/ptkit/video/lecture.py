"""Parse a lecture: one Marp Markdown file, one slide per `---`.

The narration for a slide is its presenter notes -- the HTML comments on it
that are not Marp directives. That is Marp's own convention, so the same file
previews in the Marp VS Code extension with the script visible as notes, and
there is no second file to keep in step with the slides.

    ---
    marp: true
    ---

    # Unnamed variables

    <!-- Java 22 made the underscore a real keyword. Let's see why. -->

    ---

    ```java
    for (var _ : list) count++;
    ```

    <!--
    Here the loop never reads the element, so we name it with an underscore.
    [pause 600ms]
    The compiler now knows it is unused on purpose.
    -->
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..model import ParseError

# Marpit's directive names (global and local). A comment made only of
# `name: value` lines using these is configuration, not narration -- reading
# "paginate: true" aloud is the bug this list exists to prevent.
DIRECTIVES = frozenset({
    "marp", "theme", "style", "headingDivider", "lang", "size", "math",
    "title", "description", "author", "image", "keywords", "url",
    "paginate", "header", "footer", "class", "backgroundColor",
    "backgroundImage", "backgroundPosition", "backgroundRepeat",
    "backgroundSize", "color",
})

_DIRECTIVE_LINE = re.compile(r"^\s*_?([A-Za-z]+)\s*:")
_COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)
_FENCE = re.compile(r"^\s*(```|~~~)")
_PAUSE = re.compile(r"\[pause\s+(\d+(?:\.\d+)?)\s*(ms|s)\]", re.IGNORECASE)


@dataclass
class Slide:
    number: int          # 1-based, matching Marp's slide.001.png numbering
    line: int            # 1-based line in the lecture file where it starts
    body: str            # the visible Markdown, comments removed
    narration: str       # the spoken script, pause markers still in place
    setext_risk: list = field(default_factory=list)  # lines; see split_slides

    @property
    def spoken_text(self):
        """Narration with pause markers removed -- what a listener hears."""
        return " ".join(_PAUSE.sub(" ", self.narration).split())

    @property
    def word_count(self):
        return len(self.spoken_text.split())

    def pauses_seconds(self):
        total = 0.0
        for amount, unit in _PAUSE.findall(self.narration):
            total += float(amount) / (1000 if unit.lower() == "ms" else 1)
        return total


@dataclass
class Lecture:
    path: Path
    front_matter: str
    slides: list

    @property
    def stem(self):
        return self.path.stem

    @property
    def title(self):
        """First Markdown heading in the lecture, else the filename."""
        for slide in self.slides:
            match = re.search(r"^#{1,6}\s+(.+)$", slide.body, re.MULTILINE)
            if match:
                return match.group(1).strip()
        return self.stem


def is_directive(comment):
    lines = [line for line in comment.splitlines() if line.strip()]
    if not lines:
        return True  # an empty comment says nothing either way
    for line in lines:
        match = _DIRECTIVE_LINE.match(line)
        if not match or match.group(1) not in DIRECTIVES:
            return False
    return True


def split_slides(text):
    """Split Marp Markdown into (front_matter, [(start_line, chunk)]).

    A `---` line separates slides only outside a code fence and only after a
    blank line (or at the start). Right after a line of text, Markdown reads
    `---` as a setext heading underline instead, so Marp would NOT start a new
    slide there; returned as a risk so `check` can say so, because the slide
    count then silently disagrees with the narration.
    """
    lines = text.splitlines()
    front_matter = ""
    start = 0
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                front_matter = "\n".join(lines[1:index])
                start = index + 1
                break

    chunks = []
    risks = []
    current = []
    current_start = start + 1
    in_fence = False
    for index in range(start, len(lines)):
        line = lines[index]
        if _FENCE.match(line):
            in_fence = not in_fence
        if not in_fence and line.strip() == "---":
            previous = lines[index - 1].strip() if index > start else ""
            if previous and not previous.startswith("<!--") and not previous.endswith("-->"):
                risks.append(index + 1)
            else:
                chunks.append((current_start, "\n".join(current), risks))
                current, risks = [], []
                current_start = index + 2
                continue
        current.append(line)
    chunks.append((current_start, "\n".join(current), risks))
    return front_matter, chunks


def parse_lecture(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    front_matter, chunks = split_slides(text)
    if "marp: true" not in front_matter:
        raise ParseError(
            f"{path.name}: front matter must contain `marp: true` -- without "
            f"it Marp renders the file as a plain document, not slides"
        )
    slides = []
    for start_line, chunk, risks in chunks:
        notes = [
            " ".join(comment.split())
            for comment in _COMMENT.findall(chunk)
            if not is_directive(comment)
        ]
        # An empty chunk is kept, not skipped: Marp still renders it as a
        # blank slide, and dropping it here would shift every later slide's
        # number against the PNGs Marp writes. `check` fails it instead.
        body = _COMMENT.sub("", chunk).strip()
        slides.append(Slide(
            number=len(slides) + 1,
            line=start_line,
            body=body,
            narration=" ".join(notes),
            setext_risk=risks,
        ))
    if not slides:
        raise ParseError(f"{path.name}: no slides")
    return Lecture(path=path, front_matter=front_matter, slides=slides)
