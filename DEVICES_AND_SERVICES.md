# Devices, Services, and What One More Dependency Would Cost

`LOCAL.md` explains **how** to run this project across a phone and a
computer. This file is the inventory that sits underneath it: which
devices and services the project actually depends on today, what leaves
the machine and when, and precisely what would change if the one
currently-recommended addition (a local dependency parser) were adopted.

It exists because "add spaCy" and "add an API key" sound like the same
size of decision and are not. One changes a setup step. The other
changes the sentence in `LOCAL.md` that defines the access boundary.

## Current setup

**Devices**

- **Claude PC** — the Claude Code Desktop app, or the Claude Code CLI in
  a terminal, on a real computer. This is where the filesystem, shell,
  and git access live.
- **Claude iOS** — drives a session on that computer (Remote Control) or
  one running on Anthropic-managed infrastructure (Cloud Sessions).

There is no self-hosted server, VM, or always-on box in this list, and
nothing in `scripts/` assumes one.

**Services**

- **GitHub** — a private repository with no collaborators. This is the
  state channel: the two session modes share a campaign only because
  both push to and pull from the same remote, never by talking to each
  other directly.
- **claude.ai account** — the sign-in that both session modes run under.

**Credentials**

One. `LOCAL.md`'s Security basics section puts it plainly: with a single
person and a private repository, "that account is the entire access
boundary." There is no second secret to store, rotate, or keep out of
git.

**Python dependencies**

`jsonschema`, and even that is optional — `validate_state.py` falls back
to its own manual checks and says so when the package is missing.
Everything else in `scripts/` is standard library.

`nltk` is a second optional one, not listed in `requirements.txt` and not
installed by default. When it and the WordNet corpus are present,
`self_critique.py` adds one advisory notice about possessed nouns that
read as carried items without a matching gear entry; without it that
notice is off and nothing else changes. It needs no service, no
credential, and no network at commit time — the corpus is a one-time
download of roughly 10MB. See `scripts/semantic_gear_check.py`.

**What crosses the network, and when**

- **At commit time:** the git push only. Validation, the critique gate,
  and the lore check all run locally, offline, in-process.
- **At setup time:** `pip install` from `requirements.txt`.
- **Never:** your narration. Prose exists in whatever chat interface you
  are playing in and in `saves/journal.md`; no script in the play path
  transmits it anywhere.

**One documented exception**

`scripts/adversarial_stress_test.py --auto-gm` calls the Anthropic
Messages API directly, with credentials you supply. It is a test harness
for a throwaway campaign, opt-in behind a flag, and outside the play
path entirely — no part of committing a real turn touches it. Its other
modes (`--run-tooling-cases`, `--list-stress-prompts`, `--submit-stress-prompt`,
`--compare`) need no key and no network.

## The recommended change: a local dependency parser (spaCy)

**What it would change in the lists above: nothing.**

- Devices: unchanged.
- Services: unchanged.
- Credentials: unchanged. The access-boundary sentence in `LOCAL.md`
  stays true exactly as written.
- Network at commit time: unchanged — the parser runs locally,
  in-process, the same as the checks it strengthens.

**What it would add**

- `spacy` in `requirements.txt`, plus the `en_core_web_sm` model. The
  documented install is `python -m spacy download en_core_web_sm`, but
  spaCy also supports pinning a model in `requirements.txt` by its
  release URL, which is the form worth using here: it needs no new step
  in `session.py setup`, and it pins a version rather than fetching
  whatever is current.
- An optional-import guard in `self_critique.py`, matching
  `validate_state.py`'s handling of `jsonschema`, so a machine without
  the package still runs every existing check.

**The one asymmetry worth knowing about**

Remote Control installs the model once and keeps it. A Cloud Session
starts from a fresh container each time and re-downloads it on every
setup — about 40MB. This is the only place adopting spaCy dents
`LOCAL.md`'s claim that everything "runs identically under either mode"
— and it dents it on setup time, not on behaviour. Committed turns
behave the same either way.

Memory is not the constraint it might look like. A loaded
`en_core_web_sm` pipeline is reported at roughly 100MB resident, which is
unremarkable on a personal computer and on a cloud sandbox alike. See
`docs/MODEL_NOTES.md` for why the larger growth figures on spaCy's
tracker describe a bigger model than this one.

