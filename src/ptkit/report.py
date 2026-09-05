"""Collects check results and decides the process exit code.

Three severities, and the distinctions are load-bearing:

  fail     STRUCTURAL -- something that would break the Udemy bulk upload or
           corrupt an exam. Blocks CI.
  warn     ITEM QUALITY -- a psychometric or hygiene finding that is expected
           to improve over time rather than being a pass/fail gate today.
  pending  NOT DONE YET -- work that has not been written, as opposed to
           written badly. Neither a failure nor a warning.

A check that cannot decide which of the three it is has not been thought
through yet.
"""


class Report:
    def __init__(self, stream=None):
        self.failures = []
        self.warnings = []
        self._stream = stream

    def _print(self, text):
        if self._stream is None:
            print(text)
        else:
            print(text, file=self._stream)

    def heading(self, title):
        self._print(f"\n{title}\n{'-' * len(title)}")

    def fail(self, message):
        self.failures.append(message)
        self._print(f"  FAIL  {message}")

    def warn(self, message):
        self.warnings.append(message)
        self._print(f"  WARN  {message}")

    def ok(self, message):
        self._print(f"  ok    {message}")

    def pending(self, message):
        """Report work that is simply not done yet.

        Deliberately neither a failure nor a warning: an unwritten exam is not
        a defect in what HAS been written, and counting it as either would
        leave CI permanently red through the whole authoring phase -- at which
        point a real regression is invisible, which is the opposite of what
        the gate is for. See CourseConfig.complete_exams.
        """
        self._print(f"  ....  {message}")

    def detail(self, message):
        """An indented continuation line under the finding above it."""
        self._print(f"        {message}")

    def summary(self):
        self.heading("Summary")
        self._print(
            f"  {len(self.failures)} structural failure(s), "
            f"{len(self.warnings)} quality warning(s)"
        )
        if self.failures:
            self._print("\n  Structural failures block a clean Udemy upload:")
            for message in self.failures:
                self._print(f"    - {message}")
            return 1
        self._print("  Structure is sound. Quality warnings are tracked as issues.")
        return 0
