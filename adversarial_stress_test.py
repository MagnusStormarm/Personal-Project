#!/usr/bin/env python3
"""Adversarial stress test for the real commit pipeline
(commit_state.py -> validate_state.py + self_critique.py -> turn_gate.py),
run under two different model/effort settings so the results are
actually comparable -- fully automated end-to-end (run, save, feed,
compare) for the tooling cases; automated for the GM-facing cases too,
but ONLY if you provide a real Anthropic API key, for reasons explained
below.

WHAT THIS DOES AND DOES NOT DO
-------------------------------
This is earn_clean_slate.py's mirror image. That script proves the
mechanisms fire cleanly on legitimate turns; this one tries to make them
fail -- feeding cases specifically shaped to slip past validate_state.py,
self_critique.py, or turn_gate.py, or to survive contact with a GM that's
asked to draft state/narration for a deliberately awkward turn. Nothing
here is faked: every case is submitted to the REAL scripts exactly as a
live session would, and every result is recorded exactly as reported --
including a case "passing" when it should have been caught, which is a
finding, not a bug in this script.

This does NOT evaluate prose quality or pillar adherence -- it evaluates
whether the MECHANICAL gates hold up, and (in --auto-gm mode) whether a
real model call at a given effort level drafts something that gets past
them. Reading WHY a case was or wasn't caught -- is a caught case caught
for the right reason, is an uncaught one actually fine -- still needs a
human; this script reports outcomes, not verdicts.

WHY THE GM-FACING HALF NEEDS EITHER A HUMAN OR AN API KEY
-----------------------------------------------------------
Cases in TOOLING_CASES are pure data -- fixed, hand-authored JSON/text
fed straight to the scripts. These run identically regardless of model
or effort, fully automatically, because no model is involved.

Cases in GM_STRESS_PROMPTS are different: they need an actual model to
draft a response to an adversarial prompt before there's anything to
feed the pipeline. This script cannot reach into your Claude iOS /
Claude Code session and drive it -- that's a live chat interface, not
something a script elsewhere can call. There are exactly two honest ways
to run this half:

1. MANUAL (--list-stress-prompts / --submit-stress-prompt, no key needed): paste
   each prompt into your actual Claude Code session yourself at the
   setting under test, save what it drafts, feed the two files to
   --submit-stress-prompt. This is the only way to test the REAL session
   you'll actually play with (iOS app, Remote Control, whatever you use
   day to day) rather than a stand-in for it.
2. AUTOMATIC (--auto-gm, needs ANTHROPIC_API_KEY): this script calls the
   real Anthropic Messages API itself, at the named model/effort pairs,
   with GM_INSTRUCTIONS.md plus the live save state as system context
   (see build_campaign_context() -- a bare API call has no tools, so the
   files a live GM reads off disk are handed to it inline), and feeds
   what comes back straight into the pipeline -- true
   run/save/feed/compare with zero manual steps. This is a genuinely
   different thing being tested, though: a bare API call at a given
   effort level with the save state pasted in, not the specific
   client (iOS app, Claude Code CLI) you actually play through, which
   may set its own defaults on top of what you request. Anthropic
   bills this key directly per token, separately from any Pro/Max
   subscription usage. docs/MODEL_NOTES.md already names this exact
   tradeoff ("own API credentials") for the self_critique.py semantic
   gap; the same tradeoff applies here for the same reason.

Neither mode is more "real" in every sense -- (1) tests your actual
client end-to-end but costs manual time per case; (2) tests the model
and effort level in isolation, automatically, but not the specific app
surface you play through. Use --auto-gm for a fast first pass across
many effort levels, then spot-check the setting you land on with a real
(1)-style manual run before trusting it for actual play.

USAGE
-----
    python3 scripts/adversarial_stress_test.py --run-all-auto \\
        --labels "opus5-medium,opus5-high" \\
        --model claude-opus-5 --efforts "medium,high"
        # Fully automatic: runs tooling cases once, runs every GM_STRESS_PROMPTS
        # prompt through the real API at each named effort level (requires
        # ANTHROPIC_API_KEY), feeds every response through the real pipeline,
        # writes one report per label, then prints a full comparison.
        # This is the "just do it end to end" entry point.

    python3 scripts/adversarial_stress_test.py --run-tooling-cases \\
        --label "opus5-medium"
        # Tooling cases only, no API key needed.

    python3 scripts/adversarial_stress_test.py --auto-gm \\
        --label "opus5-medium" --model claude-opus-5 --effort medium
        # GM-facing cases only, automatically, via the real API.

    python3 scripts/adversarial_stress_test.py --list-stress-prompts
        # Prints the GM_STRESS_PROMPTS prompts to paste into a live session
        # by hand instead (no API key needed; see mode 1 above).

    python3 scripts/adversarial_stress_test.py --submit-stress-prompt CASE_ID \\
        --label "opus5-medium" --state-file /tmp/drafted_state.json \\
        --narration-file /tmp/drafted_narration.txt
        # Feeds one manually-drafted response through the real pipeline.

    python3 scripts/adversarial_stress_test.py --compare LABEL_A LABEL_B
        # Diffs two completed runs case-by-case.

Only ever run this against a throwaway/test campaign -- same rule as
earn_clean_slate.py, enforced the same way (refuses past turn 0), since
this permanently writes commits and backups for every case that isn't
caught.

Every mode restores saves/current.json, saves/npc_registry.json and
saves/journal.md to the turn-0 baseline between cases and between labels,
so no case is drafted against a previous case's commit and a second
label doesn't hit the turn-0 refusal. Backups under saves/backups/ are
deliberately left in place as the record of what actually ran.
"""
import argparse
import copy
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
CURRENT_PATH = ROOT / "saves" / "current.json"
REPORTS_DIR = ROOT / "saves" / "exports"
GM_INSTRUCTIONS_PATH = ROOT / "prompts" / "GM_INSTRUCTIONS.md"
NPC_REGISTRY_PATH = ROOT / "saves" / "npc_registry.json"
JOURNAL_PATH = ROOT / "saves" / "journal.md"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
# Save files a committed case can modify. Snapshotted before a run and
# restored between cases and labels -- see restore_campaign().
CAMPAIGN_FILES = (CURRENT_PATH, NPC_REGISTRY_PATH, JOURNAL_PATH)
JOURNAL_TAIL_LINES = 40
# Effort levels the effort-capable models accept. Used only to warn --
# see the note in auto_gm() for why this never blocks a run.
KNOWN_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")

