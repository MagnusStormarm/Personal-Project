#!/usr/bin/env python3
"""Replay every committed state in a set of campaign copies through two
versions of validate_state.py, and report what the newer one says that the
older one did not -- and, just as importantly, what it no longer says.

A fix verified only against synthetic inputs is verified against the
author's imagination. This replays real committed history instead. Against
the eight retained copies it swept 55 states and earned its place: the
unpriced-obligation warning turned out to fire on money the character
merely HELD ("...with 6 copper and no one inside who knows him"), not only
on debts -- which the original 26-text calibration missed, because it asked
whether a price could be found and never whether it was that thread's
price.

The second half of the report matters as much as the first. A fix that
silently stops raising an old finding has removed a check; that appears
here under the "no longer" heading rather than as nothing at all.

Each state is written into its own copy's saves/ before validating, so
companion paths (npc_registry.json, locations.json) resolve to that
campaign rather than this one.

Tier 0: no nested sessions, no model calls, nothing against the rate limit.

Usage:
    git show <sha>:eldara/scripts/validate_state.py > /tmp/before.py
    python3 scripts/sweep_history.py            # defaults to /tmp/validate_before.py
"""
import json, subprocess, sys, glob, os, tempfile, collections
import os as _os
NEW = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "validate_state.py")
OLD = sys.argv[1] if len(sys.argv) > 1 else "/tmp/validate_before.py"

def _require(script, label):
    """A missing comparison script must not yield a silent empty set.

    findings() returns a set parsed from stdout, so a nonexistent baseline
    produced an empty set for every state: every new finding read as new,
    and the regression half printed "(none -- nothing was silently
    dropped)" while having compared against nothing at all. That is the
    exact shape this script exists to catch, in the script itself.
    """
    if not os.path.exists(script):
        sys.exit(f"FAIL: {label} validator not found at {script}. Extract one "
                 f"with `git show <sha>:eldara/scripts/validate_state.py > "
                 f"{script}` -- comparing against a missing file would report "
                 f"every finding as new and every regression as absent.")


def findings(script, path, cwd):
    r = subprocess.run([sys.executable, script, path], cwd=cwd,
                       capture_output=True, text=True, timeout=60)
    out = (r.stdout + r.stderr)
    return {l.strip().lstrip("- ").strip() for l in out.splitlines()
            if l.strip().startswith("-") or "WARNING" in l}

_require(NEW, "current"); _require(OLD, "baseline")

copies = sorted(glob.glob("/tmp/eldara-chain-*/eldara")) + sorted(glob.glob("/tmp/eldara-stress-*/eldara"))
states = 0
new_only = collections.Counter()
old_only = collections.Counter()
examples = {}

for d in copies:
    name = d.split("/")[2][-8:]
    # every committed state in this copy's history
    log = subprocess.run(["git", "log", "--format=%H", "--", "saves/current.json"],
                         cwd=d, capture_output=True, text=True).stdout.split()
    for sha in log:
        blob = subprocess.run(["git", "show", f"{sha}:saves/current.json"],
                              cwd=d, capture_output=True, text=True).stdout
        if not blob.strip():
            continue
        # write into the copy's own saves/ so companion paths resolve there
        tmp = os.path.join(d, "saves", "_sweep.json")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(blob)
        try:
            st = json.loads(blob)
        except json.JSONDecodeError:
            continue
        states += 1
        fn = findings(NEW, tmp, d)
        fo = findings(OLD, tmp, d)
        for x in fn - fo:
            key = x.split("'")[0].strip()[:70] if "'" in x else x[:70]
            new_only[key] += 1
            examples.setdefault(key, (name, st.get("turn"), x))
        for x in fo - fn:
            key = x.split("'")[0].strip()[:70] if "'" in x else x[:70]
            old_only[key] += 1
            examples.setdefault("OLD:" + key, (name, st.get("turn"), x))
        os.remove(tmp)

print(f"Swept {states} committed states across {len(copies)} campaign copies.\n")
print("FINDINGS THE NEW CHECKS RAISE THAT THE OLD ONES DID NOT:")
for k, n in new_only.most_common():
    who, turn, ex = examples[k]
    print(f"  [{n:>3}x] {k}")
    print(f"         e.g. {who} turn {turn}: {ex[:150]}")
print("\nFINDINGS THE OLD CHECKS RAISED THAT THE NEW ONES NO LONGER DO:")
if not old_only:
    print("  (none -- nothing was silently dropped)")
for k, n in old_only.most_common():
    who, turn, ex = examples["OLD:" + k]
    print(f"  [{n:>3}x] {k}")
    print(f"         e.g. {who} turn {turn}: {ex[:150]}")
