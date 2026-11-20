#!/usr/bin/env python3
"""
cycle.py: the election-cycle driver (docs/ELECTION-CYCLE-SETUP.md, 2026-11-20).

Reads a per-cycle file, docs/launch-content/<year>-cycle.json, and runs the
existing scripts the right way for each state. status and check only read;
fetch, maps, districts and content write files in the repo; load creates
polls (as drafts unless --publish).

  scripts/election-cycle/cycle.py status [--cycle 2026] [XX ...]
      In the repo, per state: House seats, research notes, content files,
      district map (Census lines / official plan / grid), district-county
      rows for search. Ends with what's missing.

  scripts/election-cycle/cycle.py check local|staging|prod|URL [--cycle 2026] [XX ...]
      On a running site, through public read-only endpoints: the site's
      election cycle, each state's published district ballots (numbered 1..N
      for its N seats, or the one ballot of a one-seat state) and its map.

  scripts/election-cycle/cycle.py fetch [--cycle 2026]
      Downloads the cycle file's "downloads" (Census boundaries, the
      county-to-district file, the full-detail county lines) into
      tmp/election-cycle/<year>/. Official plan files are yours to download.

  scripts/election-cycle/cycle.py maps XX ... [--cycle 2026]
      Rebuilds frontend/public/maps/XX.json with build-state-map.py in the
      state's mode: Census lines, its plan (shapes or block list), or a grid.

  scripts/election-cycle/cycle.py districts XX ... [--cycle 2026] [--write NAME]
      District <-> county rows for search, from the Census file or the
      state's plan, as SQL that replaces the state's rows. Printed, or with
      --write a new migration VNN__NAME.sql (review it before committing).

  scripts/election-cycle/cycle.py content XX ... [--cycle 2026]
      build-state.py: research JSON -> content files, with the cycle's year.

  scripts/election-cycle/cycle.py load local|staging|prod XX ... [--cycle 2026] [--publish]
      load-state.bash: creates the states' polls as drafts (existing ones are
      skipped); --publish then publishes them.

The geometry steps (maps, plan districts) run in a python:3.12-slim
container (shapely, pyshp, pyproj, openpyxl), so Docker must be running.
Exit code 1 when something is missing or fails, so it can gate a script.
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
FIPS = dict(AL='01', AK='02', AZ='04', AR='05', CA='06', CO='08', CT='09', DE='10', FL='12', GA='13', HI='15',
            ID='16', IL='17', IN='18', IA='19', KS='20', KY='21', LA='22', ME='23', MD='24', MA='25', MI='26',
            MN='27', MS='28', MO='29', MT='30', NE='31', NV='32', NH='33', NJ='34', NM='35', NY='36', NC='37',
            ND='38', OH='39', OK='40', OR='41', PA='42', RI='44', SC='45', SD='46', TN='47', TX='48', UT='49',
            VT='50', VA='51', WA='53', WV='54', WI='55', WY='56')


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


# ---------- fetch / maps / districts / content / load ----------

import subprocess


def dl_dir(cyc):
    d = os.path.join(ROOT, 'tmp', 'election-cycle', str(cyc['year']))
    os.makedirs(d, exist_ok=True)
    return d


def dl(cyc, name):
    """A downloaded file's path (repo-relative), or exit telling you to fetch it."""
    path = os.path.join(dl_dir(cyc), name)
    if not os.path.exists(path):
        sys.exit(f'Missing {os.path.relpath(path, ROOT)}: run `cycle.py fetch --cycle {cyc["year"]}` first.')
    return os.path.relpath(path, ROOT)


def fetch(args):
    cyc = load_cycle(args.cycle)
    for name, url in cyc['downloads'].items():
        path = os.path.join(dl_dir(cyc), name)
        if os.path.exists(path):
            print(f'· {name} already there'); continue
        print(f'↓ {name} ← {url}')
        req = urllib.request.Request(url, headers={'User-Agent': 'ballotbox-cycle-fetch'})
        with urllib.request.urlopen(req, timeout=600) as r, open(path + '.part', 'wb') as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        os.replace(path + '.part', path)
    print(f'In {os.path.relpath(dl_dir(cyc), ROOT)}. Official plan files: download them yourself (see each state\'s planFiles).')
    return 0


def in_container(script_and_args, network=False):
    """Runs a repo script in python:3.12-slim with the geometry libraries."""
    cmd = ['docker', 'run', '--rm', '-v', 'pipcache:/root/.cache/pip', '-v', f'{ROOT}:/r', '-w', '/r']
    if network:
        cmd += ['--network', 'host']
    inner = 'pip install -q shapely pyshp pyproj openpyxl 2>/dev/null; python -I -B -W ignore ' + ' '.join(
        "'" + a.replace("'", "'\\''") + "'" for a in script_and_args)
    return subprocess.run(cmd + ['python:3.12-slim', 'bash', '-c', inner], capture_output=True, text=True)


def maps(args):
    cyc = load_cycle(args.cycle)
    bad = 0
    for st in chosen(cyc, args.states):
        info, seats = cyc['states'][st], cyc['seats'][st]
        out = f'frontend/public/maps/{st}.json'
        lines = info['lines']
        if lines == 'grid':
            a = ['scripts/maps/build-state-map.py', st, '--grid', str(seats), out]
        else:
            a = ['scripts/maps/build-state-map.py', st, FIPS[st], dl(cyc, 'counties.json'), dl(cyc, 'cd.zip'), out]
            if info.get('excludeCounties'):
                a += ['--exclude-counties', ','.join(info['excludeCounties'])]
            if lines == 'plan':
                pf = info.get('planFiles') or {}
                if 'districts' in pf:
                    a += ['--districts', pf['districts'], '--field', pf['field']]
                elif 'baf' in pf:
                    a += ['--baf', pf['baf'], '--blocks', pf['blocks']]
                else:
                    print(f'✗ {st}: lines "plan" but no planFiles in the cycle file'); bad = 1; continue
                for f in pf.values():
                    if f.endswith(('.zip', '.xlsx', '.csv', '.txt')) and not os.path.exists(os.path.join(ROOT, f)):
                        print(f'✗ {st}: missing plan file {f}'); bad = 1; break
                else:
                    a += ['--source', info.get('source', '')]
                if bad: continue
        r = in_container(a)
        if r.returncode:
            print(f'✗ {st}: {(r.stderr or r.stdout).strip().splitlines()[-1:]}'); bad = 1
        else:
            print(f'✓ {st}: {out} ({lines})')
    return bad


