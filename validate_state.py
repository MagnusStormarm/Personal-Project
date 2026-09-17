#!/usr/bin/env python3
"""Validate saves/current.json (or an arbitrary state file) against
state_schema.json plus a handful of extra rules that plain JSON Schema
can't easily express (per-month day bounds, closed inventory at turn 0,
non-negative currency, soft-cap array sizes, npc_id registry consistency).

manual_checks() below is the authoritative enforcement layer: it runs
unconditionally, whether or not the optional jsonschema package is
installed. It covers required fields, basic types, the month enum, and
array-internal duplicate detection directly, so a missing field, a wrong
type, an invalid month name, or a colliding npc_id/gear name/thread text
is caught even without jsonschema present. This intentionally duplicates
only a bounded subset of what a full jsonschema pass would catch (see
TOP_LEVEL_TYPES below) -- it's not a JSON Schema reimplementation, just
enough hand-written coverage that this file's actual behavior matches
its documented guarantee.

Usage:
    python3 scripts/validate_state.py [path]      # authoritative check
    python3 scripts/validate_state.py --quick     # fast gear-only glance
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "state_schema.json"
DEFAULT_STATE_PATH = ROOT / "saves" / "current.json"
NPC_REGISTRY_PATH = ROOT / "saves" / "npc_registry.json"
LOCATIONS_PATH = ROOT / "saves" / "locations.json"

BASELINE_GEAR = {"T-shirt", "Jeans", "Underwear", "Socks", "Shoes"}

SOFT_CAPS = {
    "npc_relationships": 10,
    "open_threads": 8,
    "continuity_notes": 5,
    "throughline": 6,
}

MONEY_WORDS = {"coin", "coins", "mark", "marks", "crown", "crowns",
               "sovereign", "sovereigns", "penny", "pennies", "copper",
               "silver", "gold", "platinum"}

# Fields validate_state.py itself understands well enough to name a type
# for, independent of the jsonschema package -- kept intentionally small
# and hand-maintained rather than parsed out of state_schema.json, so a
# schema change can't silently alter what this layer checks without a
# human noticing here too.
TOP_LEVEL_REQUIRED = ["schema_version", "turn", "in_world_date", "gear", "currency"]
TOP_LEVEL_TYPES = {
    "schema_version": int,
    "turn": int,
    "in_world_date": dict,
    # state_schema.json has carried `language` as an object property, but
    # this table did not, so every save that set it drew an "unrecognized
    # top-level field" warning from the manual checks while passing schema
    # validation cleanly -- two validators disagreeing about the same
    # field. earn_clean_slate.py sets it on turn 2, so the project's own
    # coverage fixture produced that warning on every run.
    "language": dict,
    "gear": list,
    "currency": dict,
    "status": list,
    "magic": list,
    "npc_relationships": list,
    "open_threads": list,
    "continuity_notes": list,
    "throughline": list,
    "entities": list,
    "factions": list,
    "scene": str,
    "current_location": str,
    "travel": dict,
    "handoff_summary": str,
    "arc_title": str,
    "chapter_title": str,
}
VALID_MONTHS = {
    "Frostwane", "Thawmoon", "Seedmonth", "Greenrise", "Sunheight",
    "Highsummer", "Goldleaf", "Harvestide", "Mistfall", "Darkening",
    "Longnight", "Deepwinter", "The Turning",
}
# Calendar order (for date-ordinal comparisons -- e.g. "has this journey's
# ETA passed yet"), matching the month enum above. Order and each month's
# length are sourced from docs/ELDARA_REFERENCE.md \u00a72.2's calendar line
# ("Frostwane . Thawmoon . ... . Longnight . Deepwinter", 12 x 30-day
# months) plus \u00a72.9's holiday table, which places "The Turning" as a
# midwinter 5-day festival -- i.e. between Longnight and Deepwinter,
# not simply appended after the ordinary 12. manual_checks() above
# already enforces the same 5-vs-30 day-length split for the day-bound
# check; this list additionally encodes month ORDER, since nothing
# needed that before travel-date comparisons existed.
MONTH_ORDER = [
    "Frostwane", "Thawmoon", "Seedmonth", "Greenrise", "Sunheight",
    "Highsummer", "Goldleaf", "Harvestide", "Mistfall", "Darkening",
    "Longnight", "The Turning", "Deepwinter",
]
MONTH_LENGTHS = {m: (5 if m == "The Turning" else 30) for m in MONTH_ORDER}


def date_ordinal(date):
    """Converts an in_world_date dict ({day, month, year}) to a single
    increasing integer, so two dates can be compared with plain <, ==, >
    instead of hand-rolling day/month/year comparisons at every call
    site. Returns None if the date is missing required fields or names
    an unrecognized month -- callers should treat that as "can't compare"
    rather than guessing.

    Placed here rather than in commit_state.py (its first caller) because
    this module already owns MONTH_ORDER/MONTH_LENGTHS and the informal
    version of this same calendar knowledge (manual_checks()'s per-month
    day-bound check) -- keeping the calendar logic in one file means a
    future calendar change (a new month, a reordering) can't update one
    copy and silently leave the other stale."""
    if not isinstance(date, dict):
        return None
    day, month, year = date.get("day"), date.get("month"), date.get("year")
    if month not in MONTH_ORDER or not isinstance(day, int) or not isinstance(year, int):
        return None
    days_per_year = sum(MONTH_LENGTHS.values())
    month_index = MONTH_ORDER.index(month)
    days_before_this_month = sum(MONTH_LENGTHS[m] for m in MONTH_ORDER[:month_index])
    return year * days_per_year + days_before_this_month + day

KNOWN_TOP_LEVEL_FIELDS = set(TOP_LEVEL_TYPES) | {"commit_token"}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_json_as_dict(path):
    """Like load_json(), but raises ValueError if the parsed JSON isn't a
    dict at the top level. Every caller in this file assumes dict-shaped
    state -- valid JSON that parses to a list, string, or number would
    otherwise crash on the first .get()/.keys() call instead of failing
    with a clear message."""
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object at the top level, got {type(data).__name__}")
    return data


def try_jsonschema_validation(state, schema):
    """Use the jsonschema package if available; otherwise skip silently
    and rely entirely on manual_checks() below."""
    try:
        import jsonschema
    except ImportError:
        print("(jsonschema package not installed — using built-in checks only; "
              "run `pip install jsonschema` for stricter schema validation)")
        return []

    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(state), key=lambda e: list(e.path))
    return [f"{'.'.join(str(p) for p in e.path) or '(root)'}: {e.message}" for e in errors]


def normalize_npc_id(npc_id):
    """Canonical form for COMPARING npc_ids -- never for storing them.

    gear names and open_thread text are already deduped on
    .strip().lower() in manual_checks() below; npc_id was the one
    identifier still compared as an exact string, so 'innkeeper-maren'
    and 'Innkeeper-Maren' were accepted as two distinct people with no
    complaint. Normalizing only the comparison means no existing
    npc_registry.json has to be rewritten -- whatever spelling is
    already stored stays stored.
    """
    if not isinstance(npc_id, str):
        return None
    return npc_id.strip().lower() or None


def find_registered_npc_id(registry, npc_id):
    """The key under which npc_id is already registered, ignoring case
    and surrounding whitespace -- or None if it isn't registered.

    Returns the STORED spelling rather than a boolean so callers can
    update the entry that already exists instead of adding a second one,
    and can tell the author which spelling the registry uses.
    """
    target = normalize_npc_id(npc_id)
    if target is None or not isinstance(registry, dict):
        return None
    for stored in registry:
        if normalize_npc_id(stored) == target:
            return stored
    return None


DENOMINATIONS = ("copper", "silver", "gold", "platinum")

# Prose that says a thread's business is FINISHED. state_schema.json:
# "a resolved thread is removed from this array entirely, never just
# marked inactive." Detection is textual, so this drives a warning and
# never a rejection -- this project's own line is that blocking gates are
# deterministic and heuristics stay advisory.
#
# Calibrated against all 26 distinct thread texts produced by this
# session's blind runs: 4 true positives, 0 false positives. The
# phrasings it must NOT fire on are as instructive as the ones it must:
# "the healer's fee she paid on his ankle" is a live debt (hence
# `paid off|in full|it|her`, never bare "paid"), and "Maren's standing
# offer ... for 4 copper" is open-but-not-urgent with active=false, which
# is what that flag legitimately means.
# A sum in a thread's text is only that thread's PRICE if the thread is
# about owing or paying it. Sweeping all 55 committed states from this
# session's blind runs found the bare-sum test too loose: "Needs to get
# inside Hollow Creek's gate before it shuts at dark, with 6 copper and
# no one inside who knows him" states a sum, but it is money Chad HOLDS,
# not an obligation -- and a horse priced in a market rumour, or an offer
# never accepted, are information rather than debts. The original
# calibration asked only whether a price could be found, never whether it
# was this thread's price, which is why 26 texts looked clean and 10 did
# not. An advisory that cries wolf gets switched off, so it asks for an
# obligation word too.
OBLIGATION_PROSE = re.compile(
    r"\b(owes?|owed|owing|due|debt|tab|pay|paid|payment|fee|rent|"
    r"settle[sd]?|charge[sd]?|price)\b", re.I)

RESOLVED_PROSE = re.compile(
    r"\b(settled|closed by|paid (?:off|in full|it|her)|resolved|discharged|"
    r"no longer owed|fully paid)\b", re.I)

# Numbers written out in prose. Kept small and common on purpose: the
# point is to catch a price the narration plainly stated, not to parse
# arbitrary English.
WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "twenty": 20, "thirty": 30,
}


def prices_in_text(text):
    """Sums named in a thread's text, as {denomination: total}.

    Returns {denomination: {values seen}} -- a SET per denomination, not a
    sum. An earlier version added repeated figures together and promptly
    misread this project's own fixture: "2 copper a night, 14 copper for
    the week" is a rate and a total, and summing them produced 16, a
    number the text never states. Prose routinely names the same
    denomination more than once for different purposes, so any single
    figure it states is a legitimate reading and the caller checks for
    membership rather than equality. Different denominations in one
    phrase ("two silver and 6 copper") stay separate, which is what makes
    that case still work.

    Matches "22 copper", "two silver", "five copper a night". Deliberately
    literal -- it is looking for a price the prose actually stated, not
    trying to understand the sentence. Anything it cannot read confidently
    it does not report, because this drives a warning a human has to
    triage and a noisy version would be turned off.
    """
    found = {}
    if not isinstance(text, str):
        return found
    for m in re.finditer(
            r"\b(\d{1,4}|" + "|".join(WORD_NUMBERS) + r")\s+(" +
            "|".join(DENOMINATIONS) + r")\b", text, re.I):
        raw, denom = m.group(1).lower(), m.group(2).lower()
        n = WORD_NUMBERS.get(raw)
        if n is None:
            try:
                n = int(raw)
            except ValueError:
                continue
        found.setdefault(denom, set()).add(n)
    return found


def companion_paths(state_path):
    """Where to look for the campaign data files that sit ALONGSIDE a save.

    validate_state.py takes a path argument, but until now it validated
    the file at that path while reading npc_registry.json and
    locations.json relative to the SCRIPT. Validating another campaign's
    save therefore checked it against this campaign's registry: eight
    retained copies were reported as having eight unregistered NPCs each,
    confidently and wrongly. Failing loudly with a wrong answer is worse
    than not supporting the case, because it reads as a real finding.

    The rule is deliberately narrow: use a companion file only if it
    actually sits next to the save being validated. Anything else falls
    back to this script's own tree.

    That narrowness is load-bearing, not caution for its own sake.
    commit_state.py validates a PROPOSAL at /tmp/proposed_state.json,
    which has no campaign around it. Deriving paths from the target
    unconditionally would point the registry check at /tmp, find nothing,
    and skip it -- and the is_new_npc registry check is a blocking gate,
    so it would fail open on the one path that matters most. A proposal
    must keep being checked against the registry of the campaign it is
    proposed FOR.

    The schema is deliberately NOT included. state_schema.json is project
    code, not campaign data: a save is validated against THIS checkout's
    schema on purpose, which is what makes a schema change take effect
    for old saves.
    """
    registry, locations = NPC_REGISTRY_PATH, LOCATIONS_PATH
    try:
        here = Path(state_path).resolve().parent
    except (OSError, ValueError):
        return registry, locations
    sibling_registry = here / "npc_registry.json"
    sibling_locations = here / "locations.json"
    if sibling_registry.exists():
        registry = sibling_registry
    if sibling_locations.exists():
        locations = sibling_locations
    return registry, locations


def manual_checks(state, registry_path=None, locations_path=None):
    """Checks that always run, regardless of whether jsonschema is
    installed -- this is the authoritative enforcement layer."""
    errors = []
    warnings = []

    # Required top-level fields: presence and non-null. A field that's
    # present but explicitly null would otherwise pass both this check
    # (key exists) and the type check below (which deliberately skips
    # None, since optional fields may be null/absent) -- required fields
    # need this explicit null rejection to actually be required.
    for field in TOP_LEVEL_REQUIRED:
        if field not in state:
            errors.append(f"required field '{field}' is missing")
        elif state[field] is None:
            errors.append(f"required field '{field}' is present but null")

    # Basic top-level types. Booleans are rejected explicitly wherever
    # int is expected: Python's isinstance(True, int) is True (bool is
    # an int subclass), so a plain isinstance check alone would silently
    # accept "turn: true" as a valid integer.
    for field, expected_type in TOP_LEVEL_TYPES.items():
        if field in state and state[field] is not None:
            value = state[field]
            if expected_type is int and isinstance(value, bool):
                errors.append(f"{field} should be type int, got bool")
            elif not isinstance(value, expected_type):
                errors.append(
                    f"{field} should be type {expected_type.__name__}, "
                    f"got {type(value).__name__}"
                )

    # Unknown/typo'd top-level fields: the schema has no
    # additionalProperties:false, so these are otherwise accepted and
    # persisted silently forever. Flagged as a warning rather than an
    # error, since a genuinely new field a human added on purpose
    # shouldn't hard-block a commit -- but a typo like "curency" should
    # be visible rather than silently retained.
    unknown_fields = set(state.keys()) - KNOWN_TOP_LEVEL_FIELDS
    for field in sorted(unknown_fields):
        warnings.append(f"unrecognized top-level field '{field}' -- typo, or a deliberate new field not yet added to TOP_LEVEL_TYPES?")

    # Per-month day bound (schema only knows a loose 1-35 ceiling) and
    # month enum.
    date = state.get("in_world_date", {})
    month = date.get("month") if isinstance(date, dict) else None
    day = date.get("day") if isinstance(date, dict) else None
    if month is not None and month not in VALID_MONTHS:
        errors.append(f"in_world_date.month='{month}' is not a recognized month")
    if month and day is not None:
        max_day = 5 if month == "The Turning" else 30
        if day > max_day:
            errors.append(f"in_world_date.day={day} exceeds max {max_day} for month '{month}'")

    # Turn must be non-negative.
    turn = state.get("turn")
    if isinstance(turn, (int, float)) and turn < 0:
        errors.append(f"turn={turn} is negative")

    # Closed inventory at turn 0. state.get("gear", []) alone isn't safe
    # here: a present-but-null "gear" field returns None (not the []
    # default) from .get(), which would then crash iteration below. The
    # null case is already recorded as its own error above (required
    # field present but null), so this block just needs to not also
    # crash on top of that.
    if state.get("turn") == 0:
        gear_field = state.get("gear")
        gear_field = gear_field if isinstance(gear_field, list) else []
        # Non-dict gear entries (e.g. gear submitted as a list of bare
        # strings) are flagged as their own error and excluded from the
        # baseline comparison below, rather than crashing on g.get().
        malformed_gear_entries = [g for g in gear_field if not isinstance(g, dict)]
        for g in malformed_gear_entries:
            errors.append(f"gear entry {g!r} is not an object (expected {{'name': ...}}, got {type(g).__name__})")
        gear_names = {g.get("name") for g in gear_field if isinstance(g, dict)}
        if not malformed_gear_entries and gear_names != BASELINE_GEAR:
            errors.append(
                f"turn 0 gear must be exactly {sorted(BASELINE_GEAR)}, got {sorted(gear_names)}"
            )

    # Currency never negative (schema covers this too, but double-check).
    currency = state.get("currency", {})
    if isinstance(currency, dict):
        for denom, amount in currency.items():
            if isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount < 0:
                errors.append(f"currency.{denom}={amount} is negative")

    # gear_list filters to dict entries only; non-dict entries are
    # reported once above (turn-0 check) rather than repeatedly here.
    raw_gear_list = state.get("gear", []) if isinstance(state.get("gear"), list) else []
    gear_list = [g for g in raw_gear_list if isinstance(g, dict)]
    if state.get("turn") != 0:
        for g in raw_gear_list:
            if not isinstance(g, dict):
                errors.append(f"gear entry {g!r} is not an object (expected {{'name': ...}}, got {type(g).__name__})")

    # No gear entry pretending to be currency.
    for g in gear_list:
        name = str(g.get("name", "")).strip().lower()
        if name in MONEY_WORDS:
            errors.append(f"gear entry '{g.get('name')}' looks like currency; use the currency object instead")

    # Duplicate identity-bearing entries within a single array -- not
    # just cross-checked against the persistent npc_registry.json, but
    # also checked for internal collisions in the same submitted state.
    gear_seen = {}
    for idx, g in enumerate(gear_list):
        name = str(g.get("name", "")).strip().lower()
        if name and name in gear_seen:
            errors.append(f"gear has duplicate entries named '{g.get('name')}' (indices {gear_seen[name]} and {idx})")
        else:
            gear_seen[name] = idx

    raw_npc_list = state.get("npc_relationships", []) if isinstance(state.get("npc_relationships"), list) else []
    npc_list = [n for n in raw_npc_list if isinstance(n, dict)]
    for n in raw_npc_list:
        if not isinstance(n, dict):
            errors.append(f"npc_relationships entry {n!r} is not an object (expected {{'npc_id': ..., 'name': ...}}, got {type(n).__name__})")
    npc_id_seen = {}
    for idx, npc in enumerate(npc_list):
        npc_id = npc.get("npc_id")
        key = normalize_npc_id(npc_id)
        if key is None:
            # A missing npc_id is a separate problem, reported by the
            # registry check below; don't key the dedup map on None.
            continue
        if key in npc_id_seen:
            prev_idx, prev_spelling = npc_id_seen[key]
            if prev_spelling == npc_id:
                errors.append(f"npc_relationships has duplicate npc_id '{npc_id}' (indices {prev_idx} and {idx})")
            else:
                errors.append(
                    f"npc_relationships has two npc_ids differing only by case or "
                    f"surrounding whitespace: '{prev_spelling}' (index {prev_idx}) and "
                    f"'{npc_id}' (index {idx}) -- these would register as two separate "
                    "people; pick one spelling and use it consistently"
                )
        else:
            npc_id_seen[key] = (idx, npc_id)

    raw_thread_list = state.get("open_threads", []) if isinstance(state.get("open_threads"), list) else []
    thread_list = [t for t in raw_thread_list if isinstance(t, dict)]
    for t in raw_thread_list:
        if not isinstance(t, dict):
            errors.append(f"open_threads entry {t!r} is not an object (expected {{'text': ..., 'added_turn': ...}}, got {type(t).__name__})")
    thread_text_seen = {}
    for idx, thread in enumerate(thread_list):
        text = str(thread.get("text", "")).strip().lower()
        if text and text in thread_text_seen:
            errors.append(f"open_threads has duplicate entries with text '{thread.get('text')}' (indices {thread_text_seen[text]} and {idx})")
        else:
            thread_text_seen[text] = idx

    # Soft caps on tracked arrays.
    for field, cap in SOFT_CAPS.items():
        items = state.get(field, [])
        if isinstance(items, list) and len(items) > cap:
            errors.append(f"{field} has {len(items)} entries, exceeding soft cap of {cap}")

    # open_threads deadline_turn must be strictly after added_turn.
    for thread in thread_list:
        added = thread.get("added_turn")
        deadline = thread.get("deadline_turn")
        if deadline is not None and added is not None and deadline <= added:
            errors.append(
                f"open_thread '{thread.get('text', '')[:40]}...' has deadline_turn <= added_turn"
            )
        # A thread whose prose says it is finished should not still be in
        # open_threads. The array is the OPEN business; `active: false`
        # means open-but-not-time-pressured, not resolved.
        #
        # Retention looked defensible: one blind chain kept a resolved
        # thread reading "CLOSED BY PAYMENT, not by forgiveness" and did
        # resist a later attempt to rewrite that debt as forgiven. But
        # all three chains recorded the same refusal in continuity_notes,
        # which is equally part of the state the next turn reads, and the
        # chain that retained NOTHING defended just as well. The audit
        # trail is delivered by continuity_notes either way; retention
        # only spends soft-cap space -- 40% of one chain's array was
        # closed business -- and pushes toward the cap where pruning,
        # itself a known-risky path, gets invoked.
        # `active` is optional, so gating on `is False` meant "Room fee
        # settled in full" with active:true, or with no active key at all,
        # was never flagged -- the two shapes most likely to be a mistake,
        # since a thread that is genuinely finished and still marked live is
        # worse than one marked inactive.
        if RESOLVED_PROSE.search(str(thread.get("text") or "")):
            warnings.append(
                f"open_thread '{thread.get('text', '')[:40]}...' reads as already "
                f"resolved but is still in open_threads. A resolved thread is "
                f"removed entirely, never just marked inactive -- it is spending "
                f"soft-cap space on closed business. If the point is to record "
                f"HOW it closed (paid, not forgiven), that belongs in "
                f"continuity_notes, which the next turn reads too."
            )

        # An obligation's amount, where the fiction named one.
        amount = thread.get("amount")
        if amount is not None:
            if not isinstance(amount, dict):
                errors.append(
                    f"open_thread '{thread.get('text', '')[:40]}...' has an "
                    f"amount that is not an object ({type(amount).__name__})"
                )
            else:
                for denom, val in amount.items():
                    if denom not in DENOMINATIONS:
                        errors.append(
                            f"open_thread '{thread.get('text', '')[:40]}...' "
                            f"amount has unknown denomination '{denom}'"
                        )
                    elif not isinstance(val, int) or isinstance(val, bool) or val < 0:
                        errors.append(
                            f"open_thread '{thread.get('text', '')[:40]}...' "
                            f"amount.{denom}={val!r} must be a non-negative integer"
                        )

        # The field only earns its place if a stated price and a recorded
        # one cannot quietly disagree -- same shape as the deadline units
        # check above. Without this, `amount` is just another field the
        # prose can contradict.
        thread_text = str(thread.get("text") or "")
        stated = (prices_in_text(thread_text)
                  if OBLIGATION_PROSE.search(thread_text) else {})
        if stated:
            if isinstance(amount, dict):
                for denom, values in stated.items():
                    if denom not in amount:
                        # Only shared denominations used to be compared, so
                        # text "Owes Maren 14 copper" with amount
                        # {"silver": 3} passed in total silence -- the two
                        # disagreed about the DENOMINATION and the check
                        # looked the other way.
                        warnings.append(
                            f"open_thread '{thread.get('text', '')[:40]}...' text "
                            f"names {sorted(values)} {denom} but `amount` records "
                            f"no {denom} at all -- the prose and the record "
                            f"disagree about what is owed")
                    elif amount[denom] not in values:
                        warnings.append(
                            f"open_thread '{thread.get('text', '')[:40]}...' text "
                            f"names {sorted(values)} {denom} but "
                            f"amount.{denom}={amount[denom]}, which the text never "
                            f"states -- the prose and the record disagree"
                        )
            elif amount is None:
                warnings.append(
                    f"open_thread '{thread.get('text', '')[:40]}...' names a price "
                    f"in its text ({ {k: sorted(v) for k, v in stated.items()} }) "
                    f"but records no `amount`. A sum that "
                    f"lives only in prose is one a later turn can silently "
                    f"reinvent -- five blind runs settled the same unpriced debt "
                    f"at 10/4/6/0/34 copper-equivalent."
                )

        # deadline_date is checked FIRST and wins where both are present.
        # A turn count is the wrong unit for an obligation the fiction dates
        # in days: turns and days advance at rates measured between 0.00 and
        # 1.09 days/turn, so the same deadline_turn means a different date
        # in every campaign, and drifts within one. Blind testing caught a
        # GM re-pegging deadline_turn 15 -> 18 by hand and journalling that
        # it was correcting proxy drift, not extending the story.
        ddate = thread.get("deadline_date")
        deadline_ord = date_ordinal(ddate) if isinstance(ddate, dict) else None
        today_ord = date_ordinal(state.get("in_world_date"))

        if ddate is not None and deadline_ord is None:
            errors.append(
                f"open_thread '{thread.get('text', '')[:40]}...' has a "
                f"deadline_date that is not a usable date ({ddate!r})"
            )
        if deadline_ord is not None and today_ord is not None:
            added = thread.get("added_turn")
            if thread.get("active") and today_ord > deadline_ord:
                warnings.append(
                    f"open_thread '{thread.get('text', '')[:40]}...' has a lapsed "
                    f"active deadline (deadline_date={ddate.get('day')} "
                    f"{ddate.get('month')} {ddate.get('year')}, and it is now "
                    f"{(state.get('in_world_date') or {}).get('day')} "
                    f"{(state.get('in_world_date') or {}).get('month')})"
                )
            # Fix E: the two units disagreeing is the bug becoming visible.
            # Only reported when the turn proxy says lapsed and the date says
            # otherwise or vice versa -- not on every mismatch, since the two
            # legitimately differ in magnitude.
            current_turn = state.get("turn", 0)
            if deadline is not None and isinstance(current_turn, (int, float)):
                by_turn = current_turn > deadline
                by_date = today_ord > deadline_ord
                if by_turn != by_date:
                    warnings.append(
                        f"open_thread '{thread.get('text', '')[:40]}...' has "
                        f"deadline_turn and deadline_date DISAGREEING about whether "
                        f"it has lapsed (turn says {'lapsed' if by_turn else 'live'}, "
                        f"date says {'lapsed' if by_date else 'live'}). The date is "
                        f"authoritative; deadline_turn={deadline} has drifted and "
                        f"should be re-pegged or dropped."
                    )
        elif thread.get("active") and deadline is not None:
            # No usable date: fall back to the turn proxy, as before, so
            # saves written before deadline_date existed keep their check.
            current_turn = state.get("turn", 0)
            if isinstance(current_turn, (int, float)) and current_turn > deadline:
                warnings.append(
                    f"open_thread '{thread.get('text', '')[:40]}...' has a lapsed active deadline "
                    f"(deadline_turn={deadline}, current turn={current_turn}) "
                    f"-- turn-based, and turns are not days; prefer deadline_date"
                )

    # npc_id registry consistency, if a registry file exists.
    registry_path = registry_path or NPC_REGISTRY_PATH
    locations_path = locations_path or LOCATIONS_PATH
    if registry_path.exists():
        try:
            registry = load_json(registry_path)
        except (json.JSONDecodeError, OSError, RecursionError):
            registry = {}
        for npc in npc_list:
            npc_id = npc.get("npc_id")
            is_new = npc.get("is_new_npc")
            if npc_id is None:
                continue
            registered_as = find_registered_npc_id(registry, npc_id)
            already_registered = registered_as is not None
            # A different spelling of an id that IS registered isn't an
            # error -- the lookup found the right person -- but passing
            # it silently is how the save file and the registry drift
            # apart on spelling, so it earns a non-blocking note.
            if already_registered and registered_as != npc_id:
                warnings.append(
                    f"npc '{npc_id}' is registered as '{registered_as}' -- same person, "
                    "different spelling; use the registered spelling so the save and "
                    "the registry stay in agreement"
                )
            # is_new is checked against all three states (True, False,
            # None/omitted) so that omitting the field on a genuinely new
            # npc_id doesn't silently skip this consistency check.
            if is_new is True and already_registered:
                errors.append(
                    f"npc '{npc_id}' marked is_new_npc=true but already exists in "
                    f"npc_registry.json"
                    + (f" as '{registered_as}'" if registered_as != npc_id else "")
                )
            elif is_new is False and not already_registered:
                errors.append(f"npc '{npc_id}' marked is_new_npc=false but not found in npc_registry.json")
            elif is_new is None and not already_registered:
                errors.append(
                    f"npc '{npc_id}' is not in npc_registry.json (so this is a new introduction) "
                    "but is_new_npc was omitted -- set it explicitly to true or false"
                )

    # current_location / travel consistency against saves/locations.json,
    # if that file exists -- the World Map analog. Mirrors the
    # npc_id-registry check just above: absence of locations.json is not
    # itself an error (older saves, or a campaign that hasn't opted into
    # location tracking yet, both leave these fields unset), but if a
    # location id IS given, it must resolve to something real rather than
    # silently accepting a typo or an invented place that would then
    # never match locations.json's route data.
    locations_data = None
    if locations_path.exists():
        try:
            locations_data = load_json(locations_path)
        except (json.JSONDecodeError, OSError, RecursionError) as e:
            # Announce it. Silently setting this to None skips the whole
            # current_location / travel-destination block below, which turned
            # a real FAIL into a PASS: an invented location validated clean
            # the moment locations.json stopped parsing, with nothing said.
            # This file already has the right convention for a degraded check
            # -- it names a missing jsonschema rather than letting its absence
            # look like a clean result -- it just was not applied here.
            locations_data = None
            warnings.append(
                f"{locations_path.name} could not be read ({e}), so "
                f"current_location and any travel destination were NOT "
                f"checked against known locations this run. That is a skipped "
                f"check, not a passed one.")

    if locations_data is not None:
        known_locations = locations_data.get("locations", {})
        routes = locations_data.get("routes", {})

        current_location = state.get("current_location")
        if current_location is not None and current_location not in known_locations:
            errors.append(
                f"current_location '{current_location}' is not in saves/locations.json"
            )

        travel = state.get("travel")
        if isinstance(travel, dict):
            destination = travel.get("destination")
            if destination is not None and destination not in known_locations:
                errors.append(
                    f"travel.destination '{destination}' is not in saves/locations.json"
                )

            # A journey should be FROM somewhere tracked TO somewhere
            # tracked -- current_location doubles as the origin here,
            # since travel.origin would just be current_location's value
            # duplicated at the moment of departure. If current_location
            # is missing while travel is active, that's the one case this
            # can't cross-check at all, which is itself worth flagging
            # rather than silently skipping the route lookup below.
            if destination is not None and destination in known_locations:
                if current_location is None:
                    warnings.append(
                        "travel is set but current_location is unset -- route duration "
                        "can't be cross-checked against saves/locations.json without "
                        "knowing the origin"
                    )
                elif current_location == destination:
                    errors.append(
                        f"travel.destination '{destination}' is the same as current_location "
                        "-- Chad can't be traveling to where he already is"
                    )
                elif current_location in known_locations:
                    route_key = "|".join(sorted([current_location, destination]))
                    route = routes.get(route_key)
                    if route is None:
                        warnings.append(
                            f"no known route between '{current_location}' and '{destination}' "
                            "in saves/locations.json -- duration can't be checked against lore "
                            "(add the route there if this is an established journey, per "
                            "docs/ELDARA_REFERENCE.md \u00a72.8)"
                        )
                    else:
                        departed_turn = travel.get("departed_turn")
                        if departed_turn is not None and turn is not None:
                            elapsed_turns = turn - departed_turn
                            if isinstance(elapsed_turns, (int, float)) and elapsed_turns < 0:
                                errors.append(
                                    f"travel.departed_turn={departed_turn} is after the "
                                    f"current turn={turn}"
                                )

        elif travel is not None:
            errors.append(f"travel should be type dict, got {type(travel).__name__}")

    return errors, warnings


def run_validation(path):
    if not SCHEMA_PATH.exists():
        print(f"FAIL: schema file missing at {SCHEMA_PATH}")
        return False

    try:
        state = load_json_as_dict(path)
    except (json.JSONDecodeError, OSError, ValueError, RecursionError) as e:
        print(f"FAIL: could not read/parse {path}: {e}")
        return False

    schema = load_json(SCHEMA_PATH)

    schema_errors = try_jsonschema_validation(state, schema)
    registry_path, locations_path = companion_paths(path)
    manual_errors, manual_warnings = manual_checks(state, registry_path, locations_path)

    all_errors = schema_errors + manual_errors

    for w in manual_warnings:
        print(f"WARNING: {w}")

    if all_errors:
        print(f"FAIL: state validation failed ({path})")
        for e in all_errors:
            print(f"  - {e}")
        return False

    print(f"PASS: state validation succeeded ({path})")
    return True


def quick_check(path):
    """Fast glance: just confirm gear parses and turn-0 baseline holds,
    without the full schema pass."""
    try:
        state = load_json_as_dict(path)
    except (json.JSONDecodeError, OSError, ValueError, RecursionError) as e:
        print(f"FAIL (quick): could not read/parse {path}: {e}")
        return False

    gear_field = state.get("gear")
    gear_field = gear_field if isinstance(gear_field, list) else []
    gear_names = [g.get("name") if isinstance(g, dict) else g for g in gear_field]
    print(f"Turn {state.get('turn')}: gear = {gear_names}")
    if state.get("turn") == 0 and set(gear_names) != BASELINE_GEAR:
        print("WARNING: turn 0 gear does not match baseline")
    return True


def main():
    args = sys.argv[1:]
    if "--quick" in args:
        path = DEFAULT_STATE_PATH
        quick_check(path)
        return

    path = Path(args[0]) if args else DEFAULT_STATE_PATH
    ok = run_validation(path)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
