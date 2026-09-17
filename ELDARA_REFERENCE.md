# ELDARA — REFERENCE FILE

Setting canon only. Optional context for the GM — not needed to start a campaign; `prompts/GM_INSTRUCTIONS.md` (plus `saves/current.json`, if continuing) is enough to begin play immediately.

Don't paste this into every chat if the needed lore is already present elsewhere. Use `python3 scripts/world_info_lookup.py <keyword>` to pull in only the relevant numbered section below when a scene needs it, instead of the whole file. Reference text is never Chad's inventory or personal state — that lives in `saves/current.json`, validated against `state_schema.json`. Chad's own personal/old-world canon lives separately in `docs/CHAD_BACKSTORY.md`.

---

## 2.1 Geography

| Region | Description |
|---|---|
| **Heartlands** | Plains, river valleys, market towns, human kingdoms. Mild, densely settled. |
| **Elderwoods** | Elven-held temperate/northern forest, hidden glades, strict borders. |
| **Stone Peaks / Deep Holds** | Dwarven mountain kingdoms, cold, mineral-rich, tunneled. |
| **Green Hills / River Marches** | Halfling countryside, orchards, waterways. |
| **Border Marches and Wilds** | Frontier, old ruins, monsters, lingering magic. *(Where Chad landed.)* Already under pressure: frontier raids, a mining-rights dispute, and disappearances near the Elderwoods edge — loosely sketched as displaced wildlife and territorial pressure from something driven out of the deeper Wilds by the mining dispute, more likely than anything supernatural, though this is a hook for the GM to develop on-screen rather than fixed canon. The next concrete beat, if the thread is picked up: a Silverwood border patrol has quietly begun appearing closer to the Marches than their usual range, which locals read as either coincidence or evidence the elves know something they haven't shared — neither confirmed on-screen, and both should stay genuinely possible until play resolves it. Guild reach is weak there; freelance labor is common. Nearest settlement to Chad's landing point: **Hollow Creek** (see §2.3), a palisaded frontier waypoint of a few hundred people. |

**The Northern March** *(the specific stretch of the Border Marches Chad actually landed in and where Hollow Creek sits — a named sub-region, not a separate region from the row above)*: No formal border marks it off from the rest of the Border Marches — "Northern March" is the name locals and Ironwood's company use for the northern stretch of frontier they patrol and know best, closest to the Elderwoods edge and the disappearances thread. Referring to Chad's location as either "the Border Marches" or "the Northern March" is correct; the latter is simply the more specific, local term for where in the Border Marches he is.

**The mining-rights dispute, sketched with actual parties** *(a hook to develop, not fixed canon)*: A vein of good ore was found in contested ground — claimed by an independent surface outfit under an old Valenor charter, and separately claimed by Karak-Thrum as being within their traditional mining rights even though it sits above their formal hold boundary. The surface claim is held by Prospector Fenwick Osgood (`osgood` if promoted to a tracked NPC) — not a large operator, just an ambitious independent who staked the claim early and now has more invested in it than he can easily walk away from; his guards (part of what's straining Hollow Creek's labor market, §2.14a) are as much about protecting his own overextension as about the ore itself. Neither side has escalated to real violence yet. No ruling from Highcrown or Karak-Thrum's high king has come down yet, and it's plausible neither side actually wants one — an unresolved dispute quietly worked around is often more profitable than a resolved one that goes against you.

**Frontier population texture** *(archetypal, not named — draw on these when populating an ordinary scene rather than defaulting to settled locals; note that some of these archetypes now have named, on-roster examples — see the Named NPCs table in §2.3 — so check there first before inventing a new unnamed figure that would just duplicate one)*:
- A foreman who lost guild standing over a broken contract elsewhere and now runs unguilded crews on the frontier because it's the only work left open to him.
- A family working a borrowed or squatted plot near the settled edge, having left land closer to the Elderwoods after the disappearances started.
- A Port Vessar debtor who left rather than face the port's reputation-economy consequences (§2.11), rebuilding a name from nothing under a different trade.
- A former Karak-Thrum surface worker, cut loose from clan-craft standing (§2.14) after the Sundering-era disruptions, now doing work with no clan behind him.
- A young Greenmantle halfling farther from home than is typical for their people, having left after a bad harvest season rather than default on a debt to kin.

