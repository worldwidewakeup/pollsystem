#!/usr/bin/env python3
"""
rehearsal-inputs.py: the made-up inputs for a cycle rehearsal (2026-11-22;
used by rehearse.bash, docs/ELECTION-CYCLE-SETUP.md section 6).

Writes, from the 2026 cycle and research:
  docs/launch-content/<year>-cycle.json   a throwaway cycle for the chosen states
  <research-dir>/<XX>.json                edited research copies:
      - election night moved to the rehearsal's date (same local closing time);
      - in a presidential year, a President race added to the statewide races;
      - one House candidate renamed "Rehearsal Renamed Candidate";
      - measure effective dates moved by the same number of years.

  rehearsal-inputs.py --year 2028 --states ID TX WY --redraw TX --research-dir tmp/rehearsal/2028/research

--redraw XX: a state whose 2026 lines came from an official plan is switched to
the Census lines, which genuinely differ - a realistic "redraw" without a new
plan file. Only states that used a plan in 2026 can be redrawn this way.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE_YEAR, BASE_DATE = 2026, dt.date(2026, 11, 3)


def election_day(year):
    """The Tuesday after the first Monday in November."""
    d = dt.date(year, 11, 1)
    first_monday = d + dt.timedelta(days=(0 - d.weekday()) % 7)
    return first_monday + dt.timedelta(days=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--year', type=int, required=True)
    ap.add_argument('--states', nargs='+', required=True)
    ap.add_argument('--redraw', nargs='*', default=[])
    ap.add_argument('--research-dir', required=True)
    a = ap.parse_args()
    if a.year % 2 or a.year <= BASE_YEAR:
        sys.exit(f'--year must be an even year after {BASE_YEAR}')
    states = [s.upper() for s in a.states]
    redraw = [s.upper() for s in a.redraw]
    base = json.load(open(os.path.join(ROOT, f'docs/launch-content/{BASE_YEAR}-cycle.json')))
    cycle_path = os.path.join(ROOT, f'docs/launch-content/{a.year}-cycle.json')
    if os.path.exists(cycle_path):
        sys.exit(f'{os.path.relpath(cycle_path, ROOT)} already exists: is a real {a.year} cycle being prepared? Not overwriting it.')
    day = election_day(a.year)
    general = a.year % 4 == 0

    cyc = dict(base)
    cyc['_about'] = (f'REHEARSAL ONLY (made by rehearsal-inputs.py), not a real cycle: rehearse.bash deletes it. '
                     f'States {" ".join(states)}; redrawn: {" ".join(redraw) or "none"}.')
    cyc['year'], cyc['date'], cyc['kind'] = a.year, day.isoformat(), 'GENERAL' if general else 'MIDTERM'
    cyc['states'] = {}
    for st in states:
        if st not in base['states']:
            sys.exit(f'{st} is not in the {BASE_YEAR} cycle file')
        info = dict(base['states'][st])
        if st in redraw:
            if info.get('lines') != 'plan':
                sys.exit(f'--redraw {st}: its {BASE_YEAR} lines are "{info.get("lines")}", not a plan; '
                         f'pick a state that used an official plan in {BASE_YEAR} (e.g. TX, CA, FL, NC, OH, UT, AL, LA)')
            info = {'lines': 'census', 'plan': f"CD{base['congress']}", 'note': f'rehearsal: as if redrawn ({BASE_YEAR} used {info.get("plan")})'}
        cyc['states'][st] = info
    os.makedirs(a.research_dir, exist_ok=True)
    renamed = False
    shift = a.year - BASE_YEAR
    for st in states:
        src = os.path.join(ROOT, f'docs/launch-content/research/{st}.json')
        if not os.path.exists(src):
            sys.exit(f'{st} has no research JSON (docs/launch-content/research/{st}.json); pick another state')
        r = json.load(open(src))
        m = re.match(r'^(\d{4}-\d{2}-\d{2})(T.*)$', r.get('pollCloseUtc', ''))
        if m:
            offset = dt.date.fromisoformat(m.group(1)) - BASE_DATE   # election day or the day after, in UTC
            r['pollCloseUtc'] = (day + offset).isoformat() + m.group(2)
        if general:
            r['statewide'] = [{"office": "President of the United States", "candidates": [
                {"name": "Rehearsal Candidate A", "party": "Democratic"},
                {"name": "Rehearsal Candidate B", "party": "Republican"},
                {"name": "Rehearsal Candidate C", "party": "Libertarian"}]}] + r.get('statewide', [])
        for k in ('measureEffective',):
            if r.get(k):
                r[k] = re.sub(r'\d{4}', lambda y: str(int(y.group()) + shift), r[k], count=1)
        if not renamed and len(r.get('house', [])) > 1 and r['house'][1]['candidates']:
            old = r['house'][1]['candidates'][0]['name']
            r['house'][1]['candidates'][0]['name'] = 'Rehearsal Renamed Candidate'
            renamed = True
            print(f'  {st} District {r["house"][1]["district"]}: "{old}" renamed "Rehearsal Renamed Candidate"')
        json.dump(r, open(os.path.join(a.research_dir, f'{st}.json'), 'w'), indent=2, ensure_ascii=False)
        print(f'  {st}: research copy, polls close {r.get("pollCloseUtc")}' + (', President race added' if general else ''))
    json.dump(cyc, open(cycle_path, 'w'), indent=2, ensure_ascii=False)
    print(f'  wrote {os.path.relpath(cycle_path, ROOT)}: {a.year} {"General" if general else "Midterm"}, election day {day}')


if __name__ == '__main__':
    main()
