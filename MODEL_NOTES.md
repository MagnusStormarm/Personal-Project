# Notes on Running Eldara with Different Models

This project's prompts are model-agnostic in principle — `GM_INSTRUCTIONS.md`
doesn't assume any particular model — but in practice, models vary in how
reliably they follow a long, rule-heavy system prompt over many turns.

## General guidance

- **Context length matters more than raw capability here.** `GM_INSTRUCTIONS.md`,
  `ELDARA_REFERENCE.md`, and `CHAD_BACKSTORY.md` together are long. A model
  with a short effective context window will start dropping rules from
  memory well before it runs out of listed context length. If you notice
  drift (invented gear, forgotten NPCs), suspect context pressure first.
- **The STATE_CHANGE marker and turn_gate.py are a safety net, not a
  guarantee of good narration.** They only catch "did a commit actually
  happen," not "was the commit's content actually correct." Use the
  periodic continuity audit (`GM_INSTRUCTIONS.md`'s "Continuity audit"
  section) and the playtest audit (`python3 scripts/session.py audit`) to
  catch drift the marker system can't.
- **The campaign tooling doesn't run the LLM itself.** Nothing in the
  play path — `commit_state.py`, `validate_state.py`, `self_critique.py`,
  `turn_gate.py` — makes its own API calls to a model. Narration always
  happens in whatever chat interface you're using (Claude's app, a
  browser, etc.), separately from the tooling described in
  `docs/OPERATING.md`, and committing a turn never needs network access
  to anything but your git remote.

  One script is an exception, and it is deliberately outside the play
  path: `scripts/adversarial_stress_test.py --auto-gm` calls the
  Anthropic Messages API directly to draft responses to adversarial
  prompts, so the pipeline has something to chew on without a human
  pasting turns in by hand. It is a test harness for a throwaway
  campaign, opt-in behind a flag, and needs credentials you supply
  yourself; no other mode of that script, and no part of committing a
  real turn, touches it. See that file's docstring for why the manual
  `--submit-stress-prompt` path tests something more faithful.

  If you want the *play path* tooling to call a model automatically (for
  example, an automated prose-tone judge on every commit), that is still
  new, separate functionality with its own API credentials, and it does
  not exist in this project — see the semantic-gap section below for what
  it would buy and what it would cost.

## What a model needs to be good at for this to work well

1. Hold and follow the full `GM_INSTRUCTIONS.md` contract across a session.
2. Reliably draft valid JSON matching `state_schema.json`'s shape when
   asked to. This is the single most common failure point in practice —
   malformed JSON that `validate_state.py` correctly rejects.
3. Write in the specific tone described in the Prose Craft section rather
   than defaulting to a generic assistant register.

A model that struggles with (2) above is usually a capability issue, not
something more context or a bigger local model file would fix on its own.

## `self_critique.py`'s load-bearing limit, and what would actually close it

`self_critique.py`'s invented-gear check is pattern matching against a
finite set of sentence shapes ("his sword", "his grandfather's sword"),
not comprehension. It can't distinguish an item genuinely attributed to
Chad from one merely mentioned near him ("the sword at his hip", "the
weapon in his hand gleamed — a longsword") — closing that specific gap
needs the sentence's actual meaning resolved, which pattern matching
structurally cannot do no matter how many phrase variants are added.

**What would close it, and at what cost:**

- **A real LLM call** (the Anthropic API, or any other) judging "does
  this narration attribute an unlisted item to Chad" as a semantic
  question — this is the only approach that resolves meaning rather than
  shape. Real per-commit API cost and a new network-failure mode this
  script doesn't currently have; not built into this project as of this
  writing. This is the "own API credentials" option referenced above.
- **A local dependency parser (e.g. spaCy)**, entirely offline, no API
  key — genuinely raises the ceiling above plain regex by identifying
  grammatical possession (`poss`, `nsubj` relations) more reliably than
  a "his ... noun" pattern, closing cases like adjective insertion more
  robustly than the current hand-written regex. It does NOT close the
  metonymy cases above ("the sword at his hip") on its own — those need
  coreference resolution too (what does "the sword" refer to in this
  scene), which in practice means a heavier local model, not just a
  parser. Real resource cost if you go this route: `en_core_web_sm` is
  about 40MB on disk, and users report a loaded pipeline sitting at
  roughly 100MB resident. Memory growth under sustained use is reported
  on spaCy's tracker, but read that evidence carefully before treating
  it as a reason not to adopt: the detailed reports are against the
  larger `en_core_web_md` (500–600MB in one Kubernetes case), and
  maintainers attribute the growth to Python not releasing memory
  promptly and to long-document NER rather than to a confirmed leak.
  Loading the model once and reusing the object, and preferring
  `nlp.pipe()` over per-call `nlp()`, are the documented mitigations —
  both trivially satisfied by a per-commit check that runs once per
  process. Neither of
  the two ways this project is actually run is memory-constrained at that
  scale, though — `LOCAL.md`'s device list is your own computer (Remote
  Control) or an Anthropic-managed sandbox (Cloud Sessions), not a
  small self-hosted VM. The cost that does land is setup, and it lands
  unevenly: Remote Control installs the model once and keeps it, while a
  Cloud Session starts from a fresh container every time and would
  re-download it on every `session.py setup`. That is the one place
  adopting spaCy would dent `LOCAL.md`'s "runs identically under either
  mode" claim. It costs no money either way — this is a
  setup-time question, not a billing one.
- **Leaning on the human**, which is what this project already does and
  costs nothing to build further: the continuity audit and the playtest
  audit's Pass 3 exist specifically because pattern matching can't do
  full judgment. Past a certain point, the marginal hour is better spent
  making sure these actually run on schedule than widening the regex or
  standing up a new model dependency for a gap this narrow.

