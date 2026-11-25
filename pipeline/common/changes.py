"""
"What changed": the digest of the update jobs, as a small JSON file for the About window and a static Atom feed.

    python pipeline/common/changes.py

Reads  data/prices/ (index and series), data/freight/portwatch/<passage>.json (``compare.perDay``),
       data/_status/updates.json (what each source last published), data/sources.json (names), data/freight/chokepoints.json
Writes data/_status/changes.json   the latest digest (``weekly``, ``monthly``, ``passages``, ``sources``), the feed entries
                                   (``entries``, newest first) and what the last run had seen (``seen``)
       web/public/changes.atom     the entries as an Atom 1.0 feed (copied into the site by the build)

The three weekly jobs run it after their own step. A run adds one feed entry per kind of news that is new since the previous
run (daily prices that run to a later day, monthly prices of a later month, PortWatch data to a later day, a source whose
data or release changed), and writes nothing when nothing is new. Only dates, names and figures leave this script: error
messages of the status file are never copied. Always exits 0: a failure is recorded as source ``build-changes``.

    largest price moves of the week   the daily series (EIA spot): last quote against the last quote 7 days or more before it
    monthly prices                    the monthly series (World Bank): the latest month against the month before
                                      (a move beyond MAX_RATIO, and series that carry the same two figures under another name or
                                      unit, are refused: not published, listed in the status of the job)
    passages                          the last 7 days of IMF PortWatch against the 28 days before them and the 365 days before
                                      them, the five furthest from either average (passages under MIN_TRAFFIC a day before the last week left out)
    sources                           the sources whose last published data or release differs from the previous run
"""
import bisect
import json
import os
import re
import sys
import tempfile
import traceback
from datetime import date, datetime, timedelta, timezone
from xml.sax.saxutils import escape

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

from common import status  # noqa: E402

DATA = os.path.join(ROOT, "data")
CHANGES = os.path.join(DATA, "_status", "changes.json")
FEED = os.path.join(ROOT, "web", "public", "changes.atom")
SITE = "https://nathancouturier.github.io/commodity-flows-atlas/"
TAG = "tag:nathancouturier.github.io,2026:commodity-flows-atlas:"
SOURCE = "build-changes"

TOP = 5            # moves listed per kind
KEEP = 60          # feed entries kept
MIN_TRAFFIC = 3.0  # vessels a day, both for the 28 and for the 365 days before the last week: a passage under it is left out (small counts swing)
# A price that moves further than this in a week (daily series) or a month (monthly series) is taken for a data fault (a wrong
# column, a change of unit), not for news: the digest does not publish it and says so in the status of the job. A ratio, so
# that a rise and a fall weigh the same: more than five times or less than a fifth. (In the atlas's history only Henry Hub in
# February 2021, ten times in a week, would have been refused; a real move of that size is then checked by a person.)
MAX_RATIO = 5.0
EPOCH = date(1970, 1, 1)
# status keys that feed several registry sources
SOURCES_OF = {"faostat-wna": ["faostat", "wna"]}
# the workflow (.github/workflows/<id>.yml) that reads each registry source; every other source is entered by hand
JOBS = {
    "update-prices": ["eia-spot", "wb-pink", "bls", "dallasfed", "nyfed"],
    "update-portwatch": ["portwatch", "portwatch-port-traffic"],
    "update-annual": ["usda-psd", "usgs-mcs", "eia-intl", "baci", "faostat", "wna"],
}
DOW = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def load(*parts, default=None):
    try:
        with open(os.path.join(*parts), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def day_label(iso):
    """"2026-11-17" -> "17 Nov 2026"; "2026-10" -> "Oct 2026"."""
    p = iso[:10].split("-")
    if len(p) == 3:
        return f"{int(p[2])} {MON[int(p[1]) - 1]} {p[0]}"
    return f"{MON[int(p[1]) - 1]} {p[0]}"


def num(v):
    """A price or a count for a sentence: 2 decimals under 100, none from 1000."""
    return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:,.2f}" if abs(v) < 100 else f"{v:,.1f}"


def signed(p, nd=1):
    return f"{p:+.{nd}f}%".replace("-", "−")


# ----------------------------------------------------------------------------- prices
def implausible(v0, v1, kind):
    """True when a move from v0 to v1 is beyond MAX_RATIO for ``kind`` ("week" or "month")."""
    if not v0 or not v1 or v0 < 0 or v1 < 0:
        return True
    r = v1 / v0
    return r > MAX_RATIO or r < 1 / MAX_RATIO


