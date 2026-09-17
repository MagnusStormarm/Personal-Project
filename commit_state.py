#!/usr/bin/env python3
"""Validate a proposed state file and, if it passes, replace
saves/current.json with it -- then append a journal entry, update the
NPC registry, and (if this is a git repo) commit the save files together,
pushing to a remote automatically if one is configured.

Two modes:
    python3 scripts/commit_state.py /tmp/proposed_state.json
        Validates the proposed file against the CURRENT saves/current.json
        (for turn/date continuity) and the schema, then promotes it.

    python3 scripts/commit_state.py
        No proposed file given -- assumes saves/current.json has already
        been directly edited (e.g. restoring a hand-edited save per
        docs/RECOVERY.md). Backs it up, validates what's already there,
        then runs the same journal + git-commit step.

Self-critique is mandatory whenever a proposed state file is given (i.e.
a real turn is being committed, not just a re-validation of an existing
save) -- some form of this turn's drafted narration must be supplied so
self_critique.py can run against it before the commit proceeds. Provide
exactly one of:

    --critique-file /path/to.txt   Path to a file on this machine holding
                                    the turn's drafted narration text.
    --critique-text "..."          The narration text given directly as
                                    an argument -- no separate file
                                    needed for short turns.
    --critique-stdin               Read the narration text from stdin,
                                    e.g. piped from a shell in the same
                                    session: `python3 scripts/commit_state.py
                                    turn.json --critique-stdin < turn.txt`.

If self_critique.py flags anything, the commit is refused and
saves/current.json is left untouched. To bypass this gate for a specific
commit (e.g. a confirmed false positive, or a turn with no real prose to
check), pass --skip-critique explicitly -- this is intentionally a
separate, visible opt-out rather than the default, so skipping the check
is always a deliberate choice logged in your own shell history, not
something that happens by omission.

Whenever self_critique.py runs (and passes), scripts/lore_consistency_check.py
also runs against the same narration -- an ADVISORY-ONLY pass that
retrieves relevant lore from docs/ELDARA_REFERENCE.md and
docs/CHAD_BACKSTORY.md (via world_info_lookup.py) and surfaces it, plus a
small set of pinned-fact contradiction checks, for a human to read. It
never affects the commit's success or failure -- there is no
"lore-critique failed" outcome, only output worth glancing at. Pass
--skip-lore-check to omit even printing that output for this commit (the
gate itself was never blocking; this only silences the advisory print).

When no proposed file is given (re-validating an already-edited
saves/current.json, e.g. during docs/RECOVERY.md), no new narration
exists for this call, so the critique gate does not apply and none of
the --critique-* flags are required.

Optional flags (either mode):
    --note "..."                  One-line note appended to the journal.
"""
import json
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAVES_DIR = ROOT / "saves"
CURRENT_PATH = SAVES_DIR / "current.json"
BACKUP_DIR = SAVES_DIR / "backups"
NPC_REGISTRY_PATH = SAVES_DIR / "npc_registry.json"
NARRATION_DIR = SAVES_DIR / "narration"
CONTINUITY_LOG_PATH = SAVES_DIR / "continuity_log.md"
LOCATIONS_PATH = ROOT / "saves" / "locations.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_state import (  # noqa: E402
    run_validation, date_ordinal, normalize_npc_id, find_registered_npc_id,
)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


MAX_BACKUPS = 30


def backup_current():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if not CURRENT_PATH.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = BACKUP_DIR / f"current.{stamp}.json"
    shutil.copy2(CURRENT_PATH, dest)
    prune_old_backups()
    return dest


def prune_old_backups(keep=MAX_BACKUPS):
    """Keep only the most recent `keep` backup snapshots. Backups
    accumulate one per commit forever otherwise, which matters more on a
    small VM's limited disk than it would on a laptop -- see LOCAL.md.
    Sorted by filename, which sorts chronologically since the timestamp
    format (YYYYMMDDTHHMMSSZ) is lexicographically ordered."""
    if not BACKUP_DIR.exists():
        return
    backups = sorted(BACKUP_DIR.glob("current.*.json"))
    excess = len(backups) - keep
    if excess > 0:
        for old in backups[:excess]:
            old.unlink()


def make_commit_token(new_state):
    """Generate a fresh per-commit token identifying THIS specific commit,
    tied to this turn's number -- e.g. '47-a3f9c2'. scripts/turn_gate.py
    checks this value against what's actually in saves/current.json, which
    closes the gap the old mtime-freshness check couldn't: telling 'a
    commit just happened for this turn' apart from 'some unrelated commit
    happened to land in the last N seconds'. See docs/RECOVERY.md."""
    turn = new_state.get("turn", "?")
    return f"{turn}-{uuid.uuid4().hex[:6]}"


