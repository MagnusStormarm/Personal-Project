#!/usr/bin/env python3
"""Heuristic self-critique pass over drafted narration, checking for the
handful of pillar violations that are at least partially mechanically
detectable from the text alone: invented gear/currency words not present
in saves/current.json, and a few other cheap textual signals.

This is NOT a substitute for actual judgment -- it's a narrow, literal
safety net that catches obvious slips (an invented item name, a currency
word appearing outside the currency object's vocabulary) before a human
or a more careful read does. A clean pass here does not mean the turn is
good; a FLAGGED result should always be treated as something to look at.

Coverage notes: the invented-gear check tolerates a bounded amount of
sentence variation around "his X" (an inserted adjective, a nested
possessive like "his grandfather's sword") and phrase-matching normalizes
curly/smart quotes, since both were confirmed gaps in earlier testing.
None of this changes what kind of check this is -- it is still pattern
matching against a finite set of shapes, not comprehension. A sentence
that names an item without a possessive at all ("the sword at his hip",
"the weapon in his hand"), or that refers to an item only descriptively
or by what it does, will still pass the hard FLAGGED/CLEAN check silently.
Closing that class of gap for real would need semantic judgment (e.g. an
LLM call), not another regex -- see docs/MODEL_NOTES.md.

One piece of that has since been closed partway, on the vocabulary side
rather than the reference side: advisory_semantic_items() asks WordNet
whether a possessed noun is the kind of thing a person carries, so "his
falchion" no longer depends on someone having written 'falchion' into a
list. It is advisory because no WordNet category was precise enough to
block on -- the measurements are in scripts/semantic_gear_check.py. It
does nothing for "the sword at his hip", which is reference, not
vocabulary.

Advisory notices: advisory_gear_mentions(), advisory_structural_notes()
and advisory_semantic_items() below report on that exact remaining gap -- broader, looser proximity
matching that never blocks a commit (the exit code only reflects the hard
checks above). This is a genuine, deliberate trade: because these notices
can't fail a commit, they can afford to be noisier than the hard checks
without cost beyond an extra line to read. Confirmed in testing: real
false positives do occur (an incoming projectile "grazing his shoulder",
someone else's tool mentioned in the same sentence, a scar described
metaphorically) -- these are the price of surfacing evasions the hard
checks can't catch without becoming unboundedly wide themselves. Read
ADVISORY output as "might be worth a glance," never as a verdict.

Usage:
    python3 scripts/self_critique.py <path-to-drafted-turn.txt>
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURRENT_PATH = ROOT / "saves" / "current.json"

CURRENCY_WORDS = ["copper", "silver", "gold", "platinum", "coin", "mark", "crown", "sovereign", "penny"]

UNEARNED_ATTRACTION_PHRASES = [
    "falls in love instantly", "can't resist him", "irresistibly drawn to",
    "immediately smitten", "love at first sight",
    "fell in love instantly", "fell for him instantly", "instantly captivated",
    "unable to resist", "couldn't resist him", "swept off her feet",
    "irresistible pull toward him", "helplessly drawn to",
]

TONE_BREAK_PHRASES = [
    "as an ai", "i cannot generate", "i'm not able to continue",
    "as a language model", "as an ai language model", "i can't continue this",
    "i must decline", "i won't be able to write",
]


def load_state():
    """Returns {} on any problem reading/parsing saves/current.json --
    including malformed JSON and JSON that parses but isn't a dict (e.g.
    a bare list) -- rather than letting either crash this script. This
    function's job is narration-quality checking, not save-file
    diagnostics; validate_state.py and status_dump.py already own giving
    the person a detailed, actionable error for a corrupted save. Here,
    falling back to an empty state just means "no known gear to compare
    against" -- a soft degradation, not a failure."""
    if not CURRENT_PATH.exists():
        return {}
    try:
        with open(CURRENT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, RecursionError):
        return {}
    return data if isinstance(data, dict) else {}


def normalize_quotes(text):
    """Collapse curly/smart quotes to plain ASCII equivalents before
    phrase matching. Without this, a phrase in *_PHRASES lists containing
    a straight apostrophe (e.g. "can't resist him") silently fails to
    match text using a curly apostrophe (') instead -- a real gap since
    many editors, and some models, produce curly quotes by default. Pure
    string normalization; catches only this one specific evasion, not
    rewording generally."""
    return (
        text.replace("\u2018", "'").replace("\u2019", "'")
            .replace("\u201c", '"').replace("\u201d", '"')
    )