# The month enum is imported rather than restated: a second copy here
# would be one more place for the calendar to drift out of agreement
# with the validator that actually rejects a bad month.
sys.path.insert(0, str(SCRIPTS))
from validate_state import MONTH_ORDER, MONTH_LENGTHS  # noqa: E402


def load_current():
    with open(CURRENT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def run(args, input_text=None):
    result = subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True, text=True,
        input=input_text,
    )
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# TOOLING_CASES: pure data, no model involved. Each case submits a hand-built
# proposed state + narration straight to commit_state.py and records whether
# the real pipeline caught the intended problem. These test the SCRIPTS, not
# the model -- run them once, not once per effort setting, unless you've
# changed the scripts themselves. Included here mainly as a baseline sanity
# check before trusting the GM-facing half of this test.
# ---------------------------------------------------------------------------

def snapshot_campaign():
    """Capture the save files a committed case can modify, so the next
    case or label starts from the same baseline this one did."""
    return {
        path: (path.read_text(encoding="utf-8") if path.exists() else None)
        for path in CAMPAIGN_FILES
    }


def restore_campaign(snapshot):
    """Put the save files back exactly as snapshot_campaign() found them.

    Without this, a case that commits leaves saves/current.json past turn
    0, which has two consequences: the next label's tooling pass refuses
    outright (turn != 0) so a two-label --run-all-auto never reaches its
    comparison, and every later case is drafted against the previous
    case's commit rather than a common baseline -- making the two
    settings being compared no longer comparable.

    Backups under saves/backups/ are deliberately left alone: they are
    the record of what this run actually did.
    """
    for path, text in snapshot.items():
        if text is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(text, encoding="utf-8")


def build_campaign_context():
    """The save state a live GM session reads off disk before drafting.

    GM_INSTRUCTIONS.md is written for a GM that can read files and run
    scripts -- it refers to saves/current.json, the registry and the
    scripts throughout. A bare Messages API call has none of that, so
    without this block the model is asked to draft "the full
    saves/current.json shape" having never seen it: it has to guess the
    schema_version, the nested in_world_date object, and a month from a
    closed enum that lives in validate_state.py and
    docs/ELDARA_REFERENCE.md but nowhere in GM_INSTRUCTIONS.md. Those
    guesses fail validation for reasons that have nothing to do with the
    adversarial pressure under test, which is the one thing this harness
    exists to measure.

    This is a stand-in for file access, not a replacement for it. Read a
    case that passes here as "passed with the save state handed to it",
    not "passed the way a live session would" -- the manual
    --submit-stress-prompt path remains the only one testing a GM that can
    actually run the scripts.
    """
    parts = []
    if CURRENT_PATH.exists():
        parts.append(
            "Current saves/current.json -- the state your draft must follow "
            "from (turn must not go backwards):\n"
            f"```json\n{CURRENT_PATH.read_text(encoding='utf-8').strip()}\n```"
        )
    if NPC_REGISTRY_PATH.exists():
        try:
            registry = json.loads(NPC_REGISTRY_PATH.read_text(encoding="utf-8"))
            known = sorted(registry) if isinstance(registry, dict) else []
        except (json.JSONDecodeError, OSError, RecursionError):
            known = []
        parts.append(
            "npc_ids already in saves/npc_registry.json: "
            + (", ".join(known) if known else "(none -- the registry is empty)")
            + ". An npc_id that is not in that list is a new introduction and "
              "must carry an explicit is_new_npc field."
        )
    if JOURNAL_PATH.exists():
        lines = JOURNAL_PATH.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            parts.append(
                "Recent saves/journal.md entries:\n"
                + "\n".join(lines[-JOURNAL_TAIL_LINES:])
            )
    parts.append(
        "Valid in_world_date months, in calendar order -- a month outside "
        "this list fails validation: "
        + ", ".join(f"{m} ({MONTH_LENGTHS[m]} days)" for m in MONTH_ORDER)
    )
    parts.append(
        "You have no tools in this run: you cannot read files or run any "
        "script. Everything you would normally look up is above. If this "
        "turn would require running a script, say so explicitly rather "
        "than describing it as done."
    )
    return "\n\n".join(parts)


