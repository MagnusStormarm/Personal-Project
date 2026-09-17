#!/usr/bin/env python3
"""Look up a tracked place or the travel duration between two tracked
places, backed by saves/locations.json -- the fixed-coordinate World Map
analog for this project, sitting alongside world_info_lookup.py (static
lore) and journal_lookup.py (played history).

Why this exists: docs/ELDARA_REFERENCE.md §2.8 already states travel
durations as a prose table (e.g. "Highcrown <-> Thrum-Gate: 8-12 days"),
but nothing before this script made that machine-checkable -- a GM could
narrate a three-day trip one session and a one-day trip the next covering
the same route, and no existing script would catch it. saves/locations.json
mirrors that same table as structured data; this script is the read path
over it, and scripts/validate_state.py's current_location/travel checks
are the write-time enforcement.

This is read-only and advisory, same as world_info_lookup.py: it answers
"what does locations.json say", it does not decide what Chad's position
actually is or invent a duration for a route that isn't in the file. If a
route is missing, the answer is "not tracked", not a guess.

Usage:
    python3 scripts/location_lookup.py <place name or id>
    python3 scripts/location_lookup.py --route <place> <place>
    python3 scripts/location_lookup.py --list
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCATIONS_PATH = ROOT / "saves" / "locations.json"


def load_locations():
    """Returns the parsed locations.json dict, or None if it's missing or
    unparseable. Callers print their own message in that case rather than
    this function raising -- a missing locations.json is a normal state
    for a campaign that hasn't opted into location tracking, not a bug."""
    if not LOCATIONS_PATH.exists():
        return None
    try:
        with open(LOCATIONS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, RecursionError):
        return None


def resolve_id(data, name_or_id):
    """Match a location by its exact id key first, then by a
    case-insensitive match on its display name -- so both 'hollow_creek'
    and 'Hollow Creek' find the same entry, matching how a player or GM
    would naturally type either form."""
    locations = data.get("locations", {})
    if name_or_id in locations:
        return name_or_id
    lowered = name_or_id.strip().lower()
    for loc_id, entry in locations.items():
        if entry.get("name", "").strip().lower() == lowered:
            return loc_id
    return None


def format_location(loc_id, entry):
    lines = [f"{entry.get('name', loc_id)} ({loc_id})"]
    if entry.get("region"):
        lines.append(f"  Region: {entry['region']}")
    if entry.get("description"):
        lines.append(f"  {entry['description']}")
    if entry.get("reference_section"):
        lines.append(f"  See docs/ELDARA_REFERENCE.md \u00a7{entry['reference_section']}")
    return "\n".join(lines)


def routes_touching(data, loc_id):
    """Every tracked route with loc_id as one endpoint, as (other_id,
    other_name, route) tuples sorted by other_name. Used to give a
    no-known-route answer some useful context -- see format_route()'s
    comment on why this doesn't try to estimate a distance instead."""
    routes = data.get("routes", {})
    locations = data.get("locations", {})
    touching = []
    for route_key, route in routes.items():
        ids = route_key.split("|")
        if loc_id not in ids:
            continue
        other_id = ids[0] if ids[1] == loc_id else ids[1]
        other_name = locations.get(other_id, {}).get("name", other_id)
        touching.append((other_id, other_name, route))
    return sorted(touching, key=lambda t: t[1])


def format_route(data, from_id, to_id):
    routes = data.get("routes", {})
    route_key = "|".join(sorted([from_id, to_id]))
    route = routes.get(route_key)
    from_name = data["locations"][from_id].get("name", from_id)
    to_name = data["locations"][to_id].get("name", to_id)
    if route is None:
        # Deliberately does NOT estimate a distance/duration from
        # coordinates or any other inference -- saves/locations.json's
        # own header comment states the design intent plainly: this file
        # mirrors durations already established in
        # docs/ELDARA_REFERENCE.md \u00a72.8, it never originates geography
        # the lore doesn't already establish (and state_schema.json says
        # the same of current_location/travel: "not a coordinate system
        # with movement math"). Inventing a plausible-looking number here
        # would be exactly the kind of unbacked claim this project's
        # validation exists to prevent elsewhere. What CAN help without
        # inventing anything: surfacing the routes that ARE already
        # tracked from either endpoint, so a GM planning a new route has
        # real reference points instead of nothing at all.
        lines = [
            f"No known route between {from_name} and {to_name} in "
            "saves/locations.json. This does not mean the journey is "
            "impossible -- it means the duration isn't established yet. "
            "If this becomes a real journey on-screen, add the route to "
            "both docs/ELDARA_REFERENCE.md \u00a72.8 and saves/locations.json "
            "rather than narrating a specific day count with nothing "
            "backing it."
        ]
        for loc_id, loc_name in ((from_id, from_name), (to_id, to_name)):
            nearby = routes_touching(data, loc_id)
            if nearby:
                bits = [f"{other_name} ({r.get('min_days')}\u2013{r.get('max_days')}d)"
                        for _, other_name, r in nearby]
                lines.append(f"  Known routes from {loc_name}: {', '.join(bits)}")
        return "\n".join(lines)
    lines = [f"{from_name} \u2194 {to_name}: {route.get('min_days')}\u2013{route.get('max_days')} days"]
    if route.get("note"):
        lines.append(f"  {route['note']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Look up a tracked location or the travel duration "
                     "between two, from saves/locations.json."
    )
    parser.add_argument("place", nargs="*", default=None,
                         help="Place name or id to look up. With --route, "
                              "give exactly two places.")
    parser.add_argument("--route", action="store_true",
                         help="Look up the travel duration between two places.")
    parser.add_argument("--list", action="store_true",
                         help="List every tracked location.")
    args = parser.parse_args()

    data = load_locations()
    if data is None:
        print("No saves/locations.json found (or it failed to parse) -- "
              "this campaign has no tracked locations yet.")
        sys.exit(0)

    if args.list:
        locations = data.get("locations", {})
        if not locations:
            print("saves/locations.json has no locations defined.")
            return
        for loc_id, entry in sorted(locations.items()):
            print(format_location(loc_id, entry))
            print()
        return

    if args.route:
        if len(args.place) != 2:
            print("--route requires exactly two place names, e.g.:")
            print("  python3 scripts/location_lookup.py --route hollow_creek highcrown")
            sys.exit(1)
        from_id = resolve_id(data, args.place[0])
        to_id = resolve_id(data, args.place[1])
        if from_id is None:
            print(f"Unknown location: '{args.place[0]}'")
            sys.exit(0)
        if to_id is None:
            print(f"Unknown location: '{args.place[1]}'")
            sys.exit(0)
        print(format_route(data, from_id, to_id))
        return

    if not args.place:
        parser.print_help()
        sys.exit(0)

    query = " ".join(args.place)
    loc_id = resolve_id(data, query)
    if loc_id is None:
        print(f"No tracked location matches '{query}'. "
              f"Use --list to see everything tracked.")
        sys.exit(0)
    print(format_location(loc_id, data["locations"][loc_id]))


if __name__ == "__main__":
    main()
