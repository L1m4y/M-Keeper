import json
import os
from pathlib import Path
import sys
import time
import subprocess
import getpass
import shutil
import random

def get_delay_minutes():
    try:
        return max(0, int(os.environ.get("MEGA_KEEPER_DELAY_MINUTES", "5")))
    except (TypeError, ValueError):
        return 5

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = Path(os.environ.get("MEGA_KEEPER_DB", str(BASE_DIR / "accounts.json")))
DELAY_MINUTES = get_delay_minutes()


def get_command_timeout():
    try:
        return max(10, int(os.environ.get("MEGA_KEEPER_TIMEOUT_SECONDS", "60")))
    except (TypeError, ValueError):
        return 60


def check_node(email, secret):
    try:
        return subprocess.run(
            ["megatools", "df", "--reload", "-u", email, "-p", secret, "--human"],
            capture_output=True,
            text=True,
            timeout=get_command_timeout(),
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args=[], returncode=124, stdout="", stderr="megatools timed out")
    except OSError as exc:
        return subprocess.CompletedProcess(args=[], returncode=127, stdout="", stderr=str(exc) or "megatools failed to start")

class C:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

ASCII_ART = r"""
▗▖  ▗▖▗▄▄▄▖ ▗▄▄▖ ▗▄▖ ▗▖ ▗▖▗▄▄▄▖▗▄▄▄▖▗▄▄▖ ▗▄▄▄▖▗▄▄▖
▐▛▚▞▜▌▐▌   ▐▌   ▐▌ ▐▌▐▌▗▞▘▐▌   ▐▌   ▐▌ ▐▌▐▌   ▐▌ ▐▌
▐▌  ▐▌▐▛▀▀▘▐▌▝▜▌▐▛▀▜▌▐▛▚▖ ▐▛▀▀▘▐▛▀▀▘▐▛▀▘ ▐▛▀▀▘▐▛▀▚▖
▐▌  ▐▌▐▙▄▄▖▝▚▄▞▘▐▌ ▐▌▐▌ ▐▌▐▙▄▄▖▐▙▄▄▖▐▌   ▐▙▄▄▖▐▌ ▐▌
"""

def print_header():
    print(f"{C.CYAN}{C.BOLD}{ASCII_ART}{C.RESET}")
    print(f"{C.CYAN}   :: v0.6.5 by L1m4y ::{C.RESET}\n")

def animate_task(task_name, duration=1.5):
    if sys.stdout.isatty():
        steps = 20
        sys.stdout.write(f"{C.CYAN}[*] {task_name}{C.RESET}\n")
        for i in range(steps + 1):
            percent = int((i / steps) * 100)
            bar = "█" * i + "-" * (steps - i)
            sys.stdout.write(f"\r  {C.BOLD}[{bar}] {percent}%{C.RESET}")
            sys.stdout.flush()
            time.sleep(duration / steps)
        sys.stdout.write("\n")
    else:
        print(f"[*] {task_name}... DONE")
        time.sleep(duration)

def force_logout():
    animate_task("TERMINATING SESSION & PURGING LOCAL CACHE", 1.5)
    cache_dir = os.path.expanduser("~/.cache/megatools")
    if os.path.exists(cache_dir):
        shutil.rmtree(cache_dir, ignore_errors=True)
    print(f"  {C.GREEN}[+] LOGOUT SUCCESSFUL. TRACES WIPED.{C.RESET}\n")

def load_accounts():
    if not DB_FILE.exists():
        return []
    try:
        with DB_FILE.open(encoding="utf-8") as handle:
            return [item for item in json.load(handle) if isinstance(item, dict)]
    except (OSError, ValueError):
        return []

def save_accounts(data):
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DB_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=4)
    tmp.replace(DB_FILE)
    try:
        os.chmod(DB_FILE, 0o600)
    except OSError:
        pass

def list_status():
    print_header()
    accounts = load_accounts()
    print(f"{C.BOLD}>>> REGISTERED NODES <<<{C.RESET}")
    print("=" * 65)
    h_node = "TARGET NODE"
    h_status = "STATUS"
    print(f"{h_node:<40} | {h_status:<10}")
    print("-" * 65)

    if not accounts:
        print(f"  {C.RED}[!] NO NODES REGISTERED IN THE MAINFRAME.{C.RESET}")
    else:
        for acc in accounts:
            node_id = acc.get("email", "Unknown")
            status = acc.get("status", "Pending")
            color = C.GREEN if status == "Active" else C.RED if status == "Error" else C.YELLOW
            print(f"{node_id:<40} | {color}[ {status.upper()} ]{C.RESET}")

    print("=" * 65)
    print(f"[i] TYPE: mega-keeper start (To initiate sequence)\n")