# The player character's name, for possession shapes that name him
# instead of using a pronoun ("Chad's sword"). Deliberately not read from
# saves/current.json, which has no name field -- and duplicated as
# PLAYER_NAME in scripts/semantic_gear_check.py rather than imported,
# so the hard check below still works when that optional module is
# absent. Renaming the PC means changing both.
PLAYER_NAME = "Chad"


def check_invented_gear(text, state):
    known_names = {g.get("name", "").lower() for g in state.get("gear", [])}
    flags = []
    # Look for common "he draws his X" / "his X" patterns naming an item
    # that isn't in the known gear list -- deliberately narrow to avoid
    # false positives on ordinary prose.
    weapon_words = [
        "sword", "dagger", "bow", "axe", "shield", "armor", "cloak", "pack", "satchel",
        "blade", "longsword", "greatsword", "shortsword", "cutlass", "rapier", "saber",
        "spear", "lance", "mace", "hammer", "crossbow", "sling", "quiver", "scabbard",
        "helm", "helmet", "gauntlet", "gauntlets", "breastplate", "chainmail", "hauberk",
        "buckler", "knife", "hatchet", "javelin", "halberd", "flail", "warhammer",
    ]
    seen = set()
    for word in weapon_words:
        already_owned = any(word in name for name in known_names)
        if already_owned:
            continue

        # Direct adjacency: "his sword". Kept from the original check.
        direct = re.search(rf"\bhis {word}\b", text, re.IGNORECASE)

        # Tier-1 widening: tolerate up to 3 intervening words between
        # "his" and the noun, so an inserted adjective or short
        # description ("his enchanted longsword", "his trusty old
        # blade") doesn't defeat the check just by breaking direct
        # adjacency. Still requires "his" to head the phrase, so this
        # remains a narrow, literal pattern match, not comprehension --
        # see the module docstring and docs/RECOVERY.md for the
        # remaining gaps this doesn't close (e.g. "the sword at his
        # hip", "his grandfather's sword", metonymic references).
        widened = re.search(rf"\bhis(?:\s+\w+){{1,3}}\s+{word}\b", text, re.IGNORECASE)

        # Possessive-of-possessive: "his grandfather's sword", "his
        # mother's dagger" -- a distinct grammatical shape (nested
        # possession) that the widened pattern above doesn't cover,
        # since "grandfather's" isn't a plain intervening word in the
        # same slot; matched separately so the two patterns' intent
        # stays legible independently.
        #
        # Known false-positive cost of this specific pattern: it can't
        # distinguish an item Chad now carries ("his grandfather's
        # sword" handed down and wielded) from a pure memory or
        # description of something he doesn't have ("he remembered his
        # father's sword above the fireplace back home"). Both match.
        # This is a real precision tradeoff introduced to close a real
        # evasion, not an oversight -- flagging a true memory-reference
        # turn for human review is a low-cost false positive compared to
        # missing a genuine inventory violation, but it will happen.
        nested_possessive = re.search(rf"\bhis \w+'s {word}\b", text, re.IGNORECASE)

        # Named possessor: "Chad's sword" makes exactly the same
        # inventory claim as "his sword" and used to pass this check
        # clean, because every pattern above requires the pronoun.
        #
        # Restricted to the player character on purpose. A general
        # "\b[A-Z]\w+'s {word}\b" would flag "Maren's dagger" and "the
        # guard's sword" -- other people's weapons, which armed NPCs
        # carry through most scenes and which say nothing about Chad's
        # gear. Precision here comes from the same place the pronoun
        # patterns get it: WEAPON_WORDS does the filtering, so
        # "Chad's sword" can flag while "Chad's patience" never can.
        named_possessor = re.search(
            rf"\b{PLAYER_NAME}'s(?:\s+\w+){{0,3}}\s*{word}\b", text, re.IGNORECASE)
        named_nested = re.search(
            rf"\b{PLAYER_NAME}'s \w+'s {word}\b", text, re.IGNORECASE)

        if direct or widened or nested_possessive or named_possessor or named_nested:
            key = word
            if key not in seen:
                possessor = "his" if (direct or widened or nested_possessive) \
                    else f"{PLAYER_NAME}'s"
                flags.append(
                    f"mentions '...{possessor} ... {word}' but no gear entry matches '{word}'")
                seen.add(key)
    return flags


