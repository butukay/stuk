"""Curses practice screen, optional keyboard, and a small settings panel."""

from __future__ import annotations

import curses
import time

from .adaptive import (
    adaptive_text,
    focus_letters,
    generate_practice_text,
    has_words,
    mastery,
    skills_for,
)
from .curriculum import curriculum_state
from .history import append_record, load_history, make_record
from .keyboard import KEYBOARD_WIDTH, key_positions, keyboard_rows, normalize_input
from .layout import arrange, wrap_text
from .letters import render_letters
from .palette import Palette
from .progress import render_progress
from .session import TypingSession
from .settings import Settings, clean_letters, save_settings
from .words import generate_text

COPY = {
    "ru": {
        "language": "русский",
        "ready": "начните печатать",
        "done": "готово",
        "room": "чуть больше места",
        "size": "нужно хотя бы 32 × 12",
        "next": "новый текст",
        "again": "дальше",
        "quit": "выход",
        "speed": "слов/мин",
        "accuracy": "точность",
        "settings": "настройки",
        "progress": "прогресс",
        "adaptive": "адаптивный текст",
        "practice_mode": "режим",
        "guided": "по этапам",
        "free": "все буквы",
        "custom": "свои буквы",
        "custom_letters": "свои буквы",
        "letters": "буквы",
        "new_letter": "открыта буква",
        "edit_title": "свои буквы",
        "edit_prompt": "буквы для практики",
        "edit_clear": "ctrl+u очистить",
        "edit_apply": "enter применить",
        "edit_cancel": "esc отмена",
        "edit_empty": "нужна хотя бы 1 буква",
        "focus": "фокус",
        "confident": "уверенно",
        "exercise": "упражнение",
        "record": "личный рекорд",
        "average": "к среднему",
        "history_error": "прогресс не сохранён",
        "theme": "палитра",
        "lavender": "лаванда",
        "terminal": "терминал",
        "warm": "песочная",
        "keyboard": "клавиатура",
        "show_keyboard": "показывать клавиатуру",
        "text_language": "язык текста",
        "switch_language": "язык",
        "word_count": "количество слов",
        "on": "вкл",
        "off": "выкл",
        "select": "↑↓ выбор   ←→ изменить",
        "back": "esc вернуться",
        "save_error": "не удалось сохранить настройки",
        "keyboard_room": "клавиатура: нужно 46 × 22",
    },
    "en": {
        "language": "english",
        "ready": "start typing",
        "done": "complete",
        "room": "a little more room",
        "size": "at least 32 × 12, please",
        "next": "new text",
        "again": "next",
        "quit": "quit",
        "speed": "wpm",
        "accuracy": "accuracy",
        "settings": "settings",
        "progress": "progress",
        "adaptive": "adaptive text",
        "practice_mode": "mode",
        "guided": "staged",
        "free": "all letters",
        "custom": "custom",
        "custom_letters": "custom letters",
        "letters": "letters",
        "new_letter": "letter unlocked",
        "edit_title": "custom letters",
        "edit_prompt": "letters to practice",
        "edit_clear": "ctrl+u clear",
        "edit_apply": "enter apply",
        "edit_cancel": "esc cancel",
        "edit_empty": "enter a letter",
        "focus": "focus",
        "confident": "confident",
        "exercise": "exercise",
        "record": "personal best",
        "average": "vs recent average",
        "history_error": "progress could not be saved",
        "theme": "palette",
        "lavender": "lavender",
        "terminal": "terminal",
        "warm": "warm",
        "keyboard": "keyboard",
        "show_keyboard": "show keyboard",
        "text_language": "text language",
        "switch_language": "language",
        "word_count": "word count",
        "on": "on",
        "off": "off",
        "select": "↑↓ select   ←→ change",
        "back": "esc back",
        "save_error": "could not save settings",
        "keyboard_room": "keyboard needs 46 × 22",
    },
}