def district_rows(cyc, st):
    """(plan label, VALUES rows text) for one state, or exit on trouble."""
    info = cyc['states'][st]
    if cyc['seats'][st] == 1:
        return None
    if info['lines'] == 'census':
        r = subprocess.run([sys.executable, '-I', 'scripts/maps/district-counties.py', dl(cyc, 'county-district.txt'), st],
                           cwd=ROOT, capture_output=True, text=True)
    elif info['lines'] == 'plan':
        pf = info.get('planFiles') or {}
        a = ['scripts/maps/plan-district-counties.py', st, FIPS[st], dl(cyc, 'tl_2020_us_county.zip')]
        a += ['--districts', pf['districts'], '--field', pf['field']] if 'districts' in pf else ['--baf', pf['baf'], '--blocks', pf['blocks']]
        r = in_container(a)
        for line in r.stderr.splitlines():
            if line.startswith('review:') or line.startswith(st + ':'):
                print(f'  {line}', file=sys.stderr)
    else:
        print(f'· {st}: lines "{info["lines"]}": no district rows until its plan is found', file=sys.stderr)
        return None
    if r.returncode or not r.stdout.strip():
        sys.exit(f'✗ {st}: {(r.stderr or "no rows").strip().splitlines()[-1]}')
    return info.get('plan', 'CD' + str(cyc['congress'])), r.stdout.rstrip()


def districts(args):
    cyc = load_cycle(args.cycle)
    parts = [f"-- District <-> county rows for search (V46), generated by scripts/election-cycle/cycle.py districts\n"
             f"-- for the {cyc['year']} cycle. Each state's old rows are replaced.\n"]
    for st in chosen(cyc, args.states):
        got = district_rows(cyc, st)
        if not got:
            continue
        label, values = got
        parts.append(f"""-- {st} ({label}{': ' + cyc['states'][st].get('source', '') if cyc['states'][st].get('source') else ''})
DELETE FROM district_counties WHERE state_id = (SELECT id FROM states WHERE initial = '{st}');
INSERT INTO district_counties (plan, state_id, district, county_id, whole)
SELECT '{label}', s.id, v.district, c.id, v.whole
FROM (VALUES
{values}
) AS v(st, county, district, whole)
JOIN states s ON s.initial = v.st
JOIN counties c ON c.state_id = s.id AND c.name = v.county;
""")
        print(f'✓ {st}: {values.count(chr(10)) + 1} rows ({label})', file=sys.stderr)
    sql = '\n'.join(parts)
    if not args.write:
        print(sql); return 0
    mig = os.path.join(ROOT, 'backend/src/main/resources/db/migration')
    nums = [int(m.group(1)) for f in os.listdir(mig) if (m := re.match(r'V(\d+)__', f))]
    name = re.sub(r'[^a-z0-9_]+', '_', args.write.lower()).strip('_')
    path = os.path.join(mig, f'V{max(nums) + 1}__{name}.sql')
    open(path, 'w').write(sql)
    print(f'Wrote {os.path.relpath(path, ROOT)}: dry-run it on local inside BEGIN/ROLLBACK and check every row matched a county.', file=sys.stderr)
    return 0


def content(args):
    cyc = load_cycle(args.cycle)
    states = chosen(cyc, args.states)
    return subprocess.run([sys.executable, 'scripts/launch-content/build-state.py', *states, '--cycle', str(cyc['year'])],
                          cwd=ROOT).returncode


def load(args):
    cyc = load_cycle(args.cycle)
    a = ['bash', 'scripts/launch-content/load-state.bash', args.env, *chosen(cyc, args.states), '--cycle', str(cyc['year'])]
    if args.publish:
        a.append('--publish')
    return subprocess.run(a, cwd=ROOT).returncode


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
    f = sub.add_parser('fetch', help='download the Census files into tmp/election-cycle/<year>/')
    f.add_argument('--cycle', default='2026')
    for name, hlp in (('maps', 'rebuild states\' district maps'), ('content', 'build states\' content files')):
        x = sub.add_parser(name, help=hlp)
        x.add_argument('states', nargs='*'); x.add_argument('--cycle', default='2026')
    d = sub.add_parser('districts', help='district <-> county rows (SQL) for states')
    d.add_argument('states', nargs='*'); d.add_argument('--cycle', default='2026')
    d.add_argument('--write', metavar='NAME', help='write a new migration VNN__NAME.sql instead of printing')
    lo = sub.add_parser('load', help='create (and with --publish publish) states\' polls in an environment')
    lo.add_argument('env', choices=['local', 'staging', 'prod'])
    lo.add_argument('states', nargs='+'); lo.add_argument('--cycle', default='2026')
    lo.add_argument('--publish', action='store_true')
    args = ap.parse_args()
    sys.exit({'status': status, 'check': check, 'fetch': fetch, 'maps': maps, 'districts': districts,
              'content': content, 'load': load}[args.cmd](args))


if __name__ == '__main__':
    main()
