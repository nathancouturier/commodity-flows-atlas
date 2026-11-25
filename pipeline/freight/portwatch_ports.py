"""
Weekly port traffic from the IMF PortWatch daily port table: the pure part (no network, no write).

    from portwatch_ports import port_ids, weekly, build_doc, merge_weeks, validate_doc, chunks, plan

The script that asks the service and writes the files is fetch_portwatch_port_traffic.py; everything here is a function
of its arguments, so that the tests can run it on rows they make themselves.

What a file holds  data/freight/port-traffic/<PortWatch port id>.json, one per PortWatch port that a port asset of the
        atlas carries (the `portwatch` id of data/infrastructure/ports.geojson, paired by pipeline/infrastructure/
        portwatch_pairs.py):

            id, name        PortWatch's id and PortWatch's own name of the port (pipeline/cache/portwatch_ports.csv)
            s               the registry id of the source (portwatch-port-traffic)
            y               the last day of data of the port when the file was written (ISO date)
            start, step     the Monday of the first week and "week"
            u, dp           the unit of the tonnes ("kt", thousand tonnes) and the most decimals a value may have (3: the
                            tonne); a value keeps three significant figures at least, see round_tonnes
            calls           weekly sums of the daily port calls by ship type: tanker, dry (dry bulk), container, other
            exports         weekly sums of PortWatch's estimated export tonnes, the same four types, in `u`
            imports         the same for import tonnes

        A week is Monday to Sunday, stored only when the table has all seven days of it (the last, partial week is not
        stored); a week inside the span that has fewer days is null in all twelve arrays, never a zero. `other` is
        general cargo plus ro-ro, as on the chokepoint pages. The types are added here: the table's own total columns
        are never used (they differ by a tonne or two on some days). No daily value is kept.

The weekly run reads again the last WINDOW_WEEKS weeks of the ports with a file (PortWatch revises its recent days) and,
for a quarter of the ports in turn, the last DEEP_WEEKS weeks, so that every port is re-read over a year once every four
weeks and never all together. A port without a file is read in full (HISTORY_PAGES pages), a few a run.
"""
import csv
import json
import math
import os
import re
from datetime import date, timedelta
from urllib.parse import urlencode

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PORTS_GEOJSON = os.path.join(ROOT, "data", "infrastructure", "ports.geojson")
TABLE = os.path.join(ROOT, "pipeline", "cache", "portwatch_ports.csv")
OUT = os.path.join(ROOT, "data", "freight", "port-traffic")
INDEX = "index.json"

SOURCE = "portwatch-port-traffic"
URL = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0/query"
PAGE = 1000                  # the service's maxRecordCount
MAX_IDS = 20                 # ports in one request
MAX_ADDRESS = 1800           # characters of the address of one request (a longer one was answered 404 at about 4,000)
HISTORY_FROM = "2019-01-01"  # the table starts here
WINDOW_WEEKS = 6             # the weeks read again every run
DEEP_WEEKS = 52              # the weeks read again for a quarter of the ports every run
QUARTERS = 4
SCHEDULED_BACKFILL_CAP = 5   # ports without a file filled in by one scheduled run
SITTING_MAX = 15             # ports read in full by one run made by hand: a sitting of the first load (45 requests)
# Tonnes are stored in thousand tonnes, each value with three significant figures at least and never finer than a tonne
# (STEPS). Whole thousand tonnes for every value, as the first load was made, moved the 52-week sum of a small flow by
# several per cent (7.6% for the imports of Primorsk, 5.9% for a ship type of Ras Tanura, 4.6% for the imports of Narvik),
# and one decimal for every value does not cure a flow of 4 kt a year (0.08 kt a week) and makes the large ones longer for
# nothing. The step grows with the value, so that one value is never rounded by more than 0.5% of itself and a sum of
# rounded weeks is never further than 0.5% from the sum of the exact weeks. Measured on 25 November 2026 on the fifteen
# ports of the first load, read again with this rule: the 52-week sum of the four ship types moves by 0.10% at most
# (the imports of Primorsk, which whole thousand tonnes moved by 7.6%) and the sum of one ship type by 0.21% at most (the
# container imports of Richards Bay). A file is 11.0 to 21.0 kB, 246.5 kB for the fifteen against 198.6 kB in whole thousand
# tonnes: about 2.7 MB for 163 ports at the mean and 3.4 MB if every file were as large as the largest, against SIZE_STOP_KB.
# The script prints, for each port it reads in full, how far the rounding moves its sums.
UNIT = "kt"
MAX_DECIMALS = 3             # the tonne: the most decimals a value of a file may have (its `dp`)
# (from this many tonnes, rounded to this many tonnes): whole kt from 100 kt, one decimal from 10 kt, two from 1 kt, three below
STEPS = ((100_000, 1000), (10_000, 100), (1_000, 10), (0, 1))
SIZE_STOP_KB = 3500          # the folder may not exceed this (decimal kB, as check-size.mjs counts)
SIZE_WARN_SHARE = 0.9        # a run says in its summary that the stop is near from this share of it
MIN_ROW_SHARE = 0.9          # a run that gets less than this share of the rows it expects is refused
MAX_SKIPPED_SHARE = 0.1      # ... and so is one that has to skip more than this share of the ports
REVISED_SHARE = 0.25         # a port whose older weeks changed by more than this share ...
REVISED_PORTS = 0.1          # ... on more than this share of the ports read in depth: PortWatch re-estimated its history

