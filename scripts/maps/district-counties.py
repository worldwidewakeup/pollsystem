#!/usr/bin/env python3
"""Congressional district ↔ county rows for a migration (2026-11-20).

Reads the Census Bureau's county-to-district relationship file for the 119th
Congress (the maps in use for the 2026 elections in most states) and prints
SQL VALUES rows for the `district_counties` table (V46): state initial,
county name (as in our `counties` table, without " County"/" Parish"/...),
district number, and whether the county lies wholly in that district.

Search uses these rows to find a state's district ballots ("2026 Midterm
Washington District 2") from a county. A district's poll keeps its statewide
area: these rows only help search.

    curl -O https://www2.census.gov/geo/docs/maps-data/data/rel2020/cd-sld/tab20_cd11920_county20_natl.txt
    python3 -I scripts/maps/district-counties.py tab20_cd11920_county20_natl.txt WA [OR ID ...]

A county part with no land (water only) is left out. States that redrew their
maps after the 119th Congress began (TX, CA, FL, NC, OH, UT, AL, LA, ...) need
their new plan instead; this file describes the old one.
"""
import csv
import sys
from collections import defaultdict

FIPS = {
    '01': 'AL', '02': 'AK', '04': 'AZ', '05': 'AR', '06': 'CA', '08': 'CO', '09': 'CT', '10': 'DE',
    '11': 'DC', '12': 'FL', '13': 'GA', '15': 'HI', '16': 'ID', '17': 'IL', '18': 'IN', '19': 'IA',
    '20': 'KS', '21': 'KY', '22': 'LA', '23': 'ME', '24': 'MD', '25': 'MA', '26': 'MI', '27': 'MN',
    '28': 'MS', '29': 'MO', '30': 'MT', '31': 'NE', '32': 'NV', '33': 'NH', '34': 'NJ', '35': 'NM',
    '36': 'NY', '37': 'NC', '38': 'ND', '39': 'OH', '40': 'OK', '41': 'OR', '42': 'PA', '44': 'RI',
    '45': 'SC', '46': 'SD', '47': 'TN', '48': 'TX', '49': 'UT', '50': 'VT', '51': 'VA', '53': 'WA',
    '54': 'WV', '55': 'WI', '56': 'WY',
}
SUFFIXES = (' County', ' Parish', ' Borough', ' Census Area', ' Municipality', ' City and Borough', ' city')


def county_name(namelsad: str) -> str:
    for s in SUFFIXES:
        if namelsad.endswith(s):
            return namelsad[: -len(s)]
    return namelsad


def main() -> None:
    path, wanted = sys.argv[1], set(sys.argv[2:])
    parts = defaultdict(set)   # (state, county) -> {district}
    with open(path, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f, delimiter='|'):
            cd, county = r['GEOID_CD119_20'], r['GEOID_COUNTY_20']
            st = FIPS.get(cd[:2])
            if st not in wanted or county[:2] != cd[:2] or int(r['AREALAND_PART'] or 0) == 0:
                continue
            district = int(cd[2:])
            # At-large states are district 00 in the file; their ballot is the state's own.
            parts[(st, county_name(r['NAMELSAD_COUNTY_20']))].add(max(district, 1))
    rows = []
    for (st, county), ds in sorted(parts.items()):
        for d in sorted(ds):
            esc = county.replace("'", "''")
            rows.append(f"    ('{st}', '{esc}', {d}, {'TRUE' if len(ds) == 1 else 'FALSE'})")
    print(',\n'.join(rows))


if __name__ == '__main__':
    main()