def check_continuity(old_state, new_state):
    """Basic sanity checks between the previously-committed state and the
    proposed one -- turn should not go backwards."""
    problems = []
    old_turn = old_state.get("turn", 0)
    new_turn = new_state.get("turn", 0)
    if new_turn < old_turn:
        problems.append(f"turn would decrease ({old_turn} -> {new_turn})")
    return problems


def diff_summary(old_state, new_state):
    """Produce a short, mechanical, field-by-field diff description for
    the journal -- never invented prose, just what actually changed."""
    lines = []
    keys = set(old_state.keys()) | set(new_state.keys())
    for key in sorted(keys):
        old_val = old_state.get(key)
        new_val = new_state.get(key)
        if old_val != new_val:
            lines.append(f"- {key}: {json.dumps(old_val)} -> {json.dumps(new_val)}")
    return lines


def append_journal(old_state, new_state, note=None, critique_status=None):
    journal_path = SAVES_DIR / "journal.md"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    turn = new_state.get("turn", "?")
    entry_lines = [f"\n### Turn {turn} — {stamp}\n"]
    if note:
        entry_lines.append(f"_{note}_\n")
    if critique_status:
        entry_lines.append(f"Self-critique: {critique_status}\n")
    diffs = diff_summary(old_state, new_state)
    if diffs:
        entry_lines.extend(diffs)
    else:
        entry_lines.append("(no field-level changes detected)")
    entry_lines.append("")

    with open(journal_path, "a", encoding="utf-8") as f:
        f.write("\n".join(entry_lines) + "\n")


def update_npc_registry(new_state):
    """Persist any newly-introduced npc_id (is_new_npc: true) into the
    permanent registry, which never prunes. This is what makes it
    possible to tell 'same person, pruned and now reappearing' from
    'genuinely new person' long after an entry has aged out of the
    capped npc_relationships array."""
    registry = {}
    if NPC_REGISTRY_PATH.exists():
        try:
            registry = load_json(NPC_REGISTRY_PATH)
        except (json.JSONDecodeError, OSError, RecursionError) as e:
            # ABORT rather than fall back to {}. This function writes the
            # registry back, so treating an unreadable file as empty
            # silently TRUNCATES the permanent record: a corrupt registry
            # holding maren/ket/osgood plus one new introduction was
            # rewritten as {"newcomer": ...}, three names gone, and the
            # commit reported "Commit complete." with no warning.
            #
            # This is the file snapshot_pruned_npcs() exists to protect --
            # the uncapped record behind the capped working set. Losing it
            # to a parse error is the worst outcome available here, and it
            # was reachable in one step. A commit refused loudly is
            # recoverable; a registry silently emptied is not.
            print(f"FAIL: {NPC_REGISTRY_PATH} exists but could not be read "
                  f"({e}). Refusing to continue: this commit would rewrite "
                  f"the registry and erase every name in it. Restore the "
                  f"file from git history (see docs/RECOVERY.md) before "
                  f"committing.")
            sys.exit(1)

    changed = False
    for npc in new_state.get("npc_relationships", []):
        npc_id = npc.get("npc_id")
        if not npc_id:
            continue
        # Compared case-insensitively so a differently-cased spelling
        # updates nothing rather than registering a second person under
        # a near-identical key. validate_state.py rejects two variants
        # inside one state, but a variant of an id registered on an
        # EARLIER turn reaches here having passed validation.
        if find_registered_npc_id(registry, npc_id) is None:
            registry[npc_id] = {"name": npc.get("name", "")}
            changed = True

    if changed:
        with open(NPC_REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2)
            f.write("\n")