def refuse(rows, kind):
    """(kept, refused): the moves of ``rows`` without those that are out of range or that repeat the figures of a series with another
    name or unit (a duplicated column). A refused move is {"id", "pct", "why"}: ids and figures only."""
    groups = {}
    for r in rows:
        groups.setdefault((r["v0"], r["v1"], r["to"]), []).append(r)
    kept, refused = [], []
    for r in rows:
        twins = [x for x in groups[(r["v0"], r["v1"], r["to"])] if x is not r and (x["unit"], x["name"]) != (r["unit"], r["name"])]
        if implausible(r["v0"], r["v1"], kind):
            refused.append({"id": r["id"], "pct": r["pct"], "why": f"beyond a factor {MAX_RATIO:g} in a {kind}"})
        elif twins:
            refused.append({"id": r["id"], "pct": r["pct"], "why": "same two figures as " + ", ".join(sorted(x["id"] for x in twins))})
        else:
            kept.append(r)
    return kept, refused


def price_moves(prices_dir=os.path.join(DATA, "prices")):
    """({weekly}, {monthly}): the series that run to the latest day or month, largest move first, TOP of each, and the moves
    refused (``refused``: see ``refuse``)."""
    index = load(prices_dir, "index.json", default=[])
    weekly, monthly = [], []
    for m in index:
        if m["freq"] not in ("D", "M"):  # annual series (real prices, indices) move once a year: not news of the week
            continue
        doc = load(prices_dir, m["id"] + ".json")
        if not doc or not doc.get("v"):
            continue
        pts = [(d, v) for d, v in zip(doc["d"], doc["v"]) if v is not None] if m["freq"] == "D" else None
        if m["freq"] == "D":
            if len(pts) < 2:
                continue
            days = [p[0] for p in pts]
            d1, v1 = pts[-1]
            i0 = bisect.bisect_right(days, d1 - 7) - 1
            if i0 < 0 or not pts[i0][1]:
                continue
            d0, v0 = pts[i0]
            weekly.append({"id": m["id"], "name": m["name"], "k": m["k"], "unit": m["unit"], "s": m["s"],
                           "from": (EPOCH + timedelta(days=d0)).isoformat(), "to": (EPOCH + timedelta(days=d1)).isoformat(),
                           "v0": v0, "v1": v1, "pct": round(100 * (v1 / v0 - 1), 1)})
        else:
            y, mo = (int(x) for x in doc.get("start", m["start"]).split("-")[:2])
            obs = [(y * 12 + mo - 1 + i, v) for i, v in enumerate(doc["v"]) if v is not None]
            if len(obs) < 2 or not obs[-2][1]:
                continue
            (t0, v0), (t1, v1) = obs[-2], obs[-1]
            lab = lambda t: f"{t // 12}-{t % 12 + 1:02d}"  # noqa: E731
            monthly.append({"id": m["id"], "name": m["name"], "k": m["k"], "unit": m["unit"], "s": m["s"],
                            "from": lab(t0), "to": lab(t1), "v0": v0, "v1": v1, "pct": round(100 * (v1 / v0 - 1), 1)})

    def top(rows, kind):
        if not rows:
            return {"to": None, "moves": [], "refused": []}
        last = max(r["to"] for r in rows)
        cur = [r for r in rows if r["to"] == last]  # a series that stopped earlier is not this week's news
        cur, refused = refuse(cur, kind)
        cur.sort(key=lambda r: (-abs(r["pct"]), r["id"]))
        return {"to": last, "moves": cur[:TOP], "refused": sorted(refused, key=lambda r: r["id"])}

    return top(weekly, "week"), top(monthly, "month")


# ----------------------------------------------------------------------------- passages
def passage_moves(series_dir=os.path.join(DATA, "freight", "portwatch")):
    """The passages furthest from their 4-week and 1-year averages, from the ``compare.perDay`` block of the series files."""
    chk = {c["id"]: c for c in load(DATA, "freight", "chokepoints.json", default=[])}
    rows, last = [], None
    for cid in sorted(chk):
        doc = load(series_dir, cid + ".json")
        c = (doc or {}).get("compare")
        pd_ = (c or {}).get("perDay") or {}
        wk, p28, p365 = pd_.get("week"), pd_.get("prior28"), pd_.get("prior365")
        if wk is None or not p28 or not p365 or min(p28, p365) < MIN_TRAFFIC:
            continue
        last = max(last or c["to"], c["to"])
        g28, g365 = 100 * (wk / p28 - 1), 100 * (wk / p365 - 1)
        rows.append({"id": cid, "name": chk[cid]["name"].split(" (")[0], "to": c["to"], "week": wk, "prior28": p28, "prior365": p365,
                     "gap28": round(g28, 1), "gap365": round(g365, 1)})
    rows.sort(key=lambda r: (-max(abs(r["gap28"]), abs(r["gap365"])), r["id"]))
    return {"to": last, "moves": rows[:TOP]}