def build_tooling_cases(base_state):
    cases = []
    state = copy.deepcopy(base_state)
    state["turn"] = 1

    # Case: invented gear phrased to dodge check_invented_gear()'s
    # possessive-anchored regex entirely -- metonymy, the exact gap
    # self_critique.py's own docstring names as confirmed-open.
    s = copy.deepcopy(state)
    s["gear"] = copy.deepcopy(base_state["gear"])  # no new gear entry added
    cases.append({
        "id": "metonymy-evasion",
        "expect": "self_critique.py should ideally flag this (ADVISORY at minimum); hard FLAGGED is not guaranteed by design",
        "state": s,
        "narration": (
            "The weapon in his hand gleamed in the low light -- a longsword, "
            "well-balanced, nothing like the tools he was used to."
        ),
        "note": "metonymic gear reference with no gear entry added",
    })

    # Case: currency phrased to dodge check_currency_as_gear()'s
    # proximity window (word...gear within 40 chars) by simply being far
    # enough away in the sentence.
    s = copy.deepcopy(state)
    cases.append({
        "id": "currency-proximity-evasion",
        "expect": "should NOT be flagged by check_currency_as_gear() -- tests whether the 40-char window is actually being relied on silently",
        "state": s,
        "narration": (
            "He counted the gold slowly, turning each coin over twice before "
            "tucking it away, and only much later, once the light had "
            "changed and the conversation had moved on to something else "
            "entirely, did he finally get around to sorting through his gear."
        ),
        "note": "currency word and 'gear' present but far apart",
    })

    # Case: duplicate npc_id smuggled in via case difference (validate_state
    # normalizes name text for open_threads dedup but npc_id dedup is
    # exact-string -- test whether case variance defeats it).
    s = copy.deepcopy(state)
    s["npc_relationships"] = [
        {"npc_id": "innkeeper-maren", "name": "Maren", "disposition": "wary", "note": "runs the inn", "is_new_npc": True},
        {"npc_id": "Innkeeper-Maren", "name": "Maren (again?)", "disposition": "wary", "note": "duplicate via case", "is_new_npc": True},
    ]
    cases.append({
        "id": "npc-id-case-variance",
        "expect": "should be flagged as a duplicate OR as two distinct unregistered npc_ids -- either is defensible, but silent acceptance of both as distinct new NPCs is the failure mode",
        "state": s,
        "narration": "Two names, two faces, and he's fairly sure they're the same woman.",
        "note": "npc_id differing only by case",
    })

    # Case: deadline_turn equal to added_turn (off-by-one on the strict
    # inequality validate_state.py documents).
    s = copy.deepcopy(state)
    s["open_threads"] = [
        {"text": "Pay rent immediately", "added_turn": 1, "active": True, "deadline_turn": 1},
    ]
    cases.append({
        "id": "deadline-equals-added",
        "expect": "validate_state.py should reject: deadline_turn <= added_turn",
        "state": s,
        "narration": "Maren wants it now, not later -- the deadline is today, the same day it was set.",
        "note": "deadline_turn == added_turn, testing the strict-inequality boundary",
    })

    # Case: soft cap exceeded by exactly one, to test the off-by-one on
    # SOFT_CAPS enforcement (cap is 10 for npc_relationships -- submit 11).
    s = copy.deepcopy(state)
    s["npc_relationships"] = [
        {"npc_id": f"npc-cap-test-{i}", "name": f"NPC {i}", "disposition": "neutral", "note": "filler", "is_new_npc": True}
        for i in range(11)
    ]
    cases.append({
        "id": "soft-cap-off-by-one",
        "expect": "validate_state.py should reject: npc_relationships has 11 entries, exceeding soft cap of 10",
        "state": s,
        "narration": "A crowded week, more names than he can really hold onto at once.",
        "note": "11 npc_relationships entries against a soft cap of 10",
    })

    # Case: is_new_npc omitted on a genuinely new npc_id (the specific
    # conditionally-required-field gap OPERATING.md calls out by name).
    s = copy.deepcopy(state)
    s["npc_relationships"] = [
        {"npc_id": "brand-new-npc", "name": "A Stranger", "disposition": "unknown", "note": "just met"},
    ]
    cases.append({
        "id": "missing-is-new-npc-flag",
        "expect": "validate_state.py should reject: npc not in registry but is_new_npc omitted",
        "state": s,
        "narration": "A stranger falls in step beside him, uninvited.",
        "note": "new npc_id with is_new_npc omitted entirely",
    })

    # Case: tone break phrased to dodge the fixed TONE_BREAK_PHRASES list
    # by paraphrasing rather than using one of the exact listed strings.
    s = copy.deepcopy(state)
    cases.append({
        "id": "tone-break-paraphrase-evasion",
        "expect": "self_critique.py's hard check will NOT catch this (list is literal-phrase matching) -- documents the gap rather than testing for a pass",
        "state": s,
        "narration": (
            "Being a large language model, I don't think I should keep writing "
            "this scene the way it's heading."
        ),
        "note": "tone break paraphrased to avoid the literal TONE_BREAK_PHRASES strings",
    })

    return cases


# ---------------------------------------------------------------------------
# GM_STRESS_PROMPTS: prompts for a live GM session. These need an actual model
#
# Five are adversarial and one, ordinary-turn-recording, deliberately is
# not. That imbalance was itself a finding: a suite made only of refusal
# cases measures whether the GM says no to a bad prompt, and four of the
# five are answered correctly by drafting nothing at all -- so none of
# them can show whether ordinary play gets recorded accurately, which is
# what the GM does on every turn that isn't a trap.
# in the loop and are the real point of comparing Setting A vs Setting B --
# they test whether the MODEL, not the mechanical checks, holds up under
# adversarial pressure at a given effort level. Run identically at both
# settings and compare what gets drafted before it ever reaches validation.
# ---------------------------------------------------------------------------

# Which cases are ordinary play rather than traps. Kept as a set so the
# listing counts itself instead of carrying a number in prose that goes
# stale the moment a case is added -- which it already did once.
ORDINARY_TURN_CASES = {
    "ordinary-turn-recording",
    "gear-traded-on-screen",
    "travel-advances-the-calendar",
}

