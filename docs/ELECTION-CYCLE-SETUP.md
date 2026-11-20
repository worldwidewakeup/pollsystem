# Setting up a new election cycle

How to prepare BallotBox for the next midterm (or general) election: the
places (states, counties, zipcodes), the congressional districts and their
maps, and every state's ballots. Written 2026-11-20 from what the 2026
midterms needed. The steps are numbered in the order they depend on each
other.

**Status of automation:** each step below names the script that exists today.
The site's current cycle is already a setting (section 4), and
`scripts/election-cycle/cycle.py status` / `check ENV` report what's ready
(section 5).
Where several scripts or hand steps chain together, the last section proposes
one driver (`scripts/election-cycle/`) to run them in order. It isn't built
yet.

---

## 1. What changes when, and why it matters

| Layer | What it is | How often it changes | Where it lives |
|---|---|---|---|
| States | 50 states + DC | effectively never | `states` table (V2) |
| Counties | ~3,140 counties and equivalents | rarely (a few renames or new ones per decade, mostly Alaska and Connecticut) | `counties` (V8) |
| Zipcodes | zip → county, ~32,000 rows | slowly, every year | `county_zips` (V9) |
| House seats per state | apportionment | after each census (next: 2030 census → 2032 elections) | `SEATS` in `scripts/launch-content/build-state.py` |
| District lines | each district's shape | after each census, plus mid-decade redraws and court orders (2026: TX, CA, FL, NC, OH, UT, AL, LA, …) | maps: `frontend/public/maps/XX.json`; counties: `district_counties` (V46) |
| Ballots | the races, candidates, measures, poll-closing time | every election | research `docs/launch-content/research/XX.{md,json}` → content `scripts/launch-content/xx-YYYY-*.json` → polls |

So a typical midterm (no census) redoes **ballots** for all states, plus
**districts and maps** only for states that redrew. A post-census cycle
(2032) redoes districts and maps for every state with more than one seat, and
the seat counts.

---

## 2. What I need from you

Before starting:

1. **The election.** Its date and year, and whether it's a midterm or a
   presidential general (a presidential year adds the President race to
   every statewide ballot).
2. **Which states.** All 50 + DC, or a subset first (2026 started with WA,
   CA and CO).
3. **The access tokens** for the content account in each environment
   (git-ignored files, never printed):
   `.devcontainer/{local-content-super,staging-super,prod-super}-token.secrets.env`.
   Local loads as `content-super@test.local`; see
   `scripts/launch-content/load-state.bash`.
4. **Neon read-only access** for checks against prod
   (`.devcontainer/neon-readonly.secrets.env`).

While it runs, decisions that are yours:

5. **Redrawn states:** confirm the official plan for each (the enacted map's
   name, who published it, and whether a court has blocked it). I find
   the candidate files; you confirm which plan is in force. In 2026, Missouri
   was wrongly treated as redrawn and Louisiana's court status was never
   confirmed: these are judgment calls.
6. **What goes on a ballot:** which races (U.S. Senate, Governor and other
   statewide offices, House, statewide measures; judicial retention and
   local races were left out in 2026), and edge cases like Alaska's ranked
   choice or a state's "residents only" rule.
7. **Review each state's research** before it becomes polls: candidate
   names, parties, measure wording, poll-closing time.
8. **Publishing:** polls load as drafts. Publishing them, state by state,
   is your call.
9. **Prod deploys:** a schema change (a new migration) reaches prod only
   when you run the backend deploy:
   `cd backend && flyctl deploy -a pollsystem-backend -c fly.toml`.

---

## 3. The steps

Legend: **(you)** needs you, **(script)** a script does it, **(Claude)**
research or code a session does.

### Step 1 — Decide the cycle (you)

Write down: year, election date, states, and which states have new district
lines. A starting point for "who redrew": compare the Census Bureau's
current Congress files with each state's redistricting news. Record it in
`docs/launch-content/YYYY-cycle.md` (new, one per cycle).

### Step 2 — Geography: states, counties, zipcodes (script, only if needed)

