"""Small, terminal-independent state machine for a typing session."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Keystroke:
    """An accepted key, including mistakes that are subsequently corrected."""

    expected: str
    correct: bool
    interval: float | None


@dataclass
class TypingSession:
    """Track a passage, edits, and the timing of accepted keystrokes."""

    text: str
    typed: str = field(default="", init=False)
    attempts: int = field(default=0, init=False)
    mistakes: int = field(default=0, init=False)
    started_at: float | None = field(default=None, init=False)
    finished_at: float | None = field(default=None, init=False)
    keystrokes: list[Keystroke] = field(default_factory=list, init=False)
    _paused_at: float | None = field(default=None, init=False, repr=False)
    _paused_duration: float = field(default=0.0, init=False, repr=False)
    _last_input_at: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.text, str)
            or not self.text
            or not self.text.isprintable()
        ):
            raise ValueError("A passage must contain printable text.")

    @property
    def position(self) -> int:
        return len(self.typed)

    @property
    def complete(self) -> bool:
        return self.position == len(self.text)

    @property
    def accuracy(self) -> float:
        """Percentage of correct keystrokes, including subsequently fixed mistakes."""
        if not self.attempts:
            return 100.0
        return (self.attempts - self.mistakes) / self.attempts * 100

    def input(self, character: str, now: float) -> bool:
        """Accept a printable character and advance, even when it is incorrect."""
        if (
            self.complete
            or self._paused_at is not None
            or len(character) != 1
            or not character.isprintable()
        ):
            return False
        if self.started_at is None:
            self.started_at = now
        expected = self.text[self.position]
        interval = None
        if self._last_input_at is not None:
            difference = now - self._last_input_at
            if 0 < difference <= 3:
                interval = difference
        self.keystrokes.append(Keystroke(expected, character == expected, interval))
        self._last_input_at = now
        self.attempts += 1
        if character != expected:
            self.mistakes += 1
        self.typed += character
        if self.complete:
            self.finished_at = now
        return True

    def backspace(self) -> bool:
        """Remove the previous character without erasing keystroke history."""
        if self.complete or self._paused_at is not None or not self.typed:
            return False
        self.typed = self.typed[:-1]
        return True

    def delete_word(self) -> bool:
        """Remove trailing spaces and the previous word, as Ctrl+W does in a shell."""
        if self.complete or self._paused_at is not None or not self.typed:
            return False
        end = len(self.typed.rstrip(" "))
        start = self.typed.rfind(" ", 0, end) + 1
        self.typed = self.typed[:start]
        return True

    def pause(self, now: float) -> None:
        """Freeze a running session without changing its original start time."""
        if (
            self.started_at is not None
            and not self.complete
            and self._paused_at is None
        ):
            self._paused_at = now

    def resume(self, now: float) -> None:
        """Exclude the pause from elapsed practice time and allow input again."""
        if self._paused_at is not None:
            self._paused_duration += max(0.0, now - self._paused_at)
            self._paused_at = None
            self._last_input_at = None

    def elapsed(self, now: float) -> float:
        """Return active seconds, excluding pauses and frozen after completion."""
        if self.started_at is None:
            return 0.0
        end = self.finished_at if self.finished_at is not None else now
        if self._paused_at is not None:
            end = self._paused_at
        return max(0.0, end - self.started_at - self._paused_duration)

    def wpm(self, now: float) -> float:
        """Return correct current characters per minute, divided into five-char words."""
        duration = self.elapsed(now)
        if not duration:
            return 0.0
        correct = sum(
            actual == expected for actual, expected in zip(self.typed, self.text)
        )
        return correct / 5 / duration * 60