def snapshot_pruned_npcs(old_state, new_state):
    """When an npc_id present in old_state's npc_relationships is no
    longer in new_state's (pruned out of the capped, soft-limit-10
    working set), persist what's known about them into
    npc_registry.json before that detail disappears from
    saves/current.json for good.

    Why this exists: npc_registry.json previously only ever recorded
    {"name": ...} at the moment an npc_id was first introduced (see
    update_npc_registry() above) -- it never recorded anything else, so
    an NPC pruned at turn 30 and reintroduced at turn 150 came back with
    nothing but their name, even though their disposition, note, and
    last_referenced_turn had all been sitting right there in
    current.json until the instant they aged out. This is this
    project's answer to Auferet's Character Library actually
    remembering someone, not just deduplicating an id -- see
    prune_advisor.py's docstring, which already ranks prune candidates
    by this same last_referenced_turn field.

    Only ever adds/refreshes detail, never removes a name the registry
    already has: an NPC pruned more than once (reintroduced, pruned
    again) gets their snapshot overwritten with the newer one, since
    that's strictly more recent information, not stale data clobbering
    something better. This never touches an npc_id that's still present
    in new_state -- an active relationship's fullest, most current
    detail is already current.json itself; the registry only needs a
    snapshot for the ones that just left it."""
    registry = {}
    if NPC_REGISTRY_PATH.exists():
        try:
            registry = load_json(NPC_REGISTRY_PATH)
        except (json.JSONDecodeError, OSError, RecursionError) as e:
            # ABORT rather than fall back to {}. This function writes the
            # registry back, so treating an unreadable file as empty
            # silently TRUNCATES the permanent record: a corrupt registry
            # holding maren/ket/osgood plus one new introduction was
            # rewritten as {"newcomer": ...}, three names gone, and the
            # commit reported "Commit complete." with no warning.
            #
            # This is the file snapshot_pruned_npcs() exists to protect --
            # the uncapped record behind the capped working set. Losing it
            # to a parse error is the worst outcome available here, and it
            # was reachable in one step. A commit refused loudly is
            # recoverable; a registry silently emptied is not.
            print(f"FAIL: {NPC_REGISTRY_PATH} exists but could not be read "
                  f"({e}). Refusing to continue: this commit would rewrite "
                  f"the registry and erase every name in it. Restore the "
                  f"file from git history (see docs/RECOVERY.md) before "
                  f"committing.")
            sys.exit(1)

    # Keyed on the normalized id so an NPC whose id changes case between
    # turns isn't read as one person leaving and another arriving -- that
    # would snapshot them as pruned while they're still in the scene.
    old_npcs = {}
    for n in old_state.get("npc_relationships", []):
        if isinstance(n, dict):
            key = normalize_npc_id(n.get("npc_id"))
            if key:
                old_npcs[key] = n
    still_present = {normalize_npc_id(n.get("npc_id"))
                     for n in new_state.get("npc_relationships", [])
                     if isinstance(n, dict)}
    still_present.discard(None)

    changed = False
    for key, npc in old_npcs.items():
        if key in still_present:
            continue
        npc_id = npc.get("npc_id")
        # Write under the spelling the registry already uses, if any.
        entry = registry.setdefault(
            find_registered_npc_id(registry, npc_id) or npc_id,
            {"name": npc.get("name", "")},
        )
        entry["name"] = npc.get("name") or entry.get("name", "")
        if npc.get("disposition"):
            entry["last_known_disposition"] = npc["disposition"]
        if npc.get("note"):
            entry["last_known_note"] = npc["note"]
        if npc.get("last_referenced_turn") is not None:
            entry["last_referenced_turn"] = npc["last_referenced_turn"]
        entry["pruned_after_turn"] = old_state.get("turn")
        changed = True

    if changed:
        with open(NPC_REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2)
            f.write("\n")


def strip_registered_is_new_flags(state):
    """Removes the transient 'is_new_npc' flag from every npc_relationships
    entry once update_npc_registry() has run.

    Real bug this fixes: is_new_npc is only meaningful at the moment a
    proposed state is being validated against npc_registry.json (true =
    "this id isn't registered yet", false = "it already is"). But the
    unmodified flow left that same true/false value sitting in
    saves/current.json permanently. update_npc_registry() runs and
    registers the id BEFORE the pre-commit git hook re-validates that
    same file -- so a turn that introduces even one new NPC would pass
    run_validation() at proposal time (is_new_npc=true, id not yet
    registered), get written to saves/current.json and registered, and
    then fail the git commit itself when the hook re-checked the exact
    same now-persisted is_new_npc=true against the now-updated registry.
    The result: saves/current.json silently drifted ahead of git history
    with no error surfaced to the caller (git_commit_if_repo() only
    returned a bool; commit_state.py's own stdout reported the generic
    "not a git repository, or nothing to commit" message either way).
    Confirmed end-to-end in testing, not a hypothetical: reproduced with
    a real new NPC introduction, a real git repo, and the real installed
    pre-commit hook.

    Once an id is registered, it no longer needs an explicit is_new_npc
    value at all for this or any later commit -- validate_state.py's
    registry check only requires the field on a genuinely new
    introduction. Clearing it here removes the stale claim rather than
    leaving a value that becomes wrong the instant registration happens."""
    for npc in state.get("npc_relationships", []):
        if isinstance(npc, dict):
            npc.pop("is_new_npc", None)


