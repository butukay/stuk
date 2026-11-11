"""Validated local exercise history with locked, atomic updates."""

from __future__ import annotations

import fcntl
import json
import math
import os
import tempfile
import time
from contextlib import contextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Iterator
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from .session import TypingSession


class HistoryError(OSError):
    """History could not be decoded safely; existing data must be preserved."""


def history_path() -> Path:
    """Resolve an absolute XDG data directory, falling back to the user's home."""
    configured = os.environ.get("XDG_DATA_HOME", "")
    directory = Path(configured) if configured else Path.home() / ".local" / "share"
    if not directory.is_absolute():
        directory = Path.home() / ".local" / "share"
    return directory / "stuk" / "history.json"


def _number(value: object, maximum: float = math.inf) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) and 0 <= number <= maximum else None


def _integer(value: object, minimum: int, maximum: int | None = None) -> bool:
    return (
        type(value) is int
        and value >= minimum
        and (maximum is None or value <= maximum)
    )


def _validated_record(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    identifier, date = value.get("id"), value.get("date")
    if not isinstance(identifier, str) or not isinstance(date, str):
        return None
    try:
        identifier = str(UUID(identifier))
        timestamp = datetime.fromisoformat(
            date[:-1] + "+00:00" if date.endswith("Z") else date
        )
        if timestamp.utcoffset() != timedelta(0):
            return None
    except (ValueError, OverflowError):
        return None
    language, words = value.get("language"), value.get("words")
    attempts, mistakes = value.get("attempts"), value.get("mistakes")
    duration = _number(value.get("duration"))
    wpm = _number(value.get("wpm"))
    accuracy = _number(value.get("accuracy"), 100)
    if (
        language not in ("ru", "en")
        or not _integer(words, 1, 60)
        or not _integer(attempts, 1)
        or not _integer(mistakes, 0, attempts)
        or duration is None
        or wpm is None
        or accuracy is None
    ):
        return None
    keys = value.get("keys")
    if not isinstance(keys, dict):
        return None
    validated_keys = {}
    for key, statistics in keys.items():
        if (
            not isinstance(key, str)
            or len(key) != 1
            or not key.isalpha()
            or not key.islower()
            or not isinstance(statistics, dict)
        ):
            return None
        key_attempts = statistics.get("attempts")
        key_mistakes = statistics.get("mistakes")
        interval_total = _number(statistics.get("interval_total"))
        interval_count = statistics.get("interval_count")
        if (
            not _integer(key_attempts, 1, attempts)
            or not _integer(key_mistakes, 0, key_attempts)
            or not _integer(interval_count, 0, key_attempts)
            or interval_total is None
        ):
            return None
        validated_keys[key] = {
            "attempts": key_attempts,
            "mistakes": key_mistakes,
            "interval_total": interval_total,
            "interval_count": interval_count,
        }
    return {
        "id": identifier,
        "date": timestamp.isoformat(timespec="microseconds"),
        "language": language,
        "words": words,
        "duration": duration,
        "wpm": wpm,
        "accuracy": accuracy,
        "attempts": attempts,
        "mistakes": mistakes,
        "keys": validated_keys,
    }


def load_history(path: Path | None = None) -> list[dict]:
    """Return valid records oldest first; reject damaged documents without writes."""
    target = history_path() if path is None else Path(path)
    try:
        with target.open(encoding="utf-8") as source:
            document = json.load(source)
    except FileNotFoundError:
        return []
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise HistoryError(f"History is damaged: {target}") from error
    if (
        not isinstance(document, dict)
        or type(document.get("version")) is not int
        or document["version"] != 1
        or not isinstance(document.get("sessions"), list)
    ):
        raise HistoryError(f"Unsupported history format: {target}")
    records = []
    identifiers = set()
    for value in document["sessions"]:
        record = _validated_record(value)
        if record is not None and record["id"] not in identifiers:
            records.append(record)
            identifiers.add(record["id"])
    return sorted(records, key=lambda record: record["date"])


def make_record(
    session: TypingSession,
    language: str,
    words: int,
    *,
    now: float | None = None,
    date: datetime | None = None,
) -> dict:
    """Build a completed exercise record in memory, including corrected mistakes."""
    if not session.complete:
        raise ValueError("Only completed exercises can be recorded.")
    if language not in ("ru", "en") or not _integer(words, 1, 60):
        raise ValueError("Use language ru/en and a word count from 1 to 60.")
    now = time.monotonic() if now is None else now
    date = datetime.now(timezone.utc) if date is None else date
    if date.utcoffset() is None:
        raise ValueError("The record date must include a timezone.")
    keys = {}
    for stroke in session.keystrokes:
        key = stroke.expected
        if len(key) != 1 or not key.isalpha() or not key.islower():
            continue
        statistics = keys.setdefault(
            key,
            {"attempts": 0, "mistakes": 0, "interval_total": 0.0, "interval_count": 0},
        )
        statistics["attempts"] += 1
        statistics["mistakes"] += int(not stroke.correct)
        interval = _number(stroke.interval)
        if interval is not None:
            statistics["interval_total"] += interval
            statistics["interval_count"] += 1
    record = _validated_record(
        {
            "id": str(uuid4()),
            "date": date.astimezone(timezone.utc).isoformat(timespec="microseconds"),
            "language": language,
            "words": words,
            "duration": session.elapsed(now),
            "wpm": session.wpm(now),
            "accuracy": session.accuracy,
            "attempts": session.attempts,
            "mistakes": session.mistakes,
            "keys": keys,
        }
    )
    if record is None:
        raise ValueError("The exercise contains invalid statistics.")
    return record


def _private_directories(directory: Path) -> None:
    missing = [
        candidate
        for candidate in (directory, *directory.parents)
        if not candidate.exists()
    ]
    for candidate in reversed(missing):
        candidate.mkdir(mode=0o700, exist_ok=True)


@contextmanager
def _history_lock(directory: Path) -> Iterator[None]:
    descriptor = os.open(directory / ".history.lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _write_history(target: Path, records: list[dict]) -> None:
    descriptor, temporary = tempfile.mkstemp(
        prefix=".history-", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            json.dump(
                {"version": 1, "sessions": records},
                destination,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            )
            destination.write("\n")
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, target)
    finally:
        with suppress(OSError):
            os.unlink(temporary)


def append_record(record: dict, path: Path | None = None) -> None:
    """Append once by UUID under a process lock, preserving history on failure."""
    validated = _validated_record(record)
    if validated is None:
        raise ValueError("Invalid history record.")
    target = history_path() if path is None else Path(path)
    _private_directories(target.parent)
    with _history_lock(target.parent):
        records = load_history(target)
        if any(existing["id"] == validated["id"] for existing in records):
            return
        records.append(validated)
        records.sort(key=lambda existing: existing["date"])
        _write_history(target, records)


def save_session(
    session: TypingSession,
    language: str,
    words: int,
    path: Path | None = None,
) -> dict:
    """Build and persist one finished exercise, returning the stored record."""
    record = make_record(session, language, words)
    append_record(record, path)
    return record
