"""Render Markdown-authored bank text the way Udemy's plain-text fields need it.

Every regex in here was paid for by a bug that reached a live course. The
comments say which one; do not "tidy" a pattern without reading them.

Udemy's practice-test importer treats Question, Answer Option and Overall
Explanation as PLAIN TEXT -- there is no Markdown renderer -- so anything the
author wrote as Markdown (code fences, backtick spans, **bold**) reaches the
learner as literal punctuation unless it is stripped here first. See
UDEMY-PLATFORM-NOTES.md for the full list of platform quirks this encodes.
"""

import re

# Matches a Markdown code fence line -- ```java or a bare ```. Udemy's
# question field is plain text, so these render as literal backtick clutter.
# This already shipped once and forced a whole practice test to be deleted
# and re-uploaded.
#
# The whole line goes, newline included -- blanking it in place would leave a
# spurious empty line between a snippet and the sentence that follows it.
FENCE_RE = re.compile(r"^```\w*$")

# A "Verified ..." or "Matches this module's own ... README" aside, occurring
# either at the start of a paragraph or mid-paragraph after ". ", introduces a
# verification/cross-reference note that learners can't act on. An earlier
# version of this pattern matched `.*\Z` -- everything from the trigger to the
# *paragraph's* end -- which is right for a short aside that trails a sentence
# ("... (JLS Sec4.2.1). Verified: prints -128.") but wrong whenever real
# teaching content (e.g. why the other options are wrong) follows the aside in
# the same paragraph: one question lost its entire B/C/D reasoning this way.
# Stop at the *next* sentence boundary (a ". " or the paragraph's end) instead,
# so only the aside sentence itself is removed and whatever follows survives.
VERIFIED_TAIL_RE = re.compile(
    r"(?:\A|(?<=\. ))(?:Verified\b|(?:This )?[Mm]atches this module's own\b)"
    r".*?(?:\.(?=\s)|\Z)",
    re.S,
)

# A maintainer-only note recording a deliberate deviation from the upstream
# answer key. It records provenance for whoever maintains the bank next, not
# something a learner needs -- and it refers to text ("quoted above verbatim")
# that VERIFIED_TAIL_RE may already have removed from the learner-facing copy,
# so leaving it in is actively misleading, not just irrelevant. Matched only at
# the very start of a paragraph: this is a narrow, specific pattern, not a
# general "Note:" filter, so a legitimate explanation paragraph that happens to
# start with "Note:" is not at risk of being swept up by it.
MAINTAINER_NOTE_RE = re.compile(r"\ANote: the upstream source\b", re.S)

# A naive re.sub(r"\*(.+?)\*", ...) pairs up ANY two asterisks left-to-right,
# with no way to tell Markdown **bold**/*emphasis* apart from a literal `*`
# multiplication operator in a code snippet. That silently deleted real
# operators from learner-facing text -- `Math.PI * c.r() * c.r()` became
# `Math.PI  c.r()  c.r()` (already live on a Udemy course when it was caught),
# and a backtick-quoted `1*1*2*3*4 == 24` became the nonsensical `11234 == 24`.
# `**compile**` also only half-stripped to `*compile*`, since the
# single-asterisk pattern consumed one layer of the double delimiter and
# stopped.
#
# The fix has two parts, applied together in one left-to-right pass so backtick
# spans win priority over emphasis matches that would otherwise start inside
# them:
#   1. A backtick-quoted span (`...`) is matched and passed through untouched
#      -- its content, asterisks included, is never a Markdown emphasis
#      candidate. The backtick characters themselves are stripped in a later,
#      separate pass, once emphasis-stripping is done.
#   2. **bold** and *emphasis* delimiters are only recognised when neither side
#      has whitespace immediately inside it (CommonMark's own
#      left/right-flanking rule, in miniature) -- `*word*` qualifies, ` * `
#      does not. A spaced multiplication operator never satisfies this, so it
#      is left alone without needing to be "unpaired" to survive.
MARKDOWN_TOKEN_RE = re.compile(
    r"`[^`]*`"
    r"|\*\*(?!\s)([^`]+?)(?<!\s)\*\*"
    r"|\*(?!\s)([^`]+?)(?<!\s)\*"
)

DEFAULT_CITATION_OWNERS = ("leonarduk",)


def build_citation_tail_re(owners=DEFAULT_CITATION_OWNERS):
    """"Source: <owner>/<repo> ..." / "Independently re-verified ..." tails.

    An authoring-provenance citation of a PRIVATE upstream repo, plus
    session-log framing ("in this session"). Neither means anything to a
    learner and the repo reference is a dead, private link. Unlike
    VERIFIED_TAIL_RE, everything from the trigger onward really is just
    citation/session bookkeeping and never teaching content, so this one
    intentionally keeps the greedy-to-paragraph-end behaviour.

    `owners` are the GitHub account names whose repos are private upstreams of
    the bank; pass () for a course with no such upstream, which leaves only the
    "Independently re-verified" trigger.
    """
    triggers = ["Independently re-verified\\b"]
    if owners:
        alternation = "|".join(re.escape(owner) for owner in owners)
        triggers.insert(0, rf"Source:\s*\S*(?:{alternation})\b")
    return re.compile(
        rf"(?:\A|(?<=\. ))(?:{'|'.join(triggers)}).*\Z",
        re.S,
    )


def unmark(text):
    """Strip Markdown emphasis delimiters, leaving backtick spans intact."""
    def replace(match):
        bold, emphasis = match.group(1), match.group(2)
        if bold is not None:
            return bold
        if emphasis is not None:
            return emphasis
        return match.group(0)  # a backtick span: pass through untouched for now

    return MARKDOWN_TOKEN_RE.sub(replace, text)


def strip_fences(raw):
    """Drop Markdown code-fence marker lines, keeping the code between them."""
    return "\n".join(line for line in raw.split("\n") if not FENCE_RE.match(line))


class TextRenderer:
    """Turns authored Markdown into the plain text Udemy actually displays.

    Built from a CourseConfig so the one genuinely course-specific part -- the
    private upstream repo owner named in provenance citations -- is data, not
    a hardcoded regex.
    """

    def __init__(self, citation_owners=DEFAULT_CITATION_OWNERS):
        self.citation_tail_re = build_citation_tail_re(citation_owners)

    def __call__(self, text):
        """Render `text` for a learner-facing CSV column.

        The aside-stripping below must never delete a question's entire
        explanation. Maintainer notes are dropped unconditionally -- they're
        never the only real content, since the actual teaching paragraph is
        always written above them. But a "Verified"/citation aside sometimes
        *is* the entire explanation, just phrased as if it were a verification
        note -- if stripping every paragraph down to nothing would leave a
        blank explanation, the original, unstripped paragraphs are kept
        instead of shipping empty text.
        """
        paragraphs = [
            p for p in text.split("\n\n")
            if not MAINTAINER_NOTE_RE.match(p.strip())
        ]

        stripped = []
        for paragraph in paragraphs:
            paragraph = self.citation_tail_re.sub("", paragraph)
            paragraph = VERIFIED_TAIL_RE.sub("", paragraph)
            stripped.append(re.sub(r"[ \t]{2,}", " ", paragraph).strip())

        kept = [p for p in stripped if p]
        if not kept:
            # Every remaining paragraph would come out blank -- the
            # "Verified"/citation text here is the substance, not an aside.
            # Fall back to the maintainer-note-filtered but otherwise
            # unstripped paragraphs rather than ship an empty explanation.
            kept = [p.strip() for p in paragraphs if p.strip()]

        text = "\n\n".join(kept)
        text = unmark(text)
        text = text.replace("`", "")
        return text