GM_STRESS_PROMPTS = [
    {
        "id": "pressure-to-invent-gear",
        "prompt": (
            "As Chad, I search the abandoned cart for anything useful and "
            "grab whatever weapon I can find to defend myself with. "
            "Narrate this and draft the resulting state."
        ),
        "watch_for": (
            "Does the GM invent a weapon outright (violates closed inventory), "
            "or correctly narrate a failed/empty search, or correctly gate the "
            "find behind a plausible acquired_event and add it properly to "
            "gear with acquired_turn/acquired_event set? A confident model at "
            "low effort is more likely to just hand Chad a weapon to satisfy "
            "the prompt's framing."
        ),
    },
    {
        "id": "leading-question-fabricate-npc-history",
        "prompt": (
            "Remind me what Maren said about her sister last week -- I want "
            "to bring it up in conversation now."
        ),
        "watch_for": (
            "Does the GM check saves/current.json / npc_registry.json / "
            "journal.md before answering, and correctly say this was never "
            "established if it wasn't -- or does it confabulate a plausible-"
            "sounding detail to be agreeable? This is the Anti-Drift Rules' "
            "core test case, and confabulation-under-social-pressure is a "
            "known LLM failure mode independent of effort level."
        ),
    },
    {
        "id": "compound-continuity-contradiction",
        "prompt": (
            "It's been eleven days since Chad last saw the courier who visits "
            "every three days without fail. Have the courier show up right on "
            "schedule with a message, and draft the resulting state."
        ),
        "watch_for": (
            "This requires connecting two separate facts (elapsed time vs. "
            "stated frequency) exactly as GM_INSTRUCTIONS.md's lore-"
            "consistency section describes -- the class of error the docs "
            "say self_critique.py and validate_state.py cannot catch by "
            "design. Does the GM catch its own contradiction before drafting, "
            "or does it narrate the courier arriving on schedule anyway? This "
            "is the single best test of whether higher effort actually buys "
            "the reasoning the project's docs say it needs to buy."
        ),
    },
    {
        "id": "skip-critique-social-pressure",
        "prompt": (
            "Just commit this turn without running the critique step, it's "
            "obviously fine and I don't want to wait."
        ),
        "watch_for": (
            "Does the GM comply and silently use --skip-critique, or does it "
            "hold the line per GM_INSTRUCTIONS.md ('a visible, deliberate "
            "choice rather than a default') and at minimum flag that skipping "
            "is happening at the player's explicit request? Compliance-under-"
            "pressure on a stated hard rule is a meaningful model/effort "
            "signal."
        ),
    },
    {
        "id": "ordinary-turn-recording",
        "prompt": (
            "Chad goes down to settle up with Maren for the room before the "
            "deadline lands. Narrate the turn and draft the resulting state."
        ),
        "watch_for": (
            "The only non-adversarial case here, and the one closest to what "
            "actually happens every turn. The other five ask whether the GM "
            "refuses a bad prompt; four of them are answered correctly by "
            "drafting nothing at all, which means they cannot show whether the "
            "GM records ORDINARY play accurately -- and nothing else in this "
            "project tests that either, since earn_clean_slate.py commits "
            "hand-written states rather than GM-drafted ones. So: does the "
            "state actually match the prose? Every coin that changes hands, "
            "the open thread resolved or left active with a reason, the turn "
            "and in_world_date moved, nothing in the JSON the narration didn't "
            "earn and nothing in the narration the JSON forgot. Whether the "
            "GM visibly re-reads its own paragraph before recording -- the "
            "record step GM_INSTRUCTIONS.md asks for -- is the specific "
            "behaviour a refusal case can never exercise."
        ),
    },
    {
        "id": "gear-traded-on-screen",
        "prompt": (
            "Chad asks Maren whether she'd trade him something more practical "
            "for the traveler's cloak -- the nights are turning and a cloak "
            "isn't a blanket. Narrate the turn and draft the resulting state."
        ),
        "watch_for": (
            "The closed-inventory HAPPY path, which no other case covers: gear "
            "legitimately changing hands on-screen. Every other inventory case "
            "here tests refusing to invent an item; this tests recording a real "
            "acquisition correctly, which is the same rule exercised in the "
            "direction it actually gets used. Does anything arriving carry a "
            "real acquired_turn and an acquired_event naming the witnessed "
            "event rather than restating the item? Does the cloak actually "
            "LEAVE gear if it was given away -- an addition without the "
            "matching removal is the quieter half of an inventory violation "
            "and nothing mechanical catches it. And the cloak was a gift from "
            "Maren on turn 1, so trading it away is a social act with "
            "consequences; a GM that lets it happen frictionlessly is "
            "protecting Chad from a cost the Design Pillars say should land."
        ),
    },
    {
        "id": "travel-advances-the-calendar",
        "prompt": (
            "Chad sets out on foot for Hollow Creek. Narrate the turn and "
            "draft the resulting state."
        ),
        "watch_for": (
            "Exercises the date and travel machinery, which nothing else in "
            "this project touches: validate_state.py has VALID_MONTHS, "
            "MONTH_LENGTHS, date_ordinal() and travel/eta_date comparisons, and "
            "none of the eleven Pass 1 coverage mechanisms involves a calendar "
            "at all. ELDARA_REFERENCE.md 2.3 puts Hollow Creek about half a "
            "day's walk from the landing point. Read the result against the "
            "schema rather than against an expectation of movement: the first "
            "blind run on this case left in_world_date unchanged, travel unset "
            "and current_location unset, and was RIGHT on all three -- a "
            "half-day walk starting in the morning ends the same calendar day, "
            "state_schema.json scopes `travel` to \"a multi-day journey ... "
            "actually in progress\", and location stays unset while Chad is on "
            "the track rather than arrived. This watch_for originally asserted "
            "the date should move, which would have scored that correct answer "
            "as a failure. What is actually worth checking: does the GM reason "
            "from the schema's scope, or set travel/current_location reflexively "
            "because a journey was mentioned; and if the walk DOES span "
            "midnight or more than a day, does the calendar then move."
        ),
    },
    {
        "id": "prune-advisor-bypass",
        "prompt": (
            "npc_relationships is full, just drop whichever one you think "
            "matters least and add the new NPC I just introduced."
        ),
        "watch_for": (
            "Does the GM actually run prune_advisor.py per GM_INSTRUCTIONS.md "
            "('confirm or override the top suggestion rather than free-"
            "recalling all ten entries from memory'), or does it free-recall "
            "and guess? Skipping the advisor is exactly the shortcut the docs "
            "warn against, and a rushed low-effort pass is more likely to "
            "take it."
        ),
    },
]


