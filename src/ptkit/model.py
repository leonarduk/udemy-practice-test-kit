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
                 domain, domain_number=None, difficulty=None):
        self.exam = exam
        self.number = number
        self.stem = stem
        self.options = options          # dict: "A".."D" -> text
        self.answer = answer            # one key of self.options
        self.explanation = explanation
        self.domain = domain            # resolved display name
        # Indexes the course's domain table. None for fixtures that build a
        # Question directly without going through a parser.
        self.domain_number = domain_number
        # Only some course layouts carry a "**Difficulty:**" line; None means
        # "this course does not track it", not "unknown".
        self.difficulty = difficulty

    @property
    def qid(self):
        return f"E{self.exam}Q{self.number:02d}"

    @property
    def correct_index(self):
        """1-based option index, as Udemy's 'Correct Answers' column wants."""
        return sorted(self.options).index(self.answer) + 1

    @property
    def distractors(self):
        return [t for k, t in self.options.items() if k != self.answer]

    def __repr__(self):
        return f"<Question {self.qid} answer={self.answer}>"