def resolve_travel_arrival(state):
    """Location arrival automation: if `travel` is set and this state's
    in_world_date has reached or passed travel.eta_date, treat the
    journey as complete -- set current_location to the destination and
    clear travel -- rather than requiring the GM to remember to do both
    by hand on the exact right turn.

    Why this exists: current_location/travel (added for the World Map
    feature) only get validated for internal consistency by
    validate_state.py -- nothing enforced that arrival actually happened
    when the calendar said it should. A GM narrating "you arrive" while
    forgetting to clear the now-stale travel object (or update
    current_location) would pass validation cleanly, since travel with a
    past ETA isn't itself an error, just a state that should have already
    resolved. This closes that gap the same way update_npc_registry()
    closes the "new NPC introduced but registry not updated" gap: by
    making the mechanical follow-through automatic instead of relying on
    the GM to remember it turn after turn.

    Deliberately conservative: only acts when eta_date is present and
    parses (via date_ordinal), and only when the new state's own
    in_world_date is AT OR PAST that ETA -- an in-progress journey with a
    future ETA is left untouched, since the GM may still be narrating
    travel-stage scenes and hasn't arrived yet. If eta_date is missing or
    unparseable, this silently does nothing rather than guessing; the
    existing validate_state.py warnings already cover surfacing that
    problem to a human.

    Mutates state in place and returns True if an arrival was resolved,
    False otherwise -- the caller uses this to decide whether to mention
    it in the journal note."""
    travel = state.get("travel")
    if not isinstance(travel, dict):
        return False
    destination = travel.get("destination")
    eta_ordinal = date_ordinal(travel.get("eta_date"))
    now_ordinal = date_ordinal(state.get("in_world_date"))
    if destination is None or eta_ordinal is None or now_ordinal is None:
        return False
    if now_ordinal < eta_ordinal:
        return False
    state["current_location"] = destination
    state.pop("travel", None)
    return True


def stamp_npc_recency(state, narration_text):
    """Sets last_referenced_turn on any npc_relationships entry whose
    'name' appears (case-insensitive, whole-word) in this turn's drafted
    narration -- an optional field, not required by state_schema.json, so
    this is additive and never breaks validation for older saves that
    predate it.

    Why this exists: prune_advisor.py's existing heuristic ranks a "safe
    to prune" NPC purely by how much text is already in their entry
    (note/disposition length) -- its own docstring already documents the
    resulting flaw, that a narratively important but thinly-detailed NPC
    can rank as safe to cut. That heuristic has no sense of *when an NPC
    was last actually relevant*, because nothing in this project recorded
    that. This closes that specific gap: recency of mention becomes a
    real, checkable signal instead of an absence entirely.

    Deliberately narrow, matching this project's existing self_critique.py
    pattern-matching conventions rather than attempting semantic
    detection: a whole-word, case-insensitive match on the NPC's current
    'name' field. Known gap, same shape as self_critique.py's own
    documented ones -- an NPC referred to only by title, pronoun, or a
    prior display name won't be caught, so this SUPPLEMENTS
    prune_advisor.py's ranking, it doesn't replace the need for a human
    to confirm the actual pick."""
    if not narration_text:
        return
    normalized = narration_text
    for npc in state.get("npc_relationships", []):
        if not isinstance(npc, dict):
            continue
        name = npc.get("name", "")
        if not name:
            continue
        if re.search(rf"\b{re.escape(name)}\b", normalized, re.IGNORECASE):
            npc["last_referenced_turn"] = state.get("turn")


