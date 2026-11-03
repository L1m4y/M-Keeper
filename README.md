<br/>

<div align="center">

<img src="assets/icon.png" alt="M-Keeper" width="192"/>

<h1>M-Keeper</h1>

**Command-line tool for bulk Mega.nz account validation, quota checks and periodic activity.**

A local utility that logs in to each registered Mega.nz account through `megatools`, reports quota usage and keeps the account active to prevent data deletion.

[![Python](https://img.shields.io/badge/Python-3.9%2B-D9272E?logo=python&logoColor=FFFFFF)](https://www.python.org/)
[![Bash](https://img.shields.io/badge/Bash-5-D9272E?logo=gnu-bash&logoColor=FFFFFF)](https://www.gnu.org/software/bash/)
[![Node.js](https://img.shields.io/badge/Node.js-18%2B-D9272E?logo=node.js&logoColor=FFFFFF)](https://nodejs.org/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-D9272E?logo=gnu&logoColor=FFFFFF)](LICENSE)

</div>

## How it works

M-Keeper wraps [`megatools`](https://github.com/crass/megatools). For every node it writes a short-lived `megatools` configuration file with mode `0600`, runs:

```bash
megatools df --reload --human --ignore-config-file --config <tmp> --no-ask-password
```

and removes the configuration file as soon as the command finishes. A successful login marks the node as `Active`; a failed login or network error marks it as `Error`.

MEGA accounts themselves do not expire, but MEGA may delete the data of free accounts after an extended period of inactivity. According to [MEGA's help centre](https://help.mega.io/accounts/create-account/account-expiry), the process takes at least 10 months from the last activity, and logging in at any point stops it. Running `start` periodically keeps the activity timer fresh.

## Installation

```bash
git clone https://github.com/L1m4y/M-Keeper.git
cd M-Keeper
```

The scripts run directly from the checkout; no package installation is required.

Requirements:

- Python 3.9+ (reference implementation)
- `megatools` installed and available in `PATH`
- `jq` for the Bash implementation

## Dependencies

Install the runtime and all helper tools in one command per distribution. These
commands also install the optional Node.js and Rust toolchains; omit them if you
only need the Python implementation.

- Arch Linux (pacman)
  ```bash
  sudo pacman -Syu --noconfirm megatools python jq nodejs rust
  ```

- Debian / Ubuntu (apt)
  ```bash
  sudo apt update && sudo apt install -y megatools python3 jq nodejs cargo rustc
  ```

- Fedora (dnf)
  ```bash
  sudo dnf install -y megatools python3 jq nodejs cargo rust
  ```

- openSUSE (zypper)
  ```bash
  sudo zypper --non-interactive install megatools python3 jq nodejs rust cargo
  ```

## Quick start

```bash
cp accounts.example.json accounts.json
python3 keeper.py add            # register a node interactively
python3 keeper.py status         # list nodes and their status
python3 keeper.py start          # run the maintenance sequence
python3 keeper.py doctor         # check the local environment
```

Non-interactive helpers:

```bash
python3 keeper.py add --email you@example.com --password 'correct horse battery'
python3 keeper.py remove you@example.com --yes
python3 keeper.py export accounts.backup.json
python3 keeper.py import accounts.backup.json
python3 keeper.py start --delay 3 --timeout 45 --concurrency 2 --shuffle --dry-run
```

Useful global flags:

```bash
python3 keeper.py --db /path/to/accounts.json status
python3 keeper.py --json status
python3 keeper.py --no-color status
python3 keeper.py --quiet start
```

The Bash and Node.js implementations expose the same core commands:

```bash
bash bin/keeper.sh status
bash bin/keeper.sh add
bash bin/keeper.sh start
bash bin/keeper.sh doctor

node bin/keeper.js status
node bin/keeper.js add
node bin/keeper.js start
node bin/keeper.js doctor
```

The Rust binary is an environment-check helper:

```bash
cd rust/m-keeper-cli
cargo run --release -- doctor
```

## Database schema

```json
[
  {
    "email": "user@example.com",
    "password": "correct horse battery",
    "status": "Pending"
  }
]
```

Status values are `Pending`, `Active` or `Error`. The password is stored in clear
text; restrict file permissions and do not commit the database. M-Keeper creates
the database and its backups with mode `0600`, and ignores common export/backup
names in `.gitignore`.

## Behaviour notes

- A node is retried when `--retries` is greater than `1` (default is `1`, so no retry).
- `megatools` stores its session cache in the system temporary directory as
  `<sha1(lowercase email)>.megatools.cache`. M-Keeper removes the cache file for
  the node it just checked instead of deleting unrelated caches.
- When standard input is a TTY, the cooldown can be skipped by pressing ENTER
  after the first five seconds.
- In non-interactive mode the configured delay is used as-is; `SIGINT`/`SIGTERM`
  interrupt the wait immediately.
- `SIGINT`/`SIGTERM` stop the run after the node in progress finishes.
- In parallel mode each batch runs concurrently and the cooldown is applied
  between batches.

## Development

```bash
python -m compileall -q keeper.py
python -m unittest tests.test_keeper -v
node --check bin/keeper.js
bash -n bin/keeper.sh
cd rust/m-keeper-cli && cargo build --release && cargo test
```

Or run everything through `make test`.

## &#8203;

Use it at your own risk. Review `keeper.py` and `bin/keeper.sh` before running it
against your main machine. Keep `accounts.json` private: it contains plain-text
credentials.
