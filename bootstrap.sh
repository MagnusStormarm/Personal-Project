#!/usr/bin/env bash
# bootstrap.sh -- one-shot setup for a fresh Eldara Project Cloud Session.
#
# What this does:
#   1. Confirms this looks like the Eldara project (has scripts/session.py)
#   2. Runs `python3 scripts/session.py setup` -- installs requirements.txt
#      and the git pre-commit/pre-push hooks, exactly as documented in
#      README.md / LOCAL.md.
#   3. Runs `python3 scripts/session.py check` to confirm the session is
#      actually in a good state afterward.
#   4. Deletes itself.
#
# Usage (from the repo root, inside a fresh Cloud Session):
#   bash bootstrap.sh
#
# Safe to re-run if something above fails partway -- it doesn't touch
# saves/ or any campaign state, only the environment (deps + hooks).

set -euo pipefail

SCRIPT_PATH="$(readlink -f "$0" 2>/dev/null || realpath "$0" 2>/dev/null || echo "$0")"

cleanup() {
  # Always attempt self-deletion, whether setup succeeded or failed,
  # so a failed run doesn't leave a stray script cluttering the repo.
  if [ -f "$SCRIPT_PATH" ]; then
    rm -f -- "$SCRIPT_PATH"
  fi
}
trap cleanup EXIT

echo "== Eldara Project: Cloud Session bootstrap =="

if [ ! -f "scripts/session.py" ]; then
  echo "ERROR: scripts/session.py not found in the current directory."
  echo "Run this from the root of the cloned Eldara project repo."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is not available in this session."
  exit 1
fi

echo ""
echo "-- Step 1/2: python3 scripts/session.py setup --"
python3 scripts/session.py setup

echo ""
echo "-- Step 2/2: python3 scripts/session.py check --"
python3 scripts/session.py check

echo ""
echo "== Bootstrap complete. This script will now remove itself. =="
