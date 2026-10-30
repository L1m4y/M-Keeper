# Mega-Keeper

Command-line tool for bulk Mega.nz node validation, maintenance and quota checks. It stores registered nodes in `accounts.json` with `0600` permissions and runs account checks one by one.

## Usage

```bash
python3 keeper.py status
python3 keeper.py add
python3 keeper.py start
```

## Environment

- `MEGA_KEEPER_DB`: custom account database path.
- `MEGA_KEEPER_DELAY_MINUTES`: delay between nodes (default: `5`).
- `MEGA_KEEPER_TIMEOUT_SECONDS`: timeout for each `megatools` check (default: `60`).
- Optional non-interactive mode automatically uses shorter random delays.

## Requirements

- Python 3.9+
- `megatools` installed and available in `PATH`.
- Python standard library only.

## Notes

- Registered emails and passwords are stored locally and should never be committed.
- `accounts.json`, `.tmp` files and local caches remain git-ignored.
