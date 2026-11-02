#!/usr/bin/env python3
"""M-Keeper: keep Mega.nz accounts alive by validating them periodically.

This tool wraps the `megatools` command line utility. Account data never
reaches a command line; credentials are written to a short-lived configuration
file with mode 0600 and are removed as soon as the subprocess finishes.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import getpass
import json
import logging
import os
import platform
import random
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:
    fcntl = None

VERSION = "2.0.0"
DEFAULT_DELAY_MINUTES = 5
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_RETRIES = 1

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = Path(os.environ.get("MEGA_KEEPER_DB", str(BASE_DIR / "accounts.json")))


class Color:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def cyan(self, text: str) -> str:
        return self._wrap("96", text)

    def green(self, text: str) -> str:
        return self._wrap("92", text)

    def red(self, text: str) -> str:
        return self._wrap("91", text)

    def yellow(self, text: str) -> str:
        return self._wrap("93", text)

    def bold(self, text: str) -> str:
        return self._wrap("1", text)


def setup_logging(quiet: bool = False) -> None:
    level = logging.WARNING if quiet else logging.INFO
    handlers = [logging.StreamHandler(sys.stderr)]
    log_file = os.environ.get("MEGA_KEEPER_LOG")
    if log_file:
        try:
            handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
        except OSError:
            sys.stderr.write(f"warning: cannot open log file {log_file}\n")
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)


def safe_email(value: str) -> bool:
    return "@" in value and "." in value.split("@", 1)[-1]


def _lock_path(db_path: Path) -> Path:
    return db_path.with_suffix(db_path.suffix + ".lock")


def _acquire_lock(handle: Any) -> None:
    if fcntl is None:
        return
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _release_lock(handle: Any) -> None:
    if fcntl is None:
        return
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load_accounts(db_path: Path) -> list[dict[str, str]]:
    if not db_path.exists():
        return []
    lock_path = _lock_path(db_path)
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("w", encoding="utf-8") as lock_handle:
            _acquire_lock(lock_handle)
            try:
                with db_path.open(encoding="utf-8") as handle:
                    data = json.load(handle)
            except (OSError, ValueError) as exc:
                logging.error("cannot read database %s: %s", db_path, exc)
                return []
            finally:
                _release_lock(lock_handle)
    except OSError as exc:
        logging.error("cannot lock database %s: %s", db_path, exc)
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _atomic_write(path: Path, data: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, mode)
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def save_accounts(db_path: Path, data: list[dict[str, str]], *, backup: bool = True) -> None:
    lock_path = _lock_path(db_path)
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("w", encoding="utf-8") as lock_handle:
            _acquire_lock(lock_handle)
            try:
                if backup and db_path.exists():
                    backup_path = db_path.with_suffix(db_path.suffix + ".bak")
                    try:
                        backup_path.write_bytes(db_path.read_bytes())
                    except OSError as exc:
                        logging.warning("cannot create database backup: %s", exc)
                _atomic_write(db_path, json.dumps(data, indent=2, ensure_ascii=False))
            finally:
                _release_lock(lock_handle)
    except OSError as exc:
        logging.error("cannot save database %s: %s", db_path, exc)
        raise


def write_mega_config(email: str, password: str) -> str:
    fd, path = tempfile.mkstemp(prefix="mega-keeper-", text=True)
    tmp_path = Path(path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("[Login]\n")
            handle.write(f"Username = {email}\n")
            safe_password = password.replace("\\", "\\\\")
            handle.write(f"Password = {safe_password}\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, 0o600)
        return str(tmp_path)
    except Exception:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def check_node(email: str, password: str, timeout: int) -> tuple[int, str, str]:
    config_path = write_mega_config(email, password)
    try:
        result = subprocess.run(
            ["megatools", "df", "--reload", "--human", "--ignore-config-file", "--config", config_path, "--no-ask-password"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "megatools timed out"
    except FileNotFoundError as exc:
        return 127, "", f"megatools not found: {exc}"
    except OSError as exc:
        return 1, "", str(exc) or "megatools failed to start"
    finally:
        try:
            Path(config_path).unlink()
        except OSError:
            pass


def print_status(color: Color, db_path: Path, as_json: bool = False) -> int:
    accounts = load_accounts(db_path)
    if as_json:
        print(json.dumps(accounts, indent=2, ensure_ascii=False))
        return 0
    print(f"{color.cyan('M-Keeper')} {VERSION}")
    print("=" * 65)
    print(f"{'TARGET NODE':<40} | {'STATUS':<10}")
    print("-" * 65)
    if not accounts:
        print(f"  {color.red('[!] NO NODES REGISTERED.')}")
    else:
        for acc in accounts:
            node_id = str(acc.get("email", "Unknown"))
            status = str(acc.get("status", "Pending"))
            if status == "Active":
                colored = color.green(f"[ {status.upper()} ]")
            elif status == "Error":
                colored = color.red(f"[ {status.upper()} ]")
            else:
                colored = color.yellow(f"[ {status.upper()} ]")
            print(f"{node_id:<40} | {colored}")
    print("=" * 65)
    print(f"[i] total nodes: {len(accounts)}")
    return 0


def add_account(db_path: Path, color: Color, email: str | None = None, password: str | None = None) -> int:
    if email is None:
        try:
            email = input(f" {color.cyan('[?] Mega email:')} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
    if password is None:
        try:
            password = getpass.getpass(f" {color.cyan('[?] Password (hidden):')} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1

    if not email or not password or not safe_email(email):
        print(color.red("[!] INVALID NODE. NOTHING SAVED."))
        return 2

    accounts = load_accounts(db_path)
    if any(account.get("email") == email for account in accounts):
        print(color.yellow("[!] NODE ALREADY REGISTERED."))
        return 0

    accounts.append({"email": email, "password": password, "status": "Pending"})
    save_accounts(db_path, accounts)
    print(color.green("[+] NODE SECURELY REGISTERED."))
    return 0


def remove_account(db_path: Path, email: str, assume_yes: bool = False, color: Color | None = None) -> int:
    color = color or Color(False)
    accounts = load_accounts(db_path)
    if not any(account.get("email") == email for account in accounts):
        print(color.yellow(f"[!] NODE NOT FOUND: {email}"))
        return 1
    if not assume_yes:
        try:
            answer = input(f"Remove {email}? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if answer not in {"y", "yes"}:
            print("Aborted.")
            return 1
    new_accounts = [account for account in accounts if account.get("email") != email]
    save_accounts(db_path, new_accounts)
    print(color.green(f"[+] NODE REMOVED: {email}"))
    return 0


def export_accounts(db_path: Path, destination: Path) -> int:
    accounts = load_accounts(db_path)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_suffix(destination.suffix + ".tmp")
        _atomic_write(tmp, json.dumps(accounts, indent=2, ensure_ascii=False))
        tmp.replace(destination)
    except OSError as exc:
        logging.error("cannot export database to %s: %s", destination, exc)
        return 1
    return 0


def import_accounts(db_path: Path, source: Path, merge: bool = True) -> int:
    try:
        with source.open(encoding="utf-8") as handle:
            incoming = json.load(handle)
    except (OSError, ValueError) as exc:
        logging.error("cannot read import file %s: %s", source, exc)
        return 1
    if not isinstance(incoming, list):
        logging.error("import file must contain a JSON array")
        return 2
    incoming = [item for item in incoming if isinstance(item, dict)]
    existing = load_accounts(db_path)
    if merge:
        emails = {account.get("email") for account in existing}
        for account in incoming:
            if account.get("email") not in emails:
                existing.append(account)
                emails.add(account.get("email"))
    else:
        existing = incoming
    save_accounts(db_path, existing)
    logging.info("imported %d nodes (total %d)", len(incoming), len(existing))
    return 0


def _check_with_retry(email: str, password: str, timeout: int, retries: int) -> tuple[int, str, str]:
    rc, stdout, stderr = check_node(email, password, timeout)
    attempt = 1
    while rc != 0 and attempt < retries:
        attempt += 1
        time.sleep(2)
        rc, stdout, stderr = check_node(email, password, timeout)
    return rc, stdout, stderr


def _clear_cache() -> None:
    cache_dir = Path.home() / ".cache" / "megatools"
    if cache_dir.exists():
        shutil.rmtree(cache_dir, ignore_errors=True)


def _countdown(total: int, color: Color, stop_event: threading.Event, no_interactive: bool) -> None:
    interactive = sys.stdout.isatty() and not no_interactive
    if not interactive:
        delay = total if total > 0 else random.randint(60, 300)
        print(f"   [i] next rotation in {delay}s...")
        time.sleep(delay)
        return
    remaining = total
    started = time.monotonic()
    while remaining > 0 and not stop_event.is_set():
        print(f"\r  {color.bold(f'DELAY: {remaining:04d}s')}", end="", flush=True)
        if time.monotonic() - started >= 5 and select is not None:
            try:
                ready, _, _ = select.select([sys.stdin], [], [], 0)
            except (OSError, ValueError):
                ready = False
            if ready:
                try:
                    sys.stdin.readline()
                except (OSError, ValueError):
                    pass
                print(f"\n  {color.yellow('[*] COOLDOWN SKIPPED MANUALLY.')} ")
                return
        time.sleep(1)
        remaining -= 1
    print()


def keep_alive(args: argparse.Namespace, color: Color) -> int:
    accounts = load_accounts(args.db)
    if not accounts:
        print(color.red("[!] NO TARGETS FOUND. ABORTING."))
        return 1

    total = len(accounts)
    success = 0
    failed = 0
    stop_event = threading.Event()

    def _signal_handler(signum: int, frame: Any) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    delay_seconds = max(0, args.delay * 60)
    timeout = args.timeout
    retries = max(1, args.retries)
    concurrency = max(1, min(args.concurrency, total))

    print(color.cyan(f"M-Keeper {VERSION} :: maintenance sequence"))
    print(f"nodes={total} concurrency={concurrency} delay={args.delay}m timeout={timeout}s")

    indices = list(range(total))
    if args.shuffle:
        random.shuffle(indices)

    def process(index: int) -> tuple[int, str, int, str]:
        acc = accounts[index]
        email_val = str(acc.get("email", ""))
        pwd_val = str(acc.get("password", ""))
        rc, stdout, stderr = _check_with_retry(email_val, pwd_val, timeout, retries)
        return index, email_val, rc, stdout if rc == 0 else stderr

    if concurrency == 1:
        for pos, index in enumerate(indices):
            if stop_event.is_set():
                break
            acc = accounts[index]
            email_val = str(acc.get("email", ""))
            pwd_val = str(acc.get("password", ""))
            print(f"\n{color.bold('=' * 50)}")
            print(f"{color.cyan(f'[>] NODE [{pos + 1}/{total}]')} {email_val}")
            print("  [*] authenticating and checking quota...")
            rc, stdout, stderr = _check_with_retry(email_val, pwd_val, timeout, retries)
            if rc == 0:
                acc["status"] = "Active"
                success += 1
                print(f"  {color.green('[+] ACCESS GRANTED')}")
                for line in stdout.splitlines():
                    print(f"      {line.strip()}")
            else:
                acc["status"] = "Error"
                failed += 1
                print(f"  {color.red('[-] ACCESS DENIED / NETWORK FAILURE')}")
                if stderr:
                    print(f"      {stderr.splitlines()[0]}")
            save_accounts(args.db, accounts, backup=False)
            _clear_cache()
            if pos < total - 1 and delay_seconds > 0 and not stop_event.is_set():
                _countdown(delay_seconds, color, stop_event, args.no_interactive)
    else:
        batches = [indices[i : i + concurrency] for i in range(0, total, concurrency)]
        for batch_index, batch in enumerate(batches):
            if stop_event.is_set():
                break
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [executor.submit(process, i) for i in batch]
                for future in concurrent.futures.as_completed(futures):
                    index, email_val, rc, output = future.result()
                    acc = accounts[index]
                    pos = indices.index(index) + 1
                    print(f"\n{color.bold('=' * 50)}")
                    print(f"{color.cyan(f'[>] NODE [{pos}/{total}]')} {email_val}")
                    if rc == 0:
                        acc["status"] = "Active"
                        success += 1
                        print(f"  {color.green('[+] ACCESS GRANTED')}")
                        for line in output.splitlines():
                            print(f"      {line.strip()}")
                    else:
                        acc["status"] = "Error"
                        failed += 1
                        print(f"  {color.red('[-] ACCESS DENIED / NETWORK FAILURE')}")
                        if output:
                            print(f"      {output.splitlines()[0]}")
                    save_accounts(args.db, accounts, backup=False)
                    _clear_cache()
            if batch_index < len(batches) - 1 and delay_seconds > 0 and not stop_event.is_set():
                _countdown(delay_seconds, color, stop_event, args.no_interactive)

    print(f"\n{color.bold('=' * 50)}")
    print(f"{color.cyan('    MAINTENANCE SEQUENCE COMPLETED')}")
    print(f"{color.bold('=' * 50)}")
    print(f"  total nodes checked : {total}")
    print(f"  {color.green('[+] successful nodes : ' + str(success))}")
    print(f"  {color.red('[-] failed nodes      : ' + str(failed))}")
    print(f"{color.bold('=' * 50)}")
    return 0 if failed == 0 else 1


def doctor(color: Color, db_path: Path) -> int:
    print(f"{color.cyan('M-Keeper doctor')}")
    print(f"python     : {sys.version.split()[0]} ({platform.system()})")
    megatools = shutil.which("megatools")
    print(f"megatools  : {megatools or color.red('NOT FOUND')}")
    db = db_path
    print(f"database   : {db} ({'exists' if db.exists() else 'not created yet'})")
    if db.exists():
        try:
            data = json.loads(db.read_text(encoding="utf-8"))
            print(f"nodes      : {len(data) if isinstance(data, list) else 'invalid'}")
        except (OSError, ValueError) as exc:
            print(color.red(f"database error: {exc}"))
    if megatools is None:
        return 1
    try:
        result = subprocess.run([megatools, "--version"], capture_output=True, text=True, timeout=10)
        print(f"version    : {result.stdout.strip().splitlines()[0] if result.stdout else result.stderr.strip()}")
    except (OSError, subprocess.SubprocessError) as exc:
        print(color.red(f"megatools failed: {exc}"))
        return 1
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mega-keeper", description="Bulk Mega.nz node validation and maintenance.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--no-color", action="store_true", help="disable colored output")
    parser.add_argument("--json", action="store_true", help="print structured JSON where applicable")
    parser.add_argument("--quiet", "-q", action="store_true", help="reduce log output")
    parser.add_argument("--db", type=Path, default=DB_FILE, help="path to the account database")

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("status", help="show registered nodes")

    add_p = subparsers.add_parser("add", help="register a new node")
    add_p.add_argument("--email")
    add_p.add_argument("--password")

    remove_p = subparsers.add_parser("remove", help="remove a registered node")
    remove_p.add_argument("email")
    remove_p.add_argument("--yes", "-y", action="store_true", help="skip confirmation")

    import_p = subparsers.add_parser("import", help="import nodes from a JSON file")
    import_p.add_argument("path", type=Path)
    import_p.add_argument("--replace", action="store_true", help="replace the database instead of merging")

    export_p = subparsers.add_parser("export", help="export the database to a JSON file")
    export_p.add_argument("path", type=Path, nargs="?", default=Path("accounts.export.json"))

    subparsers.add_parser("doctor", help="check the local environment")

    start_p = subparsers.add_parser("start", help="run the maintenance sequence")
    start_p.add_argument("--delay", type=int, default=_env_int("MEGA_KEEPER_DELAY_MINUTES", DEFAULT_DELAY_MINUTES), help="minutes between nodes")
    start_p.add_argument("--timeout", type=int, default=_env_int("MEGA_KEEPER_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS), help="per-node timeout in seconds")
    start_p.add_argument("--retries", type=int, default=_env_int("MEGA_KEEPER_RETRIES", DEFAULT_RETRIES), help="attempts per node")
    start_p.add_argument("--concurrency", type=int, default=_env_int("MEGA_KEEPER_CONCURRENCY", 1), help="nodes processed in parallel")
    start_p.add_argument("--shuffle", action="store_true", help="process nodes in random order")
    start_p.add_argument("--no-interactive", action="store_true", help="disable interactive cooldown skipping")
    start_p.add_argument("--dry-run", action="store_true", help="print the sequence without contacting Mega")

    return parser.parse_args(argv)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    color = Color(enabled=(not args.no_color) and sys.stdout.isatty())
    setup_logging(quiet=args.quiet)

    command = args.command or "status"

    if command == "status":
        return print_status(color, args.db, as_json=args.json)
    if command == "add":
        return add_account(args.db, color, email=args.email, password=args.password)
    if command == "remove":
        return remove_account(args.db, args.email, assume_yes=args.yes, color=color)
    if command == "import":
        return import_accounts(args.db, args.path, merge=not args.replace)
    if command == "export":
        return export_accounts(args.db, args.path)
    if command == "doctor":
        return doctor(color, args.db)
    if command == "start":
        if args.dry_run:
            accounts = load_accounts(args.db)
            print(f"[dry-run] would check {len(accounts)} nodes (concurrency={args.concurrency})")
            return 0
        return keep_alive(args, color)

    print(f"Unknown command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
