#!/usr/bin/env python3
"""Decide whether a possessed noun is an ITEM by looking it up in
WordNet, instead of matching it against a hand-written word list.

WHY THIS EXISTS
---------------
self_critique.py's invented-gear check is two separate things bolted
together: a set of regexes that find possession ("his X", "his
grandfather's X"), and a hardcoded 35-word list of what counts as an
item. The regexes are fine. The list is the limitation -- "his falchion"
and "his kukri" pass silently because nobody wrote those words down.

The obvious fix is a longer list, which just moves the boundary. The
better fix is to stop maintaining a list at all: WordNet already
organizes English nouns into is-a chains, so "is this noun a man-made
object" is a lookup, not an opinion. sword -> weapon -> instrumentality
-> artifact. competence -> ability -> cognition -> abstraction.

Note what this does NOT need: a dependency parser. The grammar half
already works. Swapping the list for WordNet closes the larger hole with
one dependency, and spaCy would only add better possession grammar on
top (see docs/DEVICES_AND_SERVICES.md for that tradeoff).

WHY IT IS A HARNESS FIRST
-------------------------
The idea is only as good as its false-positive rate, and prose is full
of possessed nouns that are not items -- "his competence", "his
childhood", "his hands". Measured against this project's own writing,
roughly 24 of 25 "his X" constructions are not gear. A check that
flagged those would be worse than no check, because a noisy gate gets
skipped.

So this ships with --self-test, which runs the classifier against
labelled words drawn from this project's actual prose and from the
weapon nouns the current 35-word list misses, and reports exactly what
it got wrong. Run that BEFORE wiring any of this into self_critique.py.
Nothing here is imported by the commit path; adopting it is a separate,
later decision that should be made on the numbers that --self-test
prints.

MEASURED RESULT
---------------
    first sense only   27/33   false positives: NONE
    any sense          23/33   false positives: weight, memory, skin,
                               hands, shoulder

The polysemy risk is real, and restricting to the first sense
eliminates it: 'any sense' flags "his memory" and "his hands" exactly as
feared, because memory is also computer hardware and a clock has hands.
First-sense-only is the default here for that reason, and the only mode
worth considering behind anything that blocks a commit.

First-sense-only stays silent on six of fourteen item nouns, but five of
those (kukri, bardiche, glaive, naginata, morningstar) are simply ABSENT
FROM WORDNET, which no sense-tuning can fix -- they need a supplementary
lexicon, whether that is this project's own lore keywords or a short
hand-written list used to top WordNet up rather than to replace it. The
sixth, tunic, is present, but its first sense is the anatomical membrane
rather than the garment.

Read those misses against the status quo rather than against perfection:
self_critique.py's 35-word list misses ALL fourteen today. On this
sample, first-sense WordNet catches eight of them while introducing zero
new false positives -- strictly better than the list it would replace.

WHY IT IS ADVISORY AND NOT A GATE
---------------------------------
The 33-word set above is abstractions and weapons, which is not what
ordinary narration is made of. Tested against 63 everyday "his X" nouns
plus scene furniture, the broad 'artifact' category flags 12 of 14 scene
nouns -- room, bed, chair, door, window, cup, bowl, cot, saddle, pocket.
"He returned to his room" is not an inventory violation, and a check that
refused that commit would teach the author to reach for --skip-critique.

Narrowing the categories does not rescue it either:

    artifact (broad)   items 12/12   false positives 12/14
    portable-only       items  6/12   false positives  4/14
    + equipment/device  items  7/12   false positives  6/14

No category reaches the precision a blocking check needs. So
self_critique.py consumes this through advisory_item_notices() below, in
the advisory pass that already exists for looser matching, using
PORTABLE_ROOTS plus the four measured exclusions in NOT_INVENTORY. That
combination fires on 4 of 78 ordinary nouns, and two of those four --
'coat' and 'shirt' -- are arguably correct, since Chad's baseline gear
has neither and unlisted clothing is a real violation.

WHAT IT STILL CANNOT DO
-----------------------
WordNet resolves vocabulary, not reference. It does not know that "the
sword at his hip" is Chad's, it cannot tell a remembered item from a
carried one, and it has no memory of previous turns. Those gaps are
unchanged -- see docs/MODEL_NOTES.md.

USAGE
-----
    python3 scripts/semantic_gear_check.py --self-test
        Score the classifier against labelled words and print every
        misclassification. Start here.

    python3 scripts/semantic_gear_check.py --check turn.txt
        Run the check over a drafted turn, the way self_critique.py
        would, and print what it would flag.

    python3 scripts/semantic_gear_check.py --explain falchion
        Print a noun's WordNet hypernym chains, to see why it did or
        didn't classify as an item.

Requires the WordNet corpus: `pip install nltk` then
`python -m nltk.downloader wordnet`. It is a one-time download of tens
of megabytes; after that this runs entirely offline, with no API, no
credential, and no network access at commit time.
"""
import argparse
import functools
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURRENT_PATH = ROOT / "saves" / "current.json"

