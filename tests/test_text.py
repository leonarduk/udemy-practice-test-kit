"""Regression tests for the learner-text renderer.

Every test here corresponds to text that reached, or nearly reached, a live
Udemy course in a broken state. This is the fixture that stops a future edit
from silently reintroducing literal backticks, half-stripped asterisks, or
blanked-out explanations into the CSVs.
"""

import unittest

from ptkit.text import TextRenderer

render = TextRenderer()


class StripLearnerTextTests(unittest.TestCase):
    def test_strips_backtick_code_spans(self):
        self.assertEqual(
            render("`byte` wraps around at `127`."),
            "byte wraps around at 127.",
        )

    def test_strips_paired_emphasis_asterisks(self):
        self.assertEqual(
            render("the *and* the closing delimiter"),
            "the and the closing delimiter",
        )

    def test_leaves_unpaired_asterisk_untouched(self):
        # A single stray '*' (multiplication in a code snippet, or a glob in
        # `package.*`) has no partner to pair with and must survive.
        self.assertEqual(render("s.s() * s.s()"), "s.s() * s.s()")

    def test_leaves_two_spaced_multiplications_untouched(self):
        # A naive left-to-right "*(.+?)*" pairing treats two unrelated,
        # space-flanked multiplication operators as a single emphasis span and
        # deletes both asterisks -- silently turning valid Java into a syntax
        # error. This was live on a Udemy course before being caught.
        self.assertEqual(
            render("case Circle c -> Math.PI * c.r() * c.r();"),
            "case Circle c -> Math.PI * c.r() * c.r();",
        )

    def test_strips_double_asterisk_bold_completely(self):
        # **bold** was only half-stripped to *bold* by an earlier single-pass
        # regex, leaving stray literal asterisks in learner-facing text.
        self.assertEqual(
            render("Which line below fails to **compile**?"),
            "Which line below fails to compile?",
        )

    def test_leaves_compact_multiplication_in_backticks_untouched(self):
        # A backtick-quoted compact expression with no spaces around its
        # operators was previously indistinguishable from nested emphasis and
        # got mangled into the nonsensical `11234 == 24`.
        self.assertEqual(
            render("For example: `1*1*2*3*4 == 24` is one case."),
            "For example: 1*1*2*3*4 == 24 is one case.",
        )

    def test_drops_trailing_verified_sentence(self):
        self.assertEqual(
            render("`byte` wraps at 127 (JLS §4.2.1). Verified: prints `-128`."),
            "byte wraps at 127 (JLS §4.2.1).",
        )

    def test_drops_whole_paragraph_starting_with_verified(self):
        text = (
            "Verified by running the snippet directly: it printed 4.\n\n"
            "Autoboxing converts the primitive int to an Integer at the "
            "assignment, which is why reference equality with == can differ "
            "from value equality."
        )
        self.assertEqual(
            render(text),
            "Autoboxing converts the primitive int to an Integer at the "
            "assignment, which is why reference equality with == can differ "
            "from value equality.",
        )

    def test_verified_paragraph_that_is_the_whole_explanation_is_kept(self):
        # Two questions shipped with a completely BLANK Overall Explanation
        # because their entire explanation is a single sentence that happens
        # to open with "Verified" -- an earlier regex matched \A...\Z and
        # deleted the whole paragraph, leaving nothing. Stripping must never
        # empty out an explanation that has no other paragraph to fall back on.
        text = ("Verified directly by compiling and running the snippet: it "
                "printed the expected trace end to end")
        self.assertEqual(render(text), text)

    def test_verified_aside_does_not_swallow_later_real_content(self):
        # An earlier regex matched everything from "Verified" to the
        # *paragraph's* end, so a mid-paragraph aside deleted every sentence
        # after it too -- including, for one question, the reasoning for why
        # the other three options are wrong. Only the aside itself should go.
        text = ("Thread.ofVirtual() starts a genuine virtual thread. "
                "Verified on JDK 25.0.1: isVirtual() returned true. "
                "Thread.ofPlatform() (B) creates an ordinary platform "
                "thread instead.")
        self.assertEqual(
            render(text),
            "Thread.ofVirtual() starts a genuine virtual thread. "
            "Thread.ofPlatform() (B) creates an ordinary platform "
            "thread instead.",
        )

    def test_drops_maintainer_note_and_keeps_the_teaching_paragraph(self):
        # An earlier version kept exactly the wrong paragraph -- it dropped
        # the real, "Verified ..."-prefixed teaching content and kept the
        # maintainer-only note about an upstream answer-key discrepancy.
        text = (
            "Verified with javac: the guarded case is unreachable because "
            "the earlier unguarded case already matches every value, so "
            "compilation fails per the switch dominance rules\n\n"
            "Note: the upstream source's solution file returns a different "
            "answer than its own explanation describes; the explanation "
            "above is treated as authoritative here, not the upstream key."
        )
        result = render(text)
        self.assertIn("switch dominance rules", result)
        self.assertNotIn("upstream source", result)
        self.assertNotIn("upstream key", result)

    def test_drops_private_repo_citation_and_session_tail(self):
        # A trailing "Source: <owner>/<repo> ..." citation and "Independently
        # re-verified in this session ..." framing leaked into a
        # learner-facing explanation -- a dead link to a private repo, plus
        # authoring-process language.
        text = (
            "Static initializers run once per class, superclass before "
            "subclass. Source: [`leonarduk/java_25_cert`](https://github.com/"
            "leonarduk/java_25_cert) mock-exams/code-output-prediction, "
            "question 07. Independently re-verified in this session by "
            "compiling and running the snippet on JDK 25.0.1."
        )
        self.assertEqual(
            render(text),
            "Static initializers run once per class, superclass before "
            "subclass.",
        )

    def test_citation_owner_is_configurable(self):
        # A course with a different (or no) private upstream must not inherit
        # another course's owner name as a magic string.
        text = "Real content. Source: someoneelse/their-repo, question 07."
        self.assertEqual(render(text), text)
        other = TextRenderer(citation_owners=("someoneelse",))
        self.assertEqual(other(text), "Real content.")

    def test_no_citation_owners_still_strips_session_framing(self):
        renderer = TextRenderer(citation_owners=())
        self.assertEqual(
            renderer("Real content. Independently re-verified in this session."),
            "Real content.",
        )

    def test_drops_module_readme_cross_reference(self):
        self.assertEqual(
            render("JEP 511 imports every exported package. "
                   "Matches this module's own `t1-01-source-and-launch` README."),
            "JEP 511 imports every exported package.",
        )

    def test_strip_verified_asides_false_keeps_the_verified_sentence(self):
        # A course whose "Verified by running it: ..." sentence IS the
        # substantive evidence, not a discardable tail -- see
        # spring-boot-ai-udemy-practice-tests, where the general claim alone
        # (before "Verified") doesn't state the concrete observed behaviour
        # that sentence carries. Off by default's own tests above cover the
        # opposite course; this is the opt-out.
        renderer = TextRenderer(strip_verified_asides=False)
        text = ("Relaxed binding applies uniformly. Verified by running it: "
                "`app.greeting.repeat-count=3` produced 3 repetitions.")
        self.assertEqual(
            renderer(text),
            "Relaxed binding applies uniformly. Verified by running it: "
            "app.greeting.repeat-count=3 produced 3 repetitions.",
        )

    def test_strip_verified_asides_false_still_strips_markdown_and_citations(self):
        # The off switch only disables VERIFIED_TAIL_RE -- backtick/emphasis
        # stripping and citation-tail stripping are unrelated passes and stay
        # on.
        renderer = TextRenderer(strip_verified_asides=False)
        text = "`byte` wraps at 127. Source: leonarduk/some_repo, question 3."
        self.assertEqual(renderer(text), "byte wraps at 127.")

    def test_multi_space_code_indentation_survives(self):
        # A stem mixes prose and inline code with no fence markers left by
        # render time (strip_fences already removed them at parse time), so
        # a naive "collapse any 2+ space run" -- meant to clean up the
        # double space an aside/citation removal leaves mid-sentence --
        # flattened every nested code block's indentation to a single
        # leading space instead. Confirmed against a real course
        # (spring-boot-ai-udemy-practice-tests) before this was live: every
        # multi-line snippet with a nested block lost its indentation.
        code = ("public static void main(String[] args) {\n"
                "    int x = 1;\n"
                "    System.out.println(x);\n"
                "}")
        self.assertEqual(render(code), code)

    def test_untouched_paragraph_never_runs_the_collapse_at_all(self):
        # The collapse/strip pass only runs on a paragraph where a citation
        # or "Verified" removal actually fired -- a paragraph with neither
        # trigger must be passed through completely unchanged, mid-sentence
        # double space included, since there is no way to tell that space
        # apart from a code snippet's own comment-alignment padding once
        # fence markers are gone.
        text = "Sentence one.  Sentence two, with  aligned   spacing kept."
        self.assertEqual(render(text), text)

    def test_trailing_whitespace_left_by_a_citation_removal_still_trims(self):
        # Unlike the untouched case above, a paragraph the citation-tail
        # removal actually fired on still gets its own leftover artifact
        # (the trailing space before the now-removed citation) trimmed --
        # gating the cleanup on n_citation/n_verified must not turn it off
        # for citation removals too, only for a paragraph neither touched.
        text = "Real content. Source: leonarduk/some_repo, question 3."
        self.assertEqual(render(text), "Real content.")

    def test_lowercase_verified_mid_sentence_is_kept(self):
        # Only a sentence-*initial*, capitalised "Verified"/"Matches this
        # module's own" is a stripped aside -- lowercase "verified" appearing
        # naturally inside a sentence is ordinary explanation text.
        self.assertEqual(
            render("This is the tested, verified content, not a formatting issue."),
            "This is the tested, verified content, not a formatting issue.",
        )


if __name__ == "__main__":
    unittest.main()
