#!/usr/bin/env python3
"""
plan-district-counties.py: district ↔ county rows from a state's OFFICIAL plan
(2026-11-20), for states that redrew after the Census relationship file was
made (district-counties.py covers the rest). Same output: SQL VALUES rows
for `district_counties` (V46): state, county name, district, whole.

Two kinds of plan, like build-state-map.py:

  Shapes (shapefile .zip, any projection, read from its .prj):
    plan-district-counties.py XX SS tl_2020_us_county.zip --districts PLAN.zip --field DISTRICT

  A block assignment file (each 2020 census block's district; .xlsx/.csv/.txt):
    plan-district-counties.py XX SS tl_2020_us_county.zip --baf PLAN --blocks tl_2020_SS_tabblock20.zip

  XX = state code, SS = state FIPS.
  tl_2020_us_county.zip: https://www2.census.gov/geo/tiger/TIGER2020/COUNTY/tl_2020_us_county.zip
  (full-detail 2020 lines, the ones the plans are drawn on, so shared borders
  coincide; a generalized county file would leave slivers on every border).

Shapes: a county is in a district when the overlap is at least --min-share of
the county's area (default 0.05%) or --min-km2 square km (default 0.5).
Smaller overlaps are dropped as slivers; any overlap between 0.001% and 1%
is listed on stderr for review either way.
Blocks: exact; water-only blocks (no land) are ignored.

Needs shapely, pyshp, pyproj (and openpyxl for .xlsx), e.g. in python:3.12-slim.
"""
import argparse
import csv
import io
import sys
import zipfile
from collections import defaultdict

# Independent cities keep " city", as in our counties table (V8): "Richmond city"
# (VA) is not Richmond County; likewise Baltimore city, St. Louis city.
SUFFIXES = (' County', ' Parish', ' Borough', ' Census Area', ' Municipality', ' City and Borough')


def county_name(namelsad):
    # The same rule as district-counties.py and the V8 county seed.
    for s in SUFFIXES:
        if namelsad.endswith(s):
            return namelsad[: -len(s)]
    return namelsad


def shp_reader(zip_path, prefix=None):
    import shapefile
    z = zipfile.ZipFile(zip_path)
    names = [n for n in z.namelist() if not n.startswith('__MACOSX')]
    base = next(n[:-4] for n in names if n.lower().endswith('.shp') and (prefix is None or prefix in n))
    prj = next((z.read(n).decode('utf-8', 'replace') for n in names if n.lower() == base.lower() + '.prj'), None)
    r = shapefile.Reader(shp=io.BytesIO(z.read(base + '.shp')), shx=io.BytesIO(z.read(base + '.shx')),
                         dbf=io.BytesIO(z.read(base + '.dbf')))
    return r, prj


def counties_of(state_fips, county_zip):
    """{geoid: (name, shape in NAD83 lon/lat)}"""
    from shapely.geometry import shape
    r, _ = shp_reader(county_zip)
    out = {}
    for sr in r.iterShapeRecords():
        rec = sr.record.as_dict()
        if rec['STATEFP'] == state_fips:
            out[rec['GEOID']] = (county_name(rec['NAMELSAD']), shape(sr.shape.__geo_interface__))
    return out


