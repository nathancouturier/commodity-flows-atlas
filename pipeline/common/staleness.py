"""
Staleness check of the scheduled sources: a source can stop being updated without ever failing (a workflow that
GitHub disabled, a schedule that stopped, a publisher that keeps serving the same old file). This check reads only
data/_status/updates.json and compares, for each source, the date of its last successful check and the date its data
reach with the cadence the atlas expects. It uses the same rules as the "Data freshness" table of the site
(web/src/lib/status.ts), so that an issue and the table never disagree:

  last successful check   none yet, once the source has failed as many runs as its alert threshold (before that it is retrying),
                          or older than 16 days for a weekly source, 64 days for a monthly one (two runs missed plus a
                          margin), 80 + 64 days for FAOSTAT/WNA (checked every 80 days)
  daily data (EIA spot, PortWatch)   the last day is more than 21 days old
  monthly data (Pink Sheet, and the BLS, Dallas Fed and New York Fed freight indicators)
                                     month M is late once month M+1 should have been published: the 15th of M+2
  USGS MCS edition Y                 late after 31 March of Y+1 (the edition comes out at the end of January)
  CEPII BACI version VYYYYMM         late after 31 March of YYYY+1 with no newer version installed (one version a year,
                                     in January; the refresh is done by hand: docs/UPDATING.md)

    python pipeline/common/staleness.py            prints {"stale": {source: reason}, "fresh": [source, ...]} as JSON

Run weekly by .github/workflows/check-staleness.yml, which opens one "Data stale: <source>" issue per stale source and
closes it when the source is fresh again. Exits 0.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import status  # noqa: E402

WEEKLY = 16
MONTHLY = 64
DAY_LAG = 21
# source -> (kind of its data_to, days without a successful check before it is stale)
TRACKED = {
    "eia-spot": ("day", WEEKLY),
    "portwatch": ("day", WEEKLY),
    # the weekly port series (one file per port): nothing is said until the first load has recorded the source
    "portwatch-port-traffic": ("day", WEEKLY),
    "wb-pink": ("month", WEEKLY),
    # the three freight indicators of the weekly prices job (pipeline/prices/freight_indicators.py), monthly series
    "bls": ("month", WEEKLY),
    "dallasfed": ("month", WEEKLY),
    "nyfed": ("month", WEEKLY),
    "usda-psd": ("none", MONTHLY),
    "usgs-mcs": ("edition", MONTHLY),
    "eia-intl": ("none", MONTHLY),
    # a failed monthly check of the CEPII page already alerts ("Data update failing: baci"); what matters here is the
    # version in use
    "baci": ("version", None),
    "faostat-wna": ("none", 80 + MONTHLY),
}


def _date(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _iso(s):
    try:
        return datetime.strptime(str(s), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def reason(source, entry, now):
    """Why ``source`` is stale (a short sentence), or None when it is fresh."""
    kind, max_age = TRACKED[source]
    checked = _iso(entry.get("last_success")) if entry.get("last_success") else None
    if checked is None and max_age is not None:
        # a source whose first runs failed fewer times than its alert threshold is retrying, not stale (the issue "Data update failing" and
        # the table's "failing" take over at the threshold)
        limit = int(entry.get("alert_after") or status.ALERT_AFTER_SOURCE.get(source, status.ALERT_AFTER))
        if 0 < int(entry.get("consecutive_failures") or 0) < limit:
            return None
        return "no successful check recorded"
    age = (now - checked).days if checked else 0
    if max_age is not None and age > max_age:
        return f"no successful check for {age} days (expected at most {max_age}); last success {entry['last_success']}"
    to = entry.get("data_to")
    if kind == "day" and to and (d := _date(to)) and (now - d).days > DAY_LAG:
        return f"the latest data are of {to}, more than {DAY_LAG} days old"
    if kind == "month" and to and (m := re.fullmatch(r"(\d{4})-(\d{2})", str(to))):
        y, mo = int(m.group(1)), int(m.group(2)) + 2
        y, mo = y + (mo - 1) // 12, (mo - 1) % 12 + 1
        if now > datetime(y, mo, 15, tzinfo=timezone.utc):
            return f"the latest month is {to}; the month after it should have been published by the 15th of {y}-{mo:02d}"
    if kind == "edition" and to and re.fullmatch(r"\d{4}", str(to)) and now > datetime(int(to) + 1, 3, 31, tzinfo=timezone.utc):
        return f"the {to} edition is in use; the {int(to) + 1} edition was due at the end of January {int(to) + 1}"
    if kind == "version":
        v = str((entry.get("state") or {}).get("version") or "")
        if re.fullmatch(r"V\d{6}", v) and now > datetime(int(v[1:5]) + 1, 3, 31, tzinfo=timezone.utc):
            return (f"version {v} is in use; the version of January {int(v[1:5]) + 1} is not installed "
                    "(refresh by hand: docs/UPDATING.md)")
    return None


def check(doc=None, now=None):
    """{"stale": {source: reason}, "fresh": [sources]} for the tracked sources present in the status document."""
    doc = doc if doc is not None else status.load()
    now = now or datetime.now(timezone.utc)
    out = {"stale": {}, "fresh": []}
    for src in TRACKED:
        entry = (doc.get("sources") or {}).get(src)
        if not isinstance(entry, dict):
            continue
        why = reason(src, entry, now)
        if why:
            out["stale"][src] = why
        else:
            out["fresh"].append(src)
    return out


if __name__ == "__main__":
    print(json.dumps(check(), indent=1))
