"""CLI diagnostics must work without entering curses or requiring a TTY."""

import os
import subprocess
import sys
import unittest
from pathlib import Path

from stuk import __version__

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "src")
        return subprocess.run(
            [sys.executable, "-m", "stuk", *arguments],
            cwd=ROOT,
            env=environment,
            input="",
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )

    def test_help_works_when_redirected(self) -> None:
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--lang", result.stdout)
        self.assertIn("--words", result.stdout)
        self.assertIn("--mode", result.stdout)
        self.assertIn("--letters", result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertNotIn("\x1b", result.stdout)

    def test_version_works_when_redirected(self) -> None:
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), f"stuk {__version__}")
        self.assertEqual(result.stderr, "")

    def test_invalid_word_counts_have_actionable_errors(self) -> None:
        for count in ("0", "-1", "61", "many", "1.5"):
            with self.subTest(count=count):
                result = self.run_cli("--words", count)
                self.assertEqual(result.returncode, 2)
                self.assertIn("from 1 to 60", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_redirected_practice_explains_terminal_requirement(self) -> None:
        result = self.run_cli("--lang", "en", "--words", "25")
        self.assertEqual(result.returncode, 1)
        self.assertIn("interactive terminal", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("\x1b", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_invalid_mode_is_rejected_before_terminal_setup(self) -> None:
        result = self.run_cli("--mode", "unknown")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_custom_letters_require_selected_language_letters(self) -> None:
        for language, letters in (("en", "123"), ("ru", "abc"), ("en", "я")):
            with self.subTest(language=language, letters=letters):
                result = self.run_cli("--lang", language, "--letters", letters)
                self.assertEqual(result.returncode, 2)
                self.assertIn("at least one letter", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_custom_flags_are_accepted_before_interactive_terminal_check(self) -> None:
        result = self.run_cli(
            "--mode", "free", "--lang", "en", "--letters", "ASDF asdf 123"
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("interactive terminal", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
