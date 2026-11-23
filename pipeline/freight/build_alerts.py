"""
Build data/freight/alerts.json: the disruption banners of the site, with figures from the atlas's own data.

    python pipeline/freight/build_alerts.py

Written by hand, in pipeline/freight/alerts.json: the title, the text, the start, the event it links to (``event``: the
main one, the source of the banner and its "also" links; ``events``, optional: the list of all the events it links to, the
main one first), the passages it is about and, when it was done, the date the text was checked against its source (``checked``: only a text that was read
against the page it cites carries a date). Everything else is computed here (METHODOLOGY.md, section 5):

  * transits and estimated tonnes of each passage over the last 28 days, over the same days a year earlier, and the 2023
    average, from the ``compare`` block of data/freight/portwatch/<passage>.json (IMF PortWatch, written by
    build_portwatch.py), with the gap in per cent and the date of the last observation;
  * the severity, from the gap of the transits against the 2023 average at the worst of the alert's passages, with the
    thresholds below (the only place they are written);
  * the commodities: those whose "at least" share of seaborne trade through a passage of the alert is SHARE_MIN % or
    more, or whose "at least" tonnage is TONNES_MIN Mt or more (data/freight/chokepoints.json, ``estimates``);
  * the countries: for each of those commodities, the exporters and the importers that carry COUNTRY_MIN % or more of its
    "at least" tonnage through the passages, and every country with COUNTRY_MT_MIN Mt or more of cargo that has to cross
    them, whatever the commodity (data/freight/chokepoint-lanes.json).

An alert may carry an ``override`` with a reason, shown to the reader behind the banner's "Details":
``{"addCountries": ["IRN"], "reason": "..."}`` appends countries to the derived list (so it follows the data when they
change); ``{"commodities": [...], "countries": [...], "reason": "..."}`` replaces a derived list. The reason must come from
the atlas's own files.

Runs after build_portwatch.py (weekly job) and after build_freight.py (annual job). It never fails the job: an error is
recorded in data/_status/updates.json (source ``build-alerts``), the previous file is kept and the exit code is 0.
With --strict (the annual job, which records its own steps) the exit code is 1 on an error.
"""
import json
import os
import sys
import traceback
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

from common import status  # noqa: E402

SOURCE = "build-alerts"
FREIGHT = os.path.join(ROOT, "data", "freight")

# ---- the thresholds: written here and in METHODOLOGY.md, nowhere else ----
# Gap of the 28-day transits against the 2023 average, in per cent. The first level whose limit the gap reaches (or goes
# below) names the severity; a smaller gap is "low".
SEVERITY_LEVELS = (("high", -60.0), ("medium", -25.0))
LOWEST = "low"
SHARE_MIN = 10.0     # % of the seaborne trade of a commodity (the "at least" share of the estimate)
TONNES_MIN = 50.0    # Mt (the "at least" tonnage of the estimate)
COUNTRY_MIN = 15.0   # % of the tonnage of one commodity through the passages, for an exporter or an importer
COUNTRY_MT_MIN = 20.0  # Mt of cargo, all commodities, that has to cross the passages: a country with this much is in as well

MEASURE_SOURCE = "portwatch"