Usually skip this. Redo it when the zip data is old or a county changed.

- **Counties:** Census national county codes
  (`https://www2.census.gov/geo/docs/reference/codes2020/`; use the newest
  vintage). Names lose "County", "Parish", "Borough", "Census Area",
  "Municipality" and "Municipio", to match the `counties` table.
- **Zipcodes:** zip → county from `scpike/us-state-county-zip` (CC0), used
  for V9. HUD's ZIP-county crosswalk is a fresher, official alternative
  (needs a free HUD account: you).
- **How it ships:** a new migration that **adds** rows (`ON CONFLICT DO
  NOTHING`). Never renumber or delete counties: polls, admin grants and
  blocks point at them by id.
- **Before a migration that adds a unique index:** check local, staging and
  prod for duplicates first, and build it tolerant (a plain index plus a
  warning).

Today there's no script for this; V8 and V9 were generated by hand.

### Step 3 — House seats (script, post-census years only)

Update `SEATS` in `scripts/launch-content/build-state.py` from the Census
apportionment table. `build-state.py` refuses a state whose district count
doesn't match.

### Step 4 — District maps for `/maps/XX` (script + you)

`scripts/maps/build-state-map.py` writes `frontend/public/maps/XX.json`. It
has four modes, chosen per state:

| State's situation | Mode | Input |
|---|---|---|
| Lines unchanged since the Census file | Census lines | `cb_YYYY_us_cdNNN_500k.zip` (Census cartographic boundaries) + `counties.json` |
| Redrew, plan published as shapes | `--districts PLAN.zip --field F --source "…"` | the state's official shapefile or GeoJSON, any projection |
| Redrew, plan published as a block list | `--baf PLAN --blocks tl_2020_SS_tabblock20.zip --source "…"` | the block assignment file + Census 2020 blocks |
| Plan not found yet | `--grid N` | numbered boxes until the official map is added |
| One seat (at-large) | Census lines, one district | — |