# A noun counts as an item if one of its WordNet hypernym chains passes
# through any of these. 'artifact' is the load-bearing one: it means
# man-made object, which excludes body parts ("his hands") that would
# slip through a looser test against 'physical_entity'.
ITEM_ROOTS = {"artifact", "instrumentality", "instrument"}

# A narrower set, for the advisory self_critique.py actually uses. Broad
# 'artifact' catches every item but also every piece of scenery -- a room,
# a door, a window, a chair and a bed are all artifacts, and "he returned
# to his room" is not an inventory violation. Restricting to things a
# person carries trades recall for a signal worth reading.
PORTABLE_ROOTS = {"weapon", "clothing", "container", "tool", "implement"}

# Nouns PORTABLE_ROOTS still gets wrong, found by testing rather than
# guessed at: a cup and a bowl are containers, a pocket is clothing, and
# WordNet's first sense of 'knuckles' is brass knuckles. Four exclusions
# discovered by measurement is a different kind of list from thirty-five
# inclusions written from memory, but it is still a list -- add to it only
# with a case that actually fired.
NOT_INVENTORY = {"pocket", "cup", "bowl", "knuckles"}


_WORDNET = None
_WORDNET_TRIED = False


def load_wordnet(quiet=False):
    """The WordNet corpus reader, or None. Loads once per process.

    Kept optional in the same spirit as validate_state.py's handling of
    jsonschema: a machine without the corpus gets a clear message, not a
    traceback. quiet=True suppresses that message, for callers that
    report absence in their own words -- self_critique.py runs on every
    commit and says it once, in the advisory section.
    """
    global _WORDNET, _WORDNET_TRIED
    if _WORDNET_TRIED:
        return _WORDNET
    _WORDNET_TRIED = True
    try:
        from nltk.corpus import wordnet
    except ImportError:
        if not quiet:
            print("nltk is not installed -- `pip install nltk`, then "
                  "`python -m nltk.downloader wordnet`.")
        return None
    try:
        wordnet.synsets("test", pos=wordnet.NOUN)
    except LookupError:
        if not quiet:
            print("nltk is installed but the WordNet corpus is missing -- run "
                  "`python -m nltk.downloader wordnet`.")
        return None
    _WORDNET = wordnet
    return wordnet


@functools.lru_cache(maxsize=4096)
def _chains(noun, first_sense_only):
    """Hypernym chains for a noun, as sets of lemma names."""
    wn = load_wordnet(quiet=True)
    if wn is None:
        return []
    senses = wn.synsets(noun.lower(), pos=wn.NOUN)
    if first_sense_only:
        # WordNet orders senses by frequency, so the first is the
        # everyday meaning. Restricting to it avoids classifying "hand"
        # as an item because a clock has hands.
        senses = senses[:1]
    return [
        {s.name().split(".")[0] for s in path}
        for sense in senses
        for path in sense.hypernym_paths()
    ]


def is_item(noun, first_sense_only=True, roots=None):
    """Is this noun a man-made object, per WordNet?"""
    roots = ITEM_ROOTS if roots is None else roots
    return any(roots & chain for chain in _chains(noun, first_sense_only))


def advisory_item_notices(text, gear_names):
    """Possessed nouns that look like carried items but aren't in gear.

    This is the entry point self_critique.py uses, and it is advisory by
    construction -- see this module's MEASURED RESULT section for why no
    root set reached blocking-grade precision.
    """
    if load_wordnet(quiet=True) is None:
        return None
    known = {g.strip().lower() for g in gear_names if g}
    notices = []
    for noun, phrase in sorted(possessed_nouns(text).items()):
        if noun in NOT_INVENTORY:
            continue
        if any(noun in name or name in noun for name in known):
            continue
        if is_item(noun, first_sense_only=True, roots=PORTABLE_ROOTS):
            notices.append(
                f"possible unlisted carried item: \"{phrase}\" -- '{noun}' reads as "
                "something Chad would carry, but no gear entry matches it"
            )
    return notices


# The player character, for the named-possession shapes below. Duplicated
# from self_critique.py's PLAYER_NAME rather than imported, so this module
# stays standalone; renaming the PC means changing both.
PLAYER_NAME = "Chad"

# Possession shapes, deliberately the same ones self_critique.py matches.
#
# The named-possessor shapes are anchored to PLAYER_NAME, not to any
# capitalised word. An earlier revision used r"\b[A-Z]\w+'s\s+(\w+)\b"
# and consequently reported "Maren's dagger" and "the guard's sword" as
# possible unlisted items of Chad's -- other people's weapons, which
# armed NPCs carry through most scenes. That was a real false-positive
# class, found only by testing NPC possessives, and it is the most likely
# one to occur in actual play.
POSSESSIVE_PATTERNS = [
    r"\bhis\s+(\w+)\b",
    r"\bhis(?:\s+\w+){1,3}\s+(\w+)\b",
    r"\bhis\s+\w+'s\s+(\w+)\b",
    rf"\b{PLAYER_NAME}'s\s+(\w+)\b",
    rf"\b{PLAYER_NAME}'s(?:\s+\w+){{1,3}}\s+(\w+)\b",
    rf"\b{PLAYER_NAME}'s\s+\w+'s\s+(\w+)\b",
]