# ----------------------------------------------------------------------------- sources
def fingerprint(entry):
    """What a source last published, as a short string: its data end, release or file hash (never an error message)."""
    st = entry.get("state") or {}
    return "|".join(str(x) for x in (entry.get("data_to"), st.get("sha256", "")[:12], st.get("version"), st.get("item"), st.get("url")))


def published(updates, registry, seen):
    """(items, fingerprints): the sources whose fingerprint differs from ``seen`` (empty on the first run: nothing can be told apart)."""
    names = {s["id"]: s["name"] for s in registry}
    prints, items = {}, []
    for key, e in sorted((updates.get("sources") or {}).items()):
        if key.startswith("build-") or not e.get("last_success"):
            continue
        prints[key] = fingerprint(e)
        if seen is not None and seen.get(key) != prints[key]:
            name = " and ".join(names.get(s, s) for s in SOURCES_OF.get(key, [key]))
            items.append({"id": key, "name": name, "data_to": e.get("data_to"), "t": e["last_success"]})
    return items, prints


# ----------------------------------------------------------------------------- calendar
def parse_cron(expr):
    """{"min", "hour", "dow", "dom", "text"} of a five-field cron expression that names one weekday or one day of the month
    (the only forms the workflows use); None for any other."""
    f = expr.split()
    if len(f) != 5 or not (f[0].isdigit() and f[1].isdigit() and f[3] == "*"):
        return None
    mn, hr = int(f[0]), int(f[1])
    clock = f"{hr:02d}:{mn:02d} UTC"
    if f[2] == "*" and f[4].isdigit() and int(f[4]) % 7 in range(7):
        d = int(f[4]) % 7
        return {"min": mn, "hour": hr, "dow": d, "dom": None, "text": f"every {DOW[d]} at {clock}"}
    if f[4] == "*" and f[2].isdigit() and 1 <= int(f[2]) <= 28:
        d = int(f[2])
        suffix = "th" if 10 <= d % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th")
        return {"min": mn, "hour": hr, "dow": None, "dom": d, "text": f"the {d}{suffix} of each month at {clock}"}
    return None