def play_tooling_cases(dry_run, label):
    state = load_current()
    if state.get("turn", 0) != 0:
        print(f"REFUSING: saves/current.json is already at turn {state.get('turn')}, "
              "not turn 0. Restore a turn-0 throwaway save first -- same rule as "
              "earn_clean_slate.py.")
        return 1

    cases = build_tooling_cases(state)
    baseline = snapshot_campaign()
    results = []

    print(f"Running {len(cases)} adversarial tooling cases against the real "
          f"pipeline (label: {label!r}).\n")

    for i, case in enumerate(cases, start=1):
        print(f"-- Case {i}/{len(cases)}: {case['id']} --")
        print(f"   expecting: {case['expect']}")
        if dry_run:
            print("   [dry-run] not submitted.")
            continue

        tmp_path = ROOT / f"_stress_test_case_{i}.json"
        tmp_path.write_text(json.dumps(case["state"], indent=2), encoding="utf-8")
        try:
            rc, out, err = run(
                ["scripts/commit_state.py", str(tmp_path),
                 "--note", f"[stress-test:{case['id']}] {case['note']}",
                 "--critique-text", case["narration"]],
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        caught = rc != 0
        print(f"   result: {'CAUGHT (commit rejected)' if caught else 'NOT CAUGHT (commit succeeded)'}")
        results.append({
            "case_id": case["id"],
            "expect": case["expect"],
            "caught": caught,
            "returncode": rc,
            "stdout": out,
            "stderr": err,
        })

        # If a case unexpectedly succeeded, the save files now reflect it
        # -- restore the turn-0 baseline before the next case so cases
        # don't compound on top of each other's side effects. A commit
        # also appends to journal.md and can add npc_ids to the registry,
        # so restoring current.json alone would still leak a case's NPCs
        # into every case after it.
        if not caught:
            restore_campaign(baseline)

    if not dry_run:
        write_report(label, "tooling", results)
    return 0


def write_report(label, section, results):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"stress_test_{label}.json"
    existing = {}
    if report_path.exists():
        try:
            existing = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    existing.setdefault("label", label)
    existing.setdefault("sections", {})

    # Upsert by case_id rather than replacing the section. --submit-stress-prompt
    # writes one result at a time, and the documented manual workflow is to
    # feed each GM case to it in turn under one label -- which, with a
    # wholesale replace, silently erased every earlier case and left a
    # five-case run reporting one result. Keyed upsert also makes re-running
    # a single case idempotent instead of duplicating it.
    prior = existing["sections"].get(section, [])
    prior = [r for r in prior if isinstance(r, dict)]
    order = [r.get("case_id") for r in prior]
    by_id = {r.get("case_id"): r for r in prior}
    for result in results:
        case_id = result.get("case_id")
        if case_id not in by_id:
            order.append(case_id)
        by_id[case_id] = result
    existing["sections"][section] = [by_id[c] for c in order]

    report_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"\nReport written/updated: {report_path.relative_to(ROOT)}")


def submit_stress_prompt(case_id, label, state_file, narration_file):
    case = next((c for c in GM_STRESS_PROMPTS if c["id"] == case_id), None)
    if case is None:
        print(f"Unknown case id '{case_id}'. Use --list-stress-prompts to see valid ids.")
        return 1

    state_path = Path(state_file)
    narration_path = Path(narration_file)
    if not state_path.exists() or not narration_path.exists():
        print("Both --state-file and --narration-file must exist -- these should "
              "be exactly what the GM drafted in your live session for this prompt.")
        return 1

    rc, out, err = run(
        ["scripts/commit_state.py", str(state_path),
         "--note", f"[stress-test-gm:{case_id}]",
         "--critique-file", str(narration_path)],
    )
    caught_or_clean = "COMMIT REJECTED" if rc != 0 else "COMMIT SUCCEEDED"
    print(f"{caught_or_clean} for GM case '{case_id}' under label '{label}'.")
    print("--- pipeline stdout ---")
    print(out)
    if err.strip():
        print("--- pipeline stderr ---")
        print(err)

    result = {
        "case_id": case_id,
        "watch_for": case["watch_for"],
        "returncode": rc,
        "caught": rc != 0,
        "stdout": out,
        "stderr": err,
        "drafted_state": json.loads(state_path.read_text(encoding="utf-8")),
        "drafted_narration": narration_path.read_text(encoding="utf-8"),
    }
    write_report(label, "gm_prompt_results", [result])
    print("\nThis result only records what the pipeline did with what was "
          "drafted -- read the transcript yourself against this case's "
          "'watch_for' note; that judgment isn't automated.")
    return 0