def add_account():
    print_header()
    print(f"{C.BOLD}>>> ADD NEW STORAGE NODE <<<{C.RESET}")
    email = input(f" {C.CYAN}[?] Mega Email:{C.RESET} ").strip()
    password = getpass.getpass(f" {C.CYAN}[?] Password/Code (Hidden):{C.RESET} ").strip()

    if email and password:
        accounts = load_accounts()
        accounts.append({"email": email, "password": password, "status": "Pending"})
        save_accounts(accounts)
        print(f"\n{C.GREEN}[+] NODE SECURELY REGISTERED IN DATABASE.{C.RESET}")

def keep_alive():
    print_header()
    accounts = load_accounts()

    if not accounts:
        print(f"{C.RED}[!] NO TARGETS FOUND. ABORTING.{C.RESET}")
        return

    total_nodes = len(accounts)
    success_count = 0
    fail_count = 0

    print(f"{C.YELLOW}[*] INITIATING MAINTENANCE SEQUENCE...{C.RESET}\n")

    for i, acc in enumerate(accounts):
        email_val = acc.get("email")
        pwd_val = acc.get("password")

        print(f"{C.BOLD}" + "="*55 + f"{C.RESET}")
        print(f"{C.CYAN}[>] TARGET NODE [{i+1}/{total_nodes}]:{C.RESET} {pwd_val}")
        print(f"  [*] AUTHENTICATING & CHECKING QUOTA...")

        res = check_node(email_val, pwd_val)
        if res.returncode != 0:
            time.sleep(2)
            res = check_node(email_val, pwd_val)

        if res.returncode == 0:
            acc["status"] = "Active"
            success_count += 1
            print(f"  {C.GREEN}[+] ACCESS GRANTED. QUOTA DATA:{C.RESET}")
            for line in res.stdout.strip().split("\n"):
                print(f"      {line.strip()}")
        else:
            acc["status"] = "Error"
            fail_count += 1
            print(f"  {C.RED}[-] ACCESS DENIED / NETWORK FAILURE.{C.RESET}")
            if getattr(res, "stderr", "").strip():
                print(f"      {res.stderr.strip().splitlines()[0]}")

        save_accounts(accounts)
        force_logout()

        if i < total_nodes - 1:
            wait_seconds = DELAY_MINUTES * 60
            if wait_seconds > 0:
                print(f"{C.YELLOW}[*] COOLDOWN BEFORE NEXT NODE (Enter after 5s to skip)...{C.RESET}")
                if sys.stdout.isatty():
                    remaining = wait_seconds
                    started = time.monotonic()
                    while remaining > 0:
                        sys.stdout.write(f"\r  {C.BOLD}DELAY: {remaining:04d}s{C.RESET}")
                        sys.stdout.flush()
                        elapsed = time.monotonic() - started
                        if elapsed >= 5:
                            try:
                                import select
                                ready, _, _ = select.select([sys.stdin], [], [], 0)
                                if ready:
                                    sys.stdin.readline()
                                    sys.stdout.write("\n")
                                    print(f"  {C.YELLOW}[*] COOLDOWN SKIPPED MANUALLY.{C.RESET}\n")
                                    break
                            except (OSError, ValueError):
                                pass
                        time.sleep(1)
                        remaining -= 1
                    sys.stdout.write("\n\n")
                else:
                    random_delay = random.randint(60, 300)
                    print(f"   [i] Next rotation in {random_delay}s...")
                    time.sleep(random_delay)

    print(f"\n{C.BOLD}" + "="*55 + f"{C.RESET}")
    print(f"{C.CYAN}    MAINTENANCE SEQUENCE COMPLETED{C.RESET}")
    print(f"{C.BOLD}" + "="*55 + f"{C.RESET}")
    print(f"  [i] TOTAL NODES CHECKED : {total_nodes}")
    print(f"  {C.GREEN}[+] SUCCESSFUL NODES    : {success_count}{C.RESET}")
    print(f"  {C.RED}[-] FAILED NODES        : {fail_count}{C.RESET}")
    print(f"{C.BOLD}" + "="*55 + f"{C.RESET}\n")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "add": add_account()
    elif cmd == "list" or cmd == "status": list_status()
    elif cmd == "start": keep_alive()
