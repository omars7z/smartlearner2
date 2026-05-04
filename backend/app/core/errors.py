class LessonLockedError(Exception):
    """Raised when syllabus progression blocks access to a lesson."""

    default_message = "Lesson locked. Complete previous lesson first."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)