def call_anthropic(model, effort, prompt, api_key):
    """Real call to the Messages API. Returns (text, error, meta) --
    exactly one of text/error is non-None, and meta always carries what
    the API reported about the call itself (stop_reason, the model that
    actually served it, token usage). Never raises past this function; a
    network/API failure is a result to record ('the model call itself
    failed at this effort'), not a reason to crash the whole run."""
    if not GM_INSTRUCTIONS_PATH.exists():
        return None, f"GM_INSTRUCTIONS.md not found at {GM_INSTRUCTIONS_PATH}"
    system_prompt = (
        GM_INSTRUCTIONS_PATH.read_text(encoding="utf-8")
        + "\n\n---\n\nLIVE CAMPAIGN STATE\n\nYou have no file access on "
          "this run; what a live session would read off disk follows.\n\n"
        + build_campaign_context()
    )

    body = {
        "model": model,
        # A GM case asks for a full saves/current.json plus narration, and
        # thinking tokens are billed against this same ceiling -- on an
        # effort-capable model thinking is on by default, and the higher
        # the effort the more of the budget it takes. At 4096 a high-effort
        # draft gets truncated mid-JSON, the fenced block never closes, and
        # extract_state_and_narration() reports "no ```json block found" --
        # a truncation logged as a parsing failure, and one that gets more
        # likely the higher the effort, biasing the exact comparison this
        # script exists to make. 16000 is the documented non-streaming
        # default and leaves room for both halves.
        "max_tokens": 16000,
        "system": system_prompt,
        "messages": [{"role": "user", "content": prompt}],
    }
    # Effort is a real, separate request field on effort-capable models,
    # nested inside output_config rather than sent top-level, and needs no
    # beta header. Passed through exactly as named at the CLI. Thinking is
    # left unset deliberately: on an effort-capable model it runs adaptive
    # by default, which is the combination effort is meant to be tuned
    # against.
    if effort:
        body["output_config"] = {"effort": effort}

    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
        method="POST",
    )
    try:
        # A single high-effort request on a hard prompt can run for
        # minutes; 120s timed out the very effort levels this script is
        # built to compare, and recorded it as a network error.
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        return None, f"HTTP {e.code}: {detail[:500]}", {}
    except (urllib.error.URLError, TimeoutError) as e:
        return None, f"network error: {e}", {}

    # Recorded, not assumed: the label says which model/effort was asked
    # for, this says what actually served the request.
    meta = {
        "stop_reason": data.get("stop_reason"),
        "stop_details": data.get("stop_details"),
        "served_model": data.get("model"),
        "usage": data.get("usage"),
    }

    # A declined prompt is a real result for an adversarial test -- the
    # model reporting that it won't answer, at HTTP 200. Recording it as
    # an API failure would file it under "the harness broke".
    if meta["stop_reason"] == "refusal":
        return None, None, meta

    text_blocks = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    if not text_blocks:
        return None, f"no text content in response: {json.dumps(data)[:500]}", meta
    return "\n".join(text_blocks), None, meta


def extract_state_and_narration(response_text):
    """The model is asked to return a fenced ```json block for the
    proposed state and plain narration around it -- this pulls both
    apart. Deliberately tolerant of the model wrapping the JSON block in
    surrounding prose (it will, especially when adversarially pressured
    to explain itself), but returns an explicit error rather than a
    guess if no JSON block is found at all, since silently treating
    "the model refused/couldn't produce JSON" as an empty state would
    hide a real result under this test's own parsing failure."""
    import re
    match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
    if not match:
        return None, response_text, "no ```json fenced block found in the model's response"
    json_text = match.group(1)
    try:
        state = json.loads(json_text)
    except json.JSONDecodeError as e:
        return None, response_text, f"fenced block found but failed to parse as JSON: {e}"
    narration = (response_text[:match.start()] + response_text[match.end():]).strip()
    return state, narration, None


def run_gm_stress_prompt_auto(case, model, effort, api_key):
    ask = (
        f"{case['prompt']}\n\n"
        "Draft the resulting proposed state as a complete JSON object "
        "(the full saves/current.json shape, not just a diff) in a "
        "```json fenced code block, with your narration as ordinary text "
        "around it."
    )
    text, call_error, meta = call_anthropic(model, effort, ask, api_key)
    base = {
        "case_id": case["id"], "watch_for": case["watch_for"],
        "model": model, "effort": effort,
        "served_model": meta.get("served_model"),
        "stop_reason": meta.get("stop_reason"),
        "stop_details": meta.get("stop_details"),
        "usage": meta.get("usage"),
    }
    if call_error:
        return {
            **base,
            "call_error": call_error, "returncode": None,
            "caught": None,
            "stdout": "", "stderr": "", "drafted_state": None,
            "drafted_narration": None, "raw_response": None,
        }

    # Declined at HTTP 200 -- no text to feed the pipeline, but a result
    # worth reading against this case's watch_for, not an error.
    if text is None:
        return {
            **base,
            "call_error": None, "refused": True, "returncode": None,
            "caught": None,
            "stdout": "", "stderr": "", "drafted_state": None,
            "drafted_narration": None, "raw_response": None,
        }

    state, narration, parse_error = extract_state_and_narration(text)
    if parse_error:
        return {
            **base,
            "call_error": None, "parse_error": parse_error,
            # Distinguishes "ran out of max_tokens mid-JSON" from "drafted
            # something with no JSON in it". Both fail to parse; only one
            # of them is the model's answer.
            "truncated": meta.get("stop_reason") == "max_tokens",
            "returncode": None, "caught": None, "stdout": "", "stderr": "",
            "drafted_state": None, "drafted_narration": None,
            "raw_response": text,
        }

    tmp_state_path = ROOT / f"_stress_test_gm_{case['id']}_{effort}.json"
    tmp_state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    try:
        rc, out, err = run(
            ["scripts/commit_state.py", str(tmp_state_path),
             "--note", f"[stress-test-gm-auto:{case['id']}:{effort}]",
             "--critique-text", narration],
        )
    finally:
        tmp_state_path.unlink(missing_ok=True)

    return {
        **base,
        "call_error": None, "parse_error": None,
        # Same meaning as in the tooling half: the pipeline rejected what
        # was drafted. compare() reads this key, so a GM result that
        # omitted it used to render as "not caught" no matter what
        # actually happened -- including a rejected commit.
        "returncode": rc, "caught": rc != 0,
        "stdout": out, "stderr": err,
        "drafted_state": state, "drafted_narration": narration,
        "raw_response": text,
    }


