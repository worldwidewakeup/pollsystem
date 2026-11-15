#!/usr/bin/env bash
#
# install-pg-client-18.sh — install the PostgreSQL 18 CLIENT tools (pg_dump,
# psql) from PostgreSQL's official apt repository, so the pollsystem backup
# can run them on the host instead of in Docker (Docker traffic can't bypass
# Proton VPN's split tunnel; host user processes can).
#
# Installs no database server. Run once, as root:
#   pkexec ./scripts/install-pg-client-18.bash
#
# Safe to re-run: every step is idempotent.

set -euo pipefail

KEY_URL=https://www.postgresql.org/media/keys/ACCC4CF8.asc
KEY_FPR=B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8   # PostgreSQL Debian Repository
KEY=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
LIST=/etc/apt/sources.list.d/pgdg.list

[[ $EUID -eq 0 ]] || { echo "run as root: pkexec $0" >&2; exit 1; }
. /etc/os-release
echo "== $PRETTY_NAME ($VERSION_CODENAME)"

echo "== fetching the repository signing key"
install -d -m 755 "$(dirname "$KEY")"
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
curl -fsS --max-time 30 -o "$tmp" "$KEY_URL"

# Refuse a key that isn't the one PostgreSQL publishes.
got=$(gpg --show-keys --with-colons "$tmp" 2>/dev/null | awk -F: '$1=="fpr" {print $10; exit}')
if [[ "$got" != "$KEY_FPR" ]]; then
  echo "FAILED: key fingerprint is '$got', expected $KEY_FPR. Nothing installed." >&2
  exit 1
fi
install -m 644 "$tmp" "$KEY"
echo "   key OK ($KEY_FPR)"

echo "== adding the repository"
echo "deb [signed-by=$KEY] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" > "$LIST"
chmod 644 "$LIST"

echo "== installing postgresql-client-18"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends postgresql-client-18

echo "== check"
/usr/lib/postgresql/18/bin/pg_dump --version
/usr/lib/postgresql/18/bin/psql --version
echo "INSTALL OK"
