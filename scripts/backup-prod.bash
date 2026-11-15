#!/usr/bin/env bash
#
# backup-prod.bash — a daily backup of prod's database that we keep ourselves,
# on top of Neon's restore window (decided 2026-10-21).
#
# Takes ONE consistent snapshot (a single read-only transaction) as the
# read-only role `claude`, and writes assets/data-backups/prod-<UTC time>.tar.gz:
#   schema.sql      the table definitions (pg_dump --schema-only, schema public)
#   <table>.csv     every table's rows, with a header line
#   manifest.txt    when, schema version, and each table's row count
# Then deletes backups older than --keep-days (never the newest one).
#
# Backups hold personal data: the folder is git-ignored and files are readable
# only by you. Prod is only read.
#
# Needs: postgresql-client-18 on the host, and
# .devcontainer/neon-readonly.secrets.env (NEON_RO_PASSWORD).
# The clients run on the host, not in Docker: Neon drops connections through
# Proton VPN, and only host processes can bypass it (split tunnel, include mode).
#
# Usage:
#   ./scripts/backup-prod.bash                  # back up now, keep 14 days
#   ./scripts/backup-prod.bash --keep-days 30
# Check a backup restores: ./scripts/restore-backup-check.bash [file]
# Run daily: ./scripts/install-backup-timer.bash (on the host, once)

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT/assets/data-backups"
KEEP_DAYS=14
HOST=ep-shiny-base-ax9uc7iz.c-4.us-east-2.aws.neon.tech
CONN="host=$HOST dbname=neondb user=claude sslmode=require connect_timeout=20"
PG_BIN=/usr/lib/postgresql/18/bin   # pg_dump must be >= the server (Neon: 18)
while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-days) KEEP_DAYS="$2"; shift 2 ;;
    -h|--help) sed -n '2,27p' "$0"; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

# No `tee`: journald can't tie a line from a short-lived child process to the
# unit, so `journalctl --user -u pollsystem-backup` silently dropped some lines.
log() { local line; line="$(date -u +%FT%TZ) $*"; echo "$line"; echo "$line" >> "$OUT_DIR/backup.log"; }
fail() { log "FAILED: $*"; exit 1; }

umask 077
mkdir -p "$OUT_DIR" && chmod 700 "$OUT_DIR"
[[ -f "$ROOT/.devcontainer/neon-readonly.secrets.env" ]] || fail "missing .devcontainer/neon-readonly.secrets.env"
set -a; . "$ROOT/.devcontainer/neon-readonly.secrets.env"; set +a

stamp=$(date -u +%Y%m%dT%H%M%SZ)
work=$(mktemp -d "$OUT_DIR/.work-$stamp-XXXX")

trap 'rm -rf "$work"' EXIT

[[ -x "$PG_BIN/pg_dump" && -x "$PG_BIN/psql" ]] \
  || fail "no PostgreSQL 18 client in $PG_BIN (install postgresql-client-18 from apt.postgresql.org)"

pg() {  # run a PostgreSQL 18 client on the host; psql -X ignores ~/.psqlrc
  local cmd=$1; shift
  [[ $cmd == psql ]] && set -- -X "$@"
  PGPASSWORD="$NEON_RO_PASSWORD" "$PG_BIN/$cmd" "$@"
}

# Prod is unreachable through Proton VPN (diagnosed 2026-11-14: "server closed
# the connection unexpectedly" through the VPN, fine without it). With split
# tunnelling in include mode this script bypasses it; if a failure happens
# while all traffic goes through the VPN, say so, so the alert names the cause.
vpn_note() {
  local dev
  dev=$(ip route show default 2>/dev/null | awk 'NR==1 { for (i = 1; i < NF; i++) if ($i == "dev") print $(i+1) }')
  case "$dev" in
    pvpn*|proton*|wg*|tun*) echo " (Proton VPN is on: default route via $dev. Neon drops connections through it; check Proton's split tunnelling is on (include mode), then rerun: systemctl --user start pollsystem-backup)" ;;
  esac
}
fail_net() { fail "$*$(vpn_note)"; }

# Connection failures are sometimes transient, so try once more after 30 s.
retry() {
  "$@" && return 0
  log "attempt failed, retrying in 30 s" >&2  # stderr: retry runs inside $(...)
  sleep 30
  "$@"
}

retry pg pg_dump "$CONN" --schema-only --schema=public --no-owner --no-privileges -f "$work/schema.sql" \
  || fail_net "schema export failed"

tables=$(retry pg psql "$CONN" -tA -c "select table_name from information_schema.tables
  where table_schema='public' and table_type='BASE TABLE' order by 1") || fail_net "couldn't list tables"
[[ -n "$tables" ]] || fail "no tables found"

# One transaction: every table and every count from the same moment.
{
  echo '\set ON_ERROR_STOP on'
  echo 'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;'
  echo "\\o '$work/manifest.txt'"
  echo "select 'taken_at ' || to_char(now() at time zone 'utc', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"');"
  echo "select 'schema_version ' || max(version::int) from flyway_schema_history where success;"
  for t in $tables; do
    echo "select 'rows $t ' || count(*) from public.\"$t\";"
  done
  echo '\o'
  for t in $tables; do
    echo "\\copy public.\"$t\" to '$work/$t.csv' with (format csv, header)"
  done
  echo 'COMMIT;'
} > "$work/backup.sql"
retry pg psql "$CONN" -q -tA -f "$work/backup.sql" > /dev/null || fail_net "table export failed"

n=$(grep -c '^rows ' "$work/manifest.txt")
[[ "$n" -eq $(wc -w <<<"$tables") ]] || fail "manifest lists $n tables, expected $(wc -w <<<"$tables")"
rm "$work/backup.sql"

file="$OUT_DIR/prod-$stamp.tar.gz"
tar -czf "$file" -C "$work" . || fail "couldn't write $file"
log "OK $(basename "$file") $(du -h "$file" | cut -f1) $n tables, $(grep schema_version "$work/manifest.txt")"

# Rotation: drop backups older than KEEP_DAYS, but always keep the newest.
newest=$(ls -1t "$OUT_DIR"/prod-*.tar.gz 2>/dev/null | head -1)
find "$OUT_DIR" -maxdepth 1 -name 'prod-*.tar.gz' -mtime +"$KEEP_DAYS" ! -path "$newest" -print -delete \
  | while read -r old; do log "deleted old backup $(basename "$old")"; done