TYPES = {"tanker": ("tanker",), "dry": ("dry_bulk",), "container": ("container",), "other": ("general_cargo", "roro")}
SOURCE_TYPES = ("container", "dry_bulk", "general_cargo", "roro", "tanker")
PREFIX = {"calls": "portcalls", "exports": "export", "imports": "import"}
MEASURES = tuple(PREFIX)
ASK_FIELDS = ["date", "portid"] + [f"{p}_{t}" for p in PREFIX.values() for t in SOURCE_TYPES]
ID_RE = re.compile(r"^(port|fso)\d+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KEYS = ("id", "name", "s", "y", "start", "step", "u", "dp", "calls", "exports", "imports")


class RowError(ValueError):
    """A page of the service does not have the shape the atlas expects."""


# --------------------------------------------------------------------------------------------------- the ports
def port_ids(path=PORTS_GEOJSON):
    """The distinct PortWatch ids of the port assets, in the fixed order (sorted as text) that the rotation uses."""
    with open(path, encoding="utf-8") as fh:
        feats = json.load(fh)["features"]
    return sorted({f["properties"]["portwatch"] for f in feats if f["properties"].get("portwatch")})


def port_names(path=TABLE):
    """{PortWatch id: name} of the ports table."""
    with open(path, encoding="utf-8", newline="") as fh:
        return {r["portid"]: r["name"] for r in csv.DictReader(fh)}


def monday(d):
    """The Monday on or before ``d`` (a date)."""
    return d - timedelta(days=d.weekday())


def iso(d):
    return d.isoformat()


# --------------------------------------------------------------------------------------------------- the rows
def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0


def _day(v):
    """The ISO day of a row's ``date``: a string of the service, or a time in milliseconds (UTC)."""
    if isinstance(v, str) and DATE_RE.match(v):
        date.fromisoformat(v)
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
        return iso(date(1970, 1, 1) + timedelta(days=int(v // 86_400_000)))
    raise RowError(f"unexpected date {v!r}")


def parse_rows(features, allowed=None):
    """The rows of one page of the service as dicts of ASK_FIELDS (``date`` an ISO day). A feature without attributes,
    a missing field, a value that is not a non-negative number, or (with ``allowed``) a port that was not asked for
    raises RowError: nothing is guessed."""
    out = []
    for f in features:
        a = f.get("attributes") if isinstance(f, dict) else None
        if not isinstance(a, dict):
            raise RowError("a feature without attributes")
        missing = [k for k in ASK_FIELDS if k not in a]
        if missing:
            raise RowError("unexpected fields: missing " + ",".join(missing))
        bad = [k for k in ASK_FIELDS[2:] if not _num(a[k])]
        if bad:
            raise RowError("unexpected fields: not a number in " + ",".join(bad))
        if not isinstance(a["portid"], str) or (allowed is not None and a["portid"] not in allowed):
            raise RowError(f"a row of a port that was not asked for: {a['portid']!r}")
        r = {k: a[k] for k in ASK_FIELDS}
        r["date"] = _day(a["date"])
        out.append(r)
    return out


def last_day(rows):
    """The latest ISO day among ``rows`` (None when there are none)."""
    return max((r["date"] for r in rows), default=None)


# --------------------------------------------------------------------------------------------------- weekly sums
def weekly(rows):
    """Weekly sums of the daily rows of ONE port: {Monday ISO: {"calls": {type: n}, "exports": {...}, "imports": {...}}}
    for the complete weeks (all seven days present) only, the exact tonnes (integers, not rounded). A day that comes twice
    counts once (the later row wins). The ship types of the source are added into the four of the atlas; the source's
    total columns are never read."""
    days = {}
    for r in rows:
        days[r["date"]] = r
    weeks = {}
    for d in sorted(days):
        weeks.setdefault(iso(monday(date.fromisoformat(d))), []).append(days[d])
    out = {}
    for m, rs in weeks.items():
        if len(rs) != 7:
            continue
        out[m] = {k: {t: sum(r[f"{PREFIX[k]}_{s}"] for r in rs for s in srcs) for t, srcs in TYPES.items()} for k in MEASURES}
    return dict(sorted(out.items()))


def round_tonnes(tonnes):
    """Integer tonnes rounded half up to the step of their size (STEPS), in integer arithmetic: to 1,000 t from 100,000 t,
    to 100 t from 10,000 t, to 10 t from 1,000 t, none below. The size is that of the exact value, so 99,950 t gives
    100,000 t and 9,995 t gives 10,000 t."""
    t = int(tonnes)
    for floor, step in STEPS:
        if t >= floor:
            return (t + step // 2) // step * step
    raise ValueError(f"a negative tonnage: {tonnes!r}")


def kt(tonnes):
    """Tonnes (an integer) in thousand tonnes by round_tonnes: an int when the value is whole, else a float of at most three
    decimals."""
    q = round_tonnes(tonnes)
    return q // 1000 if q % 1000 == 0 else q / 1000


def week_values(week):
    """The values stored for one week: {"calls": {...}, "exports": {...}, "imports": {...}} (tonnes rounded)."""
    return {k: {t: (v if k == "calls" else kt(v)) for t, v in week[k].items()} for k in MEASURES}


def build_doc(port_id, name, weeks, y):
    """The document of a port from its weekly sums (``weekly``): the weeks from the first to the last, a null in the
    twelve arrays for a week missing between them. ``y`` is the last day of data of the port."""
    if not weeks:
        raise ValueError("no complete week")
    first, last = date.fromisoformat(min(weeks)), date.fromisoformat(max(weeks))
    n = (last - first).days // 7 + 1
    doc = {"id": port_id, "name": name, "s": SOURCE, "y": y, "start": iso(first), "step": "week", "u": UNIT, "dp": MAX_DECIMALS,
           "calls": {t: [None] * n for t in TYPES}, "exports": {t: [None] * n for t in TYPES},
           "imports": {t: [None] * n for t in TYPES}}
    return _put(doc, weeks)


def _put(doc, weeks):
    for m, w in weeks.items():
        i = (date.fromisoformat(m) - date.fromisoformat(doc["start"])).days // 7
        v = week_values(w)
        for k in MEASURES:
            for t in TYPES:
                if i >= len(doc[k][t]):
                    doc[k][t].extend([None] * (i + 1 - len(doc[k][t])))
                doc[k][t][i] = v[k][t]
    n = max(len(doc[k][t]) for k in MEASURES for t in TYPES)
    for k in MEASURES:
        for t in TYPES:
            doc[k][t].extend([None] * (n - len(doc[k][t])))
    return doc


def last_monday(doc):
    """The Monday of the last week a document holds."""
    return date.fromisoformat(doc["start"]) + timedelta(days=7 * (len(doc["calls"]["tanker"]) - 1))


def window_since(doc):
    """The first Monday the weekly run reads again: five weeks before the last stored week (six weeks in all)."""
    return last_monday(doc) - timedelta(weeks=WINDOW_WEEKS - 1)


def deep_since(doc):
    """The first Monday the deep pass reads again: 52 weeks before the last stored week."""
    return last_monday(doc) - timedelta(weeks=DEEP_WEEKS)


def merge_weeks(doc, weeks, since, y=None):
    """A new document: the weeks of ``weeks`` (complete weeks, exact sums) that start on or after ``since`` (a date)
    replace the same weeks of ``doc`` or are appended (a gap is filled with nulls); every other week, ``start`` and the
    rest are as they were. A week before ``start`` is not added (the history is never extended backwards here).
    ``y`` (the last day of the rows) moves ``y`` forward, never back."""
    new = json.loads(json.dumps(doc))
    start = date.fromisoformat(doc["start"])
    use = {m: w for m, w in weeks.items() if date.fromisoformat(m) >= since and date.fromisoformat(m) >= start}
    _put(new, use)
    if y and y > new["y"]:
        new["y"] = y
    return new


def check_merge(old, new, since):
    """Why ``new`` may not replace ``old`` (a message), or None. Weeks before ``since`` must be as they were, the series
    may not be shorter nor end earlier, ``start`` and ``y`` may not move back."""
    if new["start"] != old["start"]:
        return "the first week moved"
    if len(new["calls"]["tanker"]) < len(old["calls"]["tanker"]):
        return "the series has fewer weeks than before"
    if new["y"] < old["y"]:
        return "the last day of data is earlier than before"
    cut = (since - date.fromisoformat(old["start"])).days // 7
    for k in MEASURES:
        for t in TYPES:
            if new[k][t][:max(cut, 0)] != old[k][t][:max(cut, 0)]:
                return f"a week before {iso(since)} would change ({k} {t})"
    return None


def revision(old, new, since, before):
    """The share by which the weeks of ``new`` from ``since`` up to (not including) ``before`` differ from those of
    ``old``: the sum of the absolute differences of the twelve arrays over the sum of the old values (None when the old
    weeks are all zero or absent). It measures whether PortWatch re-estimated weeks that are no longer its recent days."""
    start = date.fromisoformat(old["start"])
    lo = max((since - start).days // 7, 0)
    hi = min((before - start).days // 7, len(old["calls"]["tanker"]))
    diff = base = 0
    for k in MEASURES:
        for t in TYPES:
            for a, b in zip(old[k][t][lo:hi], new[k][t][lo:hi]):
                if a is not None and b is not None:
                    diff += abs(b - a)
                    base += a
    return diff / base if base else None


def rounding_error(weeks, n=52, by_type=False):
    """(share, where): the largest relative difference between the sum of the last ``n`` rounded weeks and the exact sum,
    for the exports and the imports. By default the four ship types are added first, as the 52-week figure of the page is;
    with ``by_type`` each type is taken alone. A sum of zero is left out; (0.0, None) when there is none."""
    ms = sorted(weeks)[-n:]
    worst = (0.0, None)
    for k in ("exports", "imports"):
        groups = [(t,) for t in TYPES] if by_type else [tuple(TYPES)]
        for g in groups:
            exact = sum(weeks[m][k][t] for m in ms for t in g)
            if not exact:
                continue
            rounded = sum(round_tonnes(weeks[m][k][t]) for m in ms for t in g)
            share = abs(rounded - exact) / exact
            if share > worst[0]:
                worst = (share, f"{k} {g[0]}" if by_type else k)
    return worst


# --------------------------------------------------------------------------------------------------- the rules
def _is_int(v):
    return (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and math.isfinite(v) and v.is_integer())


def _fits_rule(v):
    """True when ``v`` (thousand tonnes) has no more decimals than the rule gives its size: none from 100, one from 10, two
    from 1, three below (so never finer than a tonne). What can be checked from the file alone."""
    d = 0 if v >= 100 else 1 if v >= 10 else 2 if v >= 1 else MAX_DECIMALS
    return abs(v * 10 ** d - round(v * 10 ** d)) < 1e-6


def _valid_date(s):
    if not isinstance(s, str) or not DATE_RE.match(s):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def validate_doc(doc, port_id=None, sources=None):
    """The problems of a port document as strings ``"code: message"`` (empty when it is good). Exactly the rules of
    web/scripts/port-traffic-rules.mjs, which the site's data check runs; a test runs both on the same documents."""
    if not isinstance(doc, dict) or set(doc) != set(KEYS):
        return ["shape: not an object with exactly the keys " + ",".join(KEYS)]
    p = []
    if not isinstance(doc["id"], str) or not ID_RE.match(doc["id"]) or (port_id is not None and doc["id"] != port_id):
        p.append(f"id: {doc['id']!r} is not the id of its file")
    if not isinstance(doc["name"], str) or not doc["name"].strip():
        p.append("name: empty")
    if doc["s"] != SOURCE or (sources is not None and doc["s"] not in sources):
        p.append(f"source: {doc['s']!r}")
    y, start = _valid_date(doc["y"]), _valid_date(doc["start"])
    if y is None or start is None:
        p.append("date: y or start is not an ISO date")
    elif start.weekday() != 0:
        p.append("monday: start is not a Monday")
    if doc["step"] != "week":
        p.append("step: not week")
    if doc["u"] != UNIT or isinstance(doc["dp"], bool) or doc["dp"] != MAX_DECIMALS:
        p.append(f"unit: u must be kt and dp {MAX_DECIMALS}")
    arrays, n = [], None
    for k in MEASURES:
        b = doc[k]
        if not isinstance(b, dict) or set(b) != set(TYPES) or any(not isinstance(b[t], list) for t in TYPES):
            p.append(f"series: {k} is not four arrays ({','.join(TYPES)})")
            return p
        arrays += [(k, t, b[t]) for t in TYPES]
    lens = {len(a) for _, _, a in arrays}
    if len(lens) != 1 or 0 in lens:
        p.append("series: the twelve arrays are not all of the same length, at least one week")
        return p
    n = lens.pop()
    holes = None
    for k, t, a in arrays:
        for v in a:
            if v is None:
                continue
            if k == "calls":
                if not (_is_int(v) and v >= 0):
                    p.append(f"calls: {k} {t} holds {v!r}, not a non-negative integer")
                    break
            elif not (isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0 and _fits_rule(v)):
                p.append(f"tonnes: {k} {t} holds {v!r}, not a non-negative number with the decimals its size allows")
                break
        h = [i for i, v in enumerate(a) if v is None]
        if holes is None:
            holes = h
        elif h != holes:
            p.append(f"holes: the missing weeks of {k} {t} differ from those of the other arrays")
            break
    if y is not None and start is not None and start + timedelta(days=7 * n - 1) > y:
        p.append("end: the last week ends after y")
    return p


def size_note(total_bytes, docs, today, stop_kb=None):
    """(share, message): the share of the size stop that the folder uses, and, from SIZE_WARN_SHARE of it, a sentence that says so
    (else None). The growth is that of the files in ``docs`` {id: document}: each adds one week a week, and the folder holds
    ``total_bytes`` for the weeks of ``docs``, so a week costs ``total_bytes`` over those weeks, times the number of files."""
    stop = (SIZE_STOP_KB if stop_kb is None else stop_kb) * 1000
    share = total_bytes / stop
    if share < SIZE_WARN_SHARE:
        return share, None
    weeks = sum(len(d["calls"]["tanker"]) for d in docs.values())
    a_week = total_bytes / weeks * len(docs) if weeks else 0
    left = max(stop - total_bytes, 0)
    msg = (f"the folder of the port files holds {total_bytes / 1000:.0f} kB, {share * 100:.0f}% of its {stop / 1000:.0f} kB stop; "
           f"it grows by about {a_week / 1000:.1f} kB a week")
    if left and a_week:
        n = math.ceil(left / a_week)
        msg += f", so the stop is reached in about {n} weeks (the week of {iso(monday(today) + timedelta(weeks=n))})"
    else:
        msg += ", and the stop is reached"
    return share, msg + "; from there a weekly run refuses everything (the stop is the owner's figure to raise: docs/UPDATING.md)"


def index_doc(none, checked, pending=()):
    """The index of the folder: ``none`` the ports that returned no rows at the last check, ``pending`` the ports not read yet
    (the first load is made in sittings: the ids are removed from the list as the files are written, and the list is empty
    once every port has a file or is in ``none``). Both lists sorted as text, as the site's rules ask."""
    return {"checked": checked, "none": sorted(set(none)), "pending": sorted(set(pending))}


# --------------------------------------------------------------------------------------------------- the requests
def quote_ids(ids):
    for i in ids:
        if not ID_RE.match(i):
            raise ValueError(f"not a PortWatch port id: {i!r}")
    return ",".join(f"'{i}'" for i in ids)


def where_window(ids, since):
    """The rows of ``ids`` from ``since`` (a date) on. The date test is the form the service was seen to answer
    (``date > 'D'``), so the day before is given."""
    return f"portid IN ({quote_ids(ids)}) AND date > '{iso(since - timedelta(days=1))}'"


def where_history(port_id):
    """Every row of one port."""
    return f"portid = {quote_ids([port_id])}"


def request_params(where, offset=0, order="ObjectId"):
    return {"where": where, "outFields": ",".join(ASK_FIELDS), "returnGeometry": "false", "f": "json",
            "orderByFields": order, "resultOffset": offset, "resultRecordCount": PAGE}


def address(where, offset=999_999, order="ObjectId"):
    """The address of a request (the offset defaults to the longest one the script can reach)."""
    return URL + "?" + urlencode(request_params(where, offset, order))


def chunks(ids, since, max_ids=MAX_IDS, max_chars=MAX_ADDRESS):
    """``ids`` in the order given, split into lists of at most ``max_ids`` ports whose request address stays under
    ``max_chars`` characters. Every id is in exactly one list."""
    out, cur = [], []
    for i in ids:
        if cur and (len(cur) >= max_ids or len(address(where_window(cur + [i], since))) > max_chars):
            out.append(cur)
            cur = []
        cur.append(i)
    if cur:
        out.append(cur)
    return out


def pages(rows):
    """The requests a query of at most ``rows`` rows takes: a page that is full is followed by one more request (the script
    does not trust a service that says nothing of the rows that remain), so a query of exactly one page of rows takes two."""
    return rows // PAGE + 1


def week_index(today):
    """Weeks since a fixed Monday: the rotation counts on it (the ISO week number jumps back to 1 at the year's end,
    which would give the same quarter twice in a row)."""
    return (monday(today) - date(1970, 1, 5)).days // 7


def quarter_of(i, today):
    """True when the port at place ``i`` of the fixed order is read in depth in the week of ``today``."""
    return i % QUARTERS == week_index(today) % QUARTERS


def _groups(ids, docs, deep_ids, end):
    """The window and deep groups of the ports ``ids`` (all with a file; ``deep_ids`` the ports of the quarter read in depth):
    [{"since", "ports", "chunks", "days"}] each."""
    out = {"window": [], "deep": []}
    for kind, members, since_of in (("window", [i for i in ids if i not in deep_ids], window_since),
                                    ("deep", [i for i in ids if i in deep_ids], deep_since)):
        groups = {}
        for i in members:
            groups.setdefault(since_of(docs[i]), []).append(i)
        for since, ports in sorted(groups.items()):
            out[kind].append({"since": iso(since), "ports": ports, "chunks": chunks(ports, since), "days": (end - since).days + 1})
    return out


def _cost(groups):
    return sum(pages(len(c) * g["days"]) for kind in ("window", "deep") for g in groups[kind] for c in g["chunks"])


def plan(ids, docs, none, today, *, backfill=False, max_ports=None, full=None, end=None, max_requests=None):
    """What a run asks for, as a dict (nothing is requested here).

    ``ids``      the ports in the fixed order, ``docs`` {id: document} of the ports that have a file, ``none`` the ids that
                 returned no rows at the last check, ``today`` a date; ``end`` the last day the rows can reach (default
                 ``today``), which only sets how many pages the requests are counted at.
    Modes        weekly (default): the window (six weeks) of the ports with a file, the deep pass (52 weeks) instead of it
                 for the quarter of the ports of the week, and at most SCHEDULED_BACKFILL_CAP ports without a file read in
                 full; a port of ``none`` is asked again only in the week of its quarter.
                 ``backfill``: only the ports without a file (not in ``none``), at most ``max_ports`` and never more than
                 SITTING_MAX (that many when ``max_ports`` is not given).
                 ``full``: the ports named, read in full, whatever they hold.
    ``max_requests``  (weekly only) the most requests the run may ask for, whatever state the files are in: the ports whose
                 files end earliest are read first, as many as fit, and the others are left to the next run
                 (``deferred``); the ports without a file take what is left of it, at most SCHEDULED_BACKFILL_CAP of them.
    Returns      {"window": [{"since", "ports", "chunks", "days"}], "deep": [...], "history": [ids], "deferred": [ids],
                  "quarter": q, "requests": {"window", "deep", "history", "total"}}
                 (pages of 1,000 rows, one row per port per day, to ``end``; a full page is followed by one more request)."""
    end = end or today
    q = week_index(today) % QUARTERS
    have = [i for i in ids if i in docs]
    out = {"window": [], "deep": [], "history": [], "deferred": [], "quarter": q}
    days = (end - date.fromisoformat(HISTORY_FROM)).days + 1
    if full:
        out["history"] = [i for i in ids if i in set(full)]
    elif backfill:
        todo = [i for i in ids if i not in docs and i not in none]
        out["history"] = todo[:min(SITTING_MAX if max_ports is None else max_ports, SITTING_MAX)]
    else:
        read = have
        deep_ids = {i for n, i in enumerate(ids) if i in docs and n % QUARTERS == q}
        if max_requests is not None and _cost(_groups(have, docs, deep_ids, end)) > max_requests:
            order = sorted(have, key=lambda i: (last_monday(docs[i]), i))
            lo, hi = 0, len(order)         # the longest run of the ports that end earliest whose requests fit (the cost only grows)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if _cost(_groups(order[:mid], docs, deep_ids, end)) <= max_requests:
                    lo = mid
                else:
                    hi = mid - 1
            read = [i for i in have if i in set(order[:lo])]
            out["deferred"] = [i for i in have if i not in set(read)]
        out.update(_groups(read, docs, deep_ids, end))
        recheck = [i for n, i in enumerate(ids) if i in none and i not in docs and n % QUARTERS == q]
        cap = SCHEDULED_BACKFILL_CAP if max_ports is None else max_ports
        if max_requests is not None:
            cap = min(cap, max(0, (max_requests - _cost(out)) // pages(days)))
        out["history"] = ([i for i in ids if i not in docs and i not in none] + recheck)[:cap]
    r = {kind: sum(pages(len(c) * g["days"]) for g in out[kind] for c in g["chunks"]) for kind in ("window", "deep")}
    r["history"] = len(out["history"]) * pages(days)
    r["total"] = r["window"] + r["deep"] + r["history"]
    out["requests"] = r
    return out


def weekly_request_bounds(n_ports, today, max_requests):
    """(least, usual, most) number of requests of one scheduled run for ``n_ports`` ports, from the plan itself.
    least: every port has a file, the rows reach only the end of the last week stored, nothing is read in full.
    usual: the files are as a weekly run leaves them, five ports have no file, the rows reach ``today``.
    most:  ``max_requests``, which the plan keeps whatever state the files are in (the ports that end earliest are read first)."""
    ids = [f"port{n}" for n in range(n_ports)]
    last = monday(today) - timedelta(weeks=2)   # the last week stored: the table lags the date by days, not by weeks
    mk = lambda: {i: {"start": iso(last - timedelta(weeks=300)), "calls": {"tanker": [0] * 301}} for i in ids}   # noqa: E731
    least = plan(ids, mk(), set(), today, end=last + timedelta(days=6), max_requests=max_requests)["requests"]["total"]
    docs = mk()
    for i in ids[:SCHEDULED_BACKFILL_CAP]:
        del docs[i]
    usual = plan(ids, docs, set(), today, max_requests=max_requests)["requests"]["total"]
    return least, usual, max_requests
