#!/usr/bin/env python3
"""
cycle.py: the election-cycle driver (docs/ELECTION-CYCLE-SETUP.md, 2026-11-20).

Reads a per-cycle file, docs/launch-content/<year>-cycle.json, and reports
what's ready for each state. Only reads: nothing here changes the repo or a
site. (maps / districts / content / load come next; see the runbook.)

  scripts/election-cycle/cycle.py status [--cycle 2026] [XX ...]
      In the repo, per state: House seats, research notes, content files,
      district map (Census lines / official plan / grid), district-county
      rows for search. Ends with what's missing.

  scripts/election-cycle/cycle.py check local|staging|prod|URL [--cycle 2026] [XX ...]
      On a running site, through public read-only endpoints: the site's
      election cycle, each state's published district ballots (numbered 1..N
      for its N seats, or the one ballot of a one-seat state) and its map.

Exit code 1 when something is missing, so it can gate a script.
"""
import argparse
import glob
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SITES = {
    'local': 'http://localhost:8080',
    'staging': 'https://pollsystem-backend-staging.fly.dev',
    'prod': 'https://pollsystem-backend.fly.dev',
}
NAMES = dict(AL='Alabama', AK='Alaska', AZ='Arizona', AR='Arkansas', CA='California', CO='Colorado',
             CT='Connecticut', DE='Delaware', FL='Florida', GA='Georgia', HI='Hawaii', ID='Idaho',
             IL='Illinois', IN='Indiana', IA='Iowa', KS='Kansas', KY='Kentucky', LA='Louisiana', ME='Maine',
             MD='Maryland', MA='Massachusetts', MI='Michigan', MN='Minnesota', MS='Mississippi',
             MO='Missouri', MT='Montana', NE='Nebraska', NV='Nevada', NH='New Hampshire', NJ='New Jersey',
             NM='New Mexico', NY='New York', NC='North Carolina', ND='North Dakota', OH='Ohio',
             OK='Oklahoma', OR='Oregon', PA='Pennsylvania', RI='Rhode Island', SC='South Carolina',
             SD='South Dakota', TN='Tennessee', TX='Texas', UT='Utah', VT='Vermont', VA='Virginia',
             WA='Washington', WV='West Virginia', WI='Wisconsin', WY='Wyoming')
KIND_WORD = {'MIDTERM': 'Midterm', 'GENERAL': 'General'}


def load_cycle(year):
    path = os.path.join(ROOT, 'docs', 'launch-content', f'{year}-cycle.json')
    if not os.path.exists(path):
        sys.exit(f'No cycle file {os.path.relpath(path, ROOT)}: copy the last one and edit it (runbook step 1).')
    cyc = json.load(open(path))
    cyc['seats'] = json.load(open(os.path.join(ROOT, cyc['apportionment'])))['seats']
    cyc['prefix'] = f"{cyc['year']} {KIND_WORD[cyc['kind']]}"
    return cyc


def chosen(cyc, wanted):
    states = [s.upper() for s in wanted] or sorted(cyc['states'])
    unknown = [s for s in states if s not in cyc['states']]
    if unknown:
        sys.exit(f"Not in the cycle file: {', '.join(unknown)}")
    return states


def mark(ok):
    return '✓' if ok else '✗'


# ---------- status: the repo ----------

def district_county_states():
    """States with district_counties rows in a migration (V46 and later)."""
    found = set()
    for f in glob.glob(os.path.join(ROOT, 'backend/src/main/resources/db/migration/V*__*.sql')):
        text = open(f).read()
        if 'district_counties' in text:
            found.update(re.findall(r"\(\s*'([A-Z]{2})',\s*'", text))
    return found


def status(args):
    cyc = load_cycle(args.cycle)
    y = cyc['year']
    dc = district_county_states()
    missing = []
    print(f"Cycle {cyc['prefix']} (election day {cyc['date']}, {cyc['congress']}th Congress)\n")
    print(f"{'':3} {'seats':>5}  research  content  map            district→county")
    for st in chosen(cyc, args.states):
        seats = cyc['seats'][st]
        # The first states (WA, CA, CO in 2026) were researched into one file each.
        research = all(os.path.exists(os.path.join(ROOT, f'docs/launch-content/research/{st}.{ext}')) for ext in ('md', 'json')) \
            or os.path.exists(os.path.join(ROOT, f"docs/launch-content/{NAMES[st].lower().replace(' ', '-')}-{y}-general.md"))
        lc = st.lower()
        files = [f'xx-{y}-ballot.json'] if seats == 1 else [f'xx-{y}-statewide.json', f'xx-{y}-house.json']
        content = all(os.path.exists(os.path.join(ROOT, 'scripts/launch-content', f.replace('xx', lc))) for f in files)
        lines = cyc['states'][st]['lines']
        has_map = os.path.exists(os.path.join(ROOT, f'frontend/public/maps/{st}.json'))
        map_label = (lines if has_map else 'missing')
        # A one-seat state needs no district lookup: its one ballot is statewide.
        needs_dc = seats > 1
        dc_ok = (st in dc) if needs_dc else True
        dc_label = ('—' if not needs_dc else mark(dc_ok)) + ('' if dc_ok or lines != 'plan' else ' (plan: build from the official map)')
        print(f"{st:3} {seats:>5}  {mark(research):^8}  {mark(content):^7}  {map_label:<14} {dc_label}")
        if not research: missing.append(f'{st}: research notes (step 6)')
        if not content: missing.append(f'{st}: content files (step 7)')
        if not has_map: missing.append(f'{st}: map (step 4)')
        elif lines == 'grid': missing.append(f'{st}: official map (still a grid; step 4 needs the plan)')
        if not dc_ok: missing.append(f'{st}: district→county rows (step 5)')
    print()
    if missing:
        print(f'Missing ({len(missing)}):')
        for m in missing:
            print('  -', m)
        return 1
    print('Nothing missing.')
    return 0


