#!/usr/bin/env bash
#
# rehearse.bash: rehearse a new election cycle on LOCAL, step by step, and put
# local back exactly as it was afterwards (2026-11-22; runbook section 6).
#
#   scripts/election-cycle/rehearse.bash [--year 2028] [--states "ID TX WY"] [--redraw "TX"] [--yes] [--no-pause]
#
#   --year      the made-up cycle's year (default 2028: a presidential year,
#               so a President race is added; an even non-presidential year
#               rehearses a midterm)
#   --states    states to rehearse (default "ID TX WY": unchanged lines, a
#               redraw, one seat); each needs a research JSON
#   --redraw    states switched from their 2026 official plan to the Census
#               lines, as a realistic redraw (default "TX")
#   --yes       run every step without asking (for a test run)
#   --no-pause  don't stop to look in the browser before restoring
#
# Before each step it shows the command: Enter runs it, s skips it, q quits.
# Local is snapshotted first, and restored however the script ends (done, q,
# an error, Ctrl-C): the backend is stopped, the snapshot restored, and every
# rehearsal file deleted, then the counts are compared with the snapshot's.
#
# Runs on the host or in the Dev Container (it reaches the local backend
# through a container on the host network when it has to).

set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

YEAR=2028; STATES="ID TX WY"; REDRAW="TX"; YES=false; PAUSE=true
while (($#)); do
  case "$1" in
    --year) YEAR="$2"; shift ;;
    --states) STATES="$2"; shift ;;
    --redraw) REDRAW="$2"; shift ;;
    --yes) YES=true ;;
    --no-pause) PAUSE=false ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

API=http://localhost:8080
SITE=http://localhost:3000
WORK="tmp/rehearsal/$YEAR"
RESEARCH="$WORK/research"
DUMP_IN_DB=/tmp/rehearsal-before.dump
COUNTS_SQL="select 'elections', count(*)::text from elections union all select 'measures', count(*)::text from ballot_measures union all select 'candidates', count(*)::text from candidates union all select 'events', count(*)::text from poll_events union all select 'district rows', count(*)::text from district_counties union all select 'cycle', election_year||' '||election_kind from app_flags"
MIGRATIONS=backend/src/main/resources/db/migration

bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
psql_q() { docker exec -i pollsystem-db psql -X -U polladmin -d pollsystem -v ON_ERROR_STOP=1 "$@"; }

# The local backend: directly, or from a container on the host network (Dev Container).
if curl -s -o /dev/null -m 3 "$API/api/election-cycle"; then
  api_curl() { curl -s "$@"; }
  py_host() { python3 "$@"; }
else
  api_curl() { docker run --rm --network host curlimages/curl:8.10.1 -s "$@"; }
  py_host() { docker run --rm --network host -v "$ROOT":/r -w /r python:3.12-slim python3 "$@"; }
fi

# step "title" command...: show it, ask, run it. Returns the command's status.
step() {
  local title="$1"; shift
  bold "== $title"
  printf '   $ %s\n' "$*"
  if ! $YES; then
    local a
    read -r -p "   [Enter] run · s skip · q quit (restores local): " a </dev/tty
    case "$a" in
      q|Q) exit 0 ;;
      s|S) echo "   skipped"; return 0 ;;
    esac
  fi
  "$@"; local rc=$?
  ((rc)) && echo "   ✗ exited $rc"
  return $rc
}

# ---------- preflight (nothing changed yet) ----------
bold "Rehearsal: $YEAR, states $STATES, redrawn: ${REDRAW:-none}"
docker ps --format '{{.Names}}' | grep -qx pollsystem-db || { echo "pollsystem-db isn't running" >&2; exit 1; }
api_curl -o /dev/null -m 10 "$API/api/election-cycle" || { echo "the local backend isn't answering at $API" >&2; exit 1; }
[[ -f .devcontainer/local-content-super-token.secrets.env ]] || { echo "missing .devcontainer/local-content-super-token.secrets.env (see load-state.bash)" >&2; exit 1; }
for f in "docs/launch-content/$YEAR-cycle.json" "frontend/public/maps/$YEAR"; do
  [[ -e "$f" ]] && { echo "$f already exists: a real $YEAR cycle may be in progress; not rehearsing over it" >&2; exit 1; }