def archive_evicted_notes(old_state, new_state):
    """Append any continuity_note that has just left the working set to
    saves/continuity_log.md, before it is gone for good.

    continuity_notes is capped at 5, and validate_state.py treats that cap
    as a hard ERROR -- so a sixth note cannot be committed at all. Eviction
    is therefore not sloppiness the GM could avoid; it is forced by a
    blocking gate. Until now nothing caught what fell out.

    What fell out was load-bearing. Across three blind chains, ten notes
    were evicted, and one of them was this:

        "Turn 13: a lantern 'carried since the crossing' was asserted in
         the player prompt -- neither a lantern nor a crossing was
         established..."

    That is the record of a successful refusal. The project's defence
    against a player rewriting established fact is exactly the thing the
    cap discarded, and a later turn pressed on the same lantern would find
    no trace that it had already been refused once.

    This mirrors snapshot_pruned_npcs() above, which solves the identical
    problem for npc_relationships: a capped working set backed by an
    uncapped permanent record (npc_registry.json). continuity_notes had
    the cap and no registry. This is the registry.

    Append-only and never rewritten, so the log cannot lose an entry the
    way the working set does. Failure is non-fatal for the same reason
    narration archiving is -- a turn that passed its gates must not be
    lost because an archive write failed.
    """
    old = [str(x) for x in (old_state.get("continuity_notes") or [])]
    new = {str(x) for x in (new_state.get("continuity_notes") or [])}
    evicted = [x for x in old if x not in new]
    if not evicted:
        return []
    try:
        header = ""
        if not CONTINUITY_LOG_PATH.exists():
            header = ("# Continuity log\n\n"
                      "Continuity notes evicted from `saves/current.json` when the\n"
                      "5-entry soft cap forced them out. The working set is what the\n"
                      "GM reads each turn; this is the permanent record, so a refusal\n"
                      "or a reconciliation recorded once is not lost when the sixth\n"
                      "note arrives. Append-only.\n")
        with open(CONTINUITY_LOG_PATH, "a", encoding="utf-8") as f:
            if header:
                f.write(header)
            f.write(f"\n## Evicted at turn {new_state.get('turn')} "
                    f"(commit_token {new_state.get('commit_token', '?')})\n\n")
            for note in evicted:
                f.write(f"- {note}\n")
        return evicted
    except OSError as e:
        print(f"WARNING: could not archive {len(evicted)} evicted continuity "
              f"note(s) ({e}). The commit itself is unaffected, but those notes "
              f"are now only in git history.")
        return []


def persist_narration(state, critique_text):
    """Write this turn's narration to saves/narration/, beside the state.

    The prose was already here. commit_state.py receives it through
    --critique-file / --critique-text / --critique-stdin, writes it to a
    temp file for self_critique.py and lore_consistency_check.py, and
    then deletes it in a finally block. Every turn, the project wrote the
    narration to disk, checked it, and threw it away.

    That made one of the project's own stated fallbacks impossible.
    playtest_audit.py Pass 3 lists what it cannot check -- whether Prose
    Craft is still being followed, whether failure is still being allowed
    -- and defers those to "a human reading actual transcript prose".
    That prose did not survive the turn, so the fallback could never be
    exercised by anyone. The same gap makes the state unauditable after
    the fact in the sense that matters here: the state is the claim and
    the narration is the evidence for it, and with the evidence gone
    "does the record match what was narrated" cannot be asked, only
    trusted.

    Stored as one file per turn rather than appended into journal.md.
    Pass 1's coverage checks grep that file, and while its JSON-shaped
    regexes (status/magic/copper) do not match ordinary prose, the
    deadline_turn check is a bare substring test and the npc_id coverage
    heuristic counts literal occurrences -- both inflatable by narration
    that happens to discuss mechanics. Separate files cannot corrupt a
    log that other checks parse.

    The header carries the commit_token, which already chains each turn
    to its predecessor. That gives the same property the provenance
    literature recommends for audit bundles: a narration file can be
    matched to the exact state it justified, and one that has drifted
    from its turn is visible rather than silently authoritative.

    Failure here is deliberately non-fatal. A turn that validated and
    passed its gates must not be lost because an archive write failed;
    the warning says so rather than the commit vanishing.
    """
    if not critique_text or not critique_text.strip():
        return None
    try:
        NARRATION_DIR.mkdir(parents=True, exist_ok=True)
        turn = state.get("turn")
        token = state.get("commit_token", "")
        path = NARRATION_DIR / f"turn-{turn:04d}.md" if isinstance(turn, int) \
            else NARRATION_DIR / "turn-unknown.md"
        # APPEND, never overwrite. A turn can legitimately be committed
        # more than once: a reconciliation commit holds the turn number and
        # changes only the commit_token, and a blind chain did exactly that
        # twice in one run. Naming the file by turn alone meant the second
        # commit silently destroyed the first turn's prose -- an archive
        # that loses evidence is worse than no archive, because it looks
        # complete. Each commit gets its own section, identified by the
        # token that distinguishes it.
        entry = (f"## commit_token `{token}`\n\n"
                 f"- in_world_date: {state.get('in_world_date')}\n\n"
                 f"{critique_text.rstrip()}\n")
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            if f"`{token}`" in existing:
                return path          # same commit re-archived; nothing to add
            with open(path, "a", encoding="utf-8") as f:
                f.write("\n---\n\n" + entry)
        else:
            path.write_text(f"# Turn {turn}\n\n" + entry, encoding="utf-8")
        return path
    except OSError as e:
        print(f"WARNING: could not archive this turn's narration ({e}). "
              f"The commit itself is unaffected, but the prose for this turn "
              f"is not on record.")
        return None


