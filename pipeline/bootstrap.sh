#!/usr/bin/env bash
# Rebuild the data of the atlas from a fresh clone, in the order the builders need (each reads what the one before
# wrote), then run the checks. From the repository root:
#
#   bash pipeline/bootstrap.sh              downloads the scheduled sources (a few hundred MB into raw/), rebuilds, checks
#   bash pipeline/bootstrap.sh --dry-run    prints the steps only
#   bash pipeline/bootstrap.sh --with-baci  also downloads CEPII BACI (2.4 GB) and rebuilds the customs cache from it
#
# Versions: Python 3.12 (the workflows; 3.11 or later works, 3.13 is used locally), Node 22. The Python packages are
# the exact versions of pipeline/requirements-lock.txt, installed in .venv; the site's in web/package-lock.json.
# Without --with-baci the trade engine is rebuilt from the committed customs cache (pipeline/cache/baci_flows.csv.gz).
# Hand-curated files (infrastructure, companies, events, route definitions) are not rebuilt: they are edited by hand.
# A step that fails stops the script; the update scripts themselves never fail on a source that is down, they record
# it in data/_status/updates.json and keep the previous files (read that file when a figure did not change).
set -euo pipefail
cd "$(dirname "$0")/.."

dry=false
baci=--baci-check-only
for a in "$@"; do
  case "$a" in
    --dry-run) dry=true ;;
    --with-baci) baci="" ;;
    *) echo "unknown option $a" >&2; exit 2 ;;
  esac
done
PY=.venv/bin/python
step() {
  echo "== $1"
  shift
  if [ "$dry" = true ]; then echo "   $*"; else "$@"; fi
}

step "versions" python3 --version
step "versions" node --version
[ -x "$PY" ] || step "Python environment" python3 -m venv .venv
step "Python packages" "$PY" -m pip install -q -r pipeline/requirements-lock.txt
step "site packages" npm ci --prefix web
# 1. weekly sources
step "prices (World Bank, EIA, freight indicators)" "$PY" pipeline/prices/fetch_prices.py
step "PortWatch chokepoint transits (the whole table on a fresh clone)" "$PY" pipeline/freight/fetch_portwatch.py
# 2. yearly sources, then what depends on them when they changed
step "yearly sources and their rebuilds" "$PY" pipeline/annual/update_annual.py $baci
# 3. the trade engine, always, from the committed customs cache
step "borders and coasts" "$PY" pipeline/geo/adjacency.py
step "lanes (about 15 minutes with cold route caches)" "$PY" pipeline/freight/build_lanes.py
step "routes, chokepoints, vessel classes, port index" "$PY" pipeline/freight/build_freight.py
step "largest vessel class of each port with published limits" "$PY" pipeline/infrastructure/port_limits.py
step "World Port Index entries of the ports (from the tracked cache)" "$PY" pipeline/infrastructure/wpi_limits.py
step "alert banners" "$PY" pipeline/freight/build_alerts.py
step "freight market digest (from the weekly chokepoint series, no network)" "$PY" pipeline/freight/build_market_now.py
step "companies files from the hand-curated lists" "$PY" pipeline/companies/build_companies.py
step "commodity pages" "$PY" pipeline/commodities/build_commodities.py
step "coverage of the commodity pages" "$PY" pipeline/commodities/build_coverage.py
step "country profiles" "$PY" pipeline/commodities/build_profiles.py
step "what changed digest" "$PY" pipeline/common/changes.py
# 4. generated documentation
step "sources table of DATA_SOURCES.md" "$PY" pipeline/common/sources_table.py
step "generated lists of NOTICE.md" "$PY" pipeline/common/notice_lists.py
# 5. checks
step "data validators" node web/scripts/validate-data.mjs
step "freight validator" node web/scripts/validate-freight.mjs
step "infrastructure validator" node web/scripts/validate-infra.mjs
step "node tests" npm test --prefix web
step "type check" npm run typecheck --prefix web
step "Python unit suite" "$PY" -m unittest discover -s pipeline/tests -p "test_*.py"
echo "Done. Review git diff, then commit data/ and pipeline/cache/."