def from_shapes(args, counties):
    from pyproj import CRS, Transformer
    from shapely.geometry import shape
    from shapely.ops import transform
    albers = CRS.from_epsg(5070)   # equal-area, so overlap areas compare fairly
    to_albers_nad83 = Transformer.from_crs(CRS.from_epsg(4269), albers, always_xy=True).transform
    plan, prj = shp_reader(args.districts)
    plan_crs = CRS.from_wkt(prj) if prj else CRS.from_epsg(4269)
    to_albers_plan = Transformer.from_crs(plan_crs, albers, always_xy=True).transform
    fields = [f[0] for f in plan.fields[1:]]
    if args.field not in fields:
        sys.exit(f'No field {args.field!r}; the plan has {fields}')
    districts = defaultdict(list)
    for sr in plan.iterShapeRecords():
        d = int(str(sr.record.as_dict()[args.field]).strip())
        districts[d].append(transform(to_albers_plan, shape(sr.shape.__geo_interface__)).buffer(0))
    from shapely.ops import unary_union
    dshape = {d: unary_union(g) for d, g in districts.items()}
    parts = defaultdict(set)
    for geoid, (name, cshape) in sorted(counties.items()):
        c = transform(to_albers_nad83, cshape).buffer(0)
        for d, ds in dshape.items():
            if not c.intersects(ds):
                continue
            area = c.intersection(ds).area
            share = area / c.area
            if 0.00001 <= share <= 0.01:
                print(f'review: {name} ∩ district {d}: {share * 100:.3f}% of the county, {area / 1e6:.2f} km²',
                      file=sys.stderr)
            if share >= args.min_share / 100 or area / 1e6 >= args.min_km2:
                parts[name].add(d)
    return parts, len(dshape)


def from_baf(args, counties):
    import shapefile
    land = {}
    z = zipfile.ZipFile(args.blocks)
    dbf = next(n for n in z.namelist() if n.lower().endswith('.dbf'))
    for rec in shapefile.Reader(dbf=io.BytesIO(z.read(dbf))).iterRecords(fields=['GEOID20', 'ALAND20']):
        land[rec[0]] = rec[1]
    rows = []
    if args.baf.lower().endswith('.xlsx') or args.baf.lower().endswith('.zip'):
        import openpyxl
        data = args.baf
        if args.baf.lower().endswith('.zip'):
            zz = zipfile.ZipFile(args.baf)
            data = io.BytesIO(zz.read(next(n for n in zz.namelist() if n.lower().endswith(('.xlsx', '.csv', '.txt')))))
        ws = openpyxl.load_workbook(data, read_only=True).active
        rows = [(str(a), b) for a, b, *_ in ws.iter_rows(values_only=True)]
    else:
        with open(args.baf, newline='') as f:
            sample = f.read(4096); f.seek(0)
            rows = [(r[0], r[1]) for r in csv.reader(f, delimiter='|' if '|' in sample else ',')]
    parts = defaultdict(set)
    seen = set()
    for block, d in rows:
        block = block.strip()
        if not block.isdigit() or len(block) != 15:
            continue   # the header row
        if land.get(block, 1) == 0:
            continue   # water only
        geoid = block[:5]
        if geoid not in counties:
            continue
        d = int(str(d).strip())
        seen.add(d)
        parts[counties[geoid][0]].add(d)
    return parts, len(seen)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('state'); ap.add_argument('fips'); ap.add_argument('county_zip')
    ap.add_argument('--districts'); ap.add_argument('--field', default='DISTRICT')
    ap.add_argument('--baf'); ap.add_argument('--blocks')
    ap.add_argument('--min-share', type=float, default=0.05, help='percent of the county (default 0.05)')
    ap.add_argument('--min-km2', type=float, default=0.5)
    args = ap.parse_args()
    counties = counties_of(args.fips, args.county_zip)
    if not counties:
        sys.exit(f'No counties for FIPS {args.fips}')
    if args.baf:
        if not args.blocks:
            sys.exit('--baf needs --blocks (the state\'s tl_2020_SS_tabblock20.zip, for land areas)')
        parts, n = from_baf(args, counties)
    elif args.districts:
        parts, n = from_shapes(args, counties)
    else:
        sys.exit('Give --districts PLAN.zip or --baf PLAN')
    missing = sorted(set(name for name, _ in counties.values()) - set(parts))
    print(f'{args.state}: {n} districts, {len(parts)} of {len(counties)} counties'
          + (f'; NOT in any district: {", ".join(missing)}' if missing else ''), file=sys.stderr)
    rows = []
    for name, ds in sorted(parts.items()):
        esc = name.replace("'", "''")
        for d in sorted(ds):
            rows.append(f"    ('{args.state}', '{esc}', {d}, {'TRUE' if len(ds) == 1 else 'FALSE'})")
    print(',\n'.join(rows))


if __name__ == '__main__':
    main()