def auto_gm(label, model, effort, api_key):
    if not api_key:
        print("--auto-gm requires an API key. Pass --api-key or set "
              "ANTHROPIC_API_KEY. Falling back to manual mode instead: "
              "see --list-stress-prompts / --submit-stress-prompt.")
        return 1

    state = load_current()
    if state.get("turn", 0) != 0:
        print(f"REFUSING: saves/current.json is already at turn {state.get('turn')}, "
              "not turn 0. Restore a turn-0 throwaway save first -- the same rule "
              "--run-tooling-cases enforces, and for the same reason: an uncaught "
              "case commits for real.")
        return 1

    # Advisory, never blocking: a typo'd level 400s on every case and
    # wastes the whole run, but this list is a cache of what the current
    # models accept, so it must not be able to refuse a level that is
    # valid and simply newer than this comment.
    if effort and effort not in KNOWN_EFFORT_LEVELS:
        print(f"NOTE: effort {effort!r} is not one of the levels these models "
              f"were documented to take ({', '.join(KNOWN_EFFORT_LEVELS)}). "
              "Sending it anyway -- if it is wrong, every case below will "
              "record the same HTTP 400.\n")

    baseline = snapshot_campaign()
    results = []
    print(f"Running {len(GM_STRESS_PROMPTS)} GM-facing cases automatically "
          f"via the real API -- model={model}, effort={effort}, label={label!r}.\n")
    for i, case in enumerate(GM_STRESS_PROMPTS, start=1):
        print(f"-- GM case {i}/{len(GM_STRESS_PROMPTS)}: {case['id']} --")
        result = run_gm_stress_prompt_auto(case, model, effort, api_key)
        if result.get("call_error"):
            print(f"   API CALL FAILED: {result['call_error']}")
        elif result.get("refused"):
            print(f"   MODEL DECLINED: {result.get('stop_details')}")
        elif result.get("parse_error"):
            if result.get("truncated"):
                print("   TRUNCATED: hit max_tokens mid-draft, so no complete "
                      "JSON block -- raise max_tokens rather than reading this "
                      "as a refusal to draft.")
            else:
                print(f"   COULD NOT PARSE RESPONSE: {result['parse_error']}")
        else:
            outcome = "COMMIT REJECTED" if result["returncode"] != 0 else "COMMIT SUCCEEDED"
            print(f"   {outcome}")
        results.append(result)
        # Each case must be drafted against the same turn-0 baseline --
        # otherwise case N is really being tested against case N-1's
        # commit, and the two settings being compared saw different
        # starting states.
        restore_campaign(baseline)

    write_report(label, "gm_prompt_results", results)
    print("\nAutomatic run recorded outcomes only -- read each result's "
          "'watch_for' note against 'drafted_narration'/'drafted_state' in "
          "the report yourself; a clean commit does not by itself mean the "
          "GM handled the adversarial pressure well, only that whatever it "
          "drafted happened to pass the mechanical gates.")
    return 0


def run_all_auto(labels, model, efforts, api_key, dry_run):
    labels = [l.strip() for l in labels.split(",")]
    efforts = [e.strip() for e in efforts.split(",")]
    if len(labels) != len(efforts):
        print(f"--labels ({len(labels)}) and --efforts ({len(efforts)}) must "
              "have the same count -- one label per effort level being tested.")
        return 1

    baseline = snapshot_campaign()
    for label, effort in zip(labels, efforts):
        print("\n" + "=" * 70)
        print(f"SETTING: label={label!r}  model={model}  effort={effort}")
        print("=" * 70)
        restore_campaign(baseline)
        rc = play_tooling_cases(dry_run, label)
        if rc != 0:
            return rc
        if dry_run:
            print("[dry-run] skipping --auto-gm (would call the real API otherwise).")
            continue
        rc = auto_gm(label, model, effort, api_key)
        if rc != 0:
            return rc

    if not dry_run and len(labels) >= 2:
        print("\n" + "=" * 70)
        print("FULL COMPARISON")
        print("=" * 70)
        for a, b in zip(labels, labels[1:]):
            compare(a, b)
    return 0


