# Setting up a new election cycle

How to prepare BallotBox for the next midterm (or general) election: the
places (states, counties, zipcodes), the congressional districts and their
maps, and every state's ballots. Written 2026-11-20 from what the 2026
midterms needed. The steps are numbered in the order they depend on each
other.

**Status of automation (2026-11-20):** the driver
`scripts/election-cycle/cycle.py` runs every scripted step from one file
per cycle (section 5). The site's current cycle is a setting (section 4).
What stays with you: the decisions in section 2, finding the official plans
of states that redrew, and reviewing the research.

**The short version for a new cycle** (e.g. 2028):

```
cp docs/launch-content/2026-cycle.json docs/launch-content/2028-cycle.json   # edit: year, date, kind, states' lines and plans
scripts/election-cycle/cycle.py status --cycle 2028          # what's missing
scripts/election-cycle/cycle.py fetch --cycle 2028           # Census files
scripts/election-cycle/cycle.py maps XX … --cycle 2028       # only states whose lines changed
scripts/election-cycle/cycle.py districts XX … --cycle 2028 --write district_counties_2028
#   research each state (step 6), then:
scripts/election-cycle/cycle.py content XX … --cycle 2028
scripts/election-cycle/cycle.py load local XX … --cycle 2028   # then staging, then prod
scripts/election-cycle/cycle.py check prod --cycle 2028
#   publish (--publish), then switch the site's cycle on the Super dashboard
```
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
| District lines | each district's shape | after each census, plus mid-decade redraws and court orders (2026: TX, CA, FL, NC, OH, UT, AL, LA, …) | **per cycle** (2026-11-22): maps `frontend/public/maps/<year>/XX.json`; counties `district_counties` rows with their `election_year` (V46, V49) |
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

`scripts/maps/build-state-map.py` writes `frontend/public/maps/<year>/XX.json`.
Maps are kept **per cycle**, so a past cycle's results stay drawn on the lines
they were voted under: `/maps/WA?year=2026`, while `/maps/WA` shows the current
cycle. A new cycle needs every state's map in its own folder (copy the unchanged
ones from the previous year; rebuild the redrawn ones). It has four modes,
chosen per state:

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
- **Redrawn states:** `scripts/maps/plan-district-counties.py`, from the same
  official plan used for the map (built 2026-11-20).
  - **Shapes:** overlaid on the full-detail 2020 county lines
    (`tl_2020_us_county.zip`). Overlaps under 0.05% of a county and
    0.5 km² are dropped as slivers, and borderline ones are listed for
    review.
  - **Block lists:** exact, ignoring water-only blocks.
  - **Coastal borderline overlaps:** check them against the land-only
    county outlines (`cb_2020_us_county_500k.zip`), since a district can
    meet a county in a bay.
- **Names:** independent cities keep " city" ("Richmond city" in Virginia is
  not Richmond County; likewise Baltimore city and St. Louis city), as in the
  `counties` table.
- **As of V48:** every multi-seat state except Tennessee has rows.
- **How it ships:** a migration whose rows carry the cycle's `election_year`
  (V49) and a plan name (e.g. `CD119`, `TX2025`). `cycle.py districts --write`
  replaces only that year's rows; earlier cycles keep theirs, and each
  ballot's county search uses its own year's rows. A new cycle needs rows for
  every multi-seat state, including the unchanged ones.

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

The scripts no longer have 2026 built in (2026-11-20): `build-state.py` and
`load-state.bash` read the year, election day, title prefix and seats from
the cycle file (`--cycle`). The Census file names for a new Congress are
set in the cycle file's `downloads`.

`ResultsPrivacy.kt` and `PollHistoryService.kt` mention 2026 only as dates
of decisions in comments.

---

## 5. The scripts

Everything runs from the repo root. The driver, `scripts/election-cycle/cycle.py`,
reads one file per cycle and calls the other scripts the right way for
each state. You rarely need to run the others directly. Their usage is
below for when you do.

