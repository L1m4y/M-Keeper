import json
import os
import sys
import time
import subprocess
import getpass
import shutil
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "accounts.json")
DELAY_MINUTES = 5

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
    if not os.path.exists(DB_FILE): return[]
    try:
        with open(DB_FILE, "r") as f: return json.load(f)
    except: return[]

def save_accounts(data):
    with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)

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
            node_id = acc.get("password", "Unknown")
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

        res = subprocess.run(["megatools", "df", "--reload", "-u", email_val, "-p", pwd_val, "--human"], capture_output=True, text=True)

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

        save_accounts(accounts)
        force_logout()

        if i < total_nodes - 1:
            print(f"{C.YELLOW}[*] ENTERING STEALTH COOLDOWN TO ROTATE IP...{C.RESET}")
            if sys.stdout.isatty():
                for remaining in range(DELAY_MINUTES * 60, 0, -1):
                    sys.stdout.write(f"\r  {C.BOLD}DELAY: {remaining:04d}s{C.RESET}")
                    sys.stdout.flush()
                    time.sleep(1)
                sys.stdout.write("\n\n")
            else:

                random_delay = random.randint(60, 300)
                print(f"   [i] Next rotation in {random_delay}s (Stealth Mode)...")
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
