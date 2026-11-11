"""Compact, terminal-independent physical keyboard layouts."""

from __future__ import annotations

KEYBOARD_WIDTH = 38
KEYBOARD_HEIGHT = 5

_LAYOUTS = {
    "en": ("`1234567890-=", "qwertyuiop[]\\", "asdfghjkl;'", "zxcvbnm,./"),
    "ru": ("ё1234567890-=", "йцукенгшщзхъ\\", "фывапролджэ", "ячсмитьбю."),
}
_SPACEBAR = "[          ]"
_SPACEBAR_COLUMN = (KEYBOARD_WIDTH - len(_SPACEBAR)) // 2
_SHIFTED_KEYS = dict(zip("`[];',.", '~{}:"<>'))


def _input_maps() -> dict[str, dict[str, str]]:
    """Build both directions from the same physical keys used by the display."""
    maps: dict[str, dict[str, str]] = {"ru": {}, "en": {}}
    for english_row, russian_row in zip(_LAYOUTS["en"], _LAYOUTS["ru"]):
        for english, russian in zip(english_row, russian_row):
            if not (english.isalpha() or russian.isalpha()):
                continue
            shifted_english = (
                english.upper() if english.isalpha() else _SHIFTED_KEYS[english]
            )
            shifted_russian = russian.upper()
            maps["ru"][english] = russian
            maps["ru"][shifted_english] = shifted_russian
            maps["en"][russian] = english
            maps["en"][shifted_russian] = shifted_english
    return maps


_INPUT_MAPS = _input_maps()


def normalize_input(character: str, language: str) -> str:
    """Interpret a single key as RU/EN while preserving case and actual mistakes.

    Terminal input exposes characters rather than physical key codes. Convert
    the other script and its letter-producing punctuation keys; native letters,
    controls, spaces, and other characters pass through unchanged.
    """
    if language not in _INPUT_MAPS:
        raise ValueError("language must be 'ru' or 'en'")
    if len(character) != 1:
        return character
    return _INPUT_MAPS[language].get(character, character)


def _layout(language: str) -> tuple[str, ...]:
    try:
        return _LAYOUTS[language]
    except KeyError as error:
        raise ValueError("language must be 'ru' or 'en'") from error


def keyboard_rows(language: str) -> tuple[str, ...]:
    """Return five equally wide rows; every glyph occupies one terminal cell."""
    rows = tuple(
        (" " * index + "  ".join(keys)).ljust(KEYBOARD_WIDTH)
        for index, keys in enumerate(_layout(language))
    )
    spacebar = (" " * _SPACEBAR_COLUMN + _SPACEBAR).ljust(KEYBOARD_WIDTH)
    return (*rows, spacebar)


def key_positions(language: str) -> dict[str, tuple[int, int]]:
    """Map physical key labels to cells, including a dedicated spacebar cell."""
    positions = {
        key: (row, row + column * 3)
        for row, keys in enumerate(_layout(language))
        for column, key in enumerate(keys)
    }
    positions[" "] = (KEYBOARD_HEIGHT - 1, KEYBOARD_WIDTH // 2)
    return positions