def check_currency_as_gear(text):
    """Flags a currency word appearing near the literal word 'gear' in
    either direction. The original pattern only matched 'gear ... word'
    order and silently missed the arguably more natural 'word ... gear'
    phrasing (e.g. "added the gold to his gear") -- confirmed as a real
    gap in testing, not a hypothetical one."""
    flags = []
    for word in CURRENCY_WORDS:
        forward = re.search(rf"\bgear\b.{{0,40}}\b{word}\b", text, re.IGNORECASE)
        backward = re.search(rf"\b{word}\b.{{0,40}}\bgear\b", text, re.IGNORECASE)
        if forward or backward:
            flags.append(f"possible currency word '{word}' appearing near 'gear' -- currency belongs in the currency object, never a gear entry")
    return flags


def check_unearned_attraction(text):
    normalized = normalize_quotes(text.lower())
    return [p for p in UNEARNED_ATTRACTION_PHRASES if p in normalized]


def check_tone_breaks(text):
    normalized = normalize_quotes(text.lower())
    return [p for p in TONE_BREAK_PHRASES if p in normalized]


def check_consequence_dodging(text):
    flags = []
    normalized = normalize_quotes(text.lower())
    dodge_phrases = [
        "but somehow he's fine", "miraculously unharmed", "nothing bad happens",
        "against all odds, he walked away", "completely unscathed",
        "escapes without a scratch", "somehow uninjured", "walks away unharmed",
    ]
    for p in dodge_phrases:
        if p in normalized:
            flags.append(f"possible consequence-dodging phrase: '{p}'")
    return flags


def advisory_gear_mentions(text, state):
    """Report-only pass, distinct from check_invented_gear() above. This
    catches broader SHAPES of gear reference that the hard-fail check
    deliberately doesn't, because widening the hard-fail check itself to
    this level trades false negatives for false positives one-for-one
    (see docs/RECOVERY.md and this module's docstring) -- it stops being
    a bounded fix and becomes an open-ended tuning problem.

    This function sidesteps that trade by never blocking a commit. It
    finds item nouns that appear anywhere near "his" without requiring a
    direct possessive at all -- "the sword at his hip", "the weapon in
    his hand gleamed, a longsword" -- and reports them as items worth a
    human glance, not as violations. A true positive here still requires
    a human to confirm it's actually unearned; a false positive just
    costs a moment's read, not a wrongly-blocked commit. This is
    deliberately wider and noisier than check_invented_gear() -- that's
    the point: report != fix, and reporting can afford lower precision
    than blocking can.
    """
    known_names = {g.get("name", "").lower() for g in state.get("gear", [])}
    weapon_words = [
        "sword", "dagger", "bow", "axe", "shield", "armor", "cloak", "pack", "satchel",
        "blade", "longsword", "greatsword", "shortsword", "cutlass", "rapier", "saber",
        "spear", "lance", "mace", "hammer", "crossbow", "sling", "quiver", "scabbard",
        "helm", "helmet", "gauntlet", "gauntlets", "breastplate", "chainmail", "hauberk",
        "buckler", "knife", "hatchet", "javelin", "halberd", "flail", "warhammer",
    ]
    notices = []
    seen = set()
    for word in weapon_words:
        if any(word in name for name in known_names):
            continue
        if word in seen:
            continue
        # Loose proximity: the weapon word and "his" appear within 8
        # words of each other, in either order, anywhere in the text --
        # no requirement that one possesses the other grammatically.
        # This is intentionally promiscuous; it will catch "his" and a
        # weapon word that are unrelated to each other in the same
        # sentence (e.g. "his hands were empty of any sword"), which is
        # exactly why this is advisory-only and never blocks a commit.
        pattern = re.compile(
            rf"(?:\bhis\b(?:\W+\w+){{0,8}}\W+\b{word}\b)|(?:\b{word}\b(?:\W+\w+){{0,8}}\W+\bhis\b)",
            re.IGNORECASE,
        )
        m = pattern.search(text)
        if m:
            snippet = text[max(0, m.start() - 15):m.end() + 15].strip()
            notices.append(f"possible unlisted item near \"his\": '{word}' -- context: \"...{snippet}...\"")
            seen.add(word)
    return notices


