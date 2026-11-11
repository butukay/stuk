"""Exercise the real curses application through a Unix pseudoterminal."""

from __future__ import annotations

import errno
import json
import os
import re
import select
import signal
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

if os.name == "posix":
    import fcntl
    import pty
    import termios


ROOT = Path(__file__).resolve().parents[1]
PALETTE_COMMAND = re.compile(
    rb"\x1b\]4;(\d+);rgb:([0-9A-Fa-f]+)/([0-9A-Fa-f]+)/([0-9A-Fa-f]+)(?:\x1b\\|\x07)"
)


def palette_updates(output: bytes) -> dict[int, list[tuple[int, int, int]]]:
    """Read real OSC4 palette changes, normalized to eight-bit channels."""
    updates: dict[int, list[tuple[int, int, int]]] = {}
    for index, *channels in PALETTE_COMMAND.findall(output):
        rgb = tuple(
            round(int(channel, 16) * 255 / (16 ** len(channel) - 1))
            for channel in channels
        )
        updates.setdefault(int(index), []).append(rgb)
    return updates


def fixed_passage_code(
    text: str, *, language: str = "ru", english_text: str | None = None
) -> str:
    """Keep end-to-end exercises reproducible without an application test mode."""
    targets = {"ru": text, "en": text if english_text is None else english_text}
    words = len(targets[language].split())
    return f"""
from unittest.mock import patch
from stuk.cli import main
from stuk.settings import load_settings

targets = {targets!r}
settings = load_settings()
settings.language = {language!r}
settings.practice_mode = 'free'
patch('stuk.cli.load_settings', return_value=settings).start()
def plain(language, *args, **kwargs):
    return targets[language]
def focused(language, *args, **kwargs):
    return targets[language], ()
patch('stuk.tui.generate_text', side_effect=plain).start()
patch('stuk.tui.adaptive_text', side_effect=focused, create=True).start()
patch('stuk.tui.generate_practice_text', side_effect=focused, create=True).start()
raise SystemExit(main(['--words', {str(words)!r}]))
"""


def capture_passage_code() -> str:
    """Observe genuine generated passages without adding production test hooks."""
    return (
        "import os\n"
        "from pathlib import Path\n"
        "from stuk.cli import main\n"
        "from stuk import tui\n"
        "session_type = tui.TypingSession\n"
        "def capture(text):\n"
        "    Path(os.environ['STUK_TEST_PASSAGE']).write_text(text, encoding='utf-8')\n"
        "    return session_type(text)\n"
        "tui.TypingSession = capture\n"
        "raise SystemExit(main())\n"
    )


def seed_history(directory: Path, plans: list[tuple[str, float, int]]) -> Path:
    """Create explicit demo/test data through the same validated history API."""
    from stuk.history import append_record, make_record
    from stuk.session import TypingSession

    target = directory / "stuk/history.json"
    for serial, (language, speed, mistakes) in enumerate(plans):
        text = " ".join(["кот" if language == "ru" else "cat"] * 25)
        session = TypingSession(text)
        duration = (len(text) - mistakes) * 12 / speed
        for index, character in enumerate(text):
            actual = "x" if index < mistakes else character
            session.input(actual, index * duration / (len(text) - 1))
        record = make_record(
            session,
            language,
            25,
            now=duration,
            date=datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
            + timedelta(days=serial),
        )
        append_record(record, target)
    return target


def _claim_terminal() -> None:
    """Give the child a controlling TTY so Ctrl+C behaves as in a shell."""
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)