def load(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return json.load(fh)


def gap_pct(now, ref):
    """(now - ref) / ref in per cent, one decimal; None when a figure is missing or the reference is zero."""
    if now is None or not ref:
        return None
    return round((now / ref - 1) * 100, 1)


def severity_of(gap):
    """high, medium or low from a gap in per cent; None when there is no gap."""
    if gap is None:
        return None
    for name, limit in SEVERITY_LEVELS:
        if gap <= limit:
            return name
    return LOWEST


def severity_note(worst):
    """The rule in words (the title attribute of the severity on the banner), then the passage that decided it."""
    (hi, hl), (me, ml) = SEVERITY_LEVELS
    rule = (f"Severity from the 28-day transits against the 2023 average: {hi} when {abs(hl):.0f}% or more below, "
            f"{me} when {abs(ml):.0f}% or more below, otherwise {LOWEST}.")
    if worst:
        rule += f" Decided by {worst['name']}: {abs(worst['gap2023']):.0f}% {'below' if worst['gap2023'] < 0 else 'above'}."
    return rule


def measure(cid, name, series):
    """The comparison figures of one passage from its series file (``compare`` block), or None when it has none."""
    cmp_ = series.get("compare")
    if not cmp_:
        return None
    t, m = cmp_["transits"], cmp_["mt"]
    return {
        "chokepoint": cid, "name": name, "to": cmp_["to"], "days": cmp_["days"], "yearAgoTo": cmp_["yearAgoTo"],
        "refYear": cmp_["refYear"], "transits": t, "mt": m,
        "gapYear": gap_pct(t["now"], t["yearAgo"]), "gap2023": gap_pct(t["now"], t["avg2023"]),
        "gapMtYear": gap_pct(m["now"], m["yearAgo"]), "gapMt2023": gap_pct(m["now"], m["avg2023"]),
        "s": MEASURE_SOURCE,
    }


def exposed_commodities(chk_by_id, cids):
    """Commodity ids whose "at least" share or tonnage through one of ``cids`` reaches the thresholds, with the figures
    behind the largest: [(commodity, share %, Mt, passage)], largest share first."""
    best = {}
    for cid in cids:
        for e in chk_by_id.get(cid, {}).get("estimates", []):
            share, tonnes = e["f"]["v"], (e.get("mt") or [0])[0]
            if share >= SHARE_MIN or tonnes >= TONNES_MIN:
                cur = best.get(e["k"])
                if cur is None or share > cur[1]:
                    best[e["k"]] = (e["k"], share, tonnes, cid)
    return sorted(best.values(), key=lambda x: (-x[1], x[0]))


def exposed_countries(lanes, cids, commodities):
    """Exporters and importers that carry COUNTRY_MIN % or more of the "at least" tonnage of one of ``commodities``
    through ``cids`` (a pair that crosses two of the passages counts once). Returns (exporters, importers), the
    countries with the most tonnage first."""
    groups = lanes["groups"]
    pairs = {}
    for cid in cids:
        for row in lanes["chokepoints"].get(cid, []):
            g, o, d, mt = row[:4]
            k = groups.get(g, {}).get("k")
            if (row[4] if len(row) > 4 else 1) == 1 and k in commodities:
                pairs[(g, o, d)] = (k, mt)
    total = {}
    for k, mt in pairs.values():
        total[k] = total.get(k, 0.0) + mt
    out = []
    for idx in (1, 2):
        by, listed = {}, {}
        for key, (k, mt) in pairs.items():
            c = key[idx]
            by[(k, c)] = by.get((k, c), 0.0) + mt
            listed[c] = listed.get(c, 0.0) + mt
        keep = {c for (k, c), mt in by.items() if 100 * mt / total[k] >= COUNTRY_MIN}
        out.append(sorted(keep, key=lambda c: (-listed[c], c)))
    return out[0], out[1]


def heavy_countries(lanes, cids):
    """Countries (origin or destination) with COUNTRY_MT_MIN Mt or more of cargo that has to cross one of ``cids``, a pair
    that crosses two of them counting once: [(country, Mt)], most tonnage first."""
    pairs = {}
    for cid in cids:
        for row in lanes["chokepoints"].get(cid, []):
            g, o, d, mt = row[:4]
            if (row[4] if len(row) > 4 else 1) == 1:
                pairs[(g, o, d)] = mt
    tot = {}
    for (_, o, d), mt in pairs.items():
        for c in {o, d}:
            tot[c] = tot.get(c, 0.0) + mt
    return sorted(((c, round(mt, 1)) for c, mt in tot.items() if mt >= COUNTRY_MT_MIN), key=lambda x: (-x[1], x[0]))


def event_ids(hand):
    """The events an alert points to, the main one first: ``events`` (a list, whose first id is ``event``) or ``event`` alone."""
    ids = hand.get("events", [hand.get("event")])
    if not isinstance(ids, list) or any(not isinstance(i, str) or not i for i in ids) or not ids:
        raise ValueError(f"alert {hand['id']}: 'events' must be a list of event ids, 'event' an event id")
    if hand.get("event") != ids[0]:
        raise ValueError(f"alert {hand['id']}: 'event' (the main event) must be the first of 'events'")
    if len(set(ids)) != len(ids):
        raise ValueError(f"alert {hand['id']}: an event is listed twice")
    return ids


def build_alert(hand, events, chk_by_id, lanes, series_dir):
    cids = hand["chokepoints"]
    for cid in cids:
        if cid not in chk_by_id:
            raise ValueError(f"alert {hand['id']}: unknown chokepoint {cid}")
    ids = event_ids(hand)
    for i in ids:
        if i not in events:
            raise ValueError(f"alert {hand['id']} points to unknown event {i}")
    ev = events[ids[0]]
    measures = []
    for cid in cids:
        path = os.path.join(series_dir, cid + ".json")
        m = measure(cid, chk_by_id[cid]["name"], load(path)) if os.path.exists(path) else None
        if m:
            measures.append(m)
    # the worst passage decides: the lowest gap against the 2023 average (the year earlier when 2023 is missing)
    key = lambda m: m["gap2023"] if m["gap2023"] is not None else (m["gapYear"] if m["gapYear"] is not None else 1e9)  # noqa: E731
    worst = min(measures, key=key) if measures else None
    worst_gap = key(worst) if worst else None
    sev = severity_of(worst_gap if worst_gap is not None and worst_gap < 1e9 else None)
    expo = exposed_commodities(chk_by_id, cids)
    commodities = [x[0] for x in expo]
    exporters, importers = exposed_countries(lanes, cids, set(commodities))
    heavy = [c for c, _ in heavy_countries(lanes, cids)]
    countries = list(dict.fromkeys(exporters + importers + heavy))
    out = {
        "id": hand["id"], "title": hand["title"], "since": hand["since"], "severity": sev,
        "text": hand["text"], "event": ids[0], "events": ids, "src": ev["src"],
        "chokepoints": cids, "measures": measures,
        "severityNote": severity_note(worst if worst and worst["gap2023"] is not None else None),
        "commodities": commodities, "countries": countries, "exporters": exporters, "importers": importers,
        "derived": f"Commodities: at least {SHARE_MIN:.0f}% of their seaborne trade, or {TONNES_MIN:.0f} Mt, has to cross "
                   f"{' or '.join(chk_by_id[c]['name'] for c in cids)} (Atlas estimate, {lanes['y']}). Countries: for each of those "
                   f"commodities, the exporters and importers with at least {COUNTRY_MIN:.0f}% of its tonnage through the passage, "
                   f"and every country with at least {COUNTRY_MT_MIN:.0f} Mt of cargo, of any kind, that has to cross it.",
    }
    if ev.get("also"):
        out["also"] = ev["also"]
    if hand.get("checked"):
        out["checked"] = hand["checked"]
    if worst and worst["gap2023"] is not None:
        out["decidedBy"] = {"chokepoint": worst["chokepoint"], "name": worst["name"], "gap": worst["gap2023"], "refYear": worst["refYear"]}
    ov = hand.get("override")
    if ov:
        if not ov.get("reason"):
            raise ValueError(f"alert {hand['id']}: an override needs a reason")
        for k in ("commodities", "countries"):
            if k in ov:
                out[k] = ov[k]
        add = ov.get("addCountries") or []
        out["countries"] = list(dict.fromkeys(out["countries"] + add))
        out["override"] = {k: v for k, v in ov.items() if k in ("commodities", "countries", "addCountries", "reason")}
    return out


def build(hand_alerts, events, chk, lanes, series_dir):
    chk_by_id = {c["id"]: c for c in chk}
    ev = {e["id"]: e for e in events}
    seen = set()
    out = []
    for h in hand_alerts:
        if h["id"] in seen:
            raise ValueError("duplicate alert id " + h["id"])
        seen.add(h["id"])
        if h.get("checked"):
            date.fromisoformat(h["checked"])
        out.append(build_alert(h, ev, chk_by_id, lanes, series_dir))
    return out


def build_files():
    """Read the inputs, build the alerts and write data/freight/alerts.json; returns the alerts. Raises when an input is
    missing or an alert has no PortWatch figure."""
    hand = load(HERE, "alerts.json")
    events = load(HERE, "events.json")
    chk = load(FREIGHT, "chokepoints.json")
    lanes = load(FREIGHT, "chokepoint-lanes.json")
    path = os.path.join(FREIGHT, "alerts.json")
    old = {a["id"]: a for a in (load(path) if os.path.exists(path) else [])}
    alerts = build(hand, events, chk, lanes, os.path.join(FREIGHT, "portwatch"))
    if not alerts or any(not a["measures"] for a in alerts):
        raise ValueError("an alert has no PortWatch figure")
    for a in alerts:
        was = old.get(a["id"], {}).get("severity")
        print(f"  {a['id']}: {a['severity']}" + (f" (was {was})" if was and was != a["severity"] else "") +
              f"; {len(a['commodities'])} commodities, {len(a['countries'])} countries; data to {a['measures'][0]['to']}")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(alerts, fh, indent=0, ensure_ascii=False)
    os.replace(tmp, path)
    return alerts


def main(strict=False):
    """Weekly job: record the outcome in the status file and never fail. ``strict`` (the annual job, which records its
    own steps): leave the error to the caller."""
    try:
        alerts = build_files()
        if not strict:
            status.record_success(SOURCE, records=len(alerts), data_to=max(m["to"] for a in alerts for m in a["measures"]))
    except Exception as e:  # noqa: BLE001
        if strict:
            raise
        if not isinstance(e, (ValueError, KeyError, OSError)):
            traceback.print_exc()
        status.record_failure(SOURCE, f"{e.__class__.__name__}: {e}")
        print("failed, previous file kept:", e)


if __name__ == "__main__":
    try:
        main(strict="--strict" in sys.argv)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