Major trade moves by river and coast. Northern winters are harsh; late-spring floods and early-autumn frosts are the main farming risks.

**Seasonal texture** *(pull for scene-setting rather than reciting)*: Frostwane and Deepwinter bring genuine hard cold and short daylight, when frontier travel slows and Hollow Creek's market days thin out. Thawmoon's mud season makes roads and tracks miserable and slow before Seedmonth's planting brings the year's first real activity. Highsummer and Goldleaf are the frontier's busiest working months — harvest labor, caravan traffic at its peak, the best chance of steady day-work. Mistfall lives up to its name near the Elderwoods edge specifically, where disorienting mist (§2.10) is worst and travel off known paths is most discouraged. Darkening and Longnight bring the year's shortest days and the leadup to the Turning festival, when even frontier settlements slow down and gather in.

## 2.2 History

| Event | When | Summary |
|---|---|---|
| **Sundering of the Deep Roads** | ~180 years ago | Collapses and monster incursions sealed the dwarven underways. |
| **War of the Two Crowns** | 87–79 years ago | Valenor succession crisis; drew in the River Marches and dwarven holds. |
| **Silverwood Accords** | 42 years ago | Trade/non-aggression treaty between Silverwood and Valenor. |
| **Red Harvest Famine** | 19 years ago | Crop failures; strengthened human–halfling cooperation. |

## 2.3 Governance & Realms

- **Valenor** *(Human, House Valen, Highcrown)* — largest human realm, feudal monarchy, guild/church balance.
- **River Marches** *(House Marchand)* — nominally Valenor's vassal, practically autonomous.
- **Silverwood Enclave** *(Elven)* — council of elder houses, isolationist, trades only at border glades.
- **Karak-Thrum** *(Dwarven, Clan Ironvein)* — federation of holds under a high king.
- **Greenmantle Confederation** *(Halfling)* — loose alliance, decisions by seasonal moot.
- **Port Vessar** — independent multi-racial coastal free city, cutthroat trade politics.

**Notable settlements:** Highcrown (Valenor capital) · Port Vessar (free port) · Thrum-Gate (dwarven surface fortress) · Silverhaven (the only elven town outsiders may enter) · Millbrook (halfling hub, home of the Harvest Moot) · Riverwatch (River Marches border fortress).

**Brief sketches of the above** *(kept intentionally lighter than Hollow Creek's treatment, since Chad hasn't reached any of these — enough to narrate a scene set there, not a full settlement writeup)*:
- **Highcrown:** Valenor's capital, a genuine city — walled, guilded, layered by wealth and district the way any real capital would be. King Aldric's court, the Church of the Harvest's seat, and the busiest Merchants' Guild hall in the Heartlands are all here. A stranger with no papers, no guild standing, and an implausible story would draw far more official scrutiny here than anywhere in the Border Marches — Highcrown has the bureaucracy to actually ask hard questions, where Hollow Creek simply doesn't have the reach to bother.
- **Silverhaven:** The one elven settlement outsiders may enter at all, and even then only under invitation or escort — everywhere else in Silverwood is closed to non-elves entirely. Reserved, quiet, built with a different sense of scale and permanence than human towns; visitors are watched courteously rather than warmly. Getting here at all would be a notable event in Chad's story, not a place he'd simply wander into.
- **Thrum-Gate:** The dwarven surface fortress and main point of contact between Karak-Thrum and the surface world — more garrison and trade post than city, loud with forge-work, guarded, and organized entirely around clan-craft standing (§2.14). An unguilded human stranger would be an oddity here, tolerated for trade purposes but not folded into anything.
- **Millbrook:** The halfling hub and site of the Harvest Moot (§2.3, §2.9) — small by human standards, communal, genuinely welcoming to outsiders who can pull their weight, per the halfling cultural note in §2.6 (they judge individuals, not origins). The easiest of these five settlements for Chad to actually be received well in, if he ever reaches it.
- **Riverwatch:** The River Marches' border fortress — practical, martial without being harsh, closer in feel to Ironwood's frontier company than to a proper city. Garrison town first, settlement second.