class TerminalProcess:
    def __init__(
        self,
        *arguments: str,
        env: dict[str, str] | None = None,
        code: str | None = None,
        size: tuple[int, int] = (80, 24),
    ) -> None:
        self.config_directory = tempfile.TemporaryDirectory(
            prefix="stuk-terminal-test-"
        )
        self.master, self.slave = pty.openpty()
        self.initial_attributes = termios.tcgetattr(self.slave)
        self.resize(*size, notify=False)
        environment = os.environ.copy()
        environment.update(
            TERM="xterm-256color",
            LANG="C.UTF-8",
            LC_ALL="C.UTF-8",
            PYTHONPATH=str(ROOT / "src"),
            XDG_CONFIG_HOME=self.config_directory.name,
            XDG_DATA_HOME=str(Path(self.config_directory.name) / "data"),
        )
        environment.update(env or {})
        command = (
            [sys.executable, "-c", code]
            if code
            else [
                sys.executable,
                "-m",
                "stuk",
                *arguments,
            ]
        )
        self.process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=environment,
            stdin=self.slave,
            stdout=self.slave,
            stderr=self.slave,
            start_new_session=True,
            preexec_fn=_claim_terminal,
        )
        self.output = bytearray()

    def __enter__(self) -> TerminalProcess:
        return self

    def __exit__(self, *_: object) -> None:
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=3)
        os.close(self.master)
        os.close(self.slave)
        self.config_directory.cleanup()

    def resize(self, columns: int, rows: int, *, notify: bool = True) -> None:
        size = struct.pack("HHHH", rows, columns, 0, 0)
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, size)
        if notify:
            self.process.send_signal(signal.SIGWINCH)

    def send(self, text: str) -> None:
        os.write(self.master, text.encode("utf-8"))

    def history(self) -> list[dict]:
        target = Path(self.config_directory.name) / "data/stuk/history.json"
        return json.loads(target.read_text())["sessions"] if target.exists() else []

    def read(self, seconds: float = 0.2) -> str:
        deadline = time.monotonic() + seconds
        result = bytearray()
        while (remaining := deadline - time.monotonic()) > 0:
            readable, _, _ = select.select([self.master], [], [], remaining)
            if not readable:
                break
            try:
                chunk = os.read(self.master, 65536)
            except OSError as error:
                if error.errno == errno.EIO:
                    break
                raise
            if not chunk:
                break
            result.extend(chunk)
        self.output.extend(result)
        return result.decode("utf-8", errors="replace")

    def wait_for(self, text: str, timeout: float = 3) -> str:
        deadline = time.monotonic() + timeout
        result = ""
        while time.monotonic() < deadline:
            result += self.read(0.1)
            if text in result:
                return result
            if self.process.poll() is not None:
                break
        raise AssertionError(f"Did not render {text!r}; terminal output: {result!r}")

    def exit_cleanly(self, key: str = "\x1b", *, alternate_screen: bool = True) -> None:
        self.send(key)
        self.process.wait(timeout=1)
        self.read(0.1)
        if self.process.returncode not in (0, 130):
            raise AssertionError(
                f"Unexpected exit {self.process.returncode}: "
                f"{self.output.decode('utf-8', errors='replace')!r}"
            )
        if b"Traceback" in self.output:
            raise AssertionError("Application printed a traceback on exit")
        if termios.tcgetattr(self.slave) != self.initial_attributes:
            raise AssertionError("Application did not restore terminal attributes")
        if alternate_screen and b"\x1b[?1049l" not in self.output:
            raise AssertionError("Application did not leave the alternate screen")