def jobs(workflows=os.path.join(ROOT, ".github", "workflows")):
    """The scheduled jobs of JOBS, read from their workflow files: name, the times they run and the sources they read."""
    out = []
    for jid, srcs in JOBS.items():
        try:
            with open(os.path.join(workflows, jid + ".yml"), encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        name = re.search(r"^name:\s*(.+?)\s*$", text, re.M)
        crons = [parse_cron(m) for m in re.findall(r"^\s*-\s*cron:\s*[\"']([^\"']+)[\"']", text, re.M)]
        crons = [c for c in crons if c]
        if name and crons:
            out.append({"id": jid, "name": name.group(1).strip("\"'"), "runs": crons, "sources": srcs})
    return out


# ----------------------------------------------------------------------------- entries and feed
# how the feed words the source of a price move: the EIA's spot prices carry the source the EIA gives for them, the others the short
# names of the price board (web/src/components/PriceBoard.tsx); the id is the default for a source with no word
SOURCE_WORDS = {"eia-spot": "EIA, source: Refinitiv", "wb-pink": "World Bank", "bls": "BLS", "dallasfed": "Dallas Fed", "nyfed": "New York Fed"}


def lines_prices(block, label):
    out = []
    for r in block["moves"]:
        when = f"in the week to {day_label(r['to'])}" if label == "week" else f"in {day_label(r['to'])}"
        out.append(f"{r['name']}: {signed(r['pct'])} {when} ({num(r['v0'])} to {num(r['v1'])} {r['unit']}; {SOURCE_WORDS.get(r['s'], r['s'])})")
    return out


def lines_passages(block):
    return [f"{r['name']}: {r['week']:.1f} vessels a day in the last week, {signed(r['gap28'], 0)} on the 4 weeks before and "
            f"{signed(r['gap365'], 0)} on the 365 days before (IMF PortWatch, to {day_label(r['to'])})" for r in block["moves"]]


def lines_sources(items):
    return [f"{i['name']}: " + (f"data to {day_label(i['data_to'])}" if i.get("data_to") else "new release") + f", checked on {day_label(i['t'])}"
            for i in items]


def build(prices_dir=os.path.join(DATA, "prices"), series_dir=os.path.join(DATA, "freight", "portwatch"), now=None, previous=None,
          updates=None, registry=None):
    """The new content of changes.json from the data and the previous file (``previous``)."""
    now = now or datetime.now(timezone.utc).replace(microsecond=0)
    prev = previous or {}
    seen = prev.get("seen")
    weekly, monthly = price_moves(prices_dir)
    passages = passage_moves(series_dir)
    items, prints = published(updates if updates is not None else status.load(), registry if registry is not None else load(DATA, "sources.json", default=[]),
                              (seen or {}).get("sources") if seen else None)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    day = now.strftime("%Y-%m-%d")
    if items and prev.get("sourcesOn") == day:
        # a second run on the same UTC day (the PortWatch and the prices jobs both run on Wednesday): the sources that the first
        # run reported stay, those of this run replace theirs
        mine = {i["id"] for i in items}
        items = items + [i for i in prev.get("sources") or [] if i["id"] not in mine]
    new = {
        "weekly": weekly, "monthly": monthly, "passages": passages, "sources": items if items else (prev.get("sources") or []),
        "sourcesOn": day if items else prev.get("sourcesOn"),
        "jobs": jobs(),
        "seen": {"weekly": weekly["to"], "monthly": monthly["to"], "passages": passages["to"], "sources": prints},
    }
    entries = list(prev.get("entries") or [])
    add = []
    s = seen or {}
    if weekly["moves"] and weekly["to"] != s.get("weekly"):
        add.append(("prices", f"Price moves, week to {day_label(weekly['to'])}", lines_prices(weekly, "week")))
    if monthly["moves"] and monthly["to"] != s.get("monthly"):
        add.append(("monthly", f"Monthly prices for {day_label(monthly['to'])}", lines_prices(monthly, "month")))
    if passages["moves"] and passages["to"] != s.get("passages"):
        add.append(("passages", f"Chokepoint traffic to {day_label(passages['to'])}", lines_passages(passages)))
    if items:
        add.append(("sources", "Sources that published new data", lines_sources(items)))
    for kind, title, lines in add:
        entries = [e for e in entries if e["id"] != f"{day}-{kind}"]
        entries.insert(0, {"id": f"{day}-{kind}", "kind": kind, "t": stamp, "title": title, "lines": lines})
    new["entries"] = sorted(entries, key=lambda e: (e["t"], e["id"]), reverse=True)[:KEEP]
    new["generated"] = stamp if add else prev.get("generated", stamp)
    return new, bool(add)


def atom(doc):
    """The entries as an Atom 1.0 feed (XML text)."""
    es = doc["entries"]
    upd = es[0]["t"] if es else doc["generated"]
    out = ['<?xml version="1.0" encoding="utf-8"?>', '<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en">',
           "  <title>Commodity Flows Atlas: what changed</title>",
           "  <subtitle>Largest price moves, chokepoint traffic and new data from the atlas's weekly updates</subtitle>",
           f'  <link rel="self" type="application/atom+xml" href="{SITE}changes.atom"/>', f'  <link rel="alternate" type="text/html" href="{SITE}"/>',
           f"  <id>{TAG}feed</id>", f"  <updated>{upd}</updated>", "  <author><name>Commodity Flows Atlas</name></author>",
           "  <rights>Figures: see the sources and licences in the About window of the atlas.</rights>"]
    for e in es:
        body = "\n".join(e["lines"])
        out += ["  <entry>", f"    <title>{escape(e['title'])}</title>", f"    <id>{TAG}{escape(e['id'])}</id>", f"    <updated>{e['t']}</updated>",
                f'    <link rel="alternate" type="text/html" href="{SITE}"/>', f'    <content type="text">{escape(body)}</content>', "  </entry>"]
    out.append("</feed>")
    return "\n".join(out) + "\n"


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def main():
    try:
        prev = load(CHANGES, default={})
        new, changed = build(previous=prev)
        same = {k: v for k, v in new.items() if k != "generated"} == {k: v for k, v in prev.items() if k != "generated"}
        if not same or not os.path.exists(FEED):
            _write(CHANGES, json.dumps(new, indent=1, ensure_ascii=False) + "\n")
            _write(FEED, atom(new))
        print(f"  changes: {len(new['entries'])} entries" + (", new ones added" if changed else ", nothing new"))
        refused = new["weekly"]["refused"] + new["monthly"]["refused"]
        for r in refused:
            print(f"  refused: {r['id']} {signed(r['pct'])} ({r['why']})")
        status.record_success(SOURCE, records=len(new["entries"]), data_to=(new["entries"][0]["t"][:10] if new["entries"] else None),
                              note="updated" if not refused else f"updated; {len(refused)} price move(s) refused as implausible",
                              state={"refused": refused[:10]})
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        status.record_failure(SOURCE, f"{e.__class__.__name__}: {e}")
        print("failed, previous files kept:", e)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    sys.exit(0)
