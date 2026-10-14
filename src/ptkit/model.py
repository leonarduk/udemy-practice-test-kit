"""The question model shared by every course bank.

Deliberately dumb: a Question knows how to identify itself and how to answer
the two questions the CSV projection asks of it (which option index is
correct, which options are distractors). Everything else -- how it was
parsed, how it is rendered, how it is judged -- lives elsewhere, so a course
with a different Markdown layout reuses this unchanged.
"""


class ParseError(Exception):
    """questions-master.md does not match the layout the course declares."""


class Question:
    def __init__(self, exam, number, stem, options, answer, explanation,
                 domain, domain_number=None, difficulty=None,
                 option_explanations=None, answers=None):
        self.exam = exam
        self.number = number
        self.stem = stem
        self.options = options          # dict: "A".."D" -> text
        # A multi-select question is declared by passing `answers` (one or
        # more keys of self.options) instead of `answer`. It is a different
        # Udemy question type, not "single-choice with a list of one": a
        # multi-select whose only correct answer is "approve, no defect" is
        # deliberately indistinguishable, to the learner, from one with three.
        if answers is not None:
            if answer is not None:
                raise ValueError("pass either answer or answers, not both")
            if not answers:
                raise ValueError("a multi-select question needs at least one answer")
            self.answers = tuple(sorted(answers))
            self.answer = None
        else:
            self.answers = (answer,)
            self.answer = answer        # one key of self.options
        self.multi = answers is not None
        self.explanation = explanation
        self.domain = domain            # resolved display name
        # Indexes the course's domain table. None for fixtures that build a
        # Question directly without going through a parser.
        self.domain_number = domain_number
        # Only some course layouts carry a "**Difficulty:**" line; None means
        # "this course does not track it", not "unknown".
        self.difficulty = difficulty
        # Optional per-option explanation ("why is A right/wrong"), keyed
        # like self.options. Empty for a course that doesn't author these --
        # not every option needs to be covered by a partially-filled dict,
        # that's a course-authoring error the parser rejects outright; this
        # is either fully populated (one entry per option) or empty.
        self.option_explanations = option_explanations or {}

    @property
    def qid(self):
        return f"E{self.exam}Q{self.number:02d}"

    @property
    def correct_index(self):
        """1-based option index, as Udemy's 'Correct Answers' column wants.

        Single-answer questions only; see correct_indices for multi-select.
        """
        if self.multi:
            raise ValueError(f"{self.qid} is multi-select; use correct_indices")
        return sorted(self.options).index(self.answer) + 1

    @property
    def correct_indices(self):
        """1-based option indexes of every correct answer, ascending."""
        ordered = sorted(self.options)
        return tuple(ordered.index(a) + 1 for a in self.answers)

    @property
    def distractors(self):
        return [t for k, t in self.options.items() if k not in self.answers]

    def __repr__(self):
        return f"<Question {self.qid} answers={','.join(self.answers)}>"
