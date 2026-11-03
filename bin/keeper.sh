#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
umask 077
STOP_REQUESTED=0
trap 'STOP_REQUESTED=1' INT TERM
VERSION="2.0.0"
DB_FILE="${M_KEEPER_DB:-accounts.json}"
DELAY_MINUTES="${M_KEEPER_DELAY_MINUTES:-5}"
TIMEOUT_SECONDS="${M_KEEPER_TIMEOUT_SECONDS:-60}"
fail() { printf '[!] %s\n' "$*" >&2; exit 1; }
has() { command -v "$1" >/dev/null 2>&1; }
require_jq() { has jq || fail "jq is required for the Bash implementation"; }
clear_cache() {
    local email="$1" digest
    digest="$(printf '%s' "$email" | tr '[:upper:]' '[:lower:]' | sha1sum | cut -d' ' -f1)"
    rm -f "${TMPDIR:-/tmp}/${digest}.megatools.cache"
}
print_status() {
    require_jq
    [ -f "$DB_FILE" ] || { echo "[i] no database file: $DB_FILE"; return 0; }
    echo "M-Keeper $VERSION :: registered nodes"
    printf '%-40s | %s\n' "TARGET NODE" "STATUS"
    jq -r '.[] | "\(.email)\t\(.status)"' "$DB_FILE" 2>/dev/null |
        while IFS=$'\t' read -r email status; do
            printf '%-40s | %s\n' "$email" "$status"
        done
}
add_account() {
    require_jq
    printf '[?] Mega email: '; read -r email
    printf '[?] Password (hidden): '; read -rs password; echo
    [ -n "$email" ] && [ -n "$password" ] || fail "email and password are required"
    printf '%s' "$email" | grep -Eq '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' || fail "invalid email"
    if [ -f "$DB_FILE" ] && jq -e --arg e "$email" 'any(.[]; (.email // "") | ascii_downcase == ($e | ascii_downcase))' "$DB_FILE" >/dev/null; then
        echo "[!] NODE ALREADY REGISTERED."; return 0
    fi
    mkdir -p "$(dirname "$DB_FILE")"
    tmp="$(mktemp)"
    trap 'rm -f "$tmp"' EXIT
    if [ -f "$DB_FILE" ]; then
        jq --arg e "$email" --arg p "$password" '. + [{"email":$e,"password":$p,"status":"Pending"}]' "$DB_FILE" > "$tmp"
    else
        jq -n --arg e "$email" --arg p "$password" '[{"email":$e,"password":$p,"status":"Pending"}]' > "$tmp"
    fi
    chmod 600 "$tmp"; mv "$tmp" "$DB_FILE"; trap - EXIT; chmod 600 "$DB_FILE"; echo "[+] NODE SECURELY REGISTERED."
}
check_node() {
    local email="$1" password="$2" cfg rc out err escaped_password
    escaped_password="${password//\\/\\\\}"
    cfg="$(mktemp)"; printf '[Login]\nUsername = %s\nPassword = %s\n' "$email" "$escaped_password" > "$cfg"
    chmod 600 "$cfg"; out="$(mktemp)"; err="$(mktemp)"
    set +e; timeout "$TIMEOUT_SECONDS" megatools df --reload --human --ignore-config-file --config "$cfg" --no-ask-password >"$out" 2>"$err"; rc=$?; set -e
    rm -f "$cfg"
    if [ "$rc" -ne 0 ]; then printf '[%s] %s\n' "$rc" "$(head -n1 "$err")" >&2; else cat "$out"; fi
    rm -f "$out" "$err"; return "$rc"
}
keep_alive() {
    require_jq
    STOP_REQUESTED=0
    [ -f "$DB_FILE" ] || fail "no database file: $DB_FILE"
    total="$(jq 'length' "$DB_FILE")"; [ "$total" -gt 0 ] || fail "NO TARGETS FOUND. ABORTING."
    local checked=0 success=0 failed=0
    echo "M-Keeper $VERSION :: maintenance sequence (bash)"; echo "nodes=$total delay=${DELAY_MINUTES}m timeout=${TIMEOUT_SECONDS}s"
    for ((idx=0; idx<total; idx++)); do
        [ "$STOP_REQUESTED" -eq 0 ] || break
        email="$(jq -r ".[$idx].email" "$DB_FILE")"
        password="$(jq -r ".[$idx].password" "$DB_FILE")"
        echo "----------------------------------------"; echo "[>] NODE [$((idx+1))/$total]: $email"; echo "  [*] authenticating and checking quota..."
        if check_node "$email" "$password"; then
            jq ".[$idx].status = \"Active\"" "$DB_FILE" > "$DB_FILE.tmp" && mv "$DB_FILE.tmp" "$DB_FILE"; chmod 600 "$DB_FILE"; echo "  [+] ACCESS GRANTED"; success=$((success + 1))
        else
            jq ".[$idx].status = \"Error\"" "$DB_FILE" > "$DB_FILE.tmp" && mv "$DB_FILE.tmp" "$DB_FILE"; chmod 600 "$DB_FILE"; echo "  [-] ACCESS DENIED / NETWORK FAILURE"; failed=$((failed + 1))
        fi
        checked=$((checked + 1))
        clear_cache "$email"
        if [ "$idx" -lt $((total-1)) ]; then
            wait_seconds=$((DELAY_MINUTES * 60))
            if [ "$wait_seconds" -gt 0 ]; then
                echo "[*] COOLDOWN: ${wait_seconds}s"
                while [ "$wait_seconds" -gt 0 ] && [ "$STOP_REQUESTED" -eq 0 ]; do
                    sleep 1 || true
                    wait_seconds=$((wait_seconds - 1))
                done
            fi
        fi
    done
    if [ "$STOP_REQUESTED" -eq 1 ]; then
        echo "MAINTENANCE SEQUENCE INTERRUPTED"
    else
        echo "MAINTENANCE SEQUENCE COMPLETED"
    fi
    echo "  total nodes registered : $total"
    echo "  total nodes checked    : $checked"
    echo "  [+] successful nodes   : $success"
    echo "  [-] failed nodes       : $failed"
    [ "$checked" -eq "$total" ] || echo "  [!] nodes skipped      : $((total - checked))"
    [ "$failed" -eq 0 ] && [ "$checked" -eq "$total" ] && [ "$STOP_REQUESTED" -eq 0 ] || return 1
}
doctor() {
    echo "M-Keeper doctor (bash)"; echo "bash       : $BASH_VERSION"
    if has megatools; then echo "megatools  : $(command -v megatools)"; else echo "megatools  : NOT FOUND"; fi
    if has jq; then echo "jq         : $(command -v jq)"; else echo "jq         : NOT FOUND"; fi
    echo "database   : $DB_FILE ($([ -f "$DB_FILE" ] && echo exists || echo 'not created yet'))"
    if has jq && [ -f "$DB_FILE" ]; then
        echo "nodes      : $(jq 'length' "$DB_FILE" 2>/dev/null || echo invalid)"
    fi
}
cmd="${1:-status}"; shift || true
case "$cmd" in
    status) print_status ;; add) add_account ;; doctor) doctor ;; start) keep_alive ;;
    --version|-V) echo "keeper.sh $VERSION" ;;
    --help|-h) cat <<EOF
Usage: bash keeper.sh [status|add|doctor|start]
Environment:
  M_KEEPER_DB                     custom account database path
  M_KEEPER_DELAY_MINUTES          delay between nodes (default: 5)
  M_KEEPER_TIMEOUT_SECONDS        timeout per node (default: 60)
EOF
    ;;
    *) fail "unknown command: $cmd (try --help)" ;;
esac