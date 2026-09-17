# Expanded Status Template (use for every checkpoint)

Ask: "Give me current status using the full template." Or run `python3 scripts/status_dump.py`, which prints this same format directly from `saves/current.json`.

```
Date: Day __ of ________, Year __
Location / Scene:
Gear:
-
Currency: __ copper / __ silver / __ gold / __ platinum
Status / Injuries:
Language:
Key NPCs / Relationships:
Open Threads:
-
Throughline:
-
```

## Drift Correction

If any invented item, unearned relationship, or continuity error appears:

1. Reply with a clear correction, e.g. "Correction: [specific error]. Continue from the correct state only."
2. Optionally paste an updated status block.
3. If a hard rule is broken (major inventory invention, a continuity error that's spread across several turns) → start a new chat and paste the last good status (see `docs/RECOVERY.md`).

## Hard Interrupts

These words end or alter the scene immediately:
- stop – halt completely
- fade – fade to black
- rewind – go back to before the last escalation
- limits – restate boundaries and pause
