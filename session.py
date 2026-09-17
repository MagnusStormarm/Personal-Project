#!/usr/bin/env python3
"""Single entry point for running The Eldara Project's mechanical side.
Designed around this project's actual deployment target: a Claude Code
session (Claude PC directly, or Claude iOS via Remote Control or a Cloud
Session -- see LOCAL.md) that has direct filesystem, shell, and git
access to this repository, in the same conversation where narration
happens. Neither a Remote Control session's host computer nor a Cloud
Session's runtime is guaranteed to run unattended forever, so nothing in
this script assumes background execution; the actual narration and the
mechanical commands below happen in the same session, but this script
still can't decide what happens in the story -- see docs/OPERATING.md for
why that boundary is real, not a gap in this script.

Subcommands:
    python3 scripts/session.py setup     One-time setup for a freshly
                                          cloned repo: installs Python
                                          dependencies from requirements.txt
                                          and the git pre-commit/pre-push
                                          hooks. Run this once right after
                                          cloning, before 'check'.

    python3 scripts/session.py check     Environment + repo sanity check
                                          (git, python deps, hooks, schema).
                                          Run any time to confirm the
                                          session is in a good state.

    python3 scripts/session.py start     Validates current state and prints
                                          a status summary. Safe to run
                                          any time.

    python3 scripts/session.py commit FILE [--note "..."]
            [--critique-file PATH | --critique-text "..." | --critique-stdin]
            [--skip-critique]
                                          Wraps commit_state.py: validates
                                          a proposed state file and, if
                                          it passes, promotes it, backs up
                                          the old one (pruning old backups
                                          beyond the most recent 30),
                                          updates the NPC registry,
                                          journals the diff, and commits
                                          to git if this is a repo --
                                          pushing to a remote automatically
                                          if one is configured.

                                          Whenever FILE is given (a real
                                          turn), self_critique.py MUST run
                                          clean against that turn's drafted
                                          narration before the commit is
                                          accepted -- this is mandatory,
                                          not optional. Supply the
                                          narration text one of three ways:
                                            --critique-file PATH   a file
                                              already on this machine
                                            --critique-text "..."  the
                                              text directly, inline --
                                              no separate file needed
                                            --critique-stdin       piped
                                              in on stdin
                                          Pass --skip-critique instead to
                                          deliberately bypass the gate for
                                          this one commit (confirmed false
                                          positive, or no real prose this
                                          turn). This is the one command
                                          to run after every state-changing
                                          turn.

    python3 scripts/session.py audit     Runs the full combined three-pass
                                          playtest_audit.py report.

    python3 scripts/session.py gm-cases  Lists the GM's situational cases
            [--due] [--category C]        (trigger -> required action) from
            [--check-sources] [QUERY]     docs/gm_cases.json, each tagged
                                          with the prompts/GM_INSTRUCTIONS.md
                                          heading it came from. --due narrows
                                          to the ones mechanically live
                                          against saves/current.json right
                                          now (turn 0, a multiple-of-20 turn,
                                          an array at its soft cap, a passed
                                          deadline, travel in progress,
                                          perishables held). Read-only and
                                          safe mid-scene. Also reachable as
                                          'list-gm-cases'.

    python3 scripts/session.py earn-coverage [--dry-run] [--audit-only]
                                          Wraps scripts/earn_clean_slate.py:
                                          plays 11 fixed, schema-valid turns
                                          through the REAL commit_state.py
                                          pipeline (real validation, real
                                          self_critique.py gate, real git
                                          commits) -- each turn targets one
                                          specific Pass-1 coverage check that
                                          hasn't fired yet -- then runs the
                                          full audit. This earns Pass-1
                                          coverage honestly; it does not
                                          fake or hardcode any result, and
                                          it will stop and report exactly
                                          why if any turn is rejected.

                                          Refuses to run if saves/current.json
                                          is already past turn 0, to avoid
                                          overwriting real campaign history --
                                          only ever run this against a fresh
                                          or throwaway clone, never a live
                                          campaign. --dry-run shows the
                                          planned turns without committing
                                          anything; --audit-only skips
                                          playing turns and just runs the
                                          real audit as-is (equivalent to
                                          plain 'audit' above).

    python3 scripts/session.py loop      Interactive loop: repeatedly
                                          prompts for a path to a proposed
                                          state file, commits it if valid,
                                          and after every commit re-runs
                                          the audit so drift signals
                                          surface immediately rather than
                                          only when someone remembers to
                                          ask. Exits on an empty input.

Typical usage in a Claude Code session (Claude PC, or Claude iOS via
Remote Control or a Cloud Session -- see LOCAL.md):
    git clone <repo-url> eldara_new && cd eldara_new
    git init   # if the clone didn't already initialize a repo
    python3 scripts/session.py setup
    python3 scripts/session.py check
    python3 scripts/session.py start
    # ... play a turn in this same session, draft the resulting state
    #     JSON directly here -- no separate file transfer needed ...
    python3 scripts/session.py commit /tmp/proposed_state.json --note "..." \\
        --critique-text "the turn's drafted narration, pasted straight in"
    python3 scripts/session.py audit
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
SAVES = ROOT / "saves"
CURRENT_PATH = SAVES / "current.json"
SCHEMA_PATH = ROOT / "state_schema.json"


def run(args, **kwargs):
    """Run a project script with this same Python interpreter and stream
    its output live rather than swallowing it -- these scripts are meant
    to be seen, not just checked for a return code."""
    result = subprocess.run([sys.executable, *args], cwd=ROOT, **kwargs)
    return result.returncode


def git_dir():
    """Resolve the actual .git directory for ROOT, wherever it lives --
    ROOT need not be the repo's top level (e.g. a project nested a
    subdirectory into a larger repo), so this can't just assume
    ROOT / ".git" exists. Returns None if ROOT isn't inside a git repo."""
    result = subprocess.run(["git", "rev-parse", "--absolute-git-dir"],
                             cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

def cmd_check(_args):
    print("=" * 70)
    print("ENVIRONMENT + REPO CHECK")
    print("=" * 70)

    ok = True

    print(f"\nPython: {sys.version.split()[0]} ({sys.executable})")

    print("\n-- git --")
    git_present = shutil.which("git") is not None
    print(f"  git on PATH: {'yes' if git_present else 'NO -- required for the commit pipeline'}")
    ok = ok and git_present
    if git_present:
        gdir = git_dir()
        is_repo = gdir is not None
        print(f"  this directory is a git repo: {'yes' if is_repo else 'no -- run: git init'}")
        if is_repo:
            hook_path = gdir / "hooks" / "pre-commit"
            installed = hook_path.exists() and "validate_state" in hook_path.read_text(encoding="utf-8")
            print(f"  pre-commit hook installed: {'yes' if installed else 'no -- run: python3 scripts/session.py setup'}")

    print("\n-- Python dependencies --")
    try:
        import jsonschema  # noqa: F401
        print("  jsonschema: installed (stricter schema validation active)")
    except ImportError:
        print("  jsonschema: NOT installed (validate_state.py still works via its")
        print("              own built-in manual checks -- this is a soft warning, not a failure)")
        print("              run: python3 scripts/session.py setup   to install it")

    print("\n-- Core files --")
    for p in [SCHEMA_PATH, CURRENT_PATH, SAVES / "journal.md", SAVES / "npc_registry.json",
              ROOT / "prompts" / "GM_INSTRUCTIONS.md"]:
        exists = p.exists()
        print(f"  {p.relative_to(ROOT)}: {'found' if exists else 'MISSING'}")
        ok = ok and exists

    print("\n-- Current state validity --")
    if CURRENT_PATH.exists():
        rc = run(["scripts/validate_state.py", str(CURRENT_PATH)])
        ok = ok and (rc == 0)
    else:
        print("  No saves/current.json yet -- fine for a brand-new campaign.")

    print("\n" + "=" * 70)
    if ok:
        print("CHECK PASSED. This machine is ready to run the project.")
    else:
        print("CHECK FOUND ISSUES -- see above. Run 'python3 scripts/session.py setup'")
        print("to fix the installable ones (hooks, dependencies) automatically.")
    print("=" * 70)
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------

def cmd_setup(_args):
    """One-time setup for a freshly cloned repo: installs Python
    dependencies and the git pre-commit/pre-push hooks."""
    print("=" * 70)
    print("SETUP")
    print("=" * 70)

    print("\n-- Python dependencies --")
    req_path = ROOT / "requirements.txt"
    if req_path.exists():
        pip_cmd = [sys.executable, "-m", "pip", "install", "-r", str(req_path)]
        rc = subprocess.run(pip_cmd).returncode
        if rc != 0:
            print("  Plain pip install failed (common on Debian/Ubuntu systems that")
            print("  externally manage Python -- PEP 668, and stock Ubuntu Server")
            print("  images are affected by this).")
            print("  On a computer you keep, a virtual environment is the better fix:")
            print("    python3 -m venv .venv && source .venv/bin/activate")
            print(f"    python3 -m pip install -r {req_path.name}")
            print("  Retrying with --break-system-packages. That installs into the")
            print("  system Python -- it is not project-scoped, whatever the flag's")
            print("  name suggests -- which is fine in a throwaway cloud sandbox and")
            print("  worth avoiding on a machine you rely on:")
            rc = subprocess.run([*pip_cmd, "--break-system-packages"]).returncode
            if rc != 0:
                print("  Still failed -- use the virtual environment shown above.")
    else:
        print("  No requirements.txt found; skipping.")

    print("\n-- Git hooks --")
    gdir = git_dir()
    if gdir is not None:
        hooks_dir = gdir / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        for hook_name in ("pre-commit", "pre-push"):
            src = SCRIPTS / "git-hooks" / hook_name
            dest = hooks_dir / hook_name
            if src.exists():
                # A plain copy isn't enough: the hook template contains
                # __ELDARA_PROJECT_ROOT__, which must be substituted for
                # this machine's actual ROOT before installing, since the
                # copied file (now living in .git/hooks/, possibly far
                # from ROOT if this project is nested in a larger repo)
                # has no other way to find it. See the hook files' own
                # comments for the full reasoning.
                content = src.read_text(encoding="utf-8")
                content = content.replace("__ELDARA_PROJECT_ROOT__", str(ROOT))
                dest.write_text(content, encoding="utf-8")
                dest.chmod(0o755)
                print(f"  Installed {hook_name}")
            else:
                print(f"  {src} not found -- skipping {hook_name}")
    else:
        print("  Not a git repository yet. Run 'git init' first, then re-run this command")
        print("  to install the hooks.")

    print("\nSetup complete. Run 'python3 scripts/session.py check' to verify.")
    print("\nOptional: if this is a brand-new, throwaway campaign (turn 0, no")
    print("real play yet) and you want to confirm the full commit/validation")
    print("pipeline actually works end-to-end on this machine before playing")
    print("for real, run:")
    print("  python3 scripts/session.py earn-coverage")
    print("This is NEVER run automatically. 'python3 scripts/session.py start'")
    print("will OFFER it (with an explicit y/N prompt, defaulting to no) the")
    print("next time you run it, but only if this repo still looks genuinely")
    print("never-played -- pristine turn-0 state, empty journal, no backups,")
    print("no commits beyond this initial one. Once any of those changes, the")
    print("offer stops appearing and earn-coverage also refuses to run on its")
    print("own. The safer habit either way is to only ever run it against a")
    print("throwaway clone, never the campaign you actually intend to play.")
    return 0


def _is_pristine_baseline_state(state):
    """True only if saves/current.json matches the exact turn-0 baseline
    byte-for-byte in the fields that matter -- not just turn == 0, which
    a hand-edited or partially-restored file could also satisfy without
    actually being a fresh, never-played campaign."""
    if state.get("turn") != 0:
        return False
    baseline_gear_names = {"T-shirt", "Jeans", "Underwear", "Socks", "Shoes"}
    gear_names = {g.get("name") for g in state.get("gear", [])}
    if gear_names != baseline_gear_names:
        return False
    if any(v not in (0, None) for v in state.get("currency", {}).values()):
        return False
    # Any of these having content at all means something has already
    # happened, even if turn/gear/currency were somehow reset afterward.
    for field in ("status", "magic", "entities", "factions",
                  "npc_relationships", "open_threads", "continuity_notes",
                  "throughline"):
        if state.get(field):
            return False
    return True


def _looks_like_never_played_repo():
    """Narrower than 'turn is 0' on its own: checks state, journal, git
    history, AND backups together, since each is a different way a
    reset-looking repo could still carry real history. All four must
    agree this repo has genuinely never been played through the real
    pipeline before earn-coverage is even offered -- turn==0 alone is
    not a safe enough signal by itself."""
    if not CURRENT_PATH.exists():
        return False
    try:
        with open(CURRENT_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError, RecursionError):
        return False
    if not _is_pristine_baseline_state(state):
        return False

    journal_path = SAVES / "journal.md"
    if journal_path.exists():
        journal_text = journal_path.read_text(encoding="utf-8")
        # The pristine journal ships with a header/instructions comment
        # (see saves/journal.md) but no turn entries -- commit_state.py's
        # append_journal() always writes a "### Turn N" heading per real
        # commit, so that heading's absence, not byte-emptiness, is the
        # real "never actually committed a turn" signal here.
        if re.search(r'^###\s+Turn\s+\d+', journal_text, re.MULTILINE):
            return False

    backups_dir = SAVES / "backups"
    if backups_dir.exists():
        # .gitkeep (or similar dotfile placeholders used to make git track
        # an otherwise-empty directory) is not a real backup -- only count
        # actual backup snapshots commit_state.py itself would have written.
        real_backups = [p for p in backups_dir.iterdir() if not p.name.startswith(".")]
        if real_backups:
            return False

    result = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                             cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        return False  # not a git repo at all -- earn-coverage needs git; don't offer it
    log = subprocess.run(["git", "log", "--oneline"],
                          cwd=ROOT, capture_output=True, text=True)
    commit_count = len([line for line in log.stdout.splitlines() if line.strip()])
    if commit_count > 1:
        return False

    return True


def _maybe_offer_earn_coverage():
    """Offers (never auto-runs) earn-coverage exactly once per invocation
    of 'start', and only when _looks_like_never_played_repo() confirms
    all four signals agree. Always requires an explicit 'y' -- silently
    does nothing on non-interactive stdin (e.g. piped input, cron-like
    invocation) rather than guessing, since a prompt that can't actually
    be answered must never be treated as an implicit yes."""
    if not _looks_like_never_played_repo():
        return
    print()
    print("This repo looks like a brand-new, never-played campaign (pristine")
    print("turn-0 state, empty journal, no backups, no commits beyond the")
    print("initial one). Optionally run 'earn-coverage' now to confirm the")
    print("full commit/validation pipeline actually works end-to-end on this")
    print("machine before you start playing for real -- see")
    print("'python3 scripts/session.py earn-coverage --help'.")
    try:
        answer = input("Run it now? [y/N]: ").strip().lower()
    except EOFError:
        print("(no input available -- skipping; run "
              "'python3 scripts/session.py earn-coverage' manually if you want it)")
        return
    if answer == "y":
        run(["scripts/earn_clean_slate.py"])
    else:
        print("Skipped. You can run 'python3 scripts/session.py earn-coverage' "
              "any time later -- it will refuse on its own once this repo is "
              "no longer pristine.")


def cmd_start(_args):
    print("=" * 70)
    print("SESSION START")
    print("=" * 70)

    if CURRENT_PATH.exists():
        run(["scripts/validate_state.py", str(CURRENT_PATH)])
        print()
        run(["scripts/status_dump.py"])
    else:
        print("No saves/current.json found -- this will be a brand-new campaign.")

    _maybe_offer_earn_coverage()

    print()
    print("Paste prompts/GM_INSTRUCTIONS.md (and prompts/FIRST_MESSAGE.md if this")
    print("is turn 0) into your chat interface to begin. This script cannot narrate")
    print("the story itself -- that step needs an actual LLM in the loop. See")
    print("docs/OPERATING.md for why that boundary exists.")
    return 0


# ---------------------------------------------------------------------------
# bootstrap
# ---------------------------------------------------------------------------

def cmd_bootstrap(args):
    """Runs setup, then check, then start, in one pass -- the exact
    sequence the README's Quick Start already documents as three
    separate commands. Stops at the first failure rather than plowing
    ahead: check assumes setup actually installed deps/hooks, and start
    assumes check confirmed those actually took.

    This does not replace bootstrap.sh -- that script has its own
    additional job (self-deleting once it's run, for a fresh Cloud
    Session -- see its own docstring). This exists so ANY environment,
    cloud or otherwise, has one command from a fresh clone to
    ready-to-play, instead of three."""
    print("=" * 70)
    print("BOOTSTRAP -- setup, check, start")
    print("=" * 70)
    rc = cmd_setup(args)
    if rc:
        return rc
    print()
    rc = cmd_check(args)
    if rc:
        print("\nBootstrap stopped: 'check' reported issues after setup. Fix them, "
              "then re-run 'python3 scripts/session.py bootstrap' (or just 'check').")
        return rc
    print()
    return cmd_start(args)


# ---------------------------------------------------------------------------
# commit
# ---------------------------------------------------------------------------

def cmd_commit(args):
    commit_args = ["scripts/commit_state.py"]
    if args.file:
        commit_args.append(args.file)
    if args.note:
        commit_args.extend(["--note", args.note])
    if args.critique_file:
        commit_args.extend(["--critique-file", args.critique_file])
    if args.critique_text:
        commit_args.extend(["--critique-text", args.critique_text])
    if args.critique_stdin:
        commit_args.append("--critique-stdin")
    if args.skip_critique:
        commit_args.append("--skip-critique")
    # stdin needs to actually reach the subprocess rather than being
    # captured/redirected by this wrapper -- run() uses subprocess.run
    # without overriding stdin, so it already inherits this process's
    # stdin by default; nothing extra needed here.
    return run(commit_args)


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------

def cmd_audit(_args):
    return run(["scripts/playtest_audit.py"])


# ---------------------------------------------------------------------------
# gm-cases
# ---------------------------------------------------------------------------

def cmd_gm_cases(args):
    cases_args = ["scripts/gm_cases.py"]
    if args.due:
        cases_args.append("--due")
    if args.state:
        cases_args.extend(["--state", args.state])
    if args.category:
        cases_args.extend(["--category", args.category])
    if args.check_sources:
        cases_args.append("--check-sources")
    cases_args.extend(args.query)
    return run(cases_args)


# ---------------------------------------------------------------------------
# earn-coverage
# ---------------------------------------------------------------------------

def cmd_earn_coverage(args):
    earn_args = ["scripts/earn_clean_slate.py"]
    if args.dry_run:
        earn_args.append("--dry-run")
    if args.audit_only:
        earn_args.append("--audit-only")
    return run(earn_args)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def cmd_export(args):
    export_args = ["scripts/export_save.py"]
    if args.output:
        export_args.append(args.output)
    if args.include_player_notes:
        export_args.append("--include-player-notes")
    return run(export_args)


# ---------------------------------------------------------------------------
# loop
# ---------------------------------------------------------------------------

def cmd_loop(_args):
    print("=" * 70)
    print("INTERACTIVE COMMIT LOOP")
    print("=" * 70)
    print("After each turn, draft the proposed state as JSON directly in this")
    print("same session and save it somewhere on this machine (e.g. /tmp/turn.json).")
    print("Paste that path below.")
    print("Empty input exits the loop.\n")
    print("This script still cannot narrate or decide what happened in the")
    print("story -- it only runs the mechanical side (validate, commit, audit)")
    print("once you tell it what changed.\n")
    print("Self-critique is mandatory for each turn committed here too -- you'll")
    print("be asked to paste this turn's drafted narration directly (no separate")
    print("file transfer needed), or type 'skip' to deliberately bypass the gate")
    print("for that one turn.\n")

    turn_count = 0
    while True:
        try:
            path_str = input("Proposed state file path (blank to exit): ").strip()
        except EOFError:
            break
        if not path_str:
            break

        path = Path(path_str)
        if not path.exists():
            print(f"  File not found: {path}\n")
            continue

        print("  Paste this turn's drafted narration below (the text that will be")
        print("  checked by self_critique.py), then a blank line to finish.")
        print("  Type 'skip' alone to deliberately bypass the critique gate for")
        print("  this turn instead.")
        narration_lines = []
        skip_this_turn = False
        while True:
            try:
                line = input()
            except EOFError:
                break
            if not narration_lines and line.strip().lower() == "skip":
                skip_this_turn = True
                break
            if line == "":
                break
            narration_lines.append(line)
        narration_text = "\n".join(narration_lines)

        note = input("  Optional note for the journal (blank to skip): ").strip()
        commit_args = ["scripts/commit_state.py", str(path)]
        if note:
            commit_args.extend(["--note", note])
        if skip_this_turn:
            commit_args.append("--skip-critique")
        else:
            commit_args.extend(["--critique-text", narration_text])

        rc = run(commit_args)
        if rc != 0:
            print("  Commit rejected -- fix the proposed file (or narration) and try again.\n")
            continue

        turn_count += 1
        print(f"\n  Turn committed ({turn_count} this session).")

        # After every commit, re-run the full audit so drift signals
        # surface immediately rather than only when someone remembers to
        # ask. Full Pass 3 prose-reading still needs a human -- see
        # playtest_audit.py's own printed caveat.
        print("  Re-checking mechanism coverage and tooling regressions...\n")
        run(["scripts/playtest_audit.py"])
        print()

    print(f"\nSession loop ended. {turn_count} turn(s) committed.")
    return 0


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Single entry point for running The Eldara Project's "
                     "mechanical side (setup, session start, state commits, "
                     "and audits) from a headless machine reached over SSH."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("setup", help="One-time: install dependencies and git hooks.")
    sub.add_parser("check", help="Verify this machine/repo is set up correctly.")
    sub.add_parser("start", help="Validate current state and print a status summary.")
    sub.add_parser("bootstrap", help="Run setup, check, and start in one pass -- "
                                      "everything needed to go from a fresh clone to ready-to-play.")

    p_commit = sub.add_parser("commit", help="Validate and promote a proposed state file.")
    p_commit.add_argument("file", nargs="?", default=None,
                           help="Path to proposed state JSON. Omit if saves/current.json "
                                "was already directly edited and just needs re-validating.")
    p_commit.add_argument("--note", default=None, help="One-line note for the journal.")
    p_commit.add_argument("--critique-file", default=None,
                           help="Path to a file on this machine holding this turn's drafted "
                                "narration text. Required (via this or one of the other two "
                                "--critique-* options) whenever FILE is given, unless "
                                "--skip-critique is passed instead.")
    p_commit.add_argument("--critique-text", default=None,
                           help="This turn's drafted narration, given directly as text -- "
                                "avoids a separate file transfer for short turns.")
    p_commit.add_argument("--critique-stdin", action="store_true",
                           help="Read this turn's drafted narration from stdin instead of "
                                "a file or inline argument.")
    p_commit.add_argument("--skip-critique", action="store_true",
                           help="Deliberately bypass the mandatory self-critique gate for "
                                "this one commit (confirmed false positive, or no real "
                                "prose this turn).")

    sub.add_parser("audit", help="Run the full three-pass playtest audit.")

    p_cases = sub.add_parser(
        "gm-cases", aliases=["list-gm-cases"],
        help="List the GM's situational cases (trigger -> required action) "
             "from docs/gm_cases.json, optionally only those live against "
             "the current save."
    )
    p_cases.add_argument("query", nargs="*", default=[],
                          help="Only show cases matching this text.")
    p_cases.add_argument("--due", action="store_true",
                          help="Only cases whose condition is mechanically true "
                               "against the save right now.")
    p_cases.add_argument("--state", default=None,
                          help="State file for --due (default saves/current.json) -- "
                               "point it at a proposed state to check it before committing.")
    p_cases.add_argument("--category", default=None,
                          help="Only one category: every-turn, player, state, "
                               "state-change, tooling.")
    p_cases.add_argument("--check-sources", action="store_true",
                          help="Verify every case still points at a real heading in "
                               "prompts/GM_INSTRUCTIONS.md. Exits non-zero on drift.")

    p_earn = sub.add_parser(
        "earn-coverage",
        help="Play a fixed set of real turns through the real commit pipeline "
             "to legitimately earn Pass-1 audit coverage, then run the full "
             "audit. Refuses to run past turn 0 -- see scripts/earn_clean_slate.py."
    )
    p_earn.add_argument("--dry-run", action="store_true",
                         help="Show the planned turns without committing anything.")
    p_earn.add_argument("--audit-only", action="store_true",
                         help="Skip playing turns; just run the real audit as-is.")

    sub.add_parser("loop", help="Interactive loop: commit turns and re-audit after each.")

    p_export = sub.add_parser(
        "export",
        help="Bundle current.json, journal.md, locations.json and "
             "npc_registry.json into one shareable/archivable file."
    )
    p_export.add_argument("output", nargs="?", default=None,
                           help="Where to write the bundle. Defaults to "
                                "saves/exports/turn<N>-<UTC timestamp>.json.")
    p_export.add_argument("--include-player-notes", action="store_true",
                           help="Also include saves/player_notes.md -- omitted "
                                "by default since it's out-of-character and not "
                                "meant to be shared.")

    args = parser.parse_args()

    dispatch = {
        "setup": cmd_setup,
        "check": cmd_check,
        "start": cmd_start,
        "bootstrap": cmd_bootstrap,
        "commit": cmd_commit,
        "audit": cmd_audit,
        "gm-cases": cmd_gm_cases,
        "list-gm-cases": cmd_gm_cases,
        "earn-coverage": cmd_earn_coverage,
        "loop": cmd_loop,
        "export": cmd_export,
    }
    sys.exit(dispatch[args.command](args))


if __name__ == "__main__":
    main()