**What it would buy**

`self_critique.py`'s invented-gear check is currently three regexes over
a closed 35-word weapon list, all requiring the literal pronoun `his` to
head the phrase. Two holes follow from that, both reproducible today:

    echo "He drew Chad's sword and stepped forward." > /tmp/t.txt
    python3 scripts/self_critique.py /tmp/t.txt      # CLEAN

    echo "He drew his falchion and stepped forward." > /tmp/t.txt
    python3 scripts/self_critique.py /tmp/t.txt      # CLEAN

    echo "He drew his sword and stepped forward." > /tmp/t.txt
    python3 scripts/self_critique.py /tmp/t.txt      # FLAGGED

A named possessor walks straight through, and so does any weapon noun
outside the hardcoded list. A `poss` dependency relation catches the
first as the same case it already catches `his sword`, and inverts the
second: instead of asking "is this one of 35 known words," you extract
every noun the narration gives Chad and diff it against `gear`. That is
vocabulary-independent, and it is the larger of the two holes.

It also drops the current patterns' 1–3 intervening-word window, so
arbitrary description ("his impossibly old, notched, blood-dark blade")
stops defeating the check by length alone.

**What it would not close**

Metonymy still needs coreference, not grammar: "the sword at his hip"
parses cleanly, but `sword` sits in a prepositional phrase rather than a
possession relation, so a parser cannot tell it is Chad's. That case
remains where it is today — caught, when it is caught, by
`advisory_structural_notes()`, advisory and non-blocking.

Nor does it remove the documented false positive: "he remembered his
father's sword above the fireplace back home" is grammatically identical
to real possession, and a parser will flag the memory too.

## The option deliberately not taken: an API-key judge

Recorded here so the reasoning survives, not as a recommendation.

An LLM judging "does this narration attribute an unlisted item to Chad"
as a semantic question is the only approach that closes metonymy and the
memory-versus-possession false positive, and the only one that
generalises to other gaps — the paraphrased tone break
(`TONE_BREAK_PHRASES` is literal-string matching) is invisible to a
parser and legible to a judge.

What it would change in the lists above is substantially more:

- **Services:** adds the Anthropic API as a metered service, billed per
  token separately from any Claude subscription.
- **Credentials:** adds a long-lived, spendable secret that must exist
  in both session modes — on your computer and injected into the Cloud
  Session environment. `LOCAL.md`'s "that account is the entire access
  boundary" would become false as written and need rewriting, not
  appending to.
- **Data flow:** campaign prose would leave the tooling for the first
  time. Today narration never does.
- **Commit path:** a network dependency inside the gate. Either a
  connectivity failure can block a legitimate commit, or the judge is
  advisory and is no longer a gate.

The shape of the tradeoff: **a parser upgrades the blocking gate; a
judge upgrades the advisory pass.** The gate wants determinism, offline
operation, and speed, which is the parser's profile and not the judge's.

## The third option, which is free

`docs/MODEL_NOTES.md` names it and it belongs in any honest comparison:
the continuity audit and the playtest audit's Pass 3 exist precisely
because pattern matching cannot do judgment. Past a point, the marginal
hour is better spent making sure those actually run on schedule than
widening a regex or standing up a new dependency for a gap this narrow.

Worth weighing against both options above, given that adversarial
testing found the gear checks performing better than their own docs
predicted — the metonymy case did fire an advisory.

## Summary

| | Current | + spaCy | + API judge |
|---|---|---|---|
| Devices | PC, iOS | unchanged | unchanged |
| Services | GitHub, claude.ai | unchanged | **+ Anthropic API (metered)** |
| Credentials | one (account) | unchanged | **+ a spendable secret, both modes** |
| Python deps | `jsonschema` (optional) | `+ spacy` + model | `+ anthropic` |
| Network at commit | git push only | git push only | **+ API call in the gate** |
| Narration leaves machine | no | no | **yes** |
| Setup differs by mode | no | **yes** (cloud re-downloads) | no |
| `LOCAL.md` rewrite needed | — | one caveat | **Security basics** |
