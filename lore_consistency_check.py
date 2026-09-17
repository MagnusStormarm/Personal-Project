#!/usr/bin/env python3
"""Advisory lore-consistency pass over drafted narration: retrieves the
lore sections relevant to what a turn actually mentions, then surfaces
places where the narration and the retrieved lore might disagree.

This is the retrieval-driven half of self_critique.py's job, not a
replacement for it. self_critique.py checks narration against MECHANICAL
state (saves/current.json) -- gear, currency, tone breaks -- using fixed,
hand-written patterns for a fixed, small vocabulary. That works because
gear/currency are closed, structured sets. World lore is neither: it's
prose, open-ended, and far bigger than anything worth hand-coding a
pattern list for. So instead of pattern-matching lore facts directly,
this script leans on retrieval (scripts/world_info_lookup.py's existing
keyword -> section mapping) to find which lore sections are RELEVANT to
this turn, prints them for a human to actually compare against, and adds
only a small number of cheap, high-confidence textual signals on top
(e.g. a named NPC the lore explicitly marks as dead appearing as if
alive). Everything else is surfaced, not adjudicated -- the same
hard/advisory split self_critique.py already uses, applied to a domain
where the "hard" side has to stay much narrower.

Why this is a separate script rather than added to self_critique.py:
self_critique.py's checks are all synchronous, dependency-free pattern
matches against a small closed vocabulary (CURRENCY_WORDS, a fixed
weapon-word list) -- cheap enough to run on every commit without a
second thought. Lore retrieval pulls in a second file
(world_info_lookup.py), operates over open-ended prose instead of a
closed vocabulary, and is expected to grow (more entity types, better
matching) independently of the gear/currency checks. Keeping it separate
means a change here can't silently alter self_critique.py's existing,
already-tuned behavior, and this script can be skipped in contexts where
world_info_lookup's data isn't available without touching the mandatory
gate at all.

Usage:
    python3 scripts/lore_consistency_check.py <path-to-drafted-turn.txt>

Exit code is always 0 -- this script never blocks a commit (see
commit_state.py's --skip-lore-check docstring for how it's wired in).
Advisory notices go to stdout; a human (or, per docs/MODEL_NOTES.md, a
future LLM-based judge) decides what to do with them.
"""
import json
import re
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = SCRIPTS_DIR.parent
DOCS = ROOT / "docs"

sys.path.insert(0, str(SCRIPTS_DIR))
import world_info_lookup as wil  # noqa: E402


# Pinned facts -- the lore equivalent of self_critique's
# CURRENCY_WORDS/UNEARNED_ATTRACTION_PHRASES lists -- live in
# saves/pinned_facts.json rather than here, so a fact established during
# play can be added without editing this script's source (this is
# Auferet's pinned-facts feature: short "never forget" one-liners a
# player can pin as the campaign goes, not just pre-authored lore). Each
# entry: a real, unambiguous fact, plus regex(es) whose match in drafted
# narration would contradict it. Kept to facts that are both load-bearing
# and cheap to check textually -- not an attempt to cover every lore fact,
# the same way self_critique.py's weapon-word list doesn't try to cover
# every possible item.
PINNED_FACTS_PATH = ROOT / "saves" / "pinned_facts.json"


def load_pinned_facts():
    """Reads saves/pinned_facts.json. Advisory-only by construction, like
    the rest of this script: a missing or malformed file is reported and
    skipped rather than treated as an error, since this check never
    blocks a commit either way."""
    if not PINNED_FACTS_PATH.exists():
        return []
    try:
        facts = json.loads(PINNED_FACTS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, RecursionError) as e:
        print(f"NOTE: could not read {PINNED_FACTS_PATH.relative_to(ROOT)} ({e}) -- skipping pinned-fact checks.")
        return []
    return facts


def load_narration(path):
    return Path(path).read_text(encoding="utf-8")


def extract_candidate_keywords(text):
    """Pulls candidate lore keywords out of the narration by checking
    which of world_info_lookup's own known keywords/entity names appear
    in the text -- deliberately reuses that module's existing vocabulary
    (KEYWORDS dict) rather than inventing a second, parallel list that
    could drift out of sync with it. Multi-word keywords are checked as
    phrases; single-word keywords as whole words, matching
    world_info_lookup.main()'s own matching rules for consistency."""
    lowered = text.lower()
    text_words = set(re.findall(r"\w+", lowered))
    found = []
    for key in wil.KEYWORDS:
        key_words = re.findall(r"\w+", key)
        if len(key_words) > 1:
            if key in lowered:
                found.append(key)
        else:
            if key_words and key_words[0] in text_words:
                found.append(key)
    return found