done
ls scripts/launch-content/*-"$YEAR"-*.json >/dev/null 2>&1 && { echo "scripts/launch-content has $YEAR content files already; not rehearsing over them" >&2; exit 1; }

# ---------- snapshot, and the restore that always runs ----------
bold "== Snapshot local (always, before anything changes)"
mkdir -p "$WORK"
psql_q -tA -c "$COUNTS_SQL" > "$WORK/before-counts.txt" || exit 1
docker exec pollsystem-db pg_dump -U polladmin -d pollsystem -Fc -f "$DUMP_IN_DB" || { echo "snapshot failed: nothing was changed" >&2; exit 1; }
docker cp "pollsystem-db:$DUMP_IN_DB" "$WORK/local-before.dump" >/dev/null
echo "   saved $WORK/local-before.dump"; sed 's/^/   /' "$WORK/before-counts.txt"

restore() {
  local rc=$?
  trap - EXIT INT TERM
  bold "== Restoring local"
  local was_running=false
  if docker ps --format '{{.Names}}' | grep -qx pollsystem-backend; then was_running=true; docker stop pollsystem-backend >/dev/null; fi
  docker exec pollsystem-db pg_restore -U polladmin -d pollsystem --clean --if-exists --single-transaction "$DUMP_IN_DB" \
    || echo "   ✗ pg_restore reported errors; the snapshot is at $WORK/local-before.dump"
  $was_running && docker start pollsystem-backend >/dev/null
  rm -rf "frontend/public/maps/$YEAR" "docs/launch-content/$YEAR-cycle.json" "tmp/election-cycle/$YEAR" "$RESEARCH"
  rm -f scripts/launch-content/*-"$YEAR"-*.json "$MIGRATIONS"/V*__rehearsal_"$YEAR".sql
  psql_q -tA -c "$COUNTS_SQL" > "$WORK/after-counts.txt"
  if diff -q "$WORK/before-counts.txt" "$WORK/after-counts.txt" >/dev/null; then
    echo "   ✓ local matches the snapshot:"; sed 's/^/     /' "$WORK/after-counts.txt"
    echo "   rehearsal files deleted (the snapshot stays at $WORK/local-before.dump)"
  else
    echo "   ✗ counts differ from the snapshot:"; diff "$WORK/before-counts.txt" "$WORK/after-counts.txt" | sed 's/^/     /'
    rc=1
  fi
  if $was_running; then
    for _ in $(seq 1 40); do api_curl -o /dev/null -m 3 "$API/api/election-cycle" && break; sleep 3; done
  fi
  exit $rc
}
trap restore EXIT
trap 'exit 130' INT TERM

# ---------- the rehearsal ----------
step "Made-up inputs: a $YEAR cycle file and edited research copies" \
  python3 scripts/election-cycle/rehearsal-inputs.py --year "$YEAR" --states $STATES --redraw $REDRAW --research-dir "$RESEARCH" || exit 1

if [[ -d tmp/election-cycle/2026 ]]; then
  step "Reuse 2026's Census downloads (the same files)" \
    bash -c "mkdir -p tmp/election-cycle/$YEAR && cp -n tmp/election-cycle/2026/* tmp/election-cycle/$YEAR/ 2>/dev/null; ls tmp/election-cycle/$YEAR"
fi
# status exits 1 when something's missing, which is what it should show here.
step "What's missing for $YEAR (everything, so far)" bash -c "python3 scripts/election-cycle/cycle.py status --cycle $YEAR $STATES; echo '   (missing items are expected at this point)'"
step "Download anything still missing" python3 scripts/election-cycle/cycle.py fetch --cycle "$YEAR" || exit 1
step "Build the $YEAR maps" python3 scripts/election-cycle/cycle.py maps $STATES --cycle "$YEAR" || exit 1
step "District <-> county rows for $YEAR, as a migration file" \
  python3 scripts/election-cycle/cycle.py districts $STATES --cycle "$YEAR" --write "rehearsal_$YEAR" || exit 1

apply_rows() {
  local f; f=$(ls "$MIGRATIONS"/V*__rehearsal_"$YEAR".sql 2>/dev/null | head -1)
  [[ -n "$f" ]] || { echo "   no rows file (skipped above?)"; return 0; }
  # Straight into local with psql (not Flyway, so the migration history isn't touched), then out of the migrations folder.
  { echo 'BEGIN;'; cat "$f"; echo "SELECT 'rows for $YEAR', count(*) FROM district_counties WHERE election_year = $YEAR;"; echo 'COMMIT;'; } | psql_q -q -tA
  local rc=$?
  mv "$f" "$WORK/"
  return $rc
}
step "Apply the rows to local (psql, not Flyway) and move the file out of the migrations folder" apply_rows || exit 1
step "Content files from the edited research" \
  python3 scripts/election-cycle/cycle.py content $STATES --cycle "$YEAR" --research-dir "$RESEARCH" || exit 1
step "Load the polls into local and publish them" \
  python3 scripts/election-cycle/cycle.py load local $STATES --cycle "$YEAR" --publish || exit 1

switch_cycle() {
  local kind=MIDTERM; ((YEAR % 4 == 0)) && kind=GENERAL
  local date; date=$(python3 -c "import json; print(json.load(open('docs/launch-content/$YEAR-cycle.json'))['date'])")
  local tok; tok=$(api_curl -X POST "$API/api/dev/token?email=demo-super@test.local" | sed 's/.*"token":"\([^"]*\)".*/\1/')
  api_curl -X PUT -H "Authorization: Bearer $tok" -H 'Content-Type: application/json' \
    -d "{\"year\":$YEAR,\"date\":\"$date\",\"kind\":\"$kind\"}" "$API/api/super/flags/election-cycle"; echo
}
step "Switch local's election cycle to $YEAR (as the Super dashboard does)" switch_cycle || exit 1
step "Check local for $YEAR" py_host scripts/election-cycle/cycle.py check local --cycle "$YEAR" $STATES

if $PAUSE && ! $YES; then
  first_redraw="${REDRAW%% *}"; any="${STATES%% *}"; show="${first_redraw:-$any}"
  bold "== Look around before local is restored"
  echo "   $SITE/maps/$show                 the $YEAR map (the current cycle now)"
  echo "   $SITE/maps/$show?year=2026       2026's map, unchanged"
  echo "   $SITE/polls/search               pick a state and a county: each year's district ballots use that year's lines"
  read -r -p "   Press Enter when you're done (local is restored then) " _ </dev/tty
fi
exit 0
