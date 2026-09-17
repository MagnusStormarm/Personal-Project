#!/usr/bin/env python3
"""Rejects a turn's output if it writes the STATE_CHANGE:committed marker
without a real commit having actually happened FOR THIS TURN. Useful as
a manual check, or wired into an agentic coding tool's test command if
you're running one.

This checks two things:
  1. If the latest assistant output (passed on stdin, or read from a
     given path) contains the marker, the token embedded in the marker
     (e.g. "<!-- STATE_CHANGE:committed:47-a3f9c2 -->") must exactly
     match the "commit_token" field currently in saves/current.json.
  2. If it doesn't contain the marker, no check is needed -- turns that
     don't change state are allowed to skip the marker entirely.

The token is generated fresh by scripts/commit_state.py on every commit
and printed to stdout, so the marker can only match if the GM actually
ran the commit for this turn and copied its real output. See
docs/RECOVERY.md for further discussion.

Remaining limitation this does NOT close: a model could still fabricate
a plausible-looking token in its reply without ever having run the
commit script or seen real output. This script can only catch that if
the fabricated token happens not to match what's actually in
saves/current.json -- which it won't, since the token space is large
and the model has no way to predict it. But if a model chooses to
transcribe the exact token another way (e.g. it was leaked earlier in
context), this check alone can't prove the commit truly happened *this
turn* rather than being copied from an earlier turn's real output. This
is the honest-narrator problem, not the timing-vs-causation problem the
original design set out to fix -- see docs/RECOVERY.md.

Usage:
    python3 scripts/turn_gate.py <path-to-turn-output>
    (or pipe the turn's text on stdin with no argument)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURRENT_PATH = ROOT / "saves" / "current.json"
MARKER_PATTERN = re.compile(r"<!--\s*STATE_CHANGE:committed:([A-Za-z0-9_-]+)\s*-->")
# Recognize a marker with no token too, so old-format output fails with a
# clear, specific message instead of just not matching anything.
BARE_MARKER_PATTERN = re.compile(r"<!--\s*STATE_CHANGE:committed\s*-->")


def read_turn_text():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        return path.read_text(encoding="utf-8")
    return sys.stdin.read()


def load_current_token():
    if not CURRENT_PATH.exists():
        return None
    try:
        with open(CURRENT_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError, RecursionError):
        return None
    if not isinstance(state, dict):
        # JSON that parses successfully but isn't a dict at the top
        # level (e.g. a bare list) is treated the same as "no usable
        # token" -- the caller already handles a None token by failing
        # the turn gate with a clear message.
        return None
    return state.get("commit_token")


def main():
    text = read_turn_text()
    matches = list(MARKER_PATTERN.finditer(text))

    if not text.strip():
        # An empty pipe produced exactly the same "PASS: no STATE_CHANGE
        # marker present" as a genuine no-change turn, same exit code. A
        # caller whose redirection silently delivered nothing got a pass
        # that looked like a verification.
        print("FAIL: no turn text was supplied (empty input). The gate cannot "
              "tell an unchanged turn from a pipe that delivered nothing, so "
              "it refuses rather than passing. Pipe the turn's text in, or "
              "pass a file path.")
        sys.exit(1)

    if not matches:
        if BARE_MARKER_PATTERN.search(text):
            print(
                "FAIL: STATE_CHANGE marker present but missing its commit token. "
                "Write it as <!-- STATE_CHANGE:committed:<token> --> using the "
                "COMMIT_TOKEN value scripts/commit_state.py just printed."
            )
            sys.exit(1)
        print("PASS: no STATE_CHANGE marker present; no commit required for this turn.")
        sys.exit(0)

    if len(matches) > 1:
        # More than one marker in a single turn is itself a sign
        # something went wrong (a turn should commit at most once) --
        # e.g. a reply redrafted mid-turn without removing an earlier
        # marker. This fails outright and names every claimed token,
        # rather than resolving to whichever marker happens to appear
        # first in the text.
        claimed = [m.group(1) for m in matches]
        print(
            f"FAIL: {len(matches)} STATE_CHANGE markers found in this turn's output "
            f"(tokens: {', '.join(claimed)}) -- a turn should contain at most one. "
            "This usually means the reply was redrafted mid-turn without removing "
            "the earlier marker. Keep only the single marker matching the commit "
            "that actually corresponds to this turn."
        )
        sys.exit(1)

    claimed_token = matches[0].group(1)

    if not CURRENT_PATH.exists():
        print("FAIL: STATE_CHANGE marker present but saves/current.json does not exist.")
        sys.exit(1)

    actual_token = load_current_token()
    if actual_token is None:
        print(
            "FAIL: STATE_CHANGE marker present but saves/current.json has no "
            "commit_token field -- run scripts/session.py commit before writing "
            "the marker."
        )
        sys.exit(1)

    if claimed_token != actual_token:
        print(
            f"FAIL: STATE_CHANGE marker claims token '{claimed_token}' but "
            f"saves/current.json's actual commit_token is '{actual_token}'. "
            "This turn's commit does not match the claimed marker -- run "
            "scripts/session.py commit for this turn and copy its real "
            "COMMIT_TOKEN output before writing the marker."
        )
        sys.exit(1)

    print(f"PASS: STATE_CHANGE marker token '{claimed_token}' matches saves/current.json.")
    sys.exit(0)


if __name__ == "__main__":
    main()