class Trainer:
    def __init__(self, screen: curses.window, settings: Settings) -> None:
        self.screen = screen
        self.settings = settings
        self.history_error = False
        try:
            self.history = load_history()
        except OSError:
            self.history = []
            self.history_error = True
        self.focus: tuple[str, ...] = ()
        self.pending_records: list[dict] = []
        self.result_feedback = ""
        self.completed_record: dict | None = None
        self.new_passage()
        self.palette = Palette(settings.theme, settings.colors)
        self.settings_open = False
        self.progress_open = False
        self.progress_page = "graphs"
        self.letters_editing = False
        self.edit_buffer = ""
        self.edit_buffers: dict[str, str] = {}
        self.edit_error = False
        self.progress_language = settings.language
        self.selected_setting = 0
        self.save_failed = False

    @property
    def copy(self) -> dict[str, str]:
        return COPY[self.settings.language]

    def write(self, y: int, x: int, text: str, style: int) -> None:
        rows, columns = self.screen.getmaxyx()
        if y < 0 or y >= rows or x < 0 or x >= columns:
            return
        try:
            # The bottom-right cell reports an error even when drawing succeeds.
            limit = columns - x - (1 if y == rows - 1 else 0)
            self.screen.addnstr(y, x, text, max(0, limit), style)
        except curses.error:
            # A resize can land between getmaxyx() and addnstr().
            pass

    def frame(self, top: int, bottom: int, left: int, width: int, title: str) -> None:
        style = self.palette.faint
        self.write(top, left, "╭" + "─" * (width - 2) + "╮", style)
        self.write(bottom, left, "╰" + "─" * (width - 2) + "╯", style)
        for y in range(top + 1, bottom):
            self.write(y, left, "│", style)
            self.write(y, left + width - 1, "│", style)
        if title:
            self.write(top, left + 3, f" {title} ", self.palette.muted)

    def persist(self) -> None:
        try:
            save_settings(self.settings)
            self.save_failed = False
        except OSError:
            self.save_failed = True

    def new_passage(self) -> None:
        self.focus = ()
        language, words = self.settings.language, self.settings.words
        self.course = curriculum_state(self.history, language)
        self.allowed = None
        if self.settings.practice_mode == "guided":
            self.allowed = self.course.available
        elif self.settings.practice_mode == "custom":
            self.allowed = self.settings.custom_letters[language]
        self.drills = not has_words(language, self.allowed)
        if self.allowed is not None:
            target = None
            if (
                self.settings.practice_mode == "guided"
                and len(self.allowed) > 6
                and self.allowed[-1] not in self.course.mastered
            ):
                target = self.allowed[-1]
            passage, self.focus = generate_practice_text(
                language,
                words,
                self.history,
                allowed=self.allowed,
                adaptive=self.settings.adaptive,
                target=target,
            )
        elif self.settings.adaptive and focus_letters(
            skills_for(self.history, language)
        ):
            passage, self.focus = adaptive_text(language, words, self.history)
        else:
            passage = generate_text(language, words)
        self.session = TypingSession(passage)

    def fresh_text(self) -> None:
        self.completed_record = None
        self.result_feedback = ""
        self.new_passage()

    def record_completion(self) -> None:
        if not self.session.complete or self.completed_record is not None:
            return
        language, words = self.settings.language, self.settings.words
        previous = [row for row in self.history if row["language"] == language]
        before, _ = mastery(skills_for(self.history, language), language)
        course_before = curriculum_state(self.history, language)
        record = make_record(self.session, language, words)
        self.completed_record = record
        self.pending_records.append(record)
        self.history.append(record)
        self.flush_history()
        confident, total = mastery(skills_for(self.history, language), language)
        copy = self.copy
        confidence = f"{copy['confident']} {confident}/{total}"
        self.result_feedback = (
            f"{copy['exercise']} {len(previous) + 1}  ·  {confidence}"
        )
        comparable = [row for row in previous if row["words"] == words]
        if confident > before:
            self.result_feedback = f"{confidence}  (+{confident - before})"
        elif len(comparable) >= 3:
            if record["accuracy"] >= 90 and record["wpm"] > max(
                row["wpm"] for row in comparable
            ):
                self.result_feedback = f"{copy['record']}  ·  {confidence}"
            else:
                baseline = sum(row["wpm"] for row in comparable[-5:]) / len(
                    comparable[-5:]
                )
                delta = record["wpm"] - baseline
                self.result_feedback = (
                    f"{delta:+.0f} {copy['speed']} {copy['average']}  ·  {confidence}"
                )

        self.course = curriculum_state(self.history, language)
        opened = self.course.available[len(course_before.available) :]
        if opened:
            self.result_feedback = f"{copy['new_letter']}: {' '.join(opened)}"

    def flush_history(self) -> None:
        """Retry every pending record before clearing the persistence warning."""
        while self.pending_records:
            try:
                append_record(self.pending_records[0])
            except OSError:
                self.history_error = True
                return
            self.pending_records.pop(0)
            self.history_error = False

    def sync_pause(self) -> None:
        rows, columns = self.screen.getmaxyx()
        now = time.monotonic()
        if self.settings_open or self.progress_open or rows < 12 or columns < 32:
            self.session.pause(now)
        else:
            self.session.resume(now)

    def draw(self) -> None:
        screen, palette, copy = self.screen, self.palette, self.copy
        rows, columns = screen.getmaxyx()
        self.sync_pause()
        screen.erase()
        if rows < 12 or columns < 32:
            for y, message in (
                (max(0, rows // 2 - 1), copy["room"]),
                (rows // 2 + 1, copy["size"]),
            ):
                self.write(
                    y, max(0, (columns - len(message)) // 2), message, palette.muted
                )
            screen.refresh()
            return
        if self.settings_open:
            if self.letters_editing:
                self.draw_letter_editor()
            else:
                self.draw_settings()
            screen.refresh()
            return
        if self.progress_open:
            if self.progress_page == "letters":
                segments = render_letters(
                    self.history,
                    self.progress_language,
                    rows,
                    columns,
                    practice_mode=self.settings.practice_mode,
                    custom_letters=self.settings.custom_letters[self.progress_language],
                    error=self.history_error,
                )
            else:
                segments = render_progress(
                    self.history,
                    self.progress_language,
                    rows,
                    columns,
                    error=self.history_error,
                )
            for segment in segments:
                self.write(
                    segment.y, segment.x, segment.text, getattr(palette, segment.role)
                )
            screen.refresh()
            return

        show_keyboard = self.settings.show_keyboard and columns >= 46 and rows >= 22
        width = min(68, columns - 8)
        lines = wrap_text(self.session.text, width)
        layout = arrange(rows, columns, lines, self.session.position, show_keyboard)
        x = layout.left
        title = f"{copy['language']}  /  {self.settings.words}"
        if self.settings.practice_mode == "guided":
            stage = f" · {len(self.course.available)}/{self.course.total}"
        elif self.drills:
            stage = f" · {copy['letters']}"
        else:
            stage = ""
        if len(title + stage) + 2 <= width:
            title += stage
        focus_label = f"  ·  {copy['focus']}: {' '.join(self.focus)}"
        if self.focus and len(title + focus_label) + 2 <= width:
            title += focus_label
        self.frame(layout.header_y, layout.frame_bottom, x - 3, width + 6, title)

        for row, line in enumerate(
            lines[layout.first_line : layout.first_line + layout.visible_lines]
        ):
            y = layout.text_y + row * layout.spacing
            for column, character in enumerate(line.text):
                index = line.start + column
                style = palette.future
                if index < self.session.position:
                    if self.session.typed[index] == character:
                        style = palette.ink
                    else:
                        style = palette.error
                        if character == " ":
                            character = "·"
                elif index == self.session.position and not self.session.complete:
                    style = palette.cursor
                    if character == " ":
                        character = "·"
                self.write(y, x + column, character, style)

        progress = int(width * self.session.position / len(self.session.text))
        self.write(layout.progress_y, x, "─" * width, palette.faint)
        if progress:
            self.write(layout.progress_y, x, "─" * progress, palette.accent)
        if self.session.complete:
            self.draw_results(layout.status_y, x, width)
        else:
            status = copy["ready"] if self.session.started_at is None else ""
            if self.settings.show_keyboard and not show_keyboard:
                status = copy["keyboard_room"]
            if self.save_failed:
                status = copy["save_error"]
            self.write(layout.status_y, x, status[:width], palette.muted)
            completed = self.session.text[: self.session.position].count(" ")
            count = f"{completed:02} / {self.settings.words}"
            if width >= len(status) + len(count) + 3:
                self.write(
                    layout.status_y, x + width - len(count), count, palette.muted
                )
        if layout.keyboard_y is not None:
            self.draw_keyboard(layout.keyboard_y, columns)
        self.draw_footer(layout.footer_y, x, width)
        screen.refresh()

    def draw_keyboard(self, y: int, columns: int) -> None:
        x = (columns - KEYBOARD_WIDTH) // 2
        for row, text in enumerate(keyboard_rows(self.settings.language)):
            self.write(
                y + row,
                x,
                text,
                self.palette.faint if self.allowed is not None else self.palette.muted,
            )
        if self.allowed is not None:
            for letter in self.allowed:
                row, column = key_positions(self.settings.language)[letter]
                self.write(y + row, x + column, letter, self.palette.ink)
        if not self.session.complete:
            character = self.session.text[self.session.position]
            position = key_positions(self.settings.language).get(character)
            if position is not None:
                row, column = position
                self.write(y + row, x + column, character, self.palette.cursor)

    def draw_results(self, y: int, x: int, width: int) -> None:
        copy, palette = self.copy, self.palette
        speed = f"{self.session.wpm(time.monotonic()):.0f} {copy['speed']}"
        accuracy = f"{self.session.accuracy:.0f}%"
        if width >= 48:
            accuracy += f" {copy['accuracy']}"
        self.write(y, x, f"{speed}   ·   {accuracy}"[:width], palette.accent)
        rows, _ = self.screen.getmaxyx()
        feedback = copy["history_error"] if self.history_error else self.result_feedback
        if y + 1 < rows - 2:
            self.write(
                y + 1,
                x,
                feedback[:width],
                palette.error if self.history_error else palette.muted,
            )
        elif self.history_error:
            self.write(y - 1, x, feedback[:width], palette.error)

    def draw_footer(self, y: int, x: int, width: int) -> None:
        copy, palette = self.copy, self.palette
        label = copy["again"] if self.session.complete else copy["next"]
        parts = [
            ("esc", copy["quit"]),
            ("tab", label),
            ("F2", copy["settings"]),
            ("F3", copy["progress"]),
            ("F4", copy["switch_language"]),
        ]
        length = sum(len(key) + len(label) + 1 for key, label in parts) + 3 * (
            len(parts) - 1
        )
        if length > width:
            self.write(y, x, "esc  tab  F2  F3  F4", palette.muted)
            return
        for key, label in parts:
            self.write(y, x, key, palette.ink)
            x += len(key) + 1
            self.write(y, x, label, palette.muted)
            x += len(label) + 3

    def draw_settings(self) -> None:
        rows, columns = self.screen.getmaxyx()
        width = min(58, columns - 2)
        left = (columns - width) // 2
        panel_height = 15 if rows >= 16 else 12
        top = max(0, (rows - panel_height) // 2)
        bottom = top + panel_height - 1
        copy, palette = self.copy, self.palette
        self.frame(top, bottom, left, width, copy["settings"])
        options = (
            (
                copy["show_keyboard"] if width >= 40 else copy["keyboard"],
                copy["on"] if self.settings.show_keyboard else copy["off"],
            ),
            (copy["text_language"], copy["language"]),
            (copy["word_count"], str(self.settings.words)),
            (copy["theme"], copy[self.settings.theme]),
            (copy["adaptive"], copy["on"] if self.settings.adaptive else copy["off"]),
            (copy["practice_mode"], copy[self.settings.practice_mode]),
            (copy["custom_letters"], "enter"),
        )
        visible = 7 if rows >= 16 else 5
        first = max(
            0, min(self.selected_setting - visible // 2, len(options) - visible)
        )
        for row, (label, value) in enumerate(options[first : first + visible]):
            index = first + row
            selected = index == self.selected_setting
            marker = "›" if selected else " "
            style = palette.accent if selected else palette.ink
            y = top + 2 + row
            self.write(y, left + 2, marker, style)
            self.write(y, left + 4, label, style)
            self.write(y, left + width - len(value) - 3, value, style)
        if visible < len(options):
            position = f" {self.selected_setting + 1}/{len(options)} "
            self.write(top, left + width - len(position) - 3, position, palette.muted)
        self.write(bottom - 3, left + 4, copy["select"], palette.muted)
        self.write(bottom - 2, left + 4, copy["back"], palette.muted)
        if self.save_failed:
            self.write(
                rows - 1,
                max(0, (columns - len(copy["save_error"])) // 2),
                copy["save_error"],
                palette.error,
            )

    def change_setting(self, direction: int = 1) -> None:
        if self.selected_setting == 0:
            self.settings.show_keyboard = not self.settings.show_keyboard
        elif self.selected_setting == 1:
            self.settings.language = "en" if self.settings.language == "ru" else "ru"
            self.fresh_text()
        elif self.selected_setting == 2:
            options = (10, 25, 50)
            value = self.settings.words
            if value in options:
                self.settings.words = options[
                    (options.index(value) + direction) % len(options)
                ]
            else:
                self.settings.words = 25
            self.fresh_text()
        elif self.selected_setting == 3:
            themes = ("lavender", "terminal", "warm")
            self.settings.theme = themes[
                (themes.index(self.settings.theme) + direction) % len(themes)
            ]
            self.palette.apply(self.settings.theme, self.settings.colors)
            self.screen.bkgd(" ", self.palette.background)
            self.screen.clearok(True)
        elif self.selected_setting == 4:
            self.settings.adaptive = not self.settings.adaptive
            self.fresh_text()
        elif self.selected_setting == 5:
            modes = ("guided", "free", "custom")
            self.settings.practice_mode = modes[
                (modes.index(self.settings.practice_mode) + direction) % len(modes)
            ]
            self.fresh_text()
        else:
            self.letters_editing = True
            self.edit_buffer = self.settings.custom_letters[self.settings.language]
            self.edit_buffers = {self.settings.language: self.edit_buffer}
            self.edit_error = False
            return
        self.persist()

    def draw_letter_editor(self) -> None:
        rows, columns = self.screen.getmaxyx()
        width = min(58, columns - 2)
        left = (columns - width) // 2
        top = max(0, (rows - 12) // 2)
        copy, palette = self.copy, self.palette
        self.frame(
            top, top + 11, left, width, f"{copy['edit_title']} · {copy['language']}"
        )
        field_width = width - 8
        self.write(top + 2, left + 4, copy["edit_prompt"][:field_width], palette.muted)
        shown = self.edit_buffer[-(field_width - 1) :]
        self.write(top + 4, left + 4, shown, palette.ink)
        self.write(top + 4, left + 4 + len(shown), " ", palette.cursor)
        self.write(top + 6, left + 4, copy["edit_clear"][:field_width], palette.muted)
        if self.edit_error:
            self.write(
                top + 7, left + 4, copy["edit_empty"][:field_width], palette.error
            )
        self.write(top + 8, left + 4, copy["edit_apply"][:field_width], palette.muted)
        self.write(top + 9, left + 4, copy["edit_cancel"][:field_width], palette.muted)

    def edit_letters(self, key: str | int) -> None:
        if key == "\x1b":
            self.letters_editing = False
        elif key in ("\n", "\r", curses.KEY_ENTER):
            letters = clean_letters(self.edit_buffer, self.settings.language)
            if not letters:
                self.edit_error = True
                return
            self.settings.custom_letters[self.settings.language] = letters
            self.settings.practice_mode = "custom"
            self.letters_editing = False
            self.fresh_text()
            self.persist()
        elif key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            self.edit_buffer = self.edit_buffer[:-1]
            self.edit_error = False
        elif key == "\x15":
            self.edit_buffer = ""
            self.edit_error = False
        elif isinstance(key, str):
            letter = clean_letters(
                normalize_input(key, self.settings.language), self.settings.language
            )
            if letter and letter not in self.edit_buffer:
                self.edit_buffer += letter
                self.edit_error = False

    def switch_language(self) -> None:
        if self.progress_open:
            self.progress_language = "en" if self.progress_language == "ru" else "ru"
        else:
            if self.letters_editing:
                self.edit_buffers[self.settings.language] = self.edit_buffer
            self.settings.language = "en" if self.settings.language == "ru" else "ru"
            if self.letters_editing:
                self.edit_buffer = self.edit_buffers.get(
                    self.settings.language,
                    self.settings.custom_letters[self.settings.language],
                )
                self.edit_error = False
            self.persist()
            self.fresh_text()
        self.sync_pause()

    def handle_key(self, key: str | int) -> bool:
        if key in ("\x03", "\x04"):
            return False
        if key == curses.KEY_RESIZE:
            self.sync_pause()
            return True
        if key in (curses.KEY_F2, "\x0f"):
            self.settings_open = not self.settings_open
            self.letters_editing = False
            self.progress_open = False
            self.sync_pause()
            return True
        if key in (curses.KEY_F3, "\x10"):
            self.progress_open = not self.progress_open
            self.settings_open = False
            self.letters_editing = False
            if self.progress_open:
                self.progress_language = self.settings.language
                self.flush_history()
            self.sync_pause()
            return True
        if key in (curses.KEY_F4, "\x0c"):
            self.switch_language()
            return True
        if self.progress_open:
            if key == "\x1b":
                self.progress_open = False
            elif key in (curses.KEY_UP, curses.KEY_DOWN):
                self.progress_page = (
                    "letters" if self.progress_page == "graphs" else "graphs"
                )
            elif key in ("l", "д"):
                self.progress_page = "letters"
            elif key in ("g", "п"):
                self.progress_page = "graphs"
            elif key in ("\t", curses.KEY_LEFT, curses.KEY_RIGHT):
                self.progress_language = (
                    "en" if self.progress_language == "ru" else "ru"
                )
            self.sync_pause()
            return True
        if self.settings_open:
            if self.letters_editing:
                self.edit_letters(key)
                self.sync_pause()
                return True
            if key == "\x1b":
                self.settings_open = False
            elif key in (curses.KEY_UP, "k", "л"):
                self.selected_setting = (self.selected_setting - 1) % 7
            elif key in (curses.KEY_DOWN, "j", "о", "\t"):
                self.selected_setting = (self.selected_setting + 1) % 7
            elif key == curses.KEY_LEFT:
                self.change_setting(-1)
            elif key in (curses.KEY_RIGHT, "\n", "\r", curses.KEY_ENTER, " "):
                self.change_setting()
            self.sync_pause()
            return True
        if key == "\x1b":
            return False
        self.sync_pause()
        if key == "\x0b":
            self.settings.show_keyboard = not self.settings.show_keyboard
            self.persist()
        elif key == "\t" or (
            self.session.complete and key in ("\n", "\r", curses.KEY_ENTER)
        ):
            self.fresh_text()
        elif self.screen.getmaxyx()[0] < 12 or self.screen.getmaxyx()[1] < 32:
            pass
        elif key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            self.session.backspace()
        elif key == "\x17":
            self.session.delete_word()
        elif isinstance(key, str):
            self.session.input(
                normalize_input(key, self.settings.language), time.monotonic()
            )
            self.record_completion()
        return True


def run(screen: curses.window, settings: Settings) -> None:
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    curses.set_escdelay(25)
    screen.keypad(True)
    screen.timeout(500)
    trainer = Trainer(screen, settings)
    try:
        screen.bkgd(" ", trainer.palette.background)
        dirty = True
        while True:
            if dirty:
                trainer.draw()
            try:
                key = screen.get_wch()
            except curses.error:
                dirty = False
                continue
            if not trainer.handle_key(key):
                break
            dirty = True
    finally:
        try:
            trainer.flush_history()
        finally:
            trainer.palette.close()