Then add the state to `STATE_MAPS` in `frontend/src/stateMaps.ts` (the page
finds a state's ballots by title).

**Needs you:** confirming each redrawn state's plan (step 2, item 5).
Tennessee was still a grid after the 2026 election.

### Step 5 — District ↔ county lookup for search (script)

`scripts/maps/district-counties.py` turns the Census county-to-district file
into rows for `district_counties` (V46). A county search uses them to find
district ballots; a split county finds each district it touches. The poll's
own area stays statewide.

- **States on the Census lines:** the `tab20_cdNNN20_county20_natl.txt`
  relationship file for the current Congress.
- **Redrawn states:** derive the rows from the same official plan used for the
  map (block assignment → county, or shapes ∩ counties). **Not built yet**:
  the driver should add it.
- **How it ships:** a migration with a new plan name per change (e.g.
  `CD119`, then `TX2026`). Drop the state's old rows in the same migration.

### Step 6 — Research each state's ballot (Claude, you review)

For each state, a session reads the official sources (the Secretary of
State's certified candidate list, sample ballots, measure texts) and writes:

- `docs/launch-content/research/XX.md`: the notes and their sources, and
  what was left out and why;
- `docs/launch-content/research/XX.json`: the structured data: `statewide`
  races, `house` races, `measures`, `pollCloseLocal` / `pollCloseUtc`,
  ranked-choice flags, `sources`.

**Needs you:** reading each `XX.md` (step 2, item 7). Research gaps in 2026
included unverified court statuses and an Alaska claim that hadn't been
checked against the source PDF: say "checked" only for what was checked.

### Step 7 — Build the content files (script)

`scripts/launch-content/build-state.py` turns each research JSON into
`scripts/launch-content/xx-YYYY-statewide.json` and `xx-YYYY-house.json`
(or `xx-YYYY-ballot.json` for one-seat states). Titles follow the pattern
search and `/maps` rely on:

- statewide: `YYYY Midterm · <State>: …`
- each district: `YYYY Midterm <State> District <n>`, which includes the
  statewide election;
- one-seat states: `YYYY Midterm <State>`.

### Step 8 — Load the polls (script), local → staging → prod

`scripts/launch-content/load-state.bash local|staging|prod XX [XX …]`
creates each state's polls as **drafts**, statewide first and then the
district ballots. It's rerunnable: existing polls are skipped. `--publish`
publishes them afterwards (**you** decide when).

Check each environment before the next. Local: look at the ballots and
`/maps/XX`. Staging: the same, on a Neon database. Prod: after the backend
deploy if anything in steps 2–5 added a migration.

### Step 9 — After the election (you, with Manage Polls)

Close dates come from the research (`pollCloseUtc`). To keep voting open
afterwards, or to set a new end date, use **Remove close dates** or **Set
close date** on Manage Polls (supers). Each poll's History records the
change.

---

## 4. Year-specific code

**The site's current cycle is a setting** (V47, 2026-11-20): year, election
day and kind (Midterm or General), changed by a super on the Super
dashboard's **Election cycle** card. Ballot titles start with its prefix
("2026 Midterm", "2028 General"). What reads it:

| Where | Uses |
|---|---|
| `backend/…/poll/StateMapController.kt` | finds a state's ballots for `/maps/XX` by the prefix |
| `frontend/src/stateMaps.ts` (+ `useElectionCycle`) | the results page's link to the state map |
| `backend/…/poll/PollSearchController.kt` | county → district ballots: matches "Midterm" or "General", any year |

**Switch the setting only when the new cycle's ballots are loaded and
published**: the maps then move to them. Preparing the next cycle doesn't
need it.

Still fixed to 2026 (the driver's per-cycle file replaces these):

| Where | What's fixed |
|---|---|
| `scripts/launch-content/build-state.py` | `P = "2026 Midterm · "`, `DATE = "2026-11-03"`, output file names, `SEATS` |
| `scripts/launch-content/load-state.bash` | the `xx-2026-*.json` file names |
| `scripts/maps/build-state-map.py`, `district-counties.py` | default Census file names (`cd119`) |

`ResultsPrivacy.kt` and `PollHistoryService.kt` mention 2026 only as dates
of decisions in comments.

---

## 5. Proposed automation (to build next)

One driver, `scripts/election-cycle/cycle.py`, around a file per cycle,
`docs/launch-content/<year>-cycle.json`. The 2026 one exists; copy it for
2028. House seats are in `scripts/election-cycle/apportionment-2020.json`.
Example of a cycle file:

```
docs/launch-content/2028-cycle.json
{
  "year": 2028, "date": "2028-11-07", "kind": "general", "congress": 121,
  "states": {
    "WA": { "lines": "census" },
    "TX": { "lines": "plan", "map": "--districts tx-plan.zip --field DISTRICT",
            "source": "<publisher>, <plan name>, <date enacted>" },
    "TN": { "lines": "grid" }
  }
}
```

Subcommands, each rerunnable and each printing what it still needs from
you:

| Command | Does |
|---|---|
| `status` **(built)** | in the repo, per state: seats, research, content files, map (Census lines / plan / grid), district→county rows; lists what's missing |
| `fetch` | downloads the Census files (boundaries, relationship file, blocks) into `tmp/election-cycle/<year>/` |
| `maps XX…` | runs `build-state-map.py` in the right mode for each state; updates `STATE_MAPS` |
| `districts XX…` | writes the `district_counties` migration (Census file, or the state's plan) |
| `content XX…` | runs `build-state.py` with the cycle's year and date |
| `load ENV XX… [--publish]` | wraps `load-state.bash` |
| `check ENV` **(built)** | on a running site (local, staging, prod or a URL), read-only: the site's cycle, each state's published ballots numbered 1..N for its seats, its map's district count |

Research (step 6) stays a guided session per state, and decisions stay
yours: the driver only reports what's missing.

---

## 6. Open questions

Decided 2026-11-20:

- **The cycle's year** lives in the database, as a setting a super changes
  (V47).
- **Presidential years:** the President race is added to each state's
  statewide election, with no separate poll.
- **Old cycles** stay searchable as closed polls; they aren't archived.