def retrieve_relevant_lore(keywords):
    """For each matched keyword, pull the backing section(s) via
    world_info_lookup's own section-splitting logic, so this script and
    `python3 scripts/world_info_lookup.py <keyword>` never disagree about
    what a keyword resolves to -- one retrieval implementation, two
    call sites."""
    retrieved = {}
    for key in keywords:
        source, section_ids = wil.KEYWORDS[key]
        if source not in retrieved:
            if not source.exists():
                continue
            text = source.read_text(encoding="utf-8")
            sections = (
                wil._load_world_sections(text)
                if source == wil.WORLD_REFERENCE
                else wil._load_chad_sections(text)
            )
            retrieved[source] = sections
        sections = retrieved[source]
        for sid in section_ids:
            heading, body = sections.get(sid, (None, None))
            if heading is not None:
                label = f"{sid} {heading}" if source == wil.WORLD_REFERENCE else heading
                yield key, label, body


def check_pinned_facts(text, pinned_facts):
    """Hard-confidence check against saves/pinned_facts.json. Kept
    separate from the general retrieval pass below because these are
    checked directly against known-contradictory phrasing, not just
    flagged for a human to cross-reference -- the closest thing this
    script has to self_critique.py's hard FLAGGED checks, but still
    reported as advisory here (see module docstring for why lore checks
    stay advisory-only for now)."""
    notices = []
    normalized = text
    for fact in pinned_facts:
        if not isinstance(fact, dict):
            continue
        # A malformed entry must degrade to skipping THAT entry, never to
        # taking the pass down. This reached fact["contradiction_patterns"]
        # directly and called re.search() unguarded, so a missing key raised
        # KeyError and a bad pattern raised re.error -- and
        # commit_state.run_lore_check() swallows failures by design, since an
        # advisory must never block a commit. One bad pinned fact therefore
        # silenced the entire lore pass while it still looked like it ran and
        # found nothing. scripts/pin_fact.py refuses to write such an entry,
        # but entries can also arrive by hand-editing or from an older file,
        # so the reader stays defensive too.
        for pattern in (fact.get("contradiction_patterns") or []):
            try:
                m = re.search(pattern, normalized, re.IGNORECASE | re.DOTALL)
            except (re.error, TypeError) as e:
                notices.append(
                    f"pinned fact {fact.get('name')!r} has an unusable "
                    f"contradiction pattern ({e}); it checked NOTHING this turn. "
                    f"Fix it with scripts/pin_fact.py or remove it -- a broken "
                    f"pattern is worse than none, because the file still looks "
                    f"like protection.")
                continue
            if m:
                notices.append(
                    f"possible contradiction: narration appears to show "
                    f"{fact.get('name')} acting, but established fact is "
                    f"'{fact.get('established_fact')}' -- context: "
                    f"\"...{m.group(0)[:80]}...\""
                )
    return notices


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/lore_consistency_check.py <path-to-drafted-turn.txt>")
        sys.exit(0)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"NOTE: file not found: {path} -- skipping lore check (advisory only).")
        sys.exit(0)

    text = load_narration(path)

    keywords = extract_candidate_keywords(text)
    pinned_notices = check_pinned_facts(text, load_pinned_facts())

    if not keywords and not pinned_notices:
        print("LORE CHECK: no known lore keywords matched in this turn's narration.")
        sys.exit(0)

    print("LORE CHECK (advisory -- never blocks a commit):")

    if pinned_notices:
        print("  PINNED FACT NOTICES:")
        for n in pinned_notices:
            print(f"    - {n}")

    if keywords:
        print(f"  Matched {len(keywords)} lore keyword(s) in this turn: "
              f"{', '.join(sorted(set(keywords)))}")
        print("  Relevant lore for a human (or a future LLM judge, see "
              "docs/MODEL_NOTES.md) to compare against the drafted narration:")
        # Group by label rather than keeping only the first keyword to
        # reach each label. Multiple matched keywords legitimately share
        # one section (e.g. "wick" and "chad" both resolving to \u00a72.3) --
        # discarding a keyword's own line just because its section was
        # already printed under a different keyword silently hid that it
        # matched at all, even though the retrieval itself was correct.
        # A human (or the reasoning step in prompts/GM_INSTRUCTIONS.md)
        # scanning this output for "did X get checked" needs every
        # matched keyword listed, not just whichever reached a shared
        # section first.
        labels_seen_order = []
        keys_by_label = {}
        body_by_label = {}
        for key, label, body in retrieve_relevant_lore(keywords):
            if label not in keys_by_label:
                labels_seen_order.append(label)
                keys_by_label[label] = []
                body_by_label[label] = body
            keys_by_label[label].append(key)
        for label in labels_seen_order:
            snippet = body_by_label[label].strip().replace("\n", " ")
            if len(snippet) > 220:
                snippet = snippet[:220].rsplit(" ", 1)[0] + "..."
            keys_str = ", ".join(sorted(set(keys_by_label[label])))
            print(f"    - [{keys_str}] {label}: {snippet}")

    print("  This pass retrieves relevant lore and surfaces possible pinned-fact "
          "contradictions; it does not itself judge whether the narration is "
          "consistent with what's retrieved. Read CLEAN/no-notices as 'nothing "
          "cheap to check here,' not as 'confirmed consistent.'")
    sys.exit(0)


if __name__ == "__main__":
    main()
