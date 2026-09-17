#!/usr/bin/env python3
"""Keyword -> lore section lookup, backed by docs/ELDARA_REFERENCE.md
(world canon) and docs/CHAD_BACKSTORY.md (Chad's personal/old-world canon).

Pulls just the relevant section(s) of one reference file instead of
dumping either file whole, so a scene needing one fact doesn't cost the
model the entire lore document in context.

Usage:
    python3 scripts/world_info_lookup.py <keyword>
"""
import json
import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
WORLD_REFERENCE = DOCS / "ELDARA_REFERENCE.md"
CHAD_REFERENCE = DOCS / "CHAD_BACKSTORY.md"
KEYWORDS_PATH = DOCS / "lore_keywords.json"
_SOURCE_TAGS = {"world": WORLD_REFERENCE, "chad": CHAD_REFERENCE}


def load_keywords():
    """Loads the keyword -> (source file, [section ids]) mapping from
    docs/lore_keywords.json rather than hand-maintaining it as a Python
    dict literal here -- so adding a new lore keyword (or repointing one
    after a doc section is renumbered) is a data edit, not a code change.
    Mirrors the same fix already applied to pinned facts -- see
    scripts/lore_consistency_check.py's PINNED_FACTS_PATH.

    Returns {} on a missing/malformed file rather than raising: this
    script is read-only and advisory (see module docstring), so a broken
    keywords file should degrade to "no lore match for anything" rather
    than crash the turn that happened to call it."""
    if not KEYWORDS_PATH.exists():
        print(f"NOTE: {KEYWORDS_PATH.relative_to(DOCS.parent)} not found -- no lore keywords available.")
        return {}
    try:
        raw = json.loads(KEYWORDS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, RecursionError) as e:
        print(f"NOTE: could not read {KEYWORDS_PATH.relative_to(DOCS.parent)} ({e}) -- no lore keywords available.")
        return {}
    keywords = {}
    for key, entry in raw.items():
        source = _SOURCE_TAGS.get(entry.get("source"))
        sections = entry.get("sections")
        if source is None or not isinstance(sections, list):
            continue
        keywords[key] = (source, sections)
    return keywords


# Keyword -> (source file, [section ids]). World reference sections are
# numbered ("## 2.x Heading"); Chad's backstory file uses plain headings
# ("## Heading"). See load_keywords() above -- the actual mapping lives
# in docs/lore_keywords.json now, not here.
KEYWORDS = load_keywords()

WORLD_SECTION_PATTERN = re.compile(r"^## (\d+\.\d+a?) (.+)$", re.MULTILINE)
CHAD_SECTION_PATTERN = re.compile(r"^## (.+)$", re.MULTILINE)


def _load_world_sections(text):
    """Split the world reference file into {section_number: (heading, body)}."""
    matches = list(WORLD_SECTION_PATTERN.finditer(text))
    sections = {}
    for i, m in enumerate(matches):
        number, heading = m.group(1), m.group(2)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[number] = (heading, text[start:end].strip())
    return sections


def _load_chad_sections(text):
    """Split Chad's backstory file into {heading: (heading, body)} -- keyed
    by heading text since that file has no numbering scheme."""
    matches = list(CHAD_SECTION_PATTERN.finditer(text))
    sections = {}
    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[heading] = (heading, text[start:end].strip())
    return sections


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/world_info_lookup.py <keyword>")
        print("Available keys:", ", ".join(sorted(KEYWORDS.keys())))
        return

    key = " ".join(sys.argv[1:]).lower()
    matched = KEYWORDS.get(key)
    if matched is None:
        # Matches on word boundaries rather than raw substrings, and
        # prefers the longest (most specific) match among those that
        # qualify. Two distinct failure modes motivate this:
        #
        # 1. Raw substring containment lets a keyword match purely by
        #    coincidence of spelling inside an unrelated word -- e.g.
        #    querying "who was his manager" would match the keyword
        #    "age" (found inside "man-AGE-r") and return fantasy-
        #    peoples/aging lore (§2.6) instead of Chad's actual
        #    property-manager backstory. That's a false match with no
        #    semantic relation at all, not a specificity problem --
        #    word-boundary matching below prevents it.
        # 2. Even among genuinely related matches, dict-insertion order
        #    alone would decide the winner rather than specificity --
        #    e.g. "old world stuff" would resolve to the short keyword
        #    "old" (§2.6) instead of the more specific "old world"
        #    (Chad's backstory) purely because of insertion order.
        #    Preferring the longest qualifying match below prevents this.
        key_words = set(re.findall(r"\w+", key))

        def keyword_matches(k):
            k_words = re.findall(r"\w+", k)
            # A multi-word keyword like "old world" must appear as a
            # contiguous phrase in the query; a single-word keyword must
            # appear as one of the query's own words.
            if len(k_words) > 1:
                return k in key
            return k_words[0] in key_words if k_words else False

        candidates = [k for k in KEYWORDS if keyword_matches(k)]
        if candidates:
            best = max(candidates, key=len)
            matched = KEYWORDS[best]

    if not matched:
        print(f"No lore match for: {key}")
        print("Available keys:", ", ".join(sorted(KEYWORDS.keys())))
        return

    source, section_ids = matched
    if not source.exists():
        print(f"Reference file missing: {source}")
        return

    text = source.read_text(encoding="utf-8")
    sections = _load_world_sections(text) if source == WORLD_REFERENCE else _load_chad_sections(text)

    for sid in section_ids:
        heading, body = sections.get(sid, (None, None))
        if heading is None:
            print(f"Section {sid!r} missing from {source}")
            continue
        label = f"{sid} {heading}" if source == WORLD_REFERENCE else heading
        print(f"=== {label} ===")
        print(body)
        print()


if __name__ == "__main__":
    main()
