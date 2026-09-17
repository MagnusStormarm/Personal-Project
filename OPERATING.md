# How the Tooling Fits Together

This is the mechanical picture behind Part 2 of `prompts/GM_INSTRUCTIONS.md`.
Read that file for the actual rules the GM follows; this file is about *why*
the tooling is shaped the way it is.

## The core loop

1. The GM narrates a turn, in a Claude Code session (Claude iOS via
   Remote Control or a Cloud Session, or Claude PC directly).
2. If the turn changed Chad's state (gear, currency, injuries, an NPC
   relationship, an open thread), the GM drafts the new full state as
   JSON directly in that same session — Claude Code already has
   filesystem access to this repository (see `LOCAL.md` for how Remote
   Control and Cloud Sessions each reach it), so there's no separate
   step to move a drafted file anywhere.
3. `python3 scripts/session.py commit <file> --critique-text "<drafted narration>"`
   (or `--critique-file` / `--critique-stdin` in place of `--critique-text`)
   validates the draft against `state_schema.json` plus the extra rules
   in `scripts/validate_state.py` (closed inventory at turn 0,
   non-negative currency, soft-cap array sizes, npc_id registry
   consistency, deadline ordering) — and requires `self_critique.py` to
   pass clean against the turn's drafted narration first. This
   self-critique step is mandatory whenever a proposed state file is
   given; `--skip-critique` is the only way to bypass it, and doing so
   is a visible, deliberate choice rather than a default. The narration
   can be passed as inline text (`--critique-text`) or piped on stdin
   (`--critique-stdin`) in the same session that drafted it — there was
   never a file-transfer step to eliminate here in the first place.
4. If it passes, the commit replaces `saves/current.json`, backs up the
   previous version to `saves/backups/`, appends a mechanical diff to
   `saves/journal.md`, updates `saves/npc_registry.json`, and — if this is
   a git repository — commits all three save files together.
5. The GM writes the `<!-- STATE_CHANGE:committed -->` marker at the end
   of its reply, but only after step 4 actually succeeded.

## Why narration and the tooling are still treated as distinct responsibilities

The tooling (validation, git, the audit scripts) needs a real filesystem,
a Python interpreter, and shell access. The narration — reading a scene,
deciding what a character does, writing prose that follows the Prose
Craft rules — needs an LLM. Claude Code provides both at once: it's
simultaneously an LLM conversation (the narration client) and a real
shell with filesystem and git access (the mechanical backend), whether
that's Claude PC directly, or Claude iOS driving a Remote Control or
Cloud Session (see `LOCAL.md` for the difference between those two and
what each one needs to stay running).

Running both in one place doesn't collapse them into one job. The GM
still only narrates and never decides on its own that a commit
succeeded; the tooling still only validates and commits and never
decides what happens in the story. Keeping that boundary explicit — a
marker the GM writes only after a real commit succeeds, a validator that
runs regardless of how confident the narration sounds — is what keeps
the mechanical side trustworthy even though it's reached from the same
conversation as the narration itself.


## Why there's a marker instead of trusting narration alone

Without the `STATE_CHANGE:committed` marker, there's no way to tell from the
conversation alone whether a turn's narration was ever actually backed by a
real state commit — the model could narrate an event and simply forget to
run the commit pipeline. The marker carries a token
(`<!-- STATE_CHANGE:committed:<token> -->`) generated fresh by
`commit_state.py` on every commit and written into `saves/current.json`'s
`commit_token` field; `scripts/turn_gate.py` checks that the marker's token
matches what's actually in the file, rather than just checking that some
commit happened recently. This still can't prove a copied, previously-seen
token wasn't reused before any newer commit existed — see
`docs/RECOVERY.md`.

## Why git commits happen automatically

Several continuity checks (deadline tracking, "was this actually committed
last turn") work by comparing the current state against git's last commit
when no other baseline is given. A state that passed validation but was
never actually committed would leave those checks comparing against a stale
baseline — so `commit_state.py` commits automatically rather than leaving
that as a separate manual step.

## Why there are two npc-tracking files

`saves/current.json`'s `npc_relationships` array is soft-capped at 10
entries and prunes over time — a minor NPC introduced on turn 5 might be
pruned by turn 80 if nothing's kept them relevant. But if that NPC comes
back on turn 150, the GM needs to know whether to reuse their original
`npc_id` or treat them as new. `saves/npc_registry.json` never prunes; it's
the permanent record that makes that distinction possible long after the
capped array has moved on.

## Why validation has two layers

`state_schema.json` covers what JSON Schema can express cleanly (types,
required fields, enums, basic numeric bounds). `scripts/validate_state.py`
adds a `manual_checks()` layer for everything schema can't express well on
its own — a day bound that depends on which month it is, "gear at turn 0
must be exactly these five items," "no gear entry whose name is actually a
currency word," duplicate entries within a single submitted array, and a
conditionally-required field (`is_new_npc`) whose condition itself needs
checking. This layer always runs, even if the optional `jsonschema`
package isn't installed, so validation is never silently skipped.

`manual_checks()` also independently re-covers a deliberately narrow slice
of what jsonschema would normally provide — required top-level fields,
basic top-level types, the `in_world_date.month` enum, and unrecognized
top-level fields — specifically because the two layers aren't equally
available in practice: on a freshly-installed guest, `jsonschema` isn't
installed until someone runs `pip install jsonschema` (or hits the
`session.py setup` retry path), so for a while every commit runs on
`manual_checks()` alone. Before this coverage was added, that meant a
missing required field, a wrong type, or an invalid month name would pass
silently in that window — not a hypothetical, since `LOCAL.md`'s own setup
instructions describe a stock Ubuntu Server image where a plain
`pip install` can fail outright on PEP 668 grounds. This redundancy is
intentional: it's cheap to hand-maintain (see `TOP_LEVEL_TYPES` in
`validate_state.py`) and means the "authoritative enforcement layer" claim
doesn't quietly depend on an optional package actually being present.
