#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
VERSION="2.0.0"
DB_FILE="${MEGA_KEEPER_DB:-accounts.json}"
DELAY_MINUTES="${MEGA_KEEPER_DELAY_MINUTES:-5}"
TIMEOUT_SECONDS="${MEGA_KEEPER_TIMEOUT_SECONDS:-60}"
fail() { printf '[!] %s\n' "$*" >&2; exit 1; }
has() { command -v "$1" >/dev/null 2>&1; }
print_status() {
    [ -f "$DB_FILE" ] || { echo "[i] no database file: $DB_FILE"; return 0; }
    echo "Mega-Keeper $VERSION :: registered nodes"
    printf '%-40s | %s\n' "TARGET NODE" "STATUS"
    jq -r '.[] | "\(.email)\t\(.status)"' "$DB_FILE" 2>/dev/null |
        while IFS=$'\t' read -r email status; do
            printf '%-40s | %s\n' "$email" "$status"
        done
}
add_account() {
    printf '[?] Mega email: '; read -r email
    printf '[?] Password (hidden): '; read -rs password; echo
    [ -n "$email" ] && [ -n "$password" ] || fail "email and password are required"
    echo "$email" | grep -q '@' || fail "invalid email"
    if [ -f "$DB_FILE" ] && jq -e --arg e "$email" 'any(.[]; .email == $e)' "$DB_FILE" >/dev/null; then
        echo "[!] NODE ALREADY REGISTERED."; return 0
    fi
    tmp="$(mktemp)"
    if [ -f "$DB_FILE" ]; then
        jq --arg e "$email" --arg p "$password" '. + [{"email":$e,"password":$p,"status":"Pending"}]' "$DB_FILE" > "$tmp"
    else
        printf '[{"email":%s,"password":%s,"status":"Pending"}]\n' \
            "$(printf '%s' "$email" | jq -R .)" "$(printf '%s' "$password" | jq -R .)" > "$tmp"
    fi
    mv "$tmp" "$DB_FILE"; chmod 600 "$DB_FILE"; echo "[+] NODE SECURELY REGISTERED."
}
check_node() {
    local email="$1" password="$2" cfg rc out err
    cfg="$(mktemp)"; printf '[Login]\nUsername = %s\nPassword = %s\n' "$email" "$password" > "$cfg"
    chmod 600 "$cfg"; out="$(mktemp)"; err="$(mktemp)"
    set +e; timeout "$TIMEOUT_SECONDS" megatools df --reload --human --config "$cfg" --no-ask-password >"$out" 2>"$err"; rc=$?; set -e
    rm -f "$cfg"
    if [ "$rc" -ne 0 ]; then printf '[%s] %s\n' "$rc" "$(head -n1 "$err")" >&2; else cat "$out"; fi
    rm -f "$out" "$err"; return "$rc"
}
keep_alive() {
    [ -f "$DB_FILE" ] || fail "no database file: $DB_FILE"
    total="$(jq 'length' "$DB_FILE")"; [ "$total" -gt 0 ] || fail "NO TARGETS FOUND. ABORTING."
    echo "Mega-Keeper $VERSION :: maintenance sequence (bash)"; echo "nodes=$total delay=${DELAY_MINUTES}m timeout=${TIMEOUT_SECONDS}s"
    for ((idx=0; idx<total; idx++)); do
        email="$(jq -r ".[$idx].email" "$DB_FILE")"
        password="$(jq -r ".[$idx].password" "$DB_FILE")"
        echo "----------------------------------------"; echo "[>] NODE [$((idx+1))/$total]: $email"; echo "  [*] authenticating and checking quota..."
        if check_node "$email" "$password"; then
            jq ".[$idx].status = \"Active\"" "$DB_FILE" > "$DB_FILE.tmp" && mv "$DB_FILE.tmp" "$DB_FILE"; chmod 600 "$DB_FILE"; echo "  [+] ACCESS GRANTED"
        else
            jq ".[$idx].status = \"Error\"" "$DB_FILE" > "$DB_FILE.tmp" && mv "$DB_FILE.tmp" "$DB_FILE"; chmod 600 "$DB_FILE"; echo "  [-] ACCESS DENIED / NETWORK FAILURE"
        fi
        rm -rf "${HOME}/.cache/megatools"
        if [ "$idx" -lt $((total-1)) ]; then
            wait_seconds=$((DELAY_MINUTES * 60))
            [ "$wait_seconds" -gt 0 ] && { echo "[*] COOLDOWN: ${wait_seconds}s"; sleep "$wait_seconds"; }
        fi
    done
    echo "MAINTENANCE SEQUENCE COMPLETED"
}
doctor() {
    echo "Mega-Keeper doctor (bash)"; echo "bash       : $BASH_VERSION"
    if has megatools; then echo "megatools  : $(command -v megatools)"; else echo "megatools  : NOT FOUND"; fi
    if has jq; then echo "jq         : $(command -v jq)"; else echo "jq         : NOT FOUND"; fi
    echo "database   : $DB_FILE"
}
cmd="${1:-status}"; shift || true
case "$cmd" in
    status) print_status ;; add) add_account ;; doctor) doctor ;; start) keep_alive ;;
    --version|-V) echo "keeper.sh $VERSION" ;;
    --help|-h) cat <<EOF
Usage: bash keeper.sh [status|add|doctor|start]
Environment:
  MEGA_KEEPER_DB                  custom account database path
  MEGA_KEEPER_DELAY_MINUTES       delay between nodes (default: 5)
  MEGA_KEEPER_TIMEOUT_SECONDS     timeout per node (default: 60)
EOF
    ;;
    *) fail "unknown command: $cmd (try --help)" ;;
esac