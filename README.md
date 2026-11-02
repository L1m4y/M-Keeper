<div align="center">

<img src="assets/icon.png" alt="M-Keeper" width="160"/>

<h1>M-Keeper</h1>

Command-line tool for bulk Mega.nz account validation, maintenance and quota checks.

<br>

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-D9272E?logo=gnu&logoColor=FFFFFF)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-D9272E?logo=python&logoColor=FFFFFF)](https://www.python.org/)
[![Bash](https://img.shields.io/badge/Bash-5-D9272E?logo=gnu-bash&logoColor=FFFFFF)](https://www.gnu.org/software/bash/)
[![Node.js](https://img.shields.io/badge/Node.js-18%2B-D9272E?logo=node.js&logoColor=FFFFFF)](https://nodejs.org/)
[![Linux](https://img.shields.io/badge/Linux-D9272E?logo=linux&logoColor=FFFFFF)](https://www.linux.org/)

</div>

`M-Keeper` iterates through a local list of Mega.nz accounts, authenticates each
one with `megatools`, prints quota information and updates the stored status.
It is meant to keep free accounts from becoming inactive, without leaking
credentials on the process list.

## Installation

```bash
git clone https://github.com/L1m4y/M-Keeper.git
cd M-Keeper
The scripts run directly from the checkout; no package installation is required.
```

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

## Development

```bash
python -m compileall -q keeper.py
python -m unittest tests.test_keeper -v
node --check bin/keeper.js
bash -n bin/keeper.sh
cd rust/mega-keeper-cli && cargo build --release && cargo test
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

## Environment

| Variable | Description | Default |
|---|---|---|
| `MEGA_KEEPER_DB` | Account database path | `./accounts.json` |
| `MEGA_KEEPER_DELAY_MINUTES` | Delay between nodes | `5` |
| `MEGA_KEEPER_TIMEOUT_SECONDS` | Timeout per `megatools` call | `60` |
| `MEGA_KEEPER_RETRIES` | Attempts per node | `1` |
| `MEGA_KEEPER_CONCURRENCY` | Nodes processed in parallel | `1` |
| `MEGA_KEEPER_LOG` | Optional log file | stderr only |

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
text; restrict file permissions and do not commit the database.

## Behaviour notes

- A node is retried when the first `megatools` call fails.
- The `megatools` cache directory is cleared after every node to avoid stale state.
- When standard input is a TTY, the cooldown can be skipped by pressing ENTER
  after the first five seconds.
- In non-interactive mode the delay is randomised between 60 and 300 seconds.
- `SIGINT`/`SIGTERM` stop the current run after the node in progress finishes.

