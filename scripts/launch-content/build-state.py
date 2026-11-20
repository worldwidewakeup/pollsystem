#!/usr/bin/env python3
"""
build-state.py: turn a state's research file (docs/launch-content/research/XX.json)
into content files for create-polls.py, checking it first.

  scripts/launch-content/build-state.py XX [XX ...] [--cycle 2026]   build (and check)
  scripts/launch-content/build-state.py XX --check [--cycle 2026]    check only

The cycle (2026-11-20) comes from docs/launch-content/<year>-cycle.json: its
year, election day, kind (Midterm or General: a presidential year's research
lists the President race among the statewide races) and House seats.

Writes, in scripts/launch-content/ (YYYY = the cycle's year, K = Midterm/General):
  xx-YYYY-statewide.json  the statewide election (statewide races) with the
                          state's ballot measures, if it has either
  xx-YYYY-house.json      one ballot per district, each including the statewide
                          election ("YYYY K <State> District N")
States with one House seat get a single ballot instead: xx-YYYY-ballot.json,
"YYYY K <State>", holding the statewide races, the House race and the
measures.

Checks: district count matches the state's seats (2020 apportionment), every
race has a candidate, no duplicate names in a race, measures have official
language and a source. Problems stop the build.
"""
import json, sys, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def load_cycle(argv):
    """The cycle file named by --cycle YEAR (default 2026)."""
    year = argv[argv.index('--cycle') + 1] if '--cycle' in argv else '2026'
    c = json.load(open(os.path.join(ROOT, 'docs/launch-content', f'{year}-cycle.json')))
    c['seats'] = json.load(open(os.path.join(ROOT, c['apportionment'])))['seats']
    return c


import datetime as _dt
CYCLE = load_cycle(sys.argv)
YEAR = CYCLE['year']
PREFIX = f"{YEAR} {'General' if CYCLE['kind'] == 'GENERAL' else 'Midterm'}"   # "2026 Midterm"
P = PREFIX + " · "
DATE = CYCLE['date']
SEATS = CYCLE['seats']
assert sum(SEATS.values()) == 435
_day = _dt.date.fromisoformat(DATE)
# Polls close in the evening, local time: in UTC that's election day or the next day.
CLOSE_UTC = re.compile(rf"({_day.isoformat()}|{(_day + _dt.timedelta(days=1)).isoformat()})T\d\d:\d\d:00Z")
DAY_TEXT = f"{_day.strftime('%b')} {_day.day} {_day.year}"   # "Nov 3 2026"


def load(abbr):
    with open(os.path.join(ROOT, 'docs/launch-content/research', f'{abbr}.json'), encoding='utf-8') as f:
        return json.load(f)


def check(r, abbr):
    problems, warnings = [], []
    if r.get('abbr') != abbr: problems.append(f"abbr is {r.get('abbr')!r}")
    if not CLOSE_UTC.fullmatch(r.get('pollCloseUtc', '')): problems.append(f"pollCloseUtc {r.get('pollCloseUtc')!r} (not election night, {DATE})")
    house = r.get('house', [])
    want = SEATS[abbr]
    got = sorted(h['district'] for h in house)
    expected = [0] if want == 1 else list(range(1, want + 1))
    if want == 1 and got == [1]: got = [0]
    if got != expected: problems.append(f"House districts {got} (want {expected})")
    for race in [(f"District {h['district']}", h['candidates']) for h in house] + [(s['office'], s['candidates']) for s in r.get('statewide', [])]:
        name, cands = race
        if not cands: warnings.append(f"{name}: no candidates (an unopposed race left off the ballot?): its ballot carries only the statewide races")
        names = [c['name'].strip() for c in cands]
        if len(set(names)) != len(names): problems.append(f"{name}: duplicate names")
        if any(not c.get('name', '').strip() for c in cands): problems.append(f"{name}: a blank name")
    for m in r.get('measures', []):
        for k in ('designation', 'subject', 'ballotTitle', 'source'):
            if not str(m.get(k, '')).strip(): problems.append(f"measure {m.get('designation')}: no {k}")
    return problems, warnings


def cand(c, office):
    return {"name": c['name'].strip(), "affiliation": (c.get('party') or '').strip() or "No party listed", "officeName": office}


