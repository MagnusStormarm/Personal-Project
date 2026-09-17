# Recovery

What to do when something goes wrong mid-session.

## A hard rule was broken, or a major continuity error made it into the committed state

1. Say `stop` to end the scene immediately.
2. Start a new chat.
3. Paste `prompts/GM_INSTRUCTIONS.md`, then run `python3 scripts/status_dump.py`
   on the machine running the tooling and paste its output as the last
   known-good state.
4. Continue from there. The bad turn is not canon and should not be
   referenced going forward.

## A continuity error or invented detail appears (but nothing hard was broken)

1. Reply with a plain correction: "Correction: [specific error]. Continue
   from the correct state only."
2. Optionally paste an updated status block from `status_dump.py`.
3. If it was actually committed to `saves/current.json`, fix the file
   directly if the error made it into the committed state, then run
   `python3 scripts/session.py commit` with no argument to re-validate and
   re-commit the corrected version.

## `saves/current.json` won't validate

1. Check `saves/backups/` for the most recent good snapshot —
   `commit_state.py` writes a timestamped backup there automatically
   before every promotion.
2. Restore the good backup:
   ```
   cp saves/backups/current.<timestamp>.json saves/current.json
   ```
3. Run `python3 scripts/session.py commit` with no argument — this mode
   assumes the file was just directly restored/edited, validates what's
   there, and re-runs the journal + git-commit step so the restoration
   itself is recorded.

## `saves/current.json` is ahead of git (git commit silently failed)

`scripts/commit_state.py` always writes `saves/current.json` to disk
before attempting the git commit step, so a failed git commit does not
roll back the file write. As of this version, a failed git commit prints
an explicit `WARNING:` with git's actual error output — if you see that
warning, `git status` will show the save files as modified/staged but
uncommitted. Run `python3 scripts/session.py commit` with no argument to
re-validate and retry the commit; if the pre-commit hook is what
rejected it, its printed reason (also shown in the warning) says why.

This exact failure used to happen silently for a specific, common case:
a turn introducing a brand-new NPC would validate correctly at proposal
time (`is_new_npc: true`, since the id wasn't registered yet), get
written to `saves/current.json` and registered to
`saves/npc_registry.json` — and then fail the git commit itself, because
the pre-commit hook re-validated that same now-persisted `is_new_npc:
true` against the now-updated registry, which correctly rejects it as a
duplicate claim. `commit_state.py` only reported "(not a git repository,
or nothing to commit -- save file updated regardless)" either way, so
this could pass unnoticed. This is fixed: `is_new_npc` is now cleared
from the persisted state immediately after registration, and any other
git-commit failure surfaces its real error instead of that generic
message. If you're running an older copy of this project and see the
generic message after a turn that introduced a new NPC, check `git
status` — you likely have this exact issue.

## The git history itself is in a bad state

Since `saves/current.json`, `saves/journal.md`, and `saves/npc_registry.json`
are committed together on every state change, you can also recover by
checking out an earlier commit of just the `saves/` directory:

```
git log --oneline -- saves/current.json
git checkout <good-commit-hash> -- saves/
```

Then run `python3 scripts/session.py commit` with no argument to re-validate
and create a fresh commit from the restored state.

## The STATE_CHANGE marker's known limitation

`scripts/turn_gate.py` checks that the marker's embedded token (e.g.
`<!-- STATE_CHANGE:committed:47-a3f9c2 -->`) exactly matches the
`commit_token` field `scripts/commit_state.py` just wrote into
`saves/current.json`. This replaces an earlier, weaker version of the
check that only confirmed *a* commit happened recently, without being able
to tell a fresh commit for *this* turn apart from a stale one made moments
earlier for an unrelated reason — the token match closes that specific
gap, since each commit gets its own fresh, unpredictable token.

What this does *not* close: a model could still write a marker with a
token it saw earlier in the conversation (e.g. copied from a previous
turn's real commit output) rather than one from a commit that actually
just happened. `turn_gate.py` can only catch this if the copied token no
longer matches what's currently in `saves/current.json` — which it won't
once a later real commit has moved the token forward, but a same-turn
reuse before any newer commit exists could still slip through. If you
suspect this has happened (narration describes a change that isn't
reflected in `saves/current.json`, or the token in the marker looks like
one you've seen before in this session), treat it the same as any other
continuity error above — correct it, don't assume the marker's presence
is proof the described change actually happened.

## Nothing above works

Manually reconstruct a minimal valid state by hand, using
`state_schema.json` as the reference for required fields, and
`saves/current.json`'s turn-0 baseline shape (five starting gear items,
zero currency, empty tracked arrays) as a last resort starting point if
no earlier good version can be found. This loses campaign history but
guarantees a schema-valid file to resume from.