**Requirements:**
- `python3` (standard library only) for the driver, `build-state.py`,
  `district-counties.py` and `rehearsal-inputs.py`.
- **Docker** for the geometry: `cycle.py maps` and plan-based `districts`
  run `build-state-map.py` / `plan-district-counties.py` in a
  `python:3.12-slim` container with shapely, pyshp, pyproj and openpyxl.
  `load-state.bash` also uses Docker, and `rehearse.bash` uses the
  `pollsystem-db` container.
- **Tokens** (git-ignored, never printed) for `load`:
  `.devcontainer/{local-content-super,staging-super,prod-super}-token.secrets.env`.

### 5.1 The cycle file

`docs/launch-content/<year>-cycle.json`. Copy the last one and edit it. An
excerpt of 2026's:

```json
{
  "year": 2026, "date": "2026-11-03", "kind": "MIDTERM", "congress": 119,
  "apportionment": "scripts/election-cycle/apportionment-2020.json",
  "downloads": {
    "counties.json": "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json",
    "cd.zip": "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_cd119_500k.zip",
    "county-district.txt": "https://www2.census.gov/geo/docs/maps-data/data/rel2020/cd-sld/tab20_cd11920_county20_natl.txt",
    "tl_2020_us_county.zip": "https://www2.census.gov/geo/tiger/TIGER2020/COUNTY/tl_2020_us_county.zip"
  },
  "states": {
    "WA": { "lines": "census", "plan": "CD119", "excludeCounties": ["53029"] },
    "TX": { "lines": "plan", "plan": "TX2025",
            "source": "Texas Legislative Council, PLANC2333 (HB 4, 2025; in effect for 2026)",
            "planFiles": { "districts": "tmp/maps/official/TX/planc2333.zip", "field": "District" } },
    "OH": { "lines": "plan", "plan": "OH2025", "source": "…",
            "planFiles": { "baf": "tmp/maps/official/OH/adopted-430.zip",
                           "blocks": "tmp/maps/blocks/tl_2020_39_tabblock20.zip" } },
    "TN": { "lines": "grid", "note": "…" }
  }
}
```

- **`kind`:** `MIDTERM` or `GENERAL` (a presidential year). Ballot titles
  start "2026 Midterm" or "2028 General".
- **`lines`:** one of three modes.
  - `census`: the Census file's lines.
  - `plan`: the state's official plan. `planFiles` holds shapes + their
    district field, or a block assignment file + the state's 2020 blocks.
  - `grid`: numbered boxes until the plan is found.
- **`plan`:** the label stored with the district rows.
- **`excludeCounties`:** counties left off the map (FIPS codes).
- **Official plan files** you download yourself, into `tmp/`, once you've
  confirmed which plan is in force.

### 5.2 `scripts/election-cycle/cycle.py`: the driver

```
cycle.py status    [XX …] [--cycle 2026]
cycle.py check     local|staging|prod|URL [XX …] [--cycle 2026]
cycle.py fetch     [--cycle 2026]
cycle.py maps      XX … [--cycle 2026]
cycle.py districts XX … [--cycle 2026] [--write NAME]
cycle.py content   XX … [--cycle 2026] [--research-dir DIR]
cycle.py load      local|staging|prod XX … [--cycle 2026] [--publish]
```

`--cycle` picks `docs/launch-content/<year>-cycle.json` (default 2026).
States are two-letter codes; with none, `status` and `check` cover every
state in the cycle file.

