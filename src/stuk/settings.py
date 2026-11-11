"""Small, local preferences with tolerant reads and atomic writes."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .adaptive import ALPHABETS
from .curriculum import ORDERS
from .theme import COLOR_KEYS, THEMES, valid_color


@dataclass
class Settings:
    language: str = "ru"
    words: int = 25
    show_keyboard: bool = False
    adaptive: bool = True
    practice_mode: str = "guided"
    custom_letters: dict[str, str] = field(
        default_factory=lambda: {
            language: order[:6] for language, order in ORDERS.items()
        }
    )
    theme: str = "lavender"
    colors: dict[str, str | int] = field(default_factory=dict)


def clean_letters(value: str, language: str) -> str:
    """Keep unique letters of the chosen language, preserving the user's order."""
    return "".join(
        dict.fromkeys(
            letter for letter in value.lower() if letter in ALPHABETS[language]
        )
    )


def config_path() -> Path:
    """Use an absolute XDG config directory, or the user's standard fallback."""
    configured = os.environ.get("XDG_CONFIG_HOME", "")
    directory = Path(configured) if configured else Path.home() / ".config"
    if not directory.is_absolute():
        directory = Path.home() / ".config"
    return directory / "stuk" / "settings.json"


def load_settings(path: Path | None = None) -> Settings:
    """Load valid fields independently; absent or damaged preferences are harmless."""
    target = config_path() if path is None else Path(path)
    defaults = Settings()
    try:
        with target.open(encoding="utf-8") as source:
            values = json.load(source)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return defaults
    if not isinstance(values, dict):
        return defaults
    language = values.get("language")
    words = values.get("words")
    show_keyboard = values.get("show_keyboard")
    adaptive = values.get("adaptive")
    practice_mode = values.get("practice_mode")
    custom_letters = values.get("custom_letters")
    theme = values.get("theme")
    colors = values.get("colors")
    if isinstance(language, str) and language in ("ru", "en"):
        defaults.language = language
    if type(words) is int and 1 <= words <= 60:
        defaults.words = words
    if type(show_keyboard) is bool:
        defaults.show_keyboard = show_keyboard
    if type(adaptive) is bool:
        defaults.adaptive = adaptive
    if isinstance(practice_mode, str) and practice_mode in ("guided", "free", "custom"):
        defaults.practice_mode = practice_mode
    if isinstance(custom_letters, dict):
        for language in ALPHABETS:
            value = custom_letters.get(language)
            if isinstance(value, str):
                letters = clean_letters(value, language)
                if letters:
                    defaults.custom_letters[language] = letters
    if isinstance(theme, str) and theme in THEMES:
        defaults.theme = theme
    if isinstance(colors, dict):
        defaults.colors = {
            key: value
            for key, value in colors.items()
            if key in COLOR_KEYS and valid_color(value)
        }
    return defaults


def save_settings(settings: Settings, path: Path | None = None) -> None:
    """Replace the settings file atomically; leave existing data intact on failure."""
    target = config_path() if path is None else Path(path)
    missing = [
        directory
        for directory in (target.parent, *target.parent.parents)
        if not directory.exists()
    ]
    for directory in reversed(missing):
        directory.mkdir(mode=0o700, exist_ok=True)

    descriptor, temporary = tempfile.mkstemp(
        prefix=".settings-", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            json.dump(asdict(settings), destination, ensure_ascii=False, indent=2)
            destination.write("\n")
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, target)
    finally:
        with suppress(OSError):
            os.unlink(temporary)