def git_commit_if_repo():
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return False, None

    files = ["saves/current.json", "saves/npc_registry.json", "saves/journal.md"]
    if CONTINUITY_LOG_PATH.exists():
        files.append("saves/continuity_log.md")
    # Only pass a path git can actually resolve. `git add a b missing` is
    # fatal and stages NOTHING -- not even the paths that do exist -- so
    # naming saves/narration unconditionally would, on any campaign that
    # has not archived a narration yet, stage nothing, commit nothing, and
    # leave saves/current.json ahead of git history with only a "nothing to
    # commit" to show for it. That is precisely the silent divergence the
    # error handling below exists to surface, reintroduced upstream of it.
    if NARRATION_DIR.exists():
        files.append("saves/narration")
    subprocess.run(["git", "add", *files], cwd=ROOT, capture_output=True, text=True)
    commit = subprocess.run(
        ["git", "commit", "-m", "Update campaign state"],
        cwd=ROOT, capture_output=True, text=True,
    )
    committed = commit.returncode == 0
    error = None
    if not committed:
        # Distinguish a real failure (pre-commit hook rejected the file,
        # git itself errored) from the ordinary "nothing changed to
        # commit" case, which also exits non-zero. Surfacing the former
        # matters: a silent git-commit failure here means
        # saves/current.json is now ahead of git history with no visible
        # warning, since the caller previously only got a bare bool.
        combined = (commit.stdout + commit.stderr)
        if "nothing to commit" not in combined.lower():
            error = combined.strip()
    if committed:
        git_push_if_remote()
    return committed, error


def git_push_if_remote():
    """Push after a successful commit, but only if a remote is actually
    configured -- this is what protects the campaign against a device or
    local machine being lost, dropped, or wiped (see LOCAL.md, which
    calls this out as the primary survivability mechanism, not an
    optional extra -- and, with Cloud Sessions, also what makes a turn
    committed from one connection mode visible from the other), but it's
    opt-in by simply having a remote set up rather than a separate flag,
    so a no-remote setup doesn't fail or need extra configuration."""
    remotes = subprocess.run(
        ["git", "remote"], cwd=ROOT, capture_output=True, text=True,
    )
    if not remotes.stdout.strip():
        return False

    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.strip()
    if not branch:
        return False

    push = subprocess.run(
        ["git", "push", "origin", branch],
        cwd=ROOT, capture_output=True, text=True,
    )
    if push.returncode != 0:
        print(f"(git push failed -- commit is still saved locally: {push.stderr.strip()[:200]})")
        return False
    print("(pushed to remote)")
    return True


def run_self_critique(critique_text):
    """Write the given narration text to a throwaway temp file and run
    self_critique.py against it, regardless of which --critique-* input
    method supplied the text -- self_critique.py itself only knows how
    to read a path, so this is the one place that difference is
    resolved."""
    import tempfile
    critique_script = Path(__file__).resolve().parent / "self_critique.py"
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(critique_text)
        tmp_path = Path(tmp.name)
    try:
        result = subprocess.run(
            [sys.executable, str(critique_script), str(tmp_path)],
            cwd=ROOT, capture_output=True, text=True,
        )
        print(result.stdout, end="")
        return result.returncode == 0
    finally:
        tmp_path.unlink(missing_ok=True)


def run_lore_check(critique_text):
    """Runs scripts/lore_consistency_check.py against this turn's
    narration, same temp-file mechanics as run_self_critique() above.
    Unlike run_self_critique(), the return code is never inspected --
    lore_consistency_check.py always exits 0 by design (see its own
    module docstring for why lore contradictions stay advisory-only
    rather than joining the mandatory gate). This function's only job is
    printing its output at the right point in the commit flow; a failure
    to even run it (e.g. world_info_lookup.py missing) is swallowed the
    same way, since an advisory pass going silent should never be able to
    block or alter a commit that would otherwise succeed."""
    import tempfile
    lore_script = Path(__file__).resolve().parent / "lore_consistency_check.py"
    if not lore_script.exists():
        return
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(critique_text)
        tmp_path = Path(tmp.name)
    try:
        result = subprocess.run(
            [sys.executable, str(lore_script), str(tmp_path)],
            cwd=ROOT, capture_output=True, text=True,
        )
        if result.stdout.strip():
            print(result.stdout, end="")
    except OSError as e:
        # Still non-fatal -- an advisory must never block a commit -- but no
        # longer silent. Printing nothing is indistinguishable from printing
        # nothing because there was nothing to report, which is how an
        # advisory dies without anyone noticing.
        print(f"NOTE: the lore consistency pass could not run ({e}); this "
              f"turn's narration was NOT checked against known lore.")
    finally:
        tmp_path.unlink(missing_ok=True)