| Command | Reads / writes | Does |
|---|---|---|
| `status` | reads the repo | per state: seats, research, content files, map mode, district→county rows for that year; then what's missing (exit 1 if anything) |
| `check ENV` | reads a site, public endpoints only | the site's current cycle; each state's published ballots numbered 1..N for its seats (or the one ballot of a one-seat state); its map's district count for the cycle's year (exit 1 on a problem) |
| `fetch` | writes `tmp/election-cycle/<year>/` | downloads the cycle file's `downloads`, skipping files already there |
| `maps XX…` | writes `frontend/public/maps/<year>/XX.json` | `build-state-map.py` in the state's mode (needs Docker) |
| `districts XX…` | prints SQL, or `--write NAME` → `backend/…/db/migration/VNN__NAME.sql` | district→county rows for the cycle's year, replacing that year's rows for those states; other years stay. Census file or the state's plan. One-seat and grid states are skipped. **Dry-run the migration on local inside `BEGIN … ROLLBACK` and check every row matched a county before committing.** |
| `content XX…` | writes `scripts/launch-content/xx-<year>-*.json` | `build-state.py`: research JSON → content files (`--research-dir` to read research from another folder) |
| `load ENV XX…` | creates polls | `load-state.bash`: drafts, statewide first then the district ballots; existing ones are skipped. `--publish` then publishes the states' drafts |

Examples:

```
scripts/election-cycle/cycle.py status --cycle 2028
scripts/election-cycle/cycle.py maps TX CA --cycle 2028
scripts/election-cycle/cycle.py districts TX CA --cycle 2028 --write district_counties_2028_redraws
scripts/election-cycle/cycle.py content WA OR ID --cycle 2028
scripts/election-cycle/cycle.py load staging WA OR ID --cycle 2028
scripts/election-cycle/cycle.py check prod --cycle 2028
```

From the Dev Container, `check local` can't reach local's backend
directly. Run it in a container on the host network:
`docker run --rm --network host -v "$PWD":/r -w /r python:3.12-slim python3 scripts/election-cycle/cycle.py check local`.

### 5.3 `scripts/election-cycle/rehearse.bash`: a rehearsal on local

```
scripts/election-cycle/rehearse.bash [--year 2028] [--states "ID TX WY"] [--redraw "TX"] [--yes] [--no-pause]
```

- **`--year`:** the made-up cycle's year. A presidential year adds a
  President race.
- **`--states`:** states to rehearse; each needs a research JSON.
- **`--redraw`:** states switched from their 2026 plan to the Census lines.
- **`--yes`:** runs every step without asking.
- **`--no-pause`:** skips the browser pause.

It shows each step's command (Enter runs it, `s` skips it, `q` quits). It
snapshots local first and restores however it ends. See section 6.

### 5.4 The scripts the driver calls

**`scripts/election-cycle/rehearsal-inputs.py`**: the rehearsal's made-up inputs.
```
rehearsal-inputs.py --year 2028 --states ID TX WY --redraw TX --research-dir tmp/rehearsal/2028/research
```
It writes `docs/launch-content/<year>-cycle.json` and edited research
copies, and refuses to overwrite an existing cycle file.

**`scripts/maps/build-state-map.py`**: one state's map.
```
build-state-map.py XX SS COUNTIES_JSON CD_ZIP OUT_JSON [--exclude-counties FIPS,…]            # Census lines
build-state-map.py XX SS COUNTIES_JSON CD_ZIP OUT_JSON --districts PLAN.zip --field F --source "…"   # plan shapes
build-state-map.py XX SS COUNTIES_JSON CD_ZIP OUT_JSON --baf PLAN --blocks tl_2020_SS_tabblock20.zip --source "…"
build-state-map.py XX --grid N OUT_JSON                                                       # numbered boxes
```
`XX` is the state code and `SS` its FIPS code. `OUT_JSON` is
`frontend/public/maps/<year>/XX.json`. It needs shapely and pyshp (plus
pyproj for plans, and openpyxl for `.xlsx` block files).

**`scripts/maps/district-counties.py`**: district→county rows from the Census file.
```
python3 -I scripts/maps/district-counties.py tab20_cd11920_county20_natl.txt WA [OR ID …]
```
It prints SQL `VALUES` rows (state, county, district, whole).

**`scripts/maps/plan-district-counties.py`**: the same rows from an official plan.
```
plan-district-counties.py XX SS tl_2020_us_county.zip --districts PLAN.zip --field DISTRICT [--min-share 0.05] [--min-km2 0.5]
plan-district-counties.py XX SS tl_2020_us_county.zip --baf PLAN --blocks tl_2020_SS_tabblock20.zip
```
- **Shapes** are overlaid on the full-detail 2020 county lines. Overlaps
  under `--min-share` % of the county **and** `--min-km2` are dropped as
  slivers.
