#!/usr/bin/env python3
"""Helper for the pre-push hook: confirms saves/current.json both exists,
validates cleanly, and has no uncommitted local changes (which would mean
what's about to be pushed doesn't match what's on disk).

Exits 0 if everything checks out, non-zero otherwise.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CURRENT_PATH = ROOT / "saves" / "current.json"

sys.path.insert(0, str(ROOT / "scripts"))
from validate_state import run_validation  # noqa: E402


def has_uncommitted_changes():
    result = subprocess.run(
        ["git", "status", "--porcelain", "saves/current.json"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def main():
    if not CURRENT_PATH.exists():
        print("saves/current.json does not exist -- nothing to check.")
        sys.exit(0)

    if has_uncommitted_changes():
        print("saves/current.json has uncommitted local changes.")
        sys.exit(1)

    if not run_validation(CURRENT_PATH):
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