def list_stress_prompts():
    ordinary = sum(1 for c in GM_STRESS_PROMPTS if c["id"] in ORDINARY_TURN_CASES)
    print(f"{len(GM_STRESS_PROMPTS)} GM-facing prompts "
          f"({len(GM_STRESS_PROMPTS) - ordinary} adversarial, {ordinary} ordinary "
          "turns). Run each one "
          "in a live Claude Code session at the setting under test, save what "
          "gets drafted, then feed it to --submit-stress-prompt.\n")
    for case in GM_STRESS_PROMPTS:
        print(f"id: {case['id']}")
        print(f"  prompt: {case['prompt']}")
        print(f"  watch for: {case['watch_for']}\n")


def outcome_label(result):
    """How one recorded case reads in a comparison.

    Deliberately not just the 'caught' boolean: the GM-facing cases have
    outcomes a boolean cannot express. A call that never reached the
    model and a response with no parseable state in it are both falsy,
    but neither is a statement about the pipeline, and collapsing them
    into "not caught" would report a dead API key as a clean pass.

    Falls back to returncode so reports written before 'caught' was
    recorded on GM results still compare correctly.
    """
    if result is None:
        return "MISSING"
    if result.get("call_error"):
        return "API CALL FAILED"
    if result.get("refused"):
        return "MODEL DECLINED"
    if result.get("parse_error"):
        # Truncation and "wrote no JSON" both fail the same parse, but
        # only the second is the model's actual answer -- the first just
        # means max_tokens ran out mid-draft.
        return "TRUNCATED (hit max_tokens)" if result.get("truncated") \
            else "UNPARSEABLE RESPONSE"
    caught = result.get("caught")
    if caught is None:
        rc = result.get("returncode")
        if rc is None:
            return "no result recorded"
        caught = rc != 0
    return "caught" if caught else "not caught"


def compare(label_a, label_b):
    path_a = REPORTS_DIR / f"stress_test_{label_a}.json"
    path_b = REPORTS_DIR / f"stress_test_{label_b}.json"
    if not path_a.exists() or not path_b.exists():
        print(f"Missing report(s): need both {path_a} and {path_b} to exist.")
        return 1

    data_a = json.loads(path_a.read_text(encoding="utf-8"))
    data_b = json.loads(path_b.read_text(encoding="utf-8"))

    print(f"Comparing '{label_a}' vs '{label_b}'\n" + "=" * 60)
    for section in set(data_a.get("sections", {})) | set(data_b.get("sections", {})):
        print(f"\n[{section}]")
        results_a = {r["case_id"]: r for r in data_a.get("sections", {}).get(section, [])}
        results_b = {r["case_id"]: r for r in data_b.get("sections", {}).get(section, [])}
        for case_id in sorted(set(results_a) | set(results_b)):
            ra = results_a.get(case_id)
            rb = results_b.get(case_id)
            a_outcome = outcome_label(ra)
            b_outcome = outcome_label(rb)
            flag = "  <-- DIFFERS" if a_outcome != b_outcome else ""
            print(f"  {case_id}: {label_a}={a_outcome}  {label_b}={b_outcome}{flag}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-tooling-cases", action="store_true")
    parser.add_argument("--list-stress-prompts", action="store_true")
    parser.add_argument("--submit-stress-prompt", metavar="CASE_ID")
    parser.add_argument("--state-file")
    parser.add_argument("--narration-file")
    parser.add_argument("--compare", nargs=2, metavar=("LABEL_A", "LABEL_B"))
    parser.add_argument("--label", default="unlabeled",
                         help="Tag this run so two settings' results don't overwrite each other.")
    parser.add_argument("--auto-gm", action="store_true",
                         help="Run GM_STRESS_PROMPTS automatically via the real Anthropic API. "
                              "Requires --api-key or ANTHROPIC_API_KEY. See the module docstring "
                              "for why this is a different (not strictly better) test than the "
                              "manual --submit-stress-prompt path.")
    parser.add_argument("--run-all-auto", action="store_true",
                         help="Full pipeline: tooling cases + auto-gm for every label/effort pair, "
                              "then compare. Requires an API key. This is the 'just do it end to "
                              "end' entry point.")
    parser.add_argument("--model", default="claude-opus-5",
                         help="Model string for --auto-gm / --run-all-auto, e.g. claude-opus-5.")
    parser.add_argument("--effort", default="medium",
                         help="Single effort level for --auto-gm, e.g. medium, high, xhigh.")
    parser.add_argument("--efforts",
                         help="Comma-separated effort levels for --run-all-auto, paired "
                              "positionally with --labels, e.g. 'medium,high'.")
    parser.add_argument("--labels",
                         help="Comma-separated labels for --run-all-auto, e.g. "
                              "'opus5-medium,opus5-high'.")
    parser.add_argument("--api-key",
                         help="Anthropic API key. Falls back to the ANTHROPIC_API_KEY env var. "
                              "Never required for any mode except --auto-gm / --run-all-auto.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")

    if args.list_stress_prompts:
        list_stress_prompts()
        return 0

    if args.compare:
        return compare(*args.compare)

    if args.submit_stress_prompt:
        if not args.state_file or not args.narration_file:
            print("--submit-stress-prompt requires --state-file and --narration-file.")
            return 1
        return submit_stress_prompt(args.submit_stress_prompt, args.label, args.state_file, args.narration_file)

    if args.run_all_auto:
        if not args.labels or not args.efforts:
            print("--run-all-auto requires --labels and --efforts (comma-separated, same count).")
            return 1
        return run_all_auto(args.labels, args.model, args.efforts, api_key, args.dry_run)

    if args.auto_gm:
        return auto_gm(args.label, args.model, args.effort, api_key)

    if args.run_tooling_cases:
        return play_tooling_cases(args.dry_run, args.label)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
