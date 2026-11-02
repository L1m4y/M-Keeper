#!/usr/bin/env python3
"""Tests for keeper.py (standard library only)."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import subprocess

import keeper

class TestHelpers(unittest.TestCase):
    def test_safe_email(self):
        self.assertTrue(keeper.safe_email("a@b.com"))
        self.assertFalse(keeper.safe_email("no-at"))
        self.assertFalse(keeper.safe_email("a@"))

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
    def test_add_remove(self):
        keeper.add_account(self.db, keeper.Color(False), email="a@b.com", password="pw")
        self.assertEqual(len(keeper.load_accounts(self.db)), 1)
        keeper.remove_account(self.db, "a@b.com", assume_yes=True, color=keeper.Color(False))
        self.assertEqual(keeper.load_accounts(self.db), [])

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
    def test_help(self):
        with self.assertRaises(SystemExit) as cm:
            keeper.main(["--help"])
        self.assertEqual(cm.exception.code, 0)
    def test_dry_run(self):
        keeper.save_accounts(self.db, [{"email": "a@b.com", "password": "p", "status": "Pending"}], backup=False)
        self.assertEqual(keeper.main(["--no-color", "--db", str(self.db), "start", "--dry-run"]), 0)

if __name__ == "__main__":
    unittest.main()