# ---------- check: a running site ----------

def get(base, path, params=None):
    url = base.rstrip('/') + path + ('?' + urllib.parse.urlencode(params) if params else '')
    req = urllib.request.Request(url, headers={'User-Agent': 'ballotbox-cycle-check', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def check(args):
    cyc = load_cycle(args.cycle)
    base = SITES.get(args.env, args.env)
    problems = []
    try:
        site = get(base, '/api/election-cycle')
    except urllib.error.HTTPError as e:
        if e.code not in (401, 404):
            raise
        # A backend from before V47 has no cycle setting; its maps read "2026 Midterm".
        site = {'titlePrefix': '2026 Midterm', 'date': '2026-11-03 (assumed)'}
        print(f"Site {base}: no election-cycle setting yet (backend older than V47); assuming 2026 Midterm")
    except urllib.error.URLError as e:
        sys.exit(f"Can't reach {base}: {e.reason}. (Local from the Dev Container: run this in a container on the host network.)")
    else:
        print(f"Site {base}: cycle {site['titlePrefix']} ({site['date']})")
    if site['titlePrefix'] != cyc['prefix']:
        print(f"  note: the cycle file is {cyc['prefix']}. Fine while preparing it; switch the site's setting"
              " (Super dashboard → Election cycle) once its ballots are published.")
    # Published ballots of this cycle (drafts aren't public).
    polls = get(base, '/api/polls/search', {'title': cyc['prefix'], 'type': 'Election', 'includeClosed': 'true'})
    titles = {p['title'] for p in polls}
    print(f"  published {cyc['prefix']} elections found by search: {len(titles)}\n")
    print(f"{'':3} {'seats':>5}  ballots   map")
    for st in chosen(cyc, args.states):
        name, seats = NAMES[st], cyc['seats'][st]
        if seats == 1:
            nums = [1] if f"{cyc['prefix']} {name}" in titles else []
        else:
            pat = re.compile(rf"^{re.escape(cyc['prefix'])} {re.escape(name)} District (\d+)$")
            nums = sorted(int(m.group(1)) for t in titles if (m := pat.match(t)))
        ballots_ok = nums == list(range(1, seats + 1))
        try:
            mp = get(base, f'/api/polls/maps/{st}/results')
            map_n = len(mp.get('districts', []))
        except Exception as e:  # noqa: BLE001 - report, don't stop
            map_n = None
            problems.append(f'{st}: map endpoint failed ({e})')
        # The site's map reads the site's cycle; only compare when they match.
        map_ok = map_n == seats if site['titlePrefix'] == cyc['prefix'] else True
        ballots = f"{len(nums)}/{seats}" + ('' if ballots_ok else f" ✗ {format_missing(nums, seats)}")
        print(f"{st:3} {seats:>5}  {ballots:<9} {'—' if map_n is None else map_n} {'' if map_ok else '✗'}")
        if not ballots_ok: problems.append(f'{st}: published ballots {format_missing(nums, seats)}')
        if not map_ok: problems.append(f'{st}: map shows {map_n} of {seats} districts')
    print()
    if problems:
        print(f'Problems ({len(problems)}):')
        for p in problems:
            print('  -', p)
        return 1
    print('All good.')
    return 0


def format_missing(nums, seats):
    want = set(range(1, seats + 1))
    miss, extra = sorted(want - set(nums)), sorted(set(nums) - want)
    parts = []
    if miss: parts.append('missing ' + ','.join(map(str, miss)))
    if extra: parts.append('unexpected ' + ','.join(map(str, extra)))
    if len(nums) != len(set(nums)): parts.append('duplicates')
    return '; '.join(parts) or 'ok'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('status', help="what's ready in the repo, per state")
    s.add_argument('states', nargs='*')
    s.add_argument('--cycle', default='2026')
    c = sub.add_parser('check', help='what a running site has, per state (read-only)')
    c.add_argument('env', help='local, staging, prod, or a backend URL')
    c.add_argument('states', nargs='*')
    c.add_argument('--cycle', default='2026')
    args = ap.parse_args()
    sys.exit(status(args) if args.cmd == 'status' else check(args))


if __name__ == '__main__':
    main()
