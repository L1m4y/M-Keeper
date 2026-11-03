#!/usr/bin/env python3
"""Tests for keeper.py (standard library only)."""

import contextlib
import hashlib
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import keeper


class TestHelpers(unittest.TestCase):
    def test_safe_email(self):
        self.assertTrue(keeper.safe_email("a@b.com"))
        self.assertFalse(keeper.safe_email("no-at"))
        self.assertFalse(keeper.safe_email("a@"))
        self.assertFalse(keeper.safe_email("a@.com"))
        self.assertFalse(keeper.safe_email("a@b."))
        self.assertFalse(keeper.safe_email("a@b@c.com"))
        self.assertFalse(keeper.safe_email("a b@c.com"))

    def test_safe_credential(self):
        self.assertTrue(keeper.safe_credential("correct horse battery"))
        self.assertFalse(keeper.safe_credential(""))
        self.assertFalse(keeper.safe_credential("line\nbreak"))
        self.assertFalse(keeper.safe_credential("carriage\rreturn"))


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "accounts.json"
        keeper.DB_FILE = self.db

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip(self):
        data = [{"email": "a@b.com", "password": "p", "status": "Pending"}]
        keeper.save_accounts(self.db, data, backup=False)
        self.assertEqual(keeper.load_accounts(self.db), data)

    def test_0600(self):
        keeper.save_accounts(self.db, [], backup=False)
        self.assertEqual(self.db.stat().st_mode & 0o777, 0o600)

    def test_backup_0600(self):
        keeper.save_accounts(self.db, [{"email": "a@b.com", "password": "p", "status": "Pending"}], backup=False)
        keeper.save_accounts(self.db, [], backup=True)
        backup = self.db.with_suffix(self.db.suffix + ".bak")
        self.assertTrue(backup.exists())
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)

    def test_add_remove(self):
        keeper.add_account(self.db, keeper.Color(False), email="a@b.com", password="pw")
        self.assertEqual(len(keeper.load_accounts(self.db)), 1)
        keeper.remove_account(self.db, "a@b.com", assume_yes=True, color=keeper.Color(False))
        self.assertEqual(keeper.load_accounts(self.db), [])

    def test_add_duplicate_is_case_insensitive(self):
        keeper.add_account(self.db, keeper.Color(False), email="A@B.com", password="pw")
        keeper.add_account(self.db, keeper.Color(False), email="a@b.com", password="pw")
        self.assertEqual(len(keeper.load_accounts(self.db)), 1)

    def test_export_0600(self):
        keeper.save_accounts(self.db, [{"email": "a@b.com", "password": "p", "status": "Pending"}], backup=False)
        destination = Path(self.tmp.name) / "export.json"
        self.assertEqual(keeper.export_accounts(self.db, destination), 0)
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(json.loads(destination.read_text(encoding="utf-8"))), 1)

    def test_import_filters_invalid_entries(self):
        source = Path(self.tmp.name) / "import.json"
        source.write_text(
            json.dumps(
                [
                    {"email": "a@b.com", "password": "p"},
                    {"email": "bad", "password": "p"},
                    {"email": "a@b.com", "password": "other"},
                    {"email": "c@d.com", "password": "p\nq"},
                    "not-an-object",
                ]
            ),
            encoding="utf-8",
        )
        self.assertEqual(keeper.import_accounts(self.db, source), 0)
        accounts = keeper.load_accounts(self.db)
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["email"], "a@b.com")
        self.assertEqual(accounts[0]["status"], "Pending")


class TestConfig(unittest.TestCase):
    def test_write_mega_config_is_private_and_escapes_backslashes(self):
        path = keeper.write_mega_config("a@b.com", "p\\ss")
        try:
            content = Path(path).read_text(encoding="utf-8")
            self.assertIn("Username = a@b.com", content)
            self.assertIn("Password = p\\\\ss", content)
            self.assertEqual(Path(path).stat().st_mode & 0o777, 0o600)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_write_mega_config_rejects_newlines(self):
        with self.assertRaises(ValueError):
            keeper.write_mega_config("a@b.com", "p\nq")


class TestCache(unittest.TestCase):
    def test_clear_cache_removes_only_the_matching_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            digest = hashlib.sha1(b"a@b.com").hexdigest()
            cache = Path(tmp) / f"{digest}.megatools.cache"
            other = Path(tmp) / "other.megatools.cache"
            cache.write_text("cache", encoding="utf-8")
            other.write_text("other", encoding="utf-8")
            with mock.patch("keeper.tempfile.gettempdir", return_value=tmp):
                keeper._clear_cache("a@b.com")
            self.assertFalse(cache.exists())
            self.assertTrue(other.exists())


class TestCountdown(unittest.TestCase):
    def test_non_interactive_wait_is_interruptible(self):
        stop = threading.Event()
        stop.set()
        keeper._countdown(300, keeper.Color(False), stop, no_interactive=True)

    def test_interactive_countdown_uses_select(self):
        stop = threading.Event()
        with mock.patch("keeper.sys.stdout.isatty", return_value=True):
            with mock.patch("keeper.select.select", return_value=([], [], [])) as select_mock:
                with mock.patch("keeper.time.monotonic", side_effect=[0.0, 6.0, 7.0]):
                    with mock.patch("keeper.time.sleep"):
                        keeper._countdown(2, keeper.Color(False), stop, no_interactive=False)
        select_mock.assert_called()


class TestCheckNode(unittest.TestCase):
    def test_missing(self):
        with mock.patch("keeper.subprocess.run", side_effect=FileNotFoundError("megatools")):
            with mock.patch("keeper.write_mega_config", return_value="/tmp/fake.ini"):
                with mock.patch("keeper.Path.unlink"):
                    rc, out, err = keeper.check_node("a@b.com", "pw", 5)
        self.assertEqual(rc, 127)

    def test_success(self):
        fake = mock.Mock(returncode=0, stdout="Total: 1\n", stderr="")
        with mock.patch("keeper.subprocess.run", return_value=fake):
            with mock.patch("keeper.write_mega_config", return_value="/tmp/fake.ini"):
                with mock.patch("keeper.Path.unlink"):
                    rc, out, err = keeper.check_node("a@b.com", "pw", 5)
        self.assertEqual(rc, 0)
        self.assertIn("Total", out)


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "accounts.json"
        keeper.DB_FILE = self.db

    def tearDown(self):
        self.tmp.cleanup()

    def test_status(self):
        self.assertEqual(keeper.main(["--no-color", "status"]), 0)

    def test_json_status_does_not_leak_passwords(self):
        keeper.save_accounts(self.db, [{"email": "a@b.com", "password": "secret", "status": "Pending"}], backup=False)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(keeper.main(["--json", "--db", str(self.db), "status"]), 0)
        self.assertNotIn("secret", output.getvalue())
        self.assertIn("a@b.com", output.getvalue())

    def test_help(self):
        with self.assertRaises(SystemExit) as cm:
            keeper.main(["--help"])
        self.assertEqual(cm.exception.code, 0)

    def test_dry_run(self):
        keeper.save_accounts(self.db, [{"email": "a@b.com", "password": "p", "status": "Pending"}], backup=False)
        self.assertEqual(keeper.main(["--no-color", "--db", str(self.db), "start", "--dry-run"]), 0)


if __name__ == "__main__":
    unittest.main()