### On Chad's Nature *(binding on all NPCs and narration)*

No people, faction, religion, or archive in Eldara has a concept that fits what Chad is. There is no "otherworlder," "summoned hero," "outlander," or similar category anyone will recognize or name, regardless of how strange his account of himself sounds. NPCs explain him the mundane way people explain anything they don't understand: a liar, an amnesiac, a deserter, someone touched in the head, a spy with a strange cover story. No prophecy, old text, or elder's tale references anyone like him — don't write one into existence later. Reactions to him range from suspicion to indifference, same as they would to any stranger with an implausible story; neither extreme is the default.

**Stock explanations available to a Border Marches local** *(canonized so NPCs reach for consistent, mundane theories rather than improvising something exotic each time — pick whichever fits the NPC and situation, don't cycle through all of them)*:
- A deserter from one of the standing conflicts near the Marches (frontier raids, the mining dispute's private guards) — the most common assumption for a stranger of fighting age with no clear origin.
- An escaped or freed indenture, unwilling or unable to say who held the debt.
- A Silverwood exile — elves are close-mouthed about their own banishments (§2.6), so a human claiming ignorance of his own past isn't automatically disbelieved on this front, just treated as someone who won't say.
- A debt-runner out of Port Vessar, given how seriously that city's reputation economy (§2.11) treats default — leaving quietly and reinventing yourself elsewhere is a known pattern, not a novel one.
- Someone "not right in the head" — a real and unstigmatized-enough category in frontier country, where hard living produces genuine cases of it; often the laziest and therefore most common default when nothing else fits.

**Away from the Border Marches, the same principle holds with different local flavor** — no framework for Chad exists anywhere in Eldara, but the specific mundane guess a stranger reaches for should fit the culture doing the guessing: a Valenor/Heartlands local is likelier to guess at guild fraud, a runaway apprentice, or someone evading formal law; a dwarf of Karak-Thrum is likelier to assume an oath-breaker cast out from somewhere and reluctant to say from where, since exile-for-oath-breaking (§2.6) is a familiar category to them; a Silverwood elf, used to elves' own reserved relationship to names and history (§2.6), is likelier to simply not press the question at all.

### Named NPCs *(introduce only when Chad would plausibly encounter them)*

Suggested `npc_id` below so the same canonical NPC gets the same slug regardless of which session or campaign introduces them — see `prompts/GM_INSTRUCTIONS.md`'s "NPC identity" section. Use it as given, or a different one if the story's specific version of this person warrants it; the only hard rule is picking one and never reusing or changing it afterward.

| Name | Suggested `npc_id` | Role |
|---|---|---|
| Captain Lysa Ironwood | `ironwood` | Hard-edged commander of the Northern March patrol (§2.1) — **likely Chad's earliest contact**, given his landing point |
| Innkeeper Marta Dell | `dell` | Runs Hollow Creek's one inn (the Ashen Kettle); pragmatic, sees every stranger who passes through, not easily impressed or alarmed — a plausible early, low-stakes contact independent of Ironwood |
| Foreman Osric Vane | `vane` | Runs one of Hollow Creek's larger unguilded labor crews (portering, caravan work); exactly the kind of foreman described in §2.14's "where people get shorted" — not a villain, just someone whose terms need watching. Latent scenario: Vane periodically has to cut a worker loose from his crew over an unpaid personal debt, and sometimes asks a trusted hand to be the one who tells the person rather than doing it himself. A plausible, mundane echo of Chad's own old-world history (see `docs/CHAD_BACKSTORY.md`) — real and weighty if it comes up on-screen, never manufactured just to force the parallel. |
| Bree Talstan | `talstan` | A frontier-born laborer roughly Chad's age, works whatever crew is hiring; plausible peer-level contact and a source of ordinary local knowledge rather than authority |
| Sera Wick | `wick` | A licensed Hearth & Healing practitioner who circuits several Border Marches settlements including Hollow Creek roughly once a month, rather than living in any one of them — the closest thing the frontier has to reliable, competent magical healing (§2.7). Practical and businesslike rather than mystical in manner; treats her work as a trade, not a calling, and charges accordingly (real coin or an equivalent favor — see §2.13). The single most likely point of contact between Chad and Eldara's magic system actually working as described, if a scene ever calls for real medical stakes. |
| Foreman Declan Hurst | `hurst` | Runs a smaller, rival crew to Vane's — a deliberate contrast, not a duplicate. Where Vane's unfairness is systemic and impersonal (§2.14's ordinary ways a worker gets shorted), Hurst's is personal: petty favoritism, a short temper when questioned, a habit of finding technical justifications for decisions that happen to always break his way. Not violent or a genuine villain, just someone whose authority Chad's "instincts toward authority and fairness" (`docs/CHAD_BACKSTORY.md`) would have real, specific grounds to distrust — the first NPC in the roster this trait actually has something to push against, rather than agreeing with every reasonable-enough authority figure by default. |
| Master Merchant Cassian Veyl | `veyl` | Ambitious Port Vessar trade-house head — possible source of the "restricted artifacts" thread (a mundane smuggling/black-market plot; not connected to Chad's origin or nature). The artifacts themselves: small, portable pre-Sundering dwarven craft-work (a lockbox that never needs a key turned twice, a lantern that doesn't need oil) — valuable because they're rare and demonstrably still function, illegal to trade because Karak-Thrum considers unrecovered Sundering-era craft to be clan property regardless of who currently holds it. Veyl's angle is straightforward profit from a jurisdictional gap, not menace. A plausible next beat, if picked up: a Karak-Thrum agent (unnamed until introduced) has quietly begun asking around Port Vessar for the source of these artifacts, which puts Veyl in a genuinely awkward spot — not dangerous exactly, but a live pressure that could plausibly touch anyone doing business with him, including Chad if that connection is ever made on-screen. The physical risk behind why these sites are dangerous to loot in the first place, not just illegal to trade from, is stoneward wisps (§2.10). |

**Seats of power, for reference only** *(trimmed from full roster entries — none of these are plausible near-term contacts from Chad's current position in the Border Marches; assign a full entry with `npc_id` only once the campaign actually reaches their region)*: Valenor is ruled by King Aldric IV Valen and Queen-Consort Elara; the River Marches by Duke Harlan Marchand; Karak-Thrum by High King Thrain Ironvein, with Thane Brokk Stonefist commanding the Hold Guard and Trade-Thane Helga Goldhammer handling surface diplomacy; the Silverwood Enclave by a council whose First Speaker, Lady Elandriel Sylvandar, favors engagement against the more hawkish Lord Vaelith Moonshadow; the Greenmantle Confederation's Harvest Moot is hosted by Mayor Tilda Greenbottle. Master Herbalist Lirael Leafwhisper, Old Man Tobin Underhill, and Scoutmaster Pip Riverfoot were previously listed as full entries with no distinguishing detail attached — cut for now; reintroduce properly, with an actual role, if and when a scene calls for them.

### Hollow Creek *(nearest settlement to Chad's landing point — the most likely stage for Chapter 1)*

A palisaded frontier waypoint of a few hundred people, roughly half a day's walk from where Chad arrived. Too small for a proper guild hall or standing garrison — Captain Ironwood's company patrols through rather than being based here — but large enough to matter: one inn (the Ashen Kettle, run by Marta Dell), one smith, a handful of general-goods stalls, and a market day every eighth day or so when a caravan or trader is due, rather than on a fixed calendar date. No mayor or formal council; disputes go to whoever's oldest, loudest, or most trusted in the moment, which in practice usually means Dell or the smith. Built where it is because it's the last reliable water and shelter before the old ruins and deeper Wilds — most traffic through here is either heading toward those ruins (scavengers, the occasional fool) or away from the raided stretches further out. Population is a mix of frontier-born families and exactly the kind of displaced arrivals described above (§2.1) — Hollow Creek doesn't ask where anyone's from, only whether they can pay or work.

**The smith:** Corran Ashby (`ashby` if promoted to a tracked NPC), a heavyset man in his fifties, does most of Hollow Creek's practical metalwork — tools, wagon fittings, the occasional weapon repair — and is the closest thing the settlement has to a second authority alongside Dell, precisely because everyone eventually needs something from him.

**The watch:** No standing garrison, but a rotating handful of armed volunteers (paid a token amount by whoever's turn it is to organize it, usually Dell or Ashby) keep the gate at night and walk the palisade — informal, imperfect, and the kind of arrangement that plausibly fails or falls short under real pressure rather than being a reliable safety net.

**Healing:** No resident healer — Sera Wick (§2.3) passes through roughly monthly, and between visits Hollow Creek relies on ordinary first aid, the Church of the Harvest's waystation shrine (§2.15) for anything a prayer and a poultice might help, and word sent ahead if her timing can be caught. A serious injury between her visits is a genuine problem, not a minor inconvenience — worth remembering for how real physical stakes actually land here.

**On casting new/incidental NPCs:** default to giving unnamed or newly-introduced NPCs their own ordinary displacement rather than settled local status. This is texture for populating scenes, not a rule that every NPC must be uprooted.

## 2.4 Calendar & Economy

**Calendar:** 12 months × 30 days, plus the 5-day midwinter "Turning" festival.
Frostwane · Thawmoon · Seedmonth · Greenrise · Sunheight · Highsummer · Goldleaf · Harvestide · Mistfall · Darkening · Longnight · Deepwinter.

**Currency** *(Valenor standard):* Copper Penny → Silver Mark (×10) → Gold Crown (×20 marks) → Platinum Sovereign (×10 crowns, rare). Dwarves use weighed/stamped bars; elves trade in goods and rare materials rather than coin.

**Regional goods:** Heartlands (grain, wool, wine) · Green Hills (beer, cheese, orchard fruit) · Stone Peaks (iron, steel, gems) · Elderwoods (fine timber, dyes, rare medicines) · Port Vessar (salt, spices, glass, exotica).

**Port Vessar's grey market:** Alongside its legitimate trade, Port Vessar runs on an open secret of goods that move without full paperwork — undeclared cargo skimmed off a legitimate shipment, goods that changed hands one time too many to trace, and the occasional genuinely restricted item (see Cassian Veyl, §2.3) moved through the same channels as ordinary smuggling rather than anything more dramatic. Everyone in the trade knows it happens; the city's reputation-economy custom (§2.11) means getting caught costs standing more than it costs coin.

## 2.5 Military Styles

| People | Style |
|---|---|
| Valenor | Heavy cavalry, crossbows, feudal levies |
| River Marches | Mobile, archery, river control |
| Karak-Thrum | Heavy infantry, underground warfare |
| Silverwood | Ambush, terrain control |
| Greenmantle | Militia, guerrilla, relies on allies |

## 2.6 Peoples — Culture Detail

| People | Religion/Custom | Law | Naming |
|---|---|---|---|
| **Humans** | Church of the Harvest; priests as scribes/healers/judges | Formal law | Given name + house/place |
| **Dwarves** | Ancestor/stone veneration, oath-keeping rituals | Clan law over abstract law — shunning/exile for oath-breaking | Given name + clan |
| **Elves** | Reverence through song and living shrines | Custom and banishment | Given name + house (private names rarely shared) |
| **Halflings** | Household-spirit offerings; taboos against waste/poor hospitality | Local custom/social pressure | Given name + family/descriptive |

**Cross-views:** Humans see dwarves as stubborn-but-reliable, elves as aloof, halflings as pleasant-but-provincial. Dwarves respect human energy, find elves indirect. Elves see humans as hasty and dwarves as unimaginative. Halflings judge individuals and just want fair-paying neighbors.

**Age and frontier labor:** Human working life in the Border Marches runs harder and shorter than in the settled Heartlands — a human doing manual frontier labor past roughly his fourth decade is unusual enough to draw comment, not so unusual as to draw real suspicion. A foreman or fellow laborer might size someone up for it ("bit old for portering, aren't you") without malice — a practical assessment that cuts both ways: age reads as a mark against stamina but for steadiness. Dwarves, with much longer lifespans, don't apply this lens to humans at all. Elves privately consider any human "old" for labor at almost any age, but rarely say so aloud.

**A note on half-elves:** Not a fifth people with their own government or law — a real but uncommon result of contact along the Silverwood Accords' trade border (§2.2), raised in whichever parent's culture they grow up in rather than a culture of their own. Where one turns up, treat them as a member of that upbringing's people first, with the added texture of an outsider's relationship to the other half — no separate mechanics or lore block needed.

## 2.7 Magic

**Traditions:** Craft (object enhancement) · Green (growth/forest) · Hearth & Healing (most common) · rare High magic.

Requires talent *and* training, but a trained practitioner is genuinely, reliably capable within their tradition — magic here is a real profession with real results, not a rare or crippled trick. Valenor licenses it; dwarves bind it to craft; elves treat it as a serious responsibility. Costs (fatigue, rare materials, real limits at large scale) exist to keep magic specific and interesting rather than to make it barely functional. Old-age artifacts are prized and feared in equal measure.

**Worked examples, for consistent tone across scenes:**
- A licensed Hearth & Healing practitioner in a Heartlands town can reliably set and knit a broken bone in days instead of weeks, or close an infected wound before it turns fatal — visible, dependable competence. The cost is real fatigue and, for anything beyond routine injury, rare herbs or materials that make it a genuine expense. Sera Wick (§2.3), who circuits Hollow Creek and nearby settlements, is this tradition made concrete for Chad's part of the world — a real, findable person rather than a background fact.
- A Craft-mage's enchanted tool or weapon does something a mundane version can't (holds an edge indefinitely, glows for light, resists rust and rot) and is treated in-world as a serious, valuable, tradeable asset.
- Green magic can accelerate a crop's growth or calm a spooked animal in a way villagers genuinely rely on each season — mundane life in the Heartlands assumes a Green practitioner's help exists and is competent, the way a modern town assumes its utilities work.
- High magic remains rare and consequential — not because it's weak, but because so few people have the talent and years of training it demands; when it appears, it should feel like a serious event precisely because everyday magic is not rare or weak.

## 2.8 Travel

**Routes:** Crown Road (Heartlands) · Gate Road (to Thrum-Gate) · river traffic · controlled forest paths to Silverhaven.

| Route | Duration |
|---|---|
| Highcrown ↔ Port Vessar | 10–14 days by road / 6–8 by water |
| Highcrown ↔ Thrum-Gate | 8–12 days |
| Millbrook ↔ Riverwatch | 3–5 days |

Inns are common on main roads; tolls at bridges and gates.

## 2.9 Holidays

| Holiday | Timing |
|---|---|
| The Turning | Midwinter, 5 days |
| Sowing Day | Early Seedmonth |
| Stone Remembrance *(dwarven)* | Mid-Thawmoon |
| Leafwake *(elven)* | Early Greenrise |
| Harvest Moot *(halfling)* | Late Harvestide |
| Crown's Justice *(human courts)* | Mid-Sunheight |
| Forgefire Night *(dwarven craft)* | Mid-Goldleaf |

## 2.10 Monsters & Hazards

**Creatures:** Wolf packs · orc/goblinoid raiders · trolls · forest spirits · giant spiders · rock drakes · deep-dwelling horrors · will-o'-wisps · ruin guardians · **stoneward wisps** · **rootblight vermin**.

**Environmental hazards:** Blizzards · rockfalls · wild-magic surges · floods · droughts · disorienting Elderwoods mists.

**Cultural weight** *(pull one when a creature needs to mean something, not just threaten)*: Trolls feature in Heartlands bedtime stories as a stand-in for debts that come due no matter how long they're avoided — "feeding the troll" is a common idiom for delaying an unavoidable cost. Will-o'-wisps are treated by Border Marches locals as the restless dead of travelers who died off the marked roads, and stepping off a known path at dusk carries real, seriously-held superstition. Forest spirits are, to Silverwood elves, closer to distant kin than monsters — an elf reacts very differently to one than a human would. Ruin guardians are widely believed to only wake for those who take something from a ruin rather than merely enter one — a belief scavengers repeat to each other whether or not it's actually true.

**Stoneward wisps** *(gives the "restricted artifacts" thread — §2.3's Veyl entry — a physical stake to match its legal/economic one)*: Small, cold points of pale light that gather around pre-Sundering dwarven sites specifically — not the same phenomenon as a will-o'-wisp, though frontier folk who've never seen one up close sometimes confuse the two. They don't attack outright; proximity to one causes disorientation, a creeping wrongness in the air, and in prolonged exposure, real physical harm consistent with wild-magic surge hazards above. Karak-Thrum scholars believe they're some residue of the craft-magic bound into Sundering-era work, which is also the closest thing to an in-world explanation for why looting such a site is dangerous, not just illegal. This is the actual reason ruin scavenging (§2.14a) carries real risk beyond just underpayment — the stakes Veyl's artifacts thread has been missing until now.

**Rootblight vermin** *(a low-stakes frontier nuisance, deliberately below "monster" tier — fills a gap the rest of this list doesn't cover)*: A blight-carrying rodent and insect problem specific to Border Marches farmland and stored grain, worse in Mistfall and after a wet season. Not dangerous to a person directly, but a real cost to ordinary labor — a bad infestation can ruin a farmer's stores, delay a caravan's food supply, or turn a routine odd job (§2.14a) into an unplanned, unpaid cleanup. Exists to give mundane competence something to actually solve that isn't a fight: noticing the signs early, knowing which stores to check first, is exactly the kind of practical read Chad's old-world instincts (`docs/CHAD_BACKSTORY.md`) are suited to.

## 2.11 Regional Customs *(flavor — pull when a scene is set there)*

| Region | Custom |
|---|---|
| Valenor / Heartlands | Public oaths, regulated duels, bread-and-salt hospitality |
| River Marches | Communal meals, river festivals, contracts sealed over running water |
| Karak-Thrum | Clan identity paramount, craft competitions, stone funerals with recounted deeds |
| Silverwood | A different sense of time, layered names, reserved hospitality, death marked by trees |
| Greenmantle | Community-first, sacred mealtimes, guests expected to contribute |
| Port Vessar | Transactional reputation economy, severe consequences for debt default |

## 2.12 Languages

Chad has no confirmed way to know, before play establishes it in-scene, whether Eldara's peoples speak anything resembling his own language. Don't assume mutual intelligibility by default, and don't assume a total language barrier either — resolve it narratively, on-screen, the first time Chad tries to communicate with someone. Whatever is established (full understanding, partial/accented understanding, an in-world translation effect, or no shared language at all) becomes canon and should be recorded in Chad's state once established.

## 2.13 Pricing in Play

Coinage is copper/silver/gold/platinum (see `state_schema.json`'s `currency` object); see §2.4 for conversion rates — enough for a GM to price things consistently, not a simulation to be min-maxed. Day-labor in the Border Marches pays a handful of copper; a decent inn room runs a few silver a night; gold-denominated purchases (a horse, a weapon of quality, a season's rent) are notable events worth narrating, not routine spends. Port Vessar's reputation-economy custom (§2.11) means unpaid debts there carry social consequences beyond the coin itself.

## 2.14 Common Professions & Guilds

Guild structure matters more than individual employers in the Heartlands and River Marches: a Merchants' Guild and a Craftsmen's Guild operate in most sizable towns, controlling who may legally trade or practice a trade within town walls. Karak-Thrum organizes similarly around clan-craft lineages rather than open guilds. Freelance or unguilded work (portering, farm labor, caravan guard) is common in frontier regions like the Border Marches precisely because guild reach is weakest there — consistent with where Chad has actually landed.

**How guild standing actually works in practice:** A guild card (a stamped wooden or metal token, not paper) is what a foreman or town watch actually checks — carrying no card marks someone as unguilded on sight. Guild dues are paid seasonally, not up front, which is why plenty of frontier-born locals let their standing lapse. Losing standing is common and not treated as a moral failing in the Border Marches the way it might be in Highcrown.

**Hiring in practice:** Most frontier hiring runs through a foreman or a caravan master working a specific job, not a guild hall — they take whoever's available, guild card or not, and pay is negotiated on the spot.

**Where people get shorted, concretely:** a foreman rounding a day's pay down "for materials" never itemized; a caravan master paying in goods valued well above their real worth; a job's scope quietly expanding mid-task with no renegotiation; a piece-rate job where the counting is done by the payer alone, out of sight; a "probationary" first day worked unpaid. None of these are illegal exactly — they're just how an unguilded worker gets squeezed, and reading for them is squarely the kind of thing Chad's old-world instincts are suited to notice.

## 2.14a Border Marches Labor & Economy *(companion to §2.14, specific to where Chad landed)*

| Work | Who hires | Typical pay | Common way to get shorted |
|---|---|---|---|
| Portering / hauling | Caravan masters, traders passing through | A few copper per day, meals sometimes included | Load weight or distance quietly increased after the rate is set |
| Caravan guard (unarmed/light) | Caravan masters, independent merchants | Day-rate plus a cut of safe arrival, sometimes | The "cut" calculated in the payer's favor with no way to check the math |
| Mine labor (surface/tailings) | Independent claim-holders, small mining outfits | Piece-rate by yield weighed on-site | Payer's own scale, no witness, no second weighing |
| Ruin scavenging | Independent, or a local buyer of curios/scrap | Per-item, negotiated after the fact | Value assessed only by the buyer, after the item's already been handed over |
| Farm/seasonal labor | Local landholders near the Marches' settled edge | Low day-rate, room and board common | "Room and board" deducted at a rate the worker never agreed to |
| Odd jobs / general labor | Anyone needing extra hands | Negotiated per job, often just a meal or a few copper | Scope creep — the small job becomes a bigger one without a new price |

Day-labor pay in the Border Marches runs a handful of copper, consistent with §2.13; this is texture for a scene, not a formal wage table.

**Real hazards behind two rows above** *(§2.10 cross-reference, so these aren't just economic risk)*: ruin scavenging's danger isn't only getting shorted by a buyer — stoneward wisps make the sites themselves genuinely risky to enter. Farm labor's seasonal risk isn't only weather (§2.1) — rootblight vermin can wipe out stored grain a laborer was counting on being paid from, or turn a routine job into unpaid cleanup no one agreed to.

**A plausible first acquisition** *(illustrative, not scripted — Chad's actual first item should still be earned on-screen per the Closed Inventory rule)*: a pair of work gloves is the single most likely first thing worth naming and tracking.

## 2.15 Religion & Belief

No single dominant faith — Valenor's church balances temporal power against the crown (§2.3) without controlling it outright; Silverwood's elves hold a more ancestral/nature-oriented reverence than an organized clergy; Karak-Thrum dwarves venerate craft-ancestors alongside the divine; Greenmantle halflings keep seasonal observance closer to folk custom than theology. Treat clergy and shrines as regional color and potential plot hooks rather than a mechanic — Eldara has no divine-magic subsystem distinct from the general `magic` state field.

**A ready hook, if one is needed rather than improvised fresh:** the Church of the Harvest maintains a small waystation shrine on the road nearest Hollow Creek, tended by a single itinerant priest (unnamed until introduced on-screen) who circuits several frontier settlements. Travelers passing through are customarily expected to leave a small offering or do a small task for the shrine's upkeep — not compulsory, but noted locally if skipped repeatedly.

## 2.16 Chad's Old-World Life

Kept entirely in `docs/CHAD_BACKSTORY.md` — that file is the single source of truth for Chad's personal/old-world canon, kept separate from world lore the same way `saves/current.json` is kept separate from both. Use `python3 scripts/world_info_lookup.py chad` (or a specific name/topic) rather than duplicating any of it here.
