# Setup: Claude iOS + Claude PC (Claude Code) + GitHub

This project's tooling (state validation, commits, audits) runs inside a
Claude Code session on a real computer -- **Claude PC** (the Claude Code
Desktop app, or the Claude Code CLI in a terminal) -- driven either from
that computer directly or from **Claude iOS** via Remote Control or Cloud
Sessions. Claude Code itself has the filesystem, shell, and git access
this project needs.

**Two ways to run a session, with a real tradeoff between them:**

- **Remote Control** -- Claude iOS connects to a Claude Code session
  running on a computer you keep on. Code execution and file access stay
  on that machine; your phone just drives it. Start it from the computer
  with `claude remote-control` (or `/remote-control` inside an existing
  session), then connect from Claude iOS by scanning the printed QR code
  or picking the session from the app's **Code** tab.
- **Cloud Sessions** -- Claude Code on the web runs the session on
  Anthropic-managed cloud infrastructure instead of your own machine.
  This requires the project to be pushed to GitHub (see "Get the project
  onto GitHub" below) rather than just sitting on a local disk. A session
  you start from your phone keeps running with your phone put away, and
  is waiting for you again from any device afterward.

Pick Remote Control if you'd rather keep working against files on a
machine you control directly; pick Cloud Sessions if you want a turn
committed from your phone to keep going (or simply persist) without that
machine needing to stay powered on. Both talk to the same repository and
the same scripts underneath -- this choice doesn't change anything about
how `commit_state.py`, `validate_state.py`, or the critique gate behave.

Everything in `scripts/` runs identically under either mode. It only
assumes a POSIX shell and Python 3, both of which Claude Code's
execution environment provides directly, whether that's your own
computer (Remote Control) or a cloud sandbox (Cloud
Sessions).

## Get the project onto GitHub

Cloud Sessions require this; Remote Control doesn't strictly need it, but
git push is still the actual protection against losing campaign data if a
device is lost or a local disk fails, exactly as it would be with any
other setup -- push a remote either way, on general principle.

If this project doesn't yet have a git repository:
```
cd "The Eldara Project"
git init
git add -A
git commit -m "Initial commit: current state of the project"
```
Check `git status` before that first `git add -A` -- worth a glance to
confirm nothing unexpected is about to be swept into the project's very
first commit.

Then create a repository on GitHub (private is the sensible default here,
given this project contains a personal backstory document and full
campaign save state) and push:
```
git remote add origin <your-repo-url>
git push -u origin main
```

## Setup, inside a Claude Code session

Once Claude Code (via either Remote Control or a Cloud Session) has the
repository open, run -- or ask Claude to run --
`python3 scripts/session.py setup`. This installs Python dependencies
from `requirements.txt` and the git pre-commit/pre-push hooks, exactly as
it always has; nothing about `session.py` itself changed for this
environment.

If a plain `pip install` fails with a message about an "externally
managed environment" (a Debian/Ubuntu PEP 668 policy that also applies to
some cloud sandbox images), `session.py setup` prints the virtual-environment
command and then retries automatically with `--break-system-packages`.

Which of those two you actually want *does* depend on the connection mode.
`--break-system-packages` installs into the system Python — it is not
project-scoped, whatever the name suggests — so it is a reasonable default
in a **Cloud Session**, whose container is thrown away anyway, and worth
declining on the **Remote Control** machine you keep, where a virtual
environment costs one command and keeps this project's packages out of
the system set:

```
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

Everything in `scripts/` runs the same either way; the only difference is
which Python owns the packages.

## Running a session

`python3 scripts/session.py start` validates the current save (if one
exists) and prints a status summary. From there, narrate directly in the
same Claude iOS or Claude PC conversation -- Claude Code's own
conversation is the narration client, so there's nothing separate to
open. Paste `prompts/GM_INSTRUCTIONS.md` in (or keep it as this
session's system context) at the start of a session.

After a turn that changes Chad's state, ask Claude to draft the resulting
JSON and run:
```
python3 scripts/session.py commit /path/to/file.json --note "..." \
    --critique-text "the turn's drafted narration, pasted straight in"
```
directly in the same session -- there's no file transfer step at all
anymore, since Claude Code already has both the drafted narration and
filesystem access to `saves/` in one place. `python3 scripts/session.py
loop` still works exactly as documented for a whole session's worth of
turns in one sitting.

## No unattended automation

Neither Remote Control nor Cloud Sessions run entirely unattended forever
-- a Remote Control session needs its host computer on, and a Cloud
Session has its own runtime limits. Nothing here depends on background
execution; everything below is something you run yourself, at a session
boundary.

- **Old backups are pruned automatically, every commit, no cron needed.**
  `session.py commit` keeps only the most recent 30 snapshots in
  `saves/backups/`.
- **Push to a remote, every commit, if one is configured.** This is what
  protects the campaign against a device or local machine being lost,
  dropped, or wiped, and it's also what lets the two connection modes
  share state: a turn committed from your phone via a Cloud Session
  becomes visible to a Remote Control session on your computer once it's
  pulled, and vice versa -- the two modes share state through GitHub,
  not through any direct connection to each other.
- **Every turn commit requires a clean prose self-check before it's
  accepted.** `--critique-text`, `--critique-file`, `--critique-stdin`,
  and `--skip-critique` all work as documented in `scripts/commit_state.py`.
- **Run the audit yourself, at the start or end of a session:**
  ```
  python3 scripts/session.py audit
  ```
  A recurring reminder in Apple Reminders (or whatever reminder app you
  use), set to your own playing cadence, is a reasonable way to remember
  to do this regularly.

## Security basics

- Remote Control's QR-code pairing is a direct, session-scoped connection
  to your computer -- treat a scanned QR code the way you'd treat any
  other credential handoff, and don't scan one you didn't generate
  yourself.
- Cloud Sessions run in Anthropic-managed infrastructure rather than on a
  device you physically hold -- credentials and repository access for
  that session are scoped to your claude.ai account and sign-in. With a
  single person using this project and a private GitHub repository with
  no collaborators added, that account is the entire access boundary:
  anyone signed into it can reach the repository, so an unattended,
  signed-in device is the actual risk to guard against, not who else
  might have repo access, since no one else does.
- Do a low-stakes test (connect, run `git status` or `ls`, disconnect)
  the first time you set up either Remote Control or a Cloud Session
  against this repository, before trusting it with a real turn commit.