- **Borderline overlaps** (0.001%–1%) are listed on stderr. Check coastal
  ones against land-only outlines.
- **Block files** are exact, and water-only blocks are ignored.

**`scripts/launch-content/build-state.py`**: research → content files.
```
build-state.py XX [XX …] [--cycle 2026] [--research-dir DIR]     # build (and check)
build-state.py XX --check [--cycle 2026]                        # check only
```
- **Checks:** district count against the seats, closing time on election
  night, candidates, and measure language.
- **Outputs** go to `scripts/launch-content/xx-<year>-{statewide,house,ballot}.json`.
- **`"rankedInApp": true`** in the research marks races the app ranks
  (Alaska).

**`scripts/launch-content/load-state.bash`**: content files → polls.
```
load-state.bash local|staging|prod XX [XX …] [--publish] [--cycle 2026]
```
It loads statewide first, then the district ballots that include it. It's
rerunnable (existing polls are skipped). Local loads as
`content-super@test.local`, so the demo seed can't wipe the ballots.

**`scripts/launch-content/create-polls.py`**: what `load-state.bash` calls, for one file.
```
create-polls.py CONTENT.json --api URL --token-file FILE
create-polls.py --api URL --token-file FILE --publish-election ID [ID …]
create-polls.py --api URL --token-file FILE --retitle RENAMES.json
create-polls.py HOUSE.json --api URL --token-file FILE --link-ballots
```
It creates elections and their measures as drafts. `--link-ballots` applies
a file's titles and includes to elections that already exist.

---

## 6. Rehearsing a cycle (done 2026-11-22)

The real changes aren't known in advance, so a rehearsal invents realistic
ones that take every path. Run it on **local**: the steps run there anyway,
maps show up at once, and local can be put back exactly.

**The script:** `scripts/election-cycle/rehearse.bash` runs all of it
interactively. Before each step it shows the command (Enter runs it, `s`
skips it, `q` quits). Local is snapshotted first and restored however it
ends. Defaults are `--year 2028 --states "ID TX WY" --redraw "TX"`; `--yes`
runs unattended. The made-up inputs come from
`scripts/election-cycle/rehearsal-inputs.py`. The steps it runs, for doing
it by hand:

1. Snapshot local: `docker exec pollsystem-db pg_dump -U polladmin -d pollsystem -Fc -f /tmp/local-before.dump`.
2. A throwaway `docs/launch-content/2028-cycle.json` for a few states: one with
   unchanged lines (ID), one "redrawn" (TX switched from its plan back to the
   Census lines, which genuinely differ), one with one seat (WY).
3. Edited research copies in `tmp/rehearsal/research/`: election night moved
   to the new date, a President race added, a candidate renamed.
4. `status`, `fetch`, `maps`, `districts --write` (apply the SQL with `psql`,
   not Flyway, then move the file out of the migrations folder), `content
   --research-dir tmp/rehearsal/research`, `load local … --publish`.
5. Switch local's cycle to the rehearsal's (Super dashboard or
   `PUT /api/super/flags/election-cycle`), then `check local --cycle 2028`,
   and look at `/maps/TX`, `/maps/TX?year=2026` and a county search.
6. Put it back: stop the backend, `pg_restore --clean --if-exists
   --single-transaction`, start it, and delete `frontend/public/maps/2028/`,
   `scripts/launch-content/*-2028-*.json` and the cycle file.

The 2026-11-22 rehearsal passed every step. Its one surprise was a gap,
fixed before it ran: maps and district rows weren't kept per cycle.

---

## 7. Open questions

Decided 2026-11-20:

- **The cycle's year** lives in the database, as a setting a super changes
  (V47).
- **Presidential years:** the President race is added to each state's
  statewide election, with no separate poll.
- **Old cycles** stay searchable as closed polls; they aren't archived.