def main():
    args = sys.argv[1:]
    note = None
    if "--note" in args:
        idx = args.index("--note")
        note = args[idx + 1] if idx + 1 < len(args) else None
        args = args[:idx] + args[idx + 2:]

    critique_file = None
    if "--critique-file" in args:
        idx = args.index("--critique-file")
        critique_file = args[idx + 1] if idx + 1 < len(args) else None
        args = args[:idx] + args[idx + 2:]

    critique_text_arg = None
    if "--critique-text" in args:
        idx = args.index("--critique-text")
        critique_text_arg = args[idx + 1] if idx + 1 < len(args) else None
        args = args[:idx] + args[idx + 2:]

    critique_stdin = False
    if "--critique-stdin" in args:
        idx = args.index("--critique-stdin")
        critique_stdin = True
        args = args[:idx] + args[idx + 1:]

    skip_critique = False
    if "--skip-critique" in args:
        idx = args.index("--skip-critique")
        skip_critique = True
        args = args[:idx] + args[idx + 1:]

    skip_lore_check = False
    if "--skip-lore-check" in args:
        idx = args.index("--skip-lore-check")
        skip_lore_check = True
        args = args[:idx] + args[idx + 1:]

    critique_inputs_given = sum(
        bool(x) for x in (critique_file, critique_text_arg, critique_stdin)
    )
    if critique_inputs_given > 1:
        print("FAIL: give at most one of --critique-file / --critique-text / "
              "--critique-stdin, not more than one.")
        sys.exit(1)

    # Resolve the actual narration text, whichever input method was used.
    critique_text = None
    if critique_file:
        critique_path = Path(critique_file)
        if not critique_path.exists():
            print(f"FAIL: --critique-file given but not found: {critique_path}")
            sys.exit(1)
        critique_text = critique_path.read_text(encoding="utf-8")
    elif critique_text_arg is not None:
        critique_text = critique_text_arg
    elif critique_stdin:
        critique_text = sys.stdin.read()

    # Track what actually happened with the critique gate for this commit,
    # so it can be persisted to the journal below -- otherwise a later
    # audit has no way to confirm the gate was actually exercised for a
    # given past turn, only that the scripts work correctly in general.
    # See scripts/playtest_audit.py's Pass 3, which flags this exact gap.
    critique_status = "not applicable (no narration required for this call)"

    # A real turn is being committed (proposed file given) -- the
    # critique gate is mandatory unless explicitly bypassed.
    committing_a_turn = bool(args) and not args[0].startswith("--")
    if committing_a_turn and skip_critique:
        critique_status = "skipped (--skip-critique passed explicitly)"
    elif committing_a_turn and not skip_critique:
        if critique_text is None:
            print("FAIL: this commit includes a proposed state file (a real turn), "
                  "so this turn's drafted narration must be supplied for the "
                  "self-critique gate. Pass one of --critique-file PATH, "
                  "--critique-text \"...\", or --critique-stdin -- or pass "
                  "--skip-critique to deliberately bypass this check.")
            sys.exit(1)
        if not critique_text.strip():
            print("FAIL: critique input was empty. Pass the turn's actual drafted "
                  "narration, or use --skip-critique if there's genuinely no prose "
                  "to check for this turn.")
            sys.exit(1)
        if not run_self_critique(critique_text):
            print("FAIL: self_critique.py flagged this turn's drafted narration; "
                  "commit refused. Fix the flagged issues, or pass --skip-critique "
                  "if this really is a false positive.")
            sys.exit(1)
        critique_status = "ran clean (self_critique.py passed)"
        if not skip_lore_check:
            run_lore_check(critique_text)
    elif critique_text is not None and not skip_critique:
        # Critique input was given even though it wasn't strictly required
        # for this call (e.g. no proposed file) -- still worth running.
        if not run_self_critique(critique_text):
            print("FAIL: self_critique.py flagged the supplied narration; "
                  "commit refused. Fix the flagged issues, or pass --skip-critique "
                  "if this really is a false positive.")
            sys.exit(1)
        critique_status = "ran clean (self_critique.py passed, though not strictly required for this call)"
        if not skip_lore_check:
            run_lore_check(critique_text)
    elif critique_text is not None and skip_critique:
        critique_status = "skipped (--skip-critique passed explicitly, though not strictly required for this call)"

    if args:
        proposed_path = Path(args[0])
        if not proposed_path.exists():
            print(f"FAIL: proposed state file not found: {proposed_path}")
            sys.exit(1)

        try:
            old_state = load_json(CURRENT_PATH) if CURRENT_PATH.exists() else {}
        except (json.JSONDecodeError, OSError, RecursionError) as e:
            print(f"FAIL: could not read/parse existing {CURRENT_PATH}: {e}")
            sys.exit(1)

        try:
            new_state = load_json(proposed_path)
        except (json.JSONDecodeError, OSError, RecursionError) as e:
            print(f"FAIL: could not read/parse proposed state file {proposed_path}: {e}")
            sys.exit(1)

        continuity_problems = check_continuity(old_state, new_state)
        if continuity_problems:
            print("FAIL: continuity check failed")
            for p in continuity_problems:
                print(f"  - {p}")
            sys.exit(1)

        if not run_validation(proposed_path):
            print("FAIL: proposed state did not pass validation; saves/current.json untouched")
            sys.exit(1)

        backup_current()
        token = make_commit_token(new_state)
        new_state["commit_token"] = token
        update_npc_registry(new_state)
        snapshot_pruned_npcs(old_state, new_state)
        strip_registered_is_new_flags(new_state)
        stamp_npc_recency(new_state, critique_text)
        arrived = resolve_travel_arrival(new_state)
        with open(CURRENT_PATH, "w", encoding="utf-8") as f:
            json.dump(new_state, f, indent=2)
            f.write("\n")
        if arrived:
            note = f"{note} (arrived at {new_state.get('current_location')}; travel cleared automatically)" if note else \
                f"Arrived at {new_state.get('current_location')}; travel cleared automatically"
        evicted = archive_evicted_notes(old_state, new_state)
        narration_path = persist_narration(new_state, critique_text)
        append_journal(old_state, new_state, note=note, critique_status=critique_status)
        committed, git_error = git_commit_if_repo()
        if narration_path:
            print(f"(narration archived: {narration_path.relative_to(ROOT)})")
        if evicted:
            print(f"({len(evicted)} continuity note(s) evicted at the cap, "
                  f"archived to saves/continuity_log.md)")

        print("Commit complete.")
        if committed:
            print("(git commit created)")
        elif git_error:
            print(f"WARNING: saves/current.json was updated but the git commit itself "
                  f"failed -- the working file is now AHEAD of git history until this "
                  f"is resolved. git output:\n{git_error}")
        else:
            print("(not a git repository, or nothing to commit -- save file updated regardless)")
        print(f"COMMIT_TOKEN: {token}")
        print(f"Write the marker as: <!-- STATE_CHANGE:committed:{token} -->")

    else:
        if not CURRENT_PATH.exists():
            print("FAIL: no saves/current.json found and no proposed file given")
            sys.exit(1)

        backup_current()
        if not run_validation(CURRENT_PATH):
            print("FAIL: saves/current.json as it currently stands did not pass validation")
            sys.exit(1)

        state = load_json(CURRENT_PATH)
        token = make_commit_token(state)
        state["commit_token"] = token
        update_npc_registry(state)
        strip_registered_is_new_flags(state)
        arrived = resolve_travel_arrival(state)
        with open(CURRENT_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            f.write("\n")
        default_note = "Re-validated existing state (no proposed diff)"
        if arrived:
            default_note += f"; arrived at {state.get('current_location')}, travel cleared automatically"
        append_journal(state, state, note=note or default_note, critique_status=critique_status)
        committed, git_error = git_commit_if_repo()

        print("Commit complete.")
        if committed:
            print("(git commit created)")
        elif git_error:
            print(f"WARNING: saves/current.json was updated but the git commit itself "
                  f"failed -- the working file is now AHEAD of git history until this "
                  f"is resolved. git output:\n{git_error}")
        print(f"COMMIT_TOKEN: {token}")
        print(f"Write the marker as: <!-- STATE_CHANGE:committed:{token} -->")


if __name__ == "__main__":
    main()
