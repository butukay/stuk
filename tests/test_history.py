"""History must remain useful after malformed input, failed writes, and races."""

import copy
import json
import multiprocessing
import os
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

from stuk.history import (
    HistoryError,
    append_record,
    history_path,
    load_history,
    make_record,
    save_session,
)
from stuk.session import TypingSession


def complete_session(text="ab"):
    session = TypingSession(text)
    for index, character in enumerate(text):
        session.input(character, 10 + index * 0.4)
    return session


def append_worker(path, records, start):
    start.wait(timeout=5)
    for record in records:
        append_record(record, Path(path))


class RecordTests(unittest.TestCase):
    def test_builder_includes_corrected_mistakes_and_excludes_spaces_and_symbols(self):
        session = TypingSession("а а.")
        session.input("я", 10)
        session.backspace()
        session.input("а", 10.4)
        session.input(" ", 10.8)
        session.input("а", 11.3)
        session.input(".", 11.6)
        record = make_record(session, "ru", 2, now=1000)
        self.assertEqual(record["attempts"], 5)
        self.assertEqual(record["mistakes"], 1)
        self.assertAlmostEqual(record["duration"], 1.6)
        self.assertAlmostEqual(record["wpm"], 30)
        self.assertEqual(record["accuracy"], 80)
        self.assertEqual(set(record["keys"]), {"а"})
        self.assertEqual(record["keys"]["а"]["attempts"], 3)
        self.assertEqual(record["keys"]["а"]["mistakes"], 1)
        self.assertEqual(record["keys"]["а"]["interval_count"], 2)
        self.assertAlmostEqual(record["keys"]["а"]["interval_total"], 0.9)

    def test_builder_produces_unique_ids_and_utc_dates(self):
        local_date = datetime(2026, 10, 28, 12, 30, tzinfo=timezone(timedelta(hours=3)))
        session = complete_session()
        first = make_record(session, "en", 1, date=local_date)
        second = make_record(session, "en", 1)
        self.assertEqual(str(UUID(first["id"])), first["id"])
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["date"], "2026-10-28T09:30:00.000000+00:00")
        self.assertEqual(
            datetime.fromisoformat(second["date"]).utcoffset(), timedelta(0)
        )

    def test_builder_does_not_write_preferences_or_history(self):
        with patch("stuk.history.history_path") as location:
            make_record(complete_session(), "en", 1)
        location.assert_not_called()

    def test_incomplete_sessions_are_rejected(self):
        session = TypingSession("ab")
        session.input("a", 10)
        with self.assertRaises(ValueError):
            make_record(session, "en", 1)

    def test_invalid_metadata_and_naive_dates_are_rejected(self):
        session = complete_session()
        for language, words in (("de", 25), ("en", 0), ("ru", 61), ("ru", True)):
            with self.subTest(language=language, words=words):
                with self.assertRaises(ValueError):
                    make_record(session, language, words)
        with self.assertRaises(ValueError):
            make_record(session, "en", 1, date=datetime(2026, 10, 28))


class HistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "stuk" / "history.json"
        self.record = make_record(complete_session(), "en", 1)

    def write_document(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(value), encoding="utf-8")

    def test_missing_history_does_not_create_directories(self):
        self.assertEqual(load_history(self.path), [])
        self.assertFalse(self.path.parent.exists())

    def test_record_round_trip_has_versioned_json_and_private_permissions(self):
        append_record(self.record, self.path)
        self.assertEqual(load_history(self.path), [self.record])
        document = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(document, {"version": 1, "sessions": [self.record]})
        self.assertTrue(self.path.read_text(encoding="utf-8").endswith("\n"))
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)
        lock = self.path.parent / ".history.lock"
        self.assertEqual(stat.S_IMODE(lock.stat().st_mode), 0o600)

    def test_appending_same_id_twice_does_not_duplicate_exercise(self):
        append_record(self.record, self.path)
        append_record(copy.deepcopy(self.record), self.path)
        self.assertEqual(load_history(self.path), [self.record])

    def test_save_session_builds_and_returns_the_persisted_record(self):
        session = complete_session("тихо")
        record = save_session(session, "ru", 1, self.path)
        self.assertEqual(record["language"], "ru")
        self.assertEqual(load_history(self.path), [record])

    def test_incomplete_session_does_not_create_a_history_file(self):
        with self.assertRaises(ValueError):
            save_session(TypingSession("unfinished"), "en", 1, self.path)
        self.assertFalse(self.path.parent.exists())

    def test_records_are_returned_chronologically_without_language_filtering(self):
        old = make_record(
            complete_session("тихо"),
            "ru",
            1,
            date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.write_document({"version": 1, "sessions": [self.record, old]})
        self.assertEqual(load_history(self.path), [old, self.record])

    def test_loading_does_not_trim_full_history_to_graph_window(self):
        records = []
        for index in range(75):
            record = copy.deepcopy(self.record)
            record["id"] = str(uuid4())
            records.append(record)
        self.write_document({"version": 1, "sessions": records})
        self.assertEqual(len(load_history(self.path)), 75)

    def test_corrupt_documents_are_never_overwritten(self):
        malformed = (
            b"{invalid json",
            b"\xff\xfe",
            b"[]",
            b"null",
            b'{"version":2,"sessions":[]}',
            b'{"version":true,"sessions":[]}',
            b'{"version":1,"sessions":{}}',
        )
        self.path.parent.mkdir()
        for contents in malformed:
            with self.subTest(contents=contents):
                self.path.write_bytes(contents)
                with self.assertRaises(HistoryError):
                    load_history(self.path)
                with self.assertRaises(HistoryError):
                    append_record(self.record, self.path)
                self.assertEqual(self.path.read_bytes(), contents)

    def test_invalid_individual_records_do_not_discard_good_records(self):
        invalid_fields = (
            {"id": "not a UUID"},
            {"date": "yesterday"},
            {"date": "2026-10-28T10:00:00"},
            {"date": "2026-10-28T10:00:00+03:00"},
            {"language": []},
            {"language": "de"},
            {"words": 0},
            {"words": True},
            {"words": 25.0},
            {"attempts": 0},
            {"attempts": False},
            {"mistakes": -1},
            {"mistakes": 3},
            {"duration": -1},
            {"wpm": float("inf")},
            {"wpm": float("nan")},
            {"wpm": 10**400},
            {"accuracy": 101},
            {"accuracy": True},
            {"keys": []},
        )
        for changes in invalid_fields:
            with self.subTest(changes=changes):
                invalid = copy.deepcopy(self.record)
                invalid["id"] = str(uuid4())
                invalid.update(changes)
                self.write_document(
                    {
                        "version": 1,
                        "sessions": [None, [], "bad", True, invalid, self.record],
                    }
                )
                self.assertEqual(load_history(self.path), [self.record])

    def test_invalid_key_statistics_do_not_enter_adaptive_history(self):
        invalid_keys = (
            {"A": {"attempts": 1}},
            {" ": {}},
            {"ab": {}},
            {
                "a": {
                    "attempts": 0,
                    "mistakes": 0,
                    "interval_total": 0,
                    "interval_count": 0,
                }
            },
            {
                "a": {
                    "attempts": 1,
                    "mistakes": 2,
                    "interval_total": 0,
                    "interval_count": 0,
                }
            },
            {
                "a": {
                    "attempts": 1,
                    "mistakes": 0,
                    "interval_total": -1,
                    "interval_count": 0,
                }
            },
            {
                "a": {
                    "attempts": 1,
                    "mistakes": 0,
                    "interval_total": 0,
                    "interval_count": 2,
                }
            },
            {
                "a": {
                    "attempts": True,
                    "mistakes": 0,
                    "interval_total": 0,
                    "interval_count": 0,
                }
            },
        )
        for keys in invalid_keys:
            with self.subTest(keys=keys):
                invalid = copy.deepcopy(self.record)
                invalid["id"] = str(uuid4())
                invalid["keys"] = keys
                self.write_document({"version": 1, "sessions": [invalid, self.record]})
                self.assertEqual(load_history(self.path), [self.record])

    def test_invalid_append_is_rejected_before_any_file_is_created(self):
        record = copy.deepcopy(self.record)
        record["accuracy"] = float("nan")
        with self.assertRaises(ValueError):
            append_record(record, self.path)
        self.assertFalse(self.path.parent.exists())

    def test_failed_replace_preserves_history_and_removes_temporary_files(self):
        append_record(self.record, self.path)
        before = self.path.read_bytes()
        another = make_record(complete_session("cd"), "en", 1)
        with patch("stuk.history.os.replace", side_effect=PermissionError("read only")):
            with self.assertRaises(PermissionError):
                append_record(another, self.path)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(
            {entry.name for entry in self.path.parent.iterdir()},
            {"history.json", ".history.lock"},
        )
        append_record(another, self.path)
        self.assertEqual(len(load_history(self.path)), 2)

    def test_read_errors_propagate_instead_of_treating_history_as_empty(self):
        with patch("pathlib.Path.open", side_effect=PermissionError("read denied")):
            with self.assertRaises(PermissionError):
                load_history(self.path)

    @unittest.skipUnless(os.name == "posix", "Process locks require Unix")
    def test_two_concurrent_writers_do_not_lose_records(self):
        context = multiprocessing.get_context("fork")
        start = context.Event()
        batches = [
            [make_record(complete_session(), "en", 1) for _ in range(5)]
            for _ in range(2)
        ]
        processes = [
            context.Process(target=append_worker, args=(str(self.path), batch, start))
            for batch in batches
        ]
        try:
            for process in processes:
                process.start()
            start.set()
            for process in processes:
                process.join(timeout=5)
                self.assertEqual(process.exitcode, 0)
        finally:
            for process in processes:
                if process.is_alive():
                    process.kill()
                    process.join(timeout=2)
        self.assertEqual(
            {record["id"] for record in load_history(self.path)},
            {record["id"] for batch in batches for record in batch},
        )

    def test_absolute_xdg_data_path_takes_precedence(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": str(self.root / "data")}):
            self.assertEqual(
                history_path(), self.root / "data" / "stuk" / "history.json"
            )

    def test_relative_empty_and_missing_xdg_data_paths_use_home(self):
        expected = self.root / ".local" / "share" / "stuk" / "history.json"
        with patch("stuk.history.Path.home", return_value=self.root):
            for value in ("relative/data", "~/data", ""):
                with self.subTest(value=value):
                    with patch.dict(os.environ, {"XDG_DATA_HOME": value}):
                        self.assertEqual(history_path(), expected)
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(history_path(), expected)

    def test_default_path_is_resolved_when_called(self):
        with patch("stuk.history.history_path", return_value=self.path):
            append_record(self.record)
            self.assertEqual(load_history(), [self.record])


if __name__ == "__main__":
    unittest.main()