def build(abbr, ids):
    r = load(abbr)
    problems, warnings = check(r, abbr)
    for w in warnings: print(f"  ! {abbr}: {w}")
    if problems:
        for p in problems: print(f"  ✗ {abbr}: {p}")
        return False
    state, sid, close = r['state'], ids[abbr], r['pollCloseUtc']
    eff = r.get('measureEffective') or f'{YEAR}-12-31'
    def election(title, cands):
        return {"pollTypeId": 1, "title": title, "date": DATE, "scopeLevel": "STATE", "regionIds": [sid], "closeDate": close, "candidates": cands}
    # The app takes one choice per office; a multi-seat race says so.
    # A race the app itself ranks (V44: "rankedInApp", Alaska) says "(ranked
    # choice)", which load-state.bash marks as ranked; elsewhere the voter picks
    # a first choice here.
    RCV = " (ranked choice)" if r.get('rankedInApp') else " (ranked-choice on the ballot; pick your first choice here)"
    def office(s): return s['office'] + (f" (vote for {s['voteFor']} on the ballot; pick your top choice here)" if s.get('voteFor', 1) > 1 else "") + (RCV if s.get('rankedChoice') else "")
    hrcv = RCV if r.get('houseRankedChoice') else ""
    if r.get('houseOfficeNote'): hrcv += f" ({r['houseOfficeNote']})"
    statewide = [cand(c, office(s)) for s in r.get('statewide', []) for c in s['candidates']]
    # A short designation ("Amendment 3") gets its subject; a descriptive one
    # (North Carolina's contest titles) stands alone.
    def mtitle(m): return f"{P}{state} {m['designation']}" + (f": {m['subject']}" if len(m['designation']) <= 30 else "")
    measures = [{"pollTypeId": 3, "title": mtitle(m),
                 "summary": f"{m['ballotTitle'].strip()}\n\nIn short: {m.get('summary', '').strip()}\n\nOfficial ballot language. Source: {m['source']}",
                 "effectiveDate": eff, "closeDate": close} for m in r.get('measures', [])]
    about = f"{state}, {DAY_TEXT}, built by build-state.py from docs/launch-content/research/{abbr}.json (sources and gaps in {abbr}.md)."
    out = os.path.join(HERE, f"{abbr.lower()}-{YEAR}-")
    for suffix in ('statewide.json', 'house.json', 'ballot.json'):
        if os.path.exists(out + suffix): os.remove(out + suffix)
    if SEATS[abbr] == 1:
        h = r['house'][0]
        house = [cand(c, "U.S. Representative, At-Large" + hrcv) for c in h['candidates']]
        doc = {"_about": about + " One House seat, so one ballot for the whole state.",
               "election": election(f"{PREFIX} {state}", statewide + house)}
        if measures: doc["ballotMeasures"] = measures
        json.dump(doc, open(out + 'ballot.json', 'w'), indent=2, ensure_ascii=False)
        print(f"  ✓ {abbr}: 1 ballot ({len(statewide) + len(house)} candidates), {len(measures)} measures")
        return True
    sw_title = None
    if statewide or measures:
        sw_title = f"{P}{state}: statewide races & measures"
        doc = {"_about": about, "election": election(sw_title, statewide)}
        if measures: doc["ballotMeasures"] = measures
        json.dump(doc, open(out + 'statewide.json', 'w'), indent=2, ensure_ascii=False)
    hdoc = {"_about": about + " One ballot per district" + (f", each including \"{sw_title}\"." if sw_title else "."),
            "elections": [election(f"{PREFIX} {state} District {h['district']}",
                                   [cand(c, f"U.S. Representative, District {h['district']}" + hrcv) for c in h['candidates']])
                          for h in sorted(r['house'], key=lambda h: h['district']) if h['candidates'] or sw_title]}
    if sw_title: hdoc["includeElectionTitled"] = sw_title
    json.dump(hdoc, open(out + 'house.json', 'w'), indent=2, ensure_ascii=False)
    print(f"  ✓ {abbr}: statewide {len(statewide)} candidates in {len(r.get('statewide', []))} races, {len(measures)} measures; {len(hdoc['elections'])} district ballots")
    return True


if __name__ == '__main__':
    argv = sys.argv[1:]
    if '--cycle' in argv:
        k = argv.index('--cycle'); del argv[k:k + 2]
    args = [a for a in argv if not a.startswith('--')]
    ids = json.load(open(os.path.join(HERE, 'state-ids.json')))
    ok = True
    for abbr in (a.upper() for a in args):
        if '--check' in sys.argv:
            p, w = check(load(abbr), abbr)
            for x in w: print(f"  ! {abbr}: {x}")
            for x in p: print(f"  ✗ {abbr}: {x}")
            ok &= not p
            if not p: print(f"  ✓ {abbr}: checks pass")
        else:
            ok &= build(abbr, ids)
    sys.exit(0 if ok else 1)