def advisory_structural_notes(text):
    """Report-only pass for a few other sentence-structure shapes worth a
    human glance, distinct from anything that blocks a commit. Currently
    covers metonymic gear references ("the weapon in his hand", "the
    blade at his side") that name an item by its location relative to
    Chad rather than by direct possession -- the exact evasion class
    demonstrated in stress testing that no possessive-anchored regex
    can catch without becoming unboundedly wide. Advisory only."""
    notices = []
    metonymy_patterns = [
        r"\b(?:weapon|blade|steel)\b[^.]{0,20}\bin his hand\b",
        r"\b(?:weapon|blade|steel|sword|dagger)\b[^.]{0,20}\bat his (?:hip|side|belt)\b",
        r"\bthe \w+ he(?:'d| had) carried\b",
        r"\bthe \w+ he(?:'d| had) worn\b",
    ]
    for pattern in metonymy_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            notices.append(f"possible metonymic item reference (names an item by location/history, not direct possession): \"...{m.group(0)}...\"")
    return notices


def advisory_semantic_items(text, state):
    """Advisory: nouns the narration hands Chad that WordNet reads as
    carried items, with no gear entry to match.

    Where check_invented_gear() above tests a possessed noun against a
    fixed list of 35 weapon words, this asks WordNet whether the noun is
    the kind of thing a person carries. That is what stops "his falchion"
    and "his waterskin" -- words the list has never heard of -- from
    passing in complete silence.

    Advisory rather than blocking, and that is a measured decision rather
    than caution. No WordNet category reaches the precision a gate needs:
    against ordinary prose the broad "artifact" category flags "his
    room", "his bed", "his chair" and "his door", none of which is an
    inventory violation, while the narrower category used here drops
    those but still catches "his pocket" and "his cup" and finds only
    half the items. Blocking on that would train the author to reach for
    --skip-critique, and a gate that gets skipped catches nothing.
    scripts/semantic_gear_check.py holds the numbers; --self-test re-runs
    them.

    Returns None (not an empty list) when WordNet isn't installed, so
    main() can say so once instead of treating it as a notice.
    """
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    try:
        from semantic_gear_check import advisory_item_notices
    except ImportError:
        return None
    gear = state.get("gear", [])
    gear_names = [g.get("name", "") for g in gear if isinstance(g, dict)]
    return advisory_item_notices(text, gear_names)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/self_critique.py <path-to-drafted-turn.txt>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"FAIL: file not found: {path}")
        sys.exit(1)

    text = path.read_text(encoding="utf-8")
    state = load_state()

    all_flags = []
    all_flags.extend(check_invented_gear(text, state))
    all_flags.extend(check_currency_as_gear(text))
    all_flags.extend(check_unearned_attraction(text))
    all_flags.extend(check_tone_breaks(text))
    all_flags.extend(check_consequence_dodging(text))

    # Advisory notices, gathered regardless of the hard-fail result above
    # and never affecting the exit code. These exist to surface Tier
    # 2/3-shaped patterns (see this module's docstring) that the hard
    # checks deliberately don't widen to cover, since doing so would
    # trade false negatives for false positives rather than closing the
    # gap. A human (or a future LLM-based judge, see docs/MODEL_NOTES.md)
    # decides what to do with these; this script never blocks on them.
    advisory_notices = []
    advisory_notices.extend(advisory_gear_mentions(text, state))
    advisory_notices.extend(advisory_structural_notes(text))
    semantic_notices = advisory_semantic_items(text, state)
    if semantic_notices is None:
        # Same convention validate_state.py uses for jsonschema: name the
        # optional dependency once, as a parenthetical, rather than
        # letting its absence look like a clean result.
        print("(nltk/WordNet not installed -- the semantic unlisted-item advisory "
              "is off; `pip install nltk` then `python -m nltk.downloader wordnet` "
              "enables it)")
    else:
        advisory_notices.extend(semantic_notices)

    if all_flags:
        print("FLAGGED: review before committing.")
        for f in all_flags:
            print(f"  - {f}")
        if advisory_notices:
            print("ADVISORY (not blocking, worth a glance):")
            for n in advisory_notices:
                print(f"  - {n}")
        sys.exit(1)

    if advisory_notices:
        print("CLEAN: no heuristic issues detected (this is not a full review -- use judgment too).")
        print("ADVISORY (not blocking, worth a glance):")
        for n in advisory_notices:
            print(f"  - {n}")
        sys.exit(0)

    print("CLEAN: no heuristic issues detected (this is not a full review -- use judgment too).")
    sys.exit(0)


if __name__ == "__main__":
    main()