@unittest.skipUnless(os.name == "posix", "curses TTY smoke tests require Unix")
class TerminalTests(unittest.TestCase):
    def test_russian_input_restart_and_language_switch(self) -> None:
        with TerminalProcess() as terminal:
            terminal.wait_for("русский")
            terminal.send("я ")
            terminal.read()
            terminal.send("\x7f\x17")  # Backspace and Ctrl+W.
            terminal.read()
            terminal.send("\t")
            self.assertTrue(terminal.read(), "Tab should redraw the exercise")
            terminal.send("\x0c")
            terminal.wait_for("english")
            self.assertIsNone(terminal.process.poll())
            terminal.exit_cleanly()

    def test_resize_pauses_and_recovers(self) -> None:
        with TerminalProcess("--lang", "en") as terminal:
            terminal.wait_for("english")
            terminal.resize(24, 8)
            terminal.wait_for("a little more room")
            terminal.send("abc")
            terminal.read()
            terminal.resize(80, 24)
            terminal.wait_for("english")
            terminal.exit_cleanly()

    def test_ctrl_c_restores_terminal(self) -> None:
        with TerminalProcess("--lang", "en", "--words", "50") as terminal:
            terminal.wait_for("english")
            terminal.exit_cleanly("\x03")

    def assert_rejected_without_terminal_changes(
        self,
        environment: dict[str, str],
        message: str,
    ) -> None:
        with TerminalProcess(env=environment) as terminal:
            terminal.process.wait(timeout=3)
            output = terminal.read()
            self.assertEqual(terminal.process.returncode, 1, output)
            self.assertIn(message, output)
            self.assertNotIn("Traceback", output)
            self.assertNotIn("\x1b", output)
            self.assertEqual(
                termios.tcgetattr(terminal.slave),
                terminal.initial_attributes,
            )

    def test_ascii_locale_is_rejected_even_with_python_utf8_mode(self) -> None:
        self.assert_rejected_without_terminal_changes(
            {"LC_ALL": "C", "PYTHONUTF8": "1", "PYTHONCOERCECLOCALE": "0"},
            "stuk needs a UTF-8 locale.",
        )

    def test_invalid_locale_is_rejected_without_traceback(self) -> None:
        self.assert_rejected_without_terminal_changes(
            {"LC_ALL": "stuk_invalid_locale.UTF-8", "PYTHONUTF8": "1"},
            "stuk needs a valid UTF-8 locale.",
        )

    def test_dumb_terminal_is_rejected_before_curses_setup(self) -> None:
        self.assert_rejected_without_terminal_changes(
            {"TERM": "dumb"},
            "stuk needs a terminal with cursor support",
        )

    def test_monochrome_terminal_can_render_and_restore(self) -> None:
        with TerminalProcess("--lang", "en", env={"TERM": "vt100"}) as terminal:
            terminal.wait_for("english")
            terminal.send("hello")
            terminal.read()
            terminal.exit_cleanly(alternate_screen=False)

    def test_completed_results_fit_smallest_supported_terminal(self) -> None:
        # A fixed passage exercises real curses rendering without depending on RNG.
        with TerminalProcess(code=fixed_passage_code("кот"), size=(32, 12)) as terminal:
            terminal.wait_for("русский")
            terminal.send("к")
            terminal.read(0.1)
            terminal.send("от")
            output = terminal.read()
            visible = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output)
            summary = re.search(r"\d+ слов/мин\s+·\s+100%", visible)
            self.assertIsNotNone(summary, output)
            self.assertLessEqual(len(summary.group()), 24)
            terminal.exit_cleanly()

    def test_settings_toggle_keyboard_without_typing_into_exercise(self) -> None:
        with TerminalProcess(code=fixed_passage_code("кот")) as terminal:
            terminal.wait_for("русский")
            terminal.send("\x0f")  # Ctrl+O opens settings.
            terminal.wait_for("настройки")
            terminal.send("zzz")
            terminal.read()
            terminal.send("\n")  # First settings row is the keyboard toggle.
            terminal.read()
            configuration = Path(terminal.config_directory.name) / "stuk/settings.json"
            self.assertTrue(json.loads(configuration.read_text())["show_keyboard"])
            terminal.send("\x1b")
            terminal.wait_for("русский")
            self.assertIsNone(
                terminal.process.poll(), "Esc should return from settings"
            )
            terminal.send("\x1bOQ")  # xterm F2 reopens settings.
            terminal.wait_for("настройки")
            terminal.send("\x1b")
            terminal.wait_for("русский")
            terminal.send("к")
            terminal.read(0.1)
            terminal.send("от")
            self.assertIn(
                "100%", terminal.read(), "Settings input must not affect accuracy"
            )
            terminal.exit_cleanly()

    def test_keyboard_toggle_is_loaded_on_next_launch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stuk-settings-test-") as config:
            environment = {"XDG_CONFIG_HOME": config}
            configuration = Path(config) / "stuk/settings.json"
            with TerminalProcess(env=environment) as terminal:
                terminal.wait_for("русский")
                terminal.send("\x0b")  # Ctrl+K quick keyboard toggle.
                terminal.read()
                self.assertTrue(json.loads(configuration.read_text())["show_keyboard"])
                terminal.exit_cleanly()
            with TerminalProcess(env=environment) as terminal:
                terminal.wait_for("русский")
                terminal.send("\x0b")
                terminal.read()
                self.assertFalse(json.loads(configuration.read_text())["show_keyboard"])
                terminal.exit_cleanly()

    def test_keyboard_survives_resize_and_settings_at_minimum_size(self) -> None:
        with TerminalProcess() as terminal:
            terminal.wait_for("русский")
            terminal.send("\x0b")
            terminal.read()
            terminal.resize(32, 12)
            terminal.wait_for("клавиатура")
            terminal.send("\x0f")
            output = terminal.wait_for("настройки")
            self.assertIn("клавиатура", output)
            self.assertIn("количество слов", output)
            terminal.send("\x1b")
            terminal.wait_for("русский")
            terminal.resize(80, 24)
            terminal.wait_for("русский")
            configuration = Path(terminal.config_directory.name) / "stuk/settings.json"
            self.assertTrue(json.loads(configuration.read_text())["show_keyboard"])
            terminal.exit_cleanly()

    def test_custom_palette_loads_and_survives_live_theme_switching(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stuk-theme-test-") as config:
            configuration = Path(config) / "stuk/settings.json"
            configuration.parent.mkdir()
            overrides = {"accent": "#abcdef", "border": "#384050"}
            configuration.write_text(
                json.dumps({"theme": "lavender", "colors": overrides})
            )
            with TerminalProcess(env={"XDG_CONFIG_HOME": config}) as terminal:
                terminal.wait_for("русский")
                updates = palette_updates(bytes(terminal.output))
                if updates:
                    self.assertTrue(
                        any(
                            all(
                                abs(actual - expected) <= 1
                                for actual, expected in zip(rgb, (171, 205, 239))
                            )
                            for values in updates.values()
                            for rgb in values
                        ),
                        "Configured accent should reach the real terminal palette",
                    )
                terminal.send("\x0f")
                terminal.wait_for("настройки")
                terminal.send("\t\t\t")  # Select fourth row: theme.
                terminal.read()
                for expected in ("terminal", "warm", "lavender"):
                    terminal.send("\x1bOC")  # xterm application Right arrow.
                    terminal.read()
                    saved = json.loads(configuration.read_text())
                    self.assertEqual(saved["theme"], expected)
                    self.assertEqual(saved["colors"], overrides)
                terminal.send("\x1b")
                terminal.wait_for("русский")
                terminal.exit_cleanly()

    def test_mutable_palette_is_restored_after_escape_and_ctrl_c(self) -> None:
        for key in ("\x1b", "\x03"):
            with self.subTest(exit_key=repr(key)), TerminalProcess() as terminal:
                terminal.wait_for("русский")
                initial = palette_updates(bytes(terminal.output))
                terminal.exit_cleanly(key)
                if not initial:
                    self.skipTest(
                        "This terminal build does not expose mutable palette colors"
                    )
                restored = palette_updates(bytes(terminal.output))
                for index, values in initial.items():
                    self.assertIn(index, range(16, 24))
                    self.assertGreater(len(restored[index]), len(values))
                    self.assertNotEqual(restored[index][-1], values[0])

    def test_completed_exercise_is_recorded_once_across_progress_and_redraw(
        self,
    ) -> None:
        with TerminalProcess(code=fixed_passage_code("кот")) as terminal:
            terminal.wait_for("русский")
            terminal.send("к")
            terminal.read(0.1)
            terminal.send("от")
            terminal.wait_for("100%")
            first = terminal.history()
            self.assertEqual(len(first), 1)
            self.assertEqual(first[0]["language"], "ru")
            terminal.send("\x10")
            terminal.wait_for("прогресс")
            terminal.resize(90, 28)
            terminal.read()
            terminal.send("\x1b")
            terminal.wait_for("русский")
            terminal.send("\x1bOR")  # xterm F3.
            terminal.wait_for("прогресс")
            terminal.send("\x1b")
            terminal.wait_for("русский")
            terminal.send("\t")
            terminal.read()
            terminal.exit_cleanly()
            self.assertEqual(terminal.history(), first)

    def test_incomplete_exercises_never_enter_history(self) -> None:
        with TerminalProcess(code=fixed_passage_code("кот")) as terminal:
            terminal.wait_for("русский")
            terminal.send("к")
            terminal.read()
            terminal.send("\t")
            terminal.read()
            terminal.send("к")
            terminal.read()
            terminal.send("\x10")
            terminal.wait_for("история пока пуста")
            terminal.send("\x1b")
            terminal.wait_for("русский")
            terminal.exit_cleanly()
            self.assertEqual(terminal.history(), [])

    def test_progress_language_filter_draws_graphs_without_changing_practice(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="stuk-history-test-") as data:
            seed_history(
                Path(data),
                [("ru", 21, 8), ("ru", 38, 2), ("en", 74, 4), ("en", 82, 0)],
            )
            with TerminalProcess(
                env={"XDG_DATA_HOME": data}, size=(100, 32)
            ) as terminal:
                terminal.wait_for("русский")
                terminal.send("\x10")
                output = terminal.wait_for("прогресс")
                self.assertTrue(any(0x2800 <= ord(char) <= 0x28FF for char in output))
                self.assertIn("38", output)
                terminal.send("\t")
                output = terminal.wait_for("english")
                self.assertIn("82", output)
                terminal.send("\x1b")
                terminal.wait_for("русский")
                terminal.exit_cleanly()

    def test_progress_pauses_time_and_does_not_accept_exercise_input(self) -> None:
        with TerminalProcess(code=fixed_passage_code("кот")) as terminal:
            terminal.wait_for("русский")
            started = time.monotonic()
            terminal.send("к")
            terminal.read(0.1)
            terminal.send("\x10")
            terminal.wait_for("прогресс")
            terminal.send("zzz")
            terminal.read(0.6)
            terminal.send("\x1b")
            terminal.wait_for("русский")
            terminal.send("от")
            terminal.wait_for("100%")
            duration = time.monotonic() - started
            record = terminal.history()[0]
            self.assertEqual(record["accuracy"], 100)
            self.assertEqual(record["attempts"], 3)
            self.assertLess(record["duration"], duration - 0.4)
            terminal.exit_cleanly()

    def test_guided_default_limits_real_passages_to_six_starting_letters(self) -> None:
        from stuk.curriculum import curriculum_state

        with tempfile.TemporaryDirectory(prefix="stuk-passage-test-") as directory:
            passage = Path(directory) / "passage.txt"
            with TerminalProcess(
                code=capture_passage_code(),
                env={"STUK_TEST_PASSAGE": str(passage)},
            ) as terminal:
                terminal.wait_for("русский")
                available = curriculum_state([], "ru").available
                self.assertEqual(len(available), 6)
                self.assertLessEqual(set(passage.read_text()) - {" "}, set(available))
                self.assertEqual(len(passage.read_text().split()), 25)
                terminal.send("\x0c")
                terminal.wait_for("english")
                available = curriculum_state([], "en").available
                self.assertEqual(len(available), 6)
                self.assertLessEqual(set(passage.read_text()) - {" "}, set(available))
                terminal.exit_cleanly()

    def test_practice_mode_cycles_and_persists_without_changing_custom_letters(
        self,
    ) -> None:
        with TerminalProcess() as terminal:
            terminal.wait_for("русский")
            terminal.send("\x0f")
            terminal.wait_for("настройки")
            terminal.send("\t" * 5)
            terminal.read()
            configuration = Path(terminal.config_directory.name) / "stuk/settings.json"
            previous_letters = None
            for expected in ("free", "custom", "guided"):
                terminal.send("\n")
                terminal.read()
                saved = json.loads(configuration.read_text())
                self.assertEqual(saved["practice_mode"], expected)
                if previous_letters is None:
                    previous_letters = saved["custom_letters"]
                self.assertEqual(saved["custom_letters"], previous_letters)
            terminal.send("\x1b")
            terminal.wait_for("русский")
            terminal.exit_cleanly()

    def test_custom_letters_editor_works_at_minimum_size_and_preserves_languages(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="stuk-passage-test-") as directory:
            passage = Path(directory) / "passage.txt"
            with TerminalProcess(
                code=capture_passage_code(),
                env={"STUK_TEST_PASSAGE": str(passage)},
                size=(32, 12),
            ) as terminal:
                terminal.wait_for("русский")
                terminal.send("\x0f")
                terminal.wait_for("настройки")
                terminal.send("\t" * 6)
                terminal.read()
                terminal.send("\n")
                terminal.wait_for("буквы")
                terminal.send(
                    "\x15ЕНоС2🙂\n"
                )  # Clear, normalize case, reject nonletters.
                terminal.read()
                configuration = (
                    Path(terminal.config_directory.name) / "stuk/settings.json"
                )
                saved = json.loads(configuration.read_text())
                self.assertEqual(saved["practice_mode"], "custom")
                self.assertEqual(set(saved["custom_letters"]["ru"]), set("енос"))
                self.assertEqual(set(saved["custom_letters"]["en"]), set("enirat"))
                self.assertLessEqual(set(passage.read_text()) - {" "}, set("енос"))
                terminal.send("\n")  # Reopen editor and cancel a different selection.
                terminal.wait_for("буквы")
                terminal.send("\x15жщ\x1b")
                terminal.read()
                self.assertEqual(json.loads(configuration.read_text()), saved)
                terminal.send("\x1b")
                terminal.wait_for("русский")
                terminal.send("\x0c")
                terminal.wait_for("english")
                self.assertLessEqual(set(passage.read_text()) - {" "}, set("enirat"))
                terminal.send("\x0c")
                terminal.wait_for("русский")
                self.assertLessEqual(set(passage.read_text()) - {" "}, set("енос"))
                terminal.exit_cleanly()

    def test_progress_letters_view_tracks_language_without_typing(self) -> None:
        with TerminalProcess() as terminal:
            terminal.wait_for("русский")
            terminal.send("\x10")
            terminal.wait_for("история пока пуста")
            terminal.send("l")
            terminal.wait_for("буквы")
            terminal.send("\t")
            terminal.wait_for("english")
            terminal.send("g")
            terminal.wait_for("no exercises yet")
            terminal.send("\x1b")
            terminal.wait_for("русский")
            terminal.exit_cleanly()
            self.assertEqual(terminal.history(), [])

    def test_russian_exercise_accepts_english_physical_keys(self) -> None:
        passage = "привет ёж хъ бью"
        with TerminalProcess(code=fixed_passage_code(passage)) as terminal:
            terminal.wait_for("русский")
            terminal.send("g")
            terminal.read(0.1)
            terminal.send("hbdtn `; [] ,m.")
            terminal.wait_for("100%")
            record = terminal.history()[0]
            self.assertEqual(record["language"], "ru")
            self.assertEqual(record["accuracy"], 100)
            self.assertEqual(record["mistakes"], 0)
            self.assertEqual(record["attempts"], len(passage))
            self.assertEqual(set(record["keys"]), set(passage) - {" "})
            terminal.exit_cleanly()

    def test_english_exercise_accepts_russian_physical_keys(self) -> None:
        passage = "hello fox"
        with TerminalProcess(
            code=fixed_passage_code(passage, language="en"),
        ) as terminal:
            terminal.wait_for("english")
            terminal.send("р")
            terminal.read(0.1)
            terminal.send("уддщ ащч")
            terminal.wait_for("100%")
            record = terminal.history()[0]
            self.assertEqual(record["language"], "en")
            self.assertEqual(record["accuracy"], 100)
            self.assertEqual(record["mistakes"], 0)
            self.assertEqual(record["attempts"], len(passage))
            self.assertEqual(set(record["keys"]), set(passage) - {" "})
            terminal.exit_cleanly()

    def test_layout_normalization_keeps_real_errors_shift_and_backspace(self) -> None:
        for incorrect in ("t", "R"):  # Wrong physical key, then incorrect Shift.
            with (
                self.subTest(key=incorrect),
                TerminalProcess(
                    code=fixed_passage_code("кот"),
                ) as terminal,
            ):
                terminal.wait_for("русский")
                terminal.send(incorrect)
                terminal.read(0.1)
                terminal.send("\x7frjn")
                terminal.wait_for("75%")
                record = terminal.history()[0]
                self.assertEqual(record["accuracy"], 75)
                self.assertEqual(record["mistakes"], 1)
                self.assertEqual(record["attempts"], 4)
                self.assertEqual(set(record["keys"]), set("кот"))
                self.assertEqual(record["keys"]["к"]["attempts"], 2)
                self.assertEqual(record["keys"]["к"]["mistakes"], 1)
                terminal.exit_cleanly()

    def test_language_switch_updates_input_normalization_immediately(self) -> None:
        with TerminalProcess(
            code=fixed_passage_code("кот", english_text="cat"),
        ) as terminal:
            terminal.wait_for("русский")
            terminal.send("r")
            terminal.read(0.1)
            terminal.send("\x0c")
            terminal.wait_for("english")
            terminal.send("с")
            terminal.read(0.1)
            terminal.send("фе")
            terminal.wait_for("100%")
            terminal.send("\x0c")
            terminal.wait_for("русский")
            terminal.send("r")
            terminal.read(0.1)
            terminal.send("jn")
            terminal.wait_for("100%")
            records = terminal.history()
            self.assertEqual([row["language"] for row in records], ["en", "ru"])
            self.assertTrue(all(row["accuracy"] == 100 for row in records))
            self.assertEqual(set(records[0]["keys"]), set("cat"))
            self.assertEqual(set(records[1]["keys"]), set("кот"))
            terminal.exit_cleanly()

    def test_letters_editor_accepts_the_other_keyboard_layout(self) -> None:
        with TerminalProcess() as terminal:
            terminal.wait_for("русский")
            terminal.send("\x0f")
            terminal.wait_for("настройки")
            terminal.send("\t" * 6)
            terminal.read()
            terminal.send("\n")
            terminal.wait_for("буквы")
            terminal.send("\x15TYJC\n")  # Physical keys for ЕНОС, editor casefolds.
            terminal.read()
            configuration = Path(terminal.config_directory.name) / "stuk/settings.json"
            saved = json.loads(configuration.read_text())
            self.assertEqual(saved["practice_mode"], "custom")
            self.assertEqual(set(saved["custom_letters"]["ru"]), set("енос"))
            terminal.send("\x1b")
            terminal.wait_for("русский")
            terminal.exit_cleanly()

    def test_progress_shortcuts_in_russian_layout_are_not_exercise_input(self) -> None:
        with TerminalProcess(code=fixed_passage_code("кот")) as terminal:
            terminal.wait_for("русский")
            terminal.send("r")
            terminal.read(0.1)
            terminal.send("\x10")
            terminal.wait_for("история пока пуста")
            terminal.send("д")
            terminal.wait_for("буквы")
            terminal.send("п")
            terminal.wait_for("история пока пуста")
            terminal.send("\x1b")
            terminal.wait_for("русский")
            terminal.send("jn")
            terminal.wait_for("100%")
            record = terminal.history()[0]
            self.assertEqual(record["attempts"], 3)
            self.assertEqual(record["mistakes"], 0)
            terminal.exit_cleanly()

    def test_f4_switches_training_language_and_discards_incomplete_text(self) -> None:
        with TerminalProcess(
            code=fixed_passage_code("кот", english_text="cat"),
        ) as terminal:
            terminal.wait_for("русский")
            terminal.send("r")
            terminal.read(0.1)
            terminal.send("\x1bOS")  # xterm F4.
            terminal.wait_for("english")
            configuration = Path(terminal.config_directory.name) / "stuk/settings.json"
            self.assertEqual(json.loads(configuration.read_text())["language"], "en")
            self.assertEqual(terminal.history(), [])
            terminal.send("с")
            terminal.read(0.1)
            terminal.send("фе")
            terminal.wait_for("100%")
            records = terminal.history()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["language"], "en")
            self.assertEqual(records[0]["accuracy"], 100)
            self.assertEqual(set(records[0]["keys"]), set("cat"))
            terminal.exit_cleanly()

    def test_f4_in_settings_resets_text_and_keeps_settings_paused(self) -> None:
        with TerminalProcess(
            code=fixed_passage_code("кот", english_text="cat"),
        ) as terminal:
            terminal.wait_for("русский")
            terminal.send("r")
            terminal.read(0.1)
            terminal.send("\x0f")
            terminal.wait_for("настройки")
            terminal.send("\x1bOS")
            terminal.wait_for("settings")
            terminal.send("zzz")
            terminal.read(0.2)
            self.assertEqual(terminal.history(), [])
            terminal.send("\x1b")
            terminal.wait_for("english")
            terminal.send("с")
            terminal.read(0.1)
            terminal.send("фе")
            terminal.wait_for("100%")
            records = terminal.history()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["language"], "en")
            self.assertEqual(records[0]["attempts"], 3)
            self.assertEqual(records[0]["accuracy"], 100)
            terminal.exit_cleanly()

    def test_f4_in_progress_changes_view_without_changing_practice(self) -> None:
        with TerminalProcess(
            code=fixed_passage_code("кот", english_text="cat"),
        ) as terminal:
            terminal.wait_for("русский")
            terminal.send("r")
            terminal.read(0.1)
            terminal.send("\x10")
            terminal.wait_for("история пока пуста")
            terminal.send("\x1bOS")
            terminal.wait_for("no exercises yet")
            terminal.send("\x1b")
            terminal.wait_for("русский")
            terminal.send("jn")
            terminal.wait_for("100%")
            record = terminal.history()[0]
            self.assertEqual(record["language"], "ru")
            self.assertEqual(record["attempts"], 3)
            self.assertEqual(record["accuracy"], 100)
            terminal.exit_cleanly()

    def test_minimum_terminal_footer_keeps_all_keys_in_order_after_completion(
        self,
    ) -> None:
        with TerminalProcess(code=fixed_passage_code("кот"), size=(32, 12)) as terminal:
            terminal.wait_for("русский")
            initial = bytes(terminal.output).decode("utf-8")
            initial = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", initial)
            keys = ("esc", "tab", "F2", "F3", "F4")
            positions = [initial.index(key) for key in keys]
            self.assertEqual(positions, sorted(positions))
            terminal.send("к")
            terminal.read(0.1)
            terminal.send("от")
            terminal.wait_for("100%")
            terminal.resize(33, 12)
            completed = terminal.wait_for("F4")
            completed = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", completed)
            positions = [completed.index(key) for key in keys]
            self.assertEqual(positions, sorted(positions))
            self.assertNotIn("enter", completed)
            terminal.send("\n")  # Enter remains a supported, undisplayed alias.
            terminal.read()
            terminal.send("к")
            terminal.read(0.1)
            terminal.send("от")
            terminal.wait_for("100%")
            self.assertEqual(len(terminal.history()), 2)
            terminal.exit_cleanly()

    def test_f4_preserves_editor_drafts_without_committing_other_languages(
        self,
    ) -> None:
        with TerminalProcess() as terminal:
            terminal.wait_for("русский")
            terminal.send("\x0f")
            terminal.wait_for("настройки")
            terminal.send("\t" * 6)
            terminal.read()
            terminal.send("\n")
            terminal.wait_for("буквы")
            terminal.send("\x15tyjc")  # Unsaved RU draft: енос.
            terminal.read()
            terminal.send("\x1bOS")
            terminal.wait_for("english")
            configuration = Path(terminal.config_directory.name) / "stuk/settings.json"
            switched = json.loads(configuration.read_text())
            self.assertEqual(switched["language"], "en")
            self.assertEqual(set(switched["custom_letters"]["ru"]), set("енотас"))
            terminal.send("\x15утшк")  # Unsaved EN draft: enir.
            terminal.read()
            terminal.send("\x1bOS")
            terminal.wait_for("русский")
            terminal.send("\n")  # Commit only the restored RU draft.
            terminal.read()
            saved = json.loads(configuration.read_text())
            self.assertEqual(saved["language"], "ru")
            self.assertEqual(saved["practice_mode"], "custom")
            self.assertEqual(set(saved["custom_letters"]["ru"]), set("енос"))
            self.assertEqual(set(saved["custom_letters"]["en"]), set("enirat"))
            terminal.send("\n")  # Reopen editor, then cancel both new drafts.
            terminal.wait_for("буквы")
            terminal.send("\x15fk\x1bOS")
            terminal.wait_for("english")
            terminal.send("\x15ут\x1bOS")
            terminal.wait_for("русский")
            terminal.send("\x1b")
            terminal.read()
            self.assertEqual(json.loads(configuration.read_text()), saved)
            terminal.send("\x1b")
            terminal.wait_for("русский")
            self.assertEqual(terminal.history(), [])
            terminal.exit_cleanly()


if __name__ == "__main__":
    unittest.main()