def possessed_nouns(text):
    """Every noun the narration gives to someone, as (noun, phrase)."""
    found = {}
    for pattern in POSSESSIVE_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            noun = m.group(1).lower()
            found.setdefault(noun, m.group(0))
    return found


def check(text, gear_names, first_sense_only=True):
    """Flag possessed nouns that are items but aren't in gear."""
    known = {g.lower() for g in gear_names}
    flags = []
    for noun, phrase in sorted(possessed_nouns(text).items()):
        if any(noun in name or name in noun for name in known):
            continue
        if is_item(noun, first_sense_only):
            flags.append(f"'{phrase}' names an item ('{noun}') with no matching gear entry")
    return flags


def load_gear_names():
    if not CURRENT_PATH.exists():
        return []
    try:
        state = json.loads(CURRENT_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, RecursionError):
        return []
    gear = state.get("gear", [])
    return [g.get("name", "") for g in gear if isinstance(g, dict)]


# --- labelled data for --self-test -------------------------------------
# Not invented: the first group is every distinct "his X" noun found in
# this project's own docs/CHAD_BACKSTORY.md and prompts/FIRST_MESSAGE.md,
# which is the real prose this check would run against. The second is
# item nouns absent from self_critique.py's 35-word list.

MUST_NOT_FLAG = [
    "competence", "childhood", "thirties", "weight", "self", "reading",
    "memory", "life", "judgment", "interiority", "parents", "mother",
    "skin", "hands", "brow", "breath", "courage", "shoulder", "name",
]
MUST_FLAG = [
    "falchion", "kukri", "bardiche", "glaive", "naginata", "scimitar",
    "cudgel", "pike", "morningstar", "tunic", "lantern", "waterskin",
    "bedroll", "rope",
]


def self_test():
    if load_wordnet() is None:
        print("\nCannot score the classifier without the corpus -- see above.")
        return 1

    print("Scoring WordNet item-classification against labelled nouns.\n")
    overall_ok = True
    for first_only in (True, False):
        mode = "first sense only" if first_only else "any sense"
        wrong_quiet = [w for w in MUST_NOT_FLAG if is_item(w, first_only)]
        wrong_loud = [w for w in MUST_FLAG if not is_item(w, first_only)]
        correct = (len(MUST_NOT_FLAG) - len(wrong_quiet)) + (len(MUST_FLAG) - len(wrong_loud))
        total = len(MUST_NOT_FLAG) + len(MUST_FLAG)
        print(f"-- {mode} --")
        print(f"   {correct}/{total} correct")
        print(f"   false positives (would flag ordinary prose): "
              f"{', '.join(wrong_quiet) if wrong_quiet else 'none'}")
        print(f"   missed items (would stay silent): "
              f"{', '.join(wrong_loud) if wrong_loud else 'none'}")
        if wrong_quiet or wrong_loud:
            overall_ok = False
        print()

    print("How to read this: false positives are the number that decides "
          "adoption.\nA check that flags ordinary narration gets skipped, "
          "and a skipped gate\ncatches nothing. Missed items are the "
          "status quo -- the current list\nmisses all of them already.")
    return 0 if overall_ok else 2


def explain(noun):
    wn = load_wordnet()
    if wn is None:
        return 1
    senses = wn.synsets(noun.lower(), pos=wn.NOUN)
    if not senses:
        print(f"'{noun}' is not in WordNet as a noun.")
        return 0
    print(f"'{noun}' -- {len(senses)} noun sense(s); first sense is the common one.\n")
    for i, sense in enumerate(senses):
        marker = " (first)" if i == 0 else ""
        print(f"  {sense.name()}{marker}: {sense.definition()}")
        for path in sense.hypernym_paths()[:1]:
            print("    " + " -> ".join(s.name().split(".")[0] for s in path))
    print(f"\nclassified as an item: first-sense={is_item(noun, True)} "
          f"any-sense={is_item(noun, False)}")
    return 0


def run_check(path):
    if load_wordnet() is None:
        return 1
    text = Path(path).read_text(encoding="utf-8")
    flags = check(text, load_gear_names())
    if not flags:
        print("CLEAN: no possessed noun classified as an unlisted item.")
        print("(Vocabulary only -- this cannot see 'the sword at his hip'.)")
        return 0
    print("FLAGGED:")
    for f in flags:
        print(f"  - {f}")
    return 1


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true",
                        help="Score the classifier against labelled nouns. Start here.")
    parser.add_argument("--check", metavar="FILE",
                        help="Run the check over a drafted turn.")
    parser.add_argument("--explain", metavar="NOUN",
                        help="Show a noun's WordNet chains and classification.")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if args.explain:
        return explain(args.explain)
    if args.check:
        return run_check(args.check)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
