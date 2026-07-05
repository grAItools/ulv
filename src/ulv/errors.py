"""User-facing errors.

`UlvError` is the single error type the CLI maps to a diagnostic message
and a non-zero exit; everything else propagating out of ulv code is a bug.
"""


class UlvError(Exception):
    """A user-actionable failure.

    `offending_input` names the file, URL, or setting that caused the
    failure so diagnostics can point at it (spec: malformed input must be
    identified, never silently mis-parsed or dropped).
    """

    def __init__(self, message: str, *, offending_input: str | None = None):
        super().__init__(message)
        self.message = message
        self.offending_input = offending_input

    def __str__(self) -> str:
        if self.offending_input is not None:
            return f"{self.message} [input: {self.offending_input}]"
        return self.message
