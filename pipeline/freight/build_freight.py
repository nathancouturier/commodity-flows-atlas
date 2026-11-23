"""
Build the freight layer files served by the site (run after build_lanes.py).

    python pipeline/freight/build_freight.py

Inputs (curated, in pipeline/freight/): routes_def.json, vessel_classes.json, chokepoints.json,
events.json, sources_*.json; BACI cache (cleaned and classed by mode as in build_lanes.py);
data/freight/pairs/<group>.json and lanes/<group>.json (build_lanes.py); raw/portwatch/*.json (optional,
for transit series and the volumes by vessel type); data/freight/portwatch/*.json (tracked: the chokepoint
traffic figures are copied from these files, so a rebuild without raw/ keeps them).
Outputs (data/freight/): routes.json, routes.geo.json, vessel-classes.json, chokepoints.json,
events.json, portwatch/<chokepoint>.json, chokepoint-lanes.json; merges new sources into data/sources.json;
the K9 records of pipeline/cache/trade_checks.json (passages against IMF PortWatch).

Chokepoint shares (METHODOLOGY.md, section 5; trade-engine plan 2.6): over every recorded seaborne pair of
the pairs table, "at least" counts the pairs whose assumed route has to cross the passage (`via`), "up to"
adds the pairs that may cross it (`viaAlt`); both are shares of the group's seaborne tonnes. Routes are
planned with routing.plan() like the lanes.
"""
import glob
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import unquote

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ports as P  # noqa: E402
import build_lanes as BL  # noqa: E402
import build_portwatch as BW  # noqa: E402
import build_chokepoint_lanes as BCL  # noqa: E402
import routing as RT  # noqa: E402
import vessel_rules as VR  # noqa: E402
import route_countries as RC  # noqa: E402

sys.path.insert(0, os.path.join(HERE, "..", "trade"))
import caveats as CV  # noqa: E402
import checks as K  # noqa: E402
from clean import history_flags  # noqa: E402

ROOT = BL.ROOT
OUT = os.path.join(ROOT, "data", "freight")
RAW = os.path.join(ROOT, "raw")

# commodity id -> BACI groups used for corridor volumes
GROUPS_OF = {
    "thermal-coal": ["coal"], "met-coal": ["coal"], "copper": ["copper-ore"], "nickel": ["nickel-ore"],
    "phosphate": ["phosphate-rock", "dap"], "bauxite": ["bauxite"], "lithium": ["spodumene"],
}
# vessel size families used for the "share of class activity" estimate
FAMILY = {"vloc": "capesize", "newcastlemax": "capesize", "capesize": "capesize", "kamsarmax": "panamax", "panamax": "panamax",
          "ultramax": "supramax", "supramax": "supramax", "handysize": "handysize", "vlcc": "vlcc", "suezmax": "suezmax",
          "aframax": "aframax", "lr2": "lr2", "lr1": "lr1", "mr": "mr", "handy-tanker": "mr", "lng": "lng", "vlgc": "vlgc"}
# The class share is published only for classes whose cargo base the atlas covers almost completely.
# Elsewhere the atlas's commodity list leaves out the main cargoes (minor bulks, grain parcels, products of
# smaller tankers), so a share would divide one cargo by a fraction of the class's real work.
CLASS_SHARE_BASIS = {
    "capesize": "iron-ore, coal and bauxite", "vlcc": "crude-oil", "lng": "LNG", "vlgc": "LPG",
}
CLASS_SHARE_NAME = {"capesize": "Capesize, Newcastlemax and VLOC", "vlcc": "VLCC", "lng": "LNG carrier", "vlgc": "VLGC"}

# Chokepoint shares (plan 2.6). PortWatch counts by vessel type: these groups sail in tankers; the groups whose
# gateway segment is general cargo ("box" in ports.py: steel, refined copper, aluminium, coffee, cocoa, cotton; metal
# and soft families of modes.py) are compared with PortWatch's container, general-cargo and ro-ro ships; the others
# with its dry-bulk ships. An entry is written when the "up to" tonnage is at least 2% of the group or 1 Mt.
TANKER_GROUPS = {"crude-oil", "refined-products", "lng", "lpg", "palm-oil", "soyoil"}
CARGO_GROUPS = {g for g, s in P.SEGMENT.items() if s == "box"}
TYPES = ("dry", "tanker", "cargo")
TYPE_NAME = {"dry": "dry bulk", "tanker": "tanker", "cargo": "container, general cargo and ro-ro"}


def vessel_type(g):
    return "tanker" if g in TANKER_GROUPS else "cargo" if g in CARGO_GROUPS else "dry"


# Origins whose exports customs data miss (caveats): the passages of the routes to every buyer with at least this
# share of the origin's exports in the reference year are named in the notes.
UNRECORDED_BUYER_SHARE = 0.10
EST_MIN_SHARE, EST_MIN_MT = 0.02, 1.0
DEFINITION = ("every recorded seaborne pair whose assumed route has to cross this passage. Pairs that can use a parallel "
              "passage of similar length, pairs split between coasts, mixed sea-and-land pairs and trades that customs "
              "data do not record are not in it")
# K9: "at least" tonnage by vessel type against PortWatch's best full year since PW_FIRST_YEAR; a report, never a
# failure. The Danish Straits counter is the Oresund only, so no comparison is valid there.
PW_FIRST_YEAR, K9_MAX = 2019, 1.10
K9_NO_COMPARISON = {"danish-straits"}
# the shares of a vessel type get a note from this share of PortWatch's volume of the same type and year: the atlas's
# groups are not all the cargo of these ships, so an "at least" tonnage close to that volume leaves little room
PW_NEAR = 0.85
# QA.md: "at least" and "up to" of the parallel passages under other thresholds of the parallel rule (plan 2.5)
SENSITIVITY = ((0.03, 150), (0.05, 300), (0.10, 500))
SENSITIVITY_GATES = ("malacca", "sunda", "lombok", "taiwan-strait", "luzon")
# year the typical laden speeds of vessel_rules.SPEED were set (an Atlas assumption, published with s "atlas")
SPEED_YEAR = 2026


def mt(v):
    return f"{v:,.0f} Mt" if v >= 10 else f"{v:.1f} Mt" if v >= 1 else f"{v:.2f} Mt"


def mt3(v):
    """mt() with one more figure under 100 Mt, for comparisons of two close tonnages."""
    return f"{v:,.0f} Mt" if v >= 100 else f"{v:.1f} Mt" if v >= 1 else f"{v:.2f} Mt"


ACRONYM = {"lng": "LNG", "lpg": "LPG", "dap": "DAP", "nickel-int": "nickel intermediates", "copper-ore": "copper concentrate",
           "zinc-ore": "zinc concentrate", "copper-refined": "refined copper"}


def label_of(g):
    return ACRONYM.get(g) or K.label(g)


def load_pairs(path=None):
    """Pairs files of build_lanes.py, decoded: {group: {k, y, seaborne (Mt), rows: [{o, d, t (Mt), m, load, nm, cls,
    via (set), alt (set), f}]}}."""
    out = {}
    for f in sorted(glob.glob(os.path.join(path or os.path.join(OUT, "pairs"), "*.json"))):
        with open(f, encoding="utf-8") as fh:
            p = json.load(fh)
        gates, classes, rows = p["gates"], p["classes"], []
        for r in p["rows"]:
            x = dict(zip(p["cols"], r))
            x["t"] = x["kt"] / 1e3
            x["via"] = {g for i, g in enumerate(gates) if x["via"] >> i & 1}
            x["alt"] = {g for i, g in enumerate(gates) if x["alt"] >> i & 1} - x["via"]
            x["cls"] = classes[x["cls"]] if x["cls"] >= 0 else None
            rows.append(x)
        out[p["group"]] = {"k": p["k"], "y": p["y"], "seaborne": p["seaborne"] / 1e3, "rows": rows}
    return out


def frame():
    """The cleaned customs frame of build_lanes.py with the mode of every pair (sea, transit, mixed or land)."""
    df = pd.read_csv(os.path.join(BL.CACHE, "baci_flows.csv.gz"))
    df = BL.clean_baci(df[df["group"].isin(BL.GROUPS)]).reset_index(drop=True)
    kinds = {}
    for k in set(zip(df["o"], df["d"], df["group"])):
        m = BL.MD.mode_of(*k)
        kinds[k] = m.kind if m else "land"
    df["mode"] = [kinds[k] for k in zip(df["o"], df["d"], df["group"])]
    return df


def pw_volumes(chk, rows):
    """IMF PortWatch estimated trade volume, Mt per full calendar year: {chokepoint: {year: {dry, tanker, cargo, all}}}
    (cargo: container, general-cargo and ro-ro ships). From the daily raw rows when present, otherwise from the weekly
    series of data/freight/portwatch (Mt/day x the days of each week inside the year)."""
    out = defaultdict(dict)
    if rows:
        pw = pd.DataFrame(rows)
        ids = BW.mapped(chk)
        pw["y"] = pd.to_datetime(pw["date"]).dt.year
        pw["cargo"] = pw["capacity_container"].fillna(0) + pw["capacity_general_cargo"].fillna(0) + pw["capacity_roro"].fillna(0)
        agg = pw.groupby(["portid", "y"]).agg(n=("date", "size"), dry=("capacity_dry_bulk", "sum"),
                                               tanker=("capacity_tanker", "sum"), cargo=("cargo", "sum"), all=("capacity", "sum"))
        for (pid, y), r in agg.iterrows():
            if pid in ids and r["n"] >= 365:
                out[ids[pid]][int(y)] = {k: float(r[k]) / 1e6 for k in ("dry", "tanker", "cargo", "all")}
        return out
    for c in chk:
        path = os.path.join(OUT, "portwatch", c["id"] + ".json")
        if not c.get("portwatch") or not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            s = json.load(f)
        start, last, acc = date.fromisoformat(s["start"]), date.fromisoformat(s["y"]), defaultdict(lambda: defaultdict(float))
        for i in range(len(s["vol"]["total"])):
            for k in range(7):
                day = start + timedelta(days=7 * i + k)
                for t, key in (("dry", "dry"), ("tanker", "tanker"), ("cargo", "container"), ("cargo", "other"), ("all", "total")):
                    acc[day.year][t] += s["vol"][key][i]
        for y, v in acc.items():
            if date(y, 1, 1) >= start and date(y, 12, 31) <= last:
                out[c["id"]][y] = dict(v)
    return out


def best_year(vols, typ):
    ys = [(v[typ], y) for y, v in vols.items() if y >= PW_FIRST_YEAR]
    return max(ys) if ys else (None, None)


def unrecorded_through(df, active, latest):
    """Origins whose exports customs data do not record, or record only in part: {(group, chokepoint): [origin]} for
    the passages that the routes to the origin's buyers in a reference year cross or may cross (via and viaAlt of every
    seaborne buyer with at least UNRECORDED_BUYER_SHARE of the origin's exports that year). "unrecorded" caveats use
    the caveat's reference year; "break" caveats whose exports fell use the best of the five years before `latest`
    (the rule of caveats._break), and a break that is a rise is not read."""
    out = defaultdict(list)
    sea = df[df["mode"].isin(["sea", "transit"])]
    for e in active.values():
        if e["kind"] not in ("unrecorded", "break") or e.get("d"):
            continue
        ex = df[(df["group"] == e["group"]) & (df["o"] == e["o"])].groupby("year")["t"].sum()
        if e["kind"] == "unrecorded":
            ref = CV.REF_YEAR
        else:
            past = ex[(ex.index >= latest - 5) & (ex.index < latest)]
            if past.empty or ex.get(latest, 0.0) >= past.max():
                continue
            ref = int(past.idxmax())
        tot = ex.get(ref, 0.0)
        z = sea[(sea["group"] == e["group"]) & (sea["o"] == e["o"]) & (sea["year"] == ref)]
        gates = set()
        for r in z[z["t"] >= UNRECORDED_BUYER_SHARE * tot].itertuples(index=False):
            rec, _ = BL.route_pair(r.o, r.d, r.group, r.t, r.mode)
            if rec:
                gates |= set(rec["via"]) | {x for lst in rec["viaAlt"] for x in lst}
        for c in sorted(gates):
            out[(e["group"], c)].append(e["o"])
    return out


def _wiki_name(url):
    if url and "wikipedia.org/wiki/" in url:
        return "Wikipedia, " + unquote(url.rsplit("/", 1)[-1]).replace("_", " ")
    return url


def alert_reason(alerts, cid, latest):
    """The first sentence of a curated alert on the passage that was active in `latest`, quoted with its source; None
    when there is none (the atlas then states no cause)."""
    for a in alerts or []:
        if cid in a.get("chokepoints", []) and str(a.get("since", "9999"))[:4] <= str(latest):
            first = a["text"].split(". ")[0].rstrip(".")
            return f"The atlas's alert \"{a['title']}\" says: \"{first}\" ({_wiki_name(a.get('src'))})"
    return None


def chokepoint_shares(chk, pairs, pw, active, unrec, latest, alerts=None):
    """`estimates` of every chokepoint and the K9 records of the passages with a PortWatch counter."""
    k9 = []
    for c in chk:
        cid, est = c["id"], []
        if cid not in RT.GATES:
            continue
        own = c.get("portwatch") and not c.get("portwatchLabel")  # a counter of this passage, not of a part of it
        vols = pw.get(cid, {})
        pw_y = vols.get(latest, {})
        # first pass: low and high of every group, and their sums by vessel type (the cap and K9 need the sums)
        by_type = {t: [0.0, 0.0, defaultdict(float)] for t in TYPES}
        per_group = {}
        for g, p in pairs.items():
            typ = vessel_type(g)
            seaborne_rows = [r for r in p["rows"] if r["m"] in (0, 1)]
            low = sum(r["t"] for r in seaborne_rows if cid in r["via"])
            alt_by = defaultdict(float)
            for r in seaborne_rows:
                if cid in r["alt"]:
                    alt_by[r["o"]] += r["t"]
            high = low + sum(alt_by.values())
            by_type[typ][0] += low
            by_type[typ][1] += high
            for r in seaborne_rows:
                if cid in r["via"]:
                    by_type[typ][2][(g, r["o"], r["d"])] += r["t"]
            per_group[g] = (typ, seaborne_rows, low, high, alt_by)
        # the passage against PortWatch, by vessel type: a note on the shares of a type whose "at least" tonnage is
        # above PortWatch's volume of the same year, and the K9 records
        type_note = {}
        if c.get("portwatch") and vols:
            for typ, (low, high, pairs_t) in by_type.items():
                ref = pw_y.get(typ)
                best, by = best_year(vols, typ)
                if not best:
                    continue
                top = sorted(pairs_t.items(), key=lambda x: -x[1])[:3]
                text = (f"{c['name']}, {TYPE_NAME[typ]}: at least {mt3(low)} and up to {mt3(high)} of the atlas's seaborne groups in {latest}, "
                        f"against {mt3(ref) if ref is not None else 'no figure'} for all {TYPE_NAME[typ]} ships in IMF PortWatch {latest} "
                        f"(best full year since {PW_FIRST_YEAR}: {mt3(best)} in {by})")
                level = "qa"
                above = (f"The 'at least' tonnage of all {TYPE_NAME[typ]} cargo of the atlas through this passage ({mt3(low)}) is above "
                         f"IMF PortWatch's estimate for all {TYPE_NAME[typ]} ships" + (f" in {latest} ({mt3(ref)}; " if ref is not None else " (")
                         + f"{mt3(best)} in {by}, its best full year since {PW_FIRST_YEAR})")
                if cid in K9_NO_COMPARISON:
                    text += f"; the PortWatch counter is the {c.get('portwatchLabel') or 'part of the passage'}: no comparison is valid"
                elif low > K9_MAX * best:
                    level = "flag"
                    text += (f"; above {K9_MAX:.0%} of the best year: the ports or routes the atlas assumes probably overstate it. "
                             "Largest pairs: " + ", ".join(f"{label_of(g)} {K._name(o)} to {K._name(d)} {mt(v)}" for (g, o, d), v in top))
                    type_note[typ] = f"{above}: the assumed ports or routes probably overstate it"
                elif ref is not None and low > ref:
                    level = "flag"
                    reason = alert_reason(alerts, cid, latest)
                    text += (f"; above PortWatch's {latest} volume: the atlas routes cargo on the normal itinerary"
                             + (f". {reason}" if reason else ""))
                    type_note[typ] = (f"{above}. The atlas routes cargo on the normal itinerary, so this is the tonnage of the normal "
                                      f"route, not the {latest} traffic" + (f". {reason}" if reason else ""))
                elif ref and low > PW_NEAR * ref:
                    type_note[typ] = (f"The 'at least' tonnage of all {TYPE_NAME[typ]} cargo of the atlas through this passage ({mt3(low)}) is "
                                      f"{low / ref:.0%} of IMF PortWatch's estimate for all {TYPE_NAME[typ]} ships in {latest} ({mt3(ref)}), "
                                      f"although the atlas's groups are not all the cargo these ships carry: the ports or routes the atlas "
                                      "assumes may overstate it")
                k9.append({"check": "K9", "kind": "passage", "group": None, "year": latest, "chokepoint": cid, "type": typ,
                           "value": round(low, 1), "high": round(high, 1), "reference": None if ref is None else round(ref, 1),
                           "best": round(best, 1), "bestYear": by, "ratio": round(low / best, 2), "level": level, "text": text})
        # second pass: the entries
        for g, (typ, seaborne_rows, low, high, alt_by) in per_group.items():
            p = pairs[g]
            sea = p["seaborne"]
            if not sea or not (high >= EST_MIN_MT or high / sea >= EST_MIN_SHARE):
                continue
            label = label_of(g)
            n = [f"at least {mt(low)} of {mt(sea)} of seaborne {label}: {DEFINITION} (CEPII BACI {latest}, Atlas routing)"]
            unr = sum(r["t"] for r in seaborne_rows if r["load"] == -1)
            if unr >= 0.05:
                n.append(f"{mt(unr)} of seaborne {label} could not be routed (no gateway, no sourced transit port, or one port at both ends)")
            mixed = sum(r["t"] for r in p["rows"] if r["m"] == 2 and cid in r["via"] | r["alt"])
            if mixed >= 0.05:
                n.append(f"{mt(mixed)} of {label} that moves both by sea and overland (split not known) would cross it by sea and is not counted")
            names = [K._name(o) for o in unrec.get((g, cid), [])]
            if names:
                n.append(f"Exports that customs data do not record for {latest}, or record only in part, are missing: {', '.join(names)} "
                         "(see the caveat of each origin; before the gap, the routes to their main buyers cross this passage or may cross it)")
            # cap of the upper figure: PortWatch's volume of the type, less the "at least" tonnage of the other groups of
            # the type, never below this group's own "at least"
            hi_pub, room = high, None
            pw_t = pw_y.get(typ) if own else None
            if pw_t is not None:
                others = by_type[typ][0] - low
                room = max(low, pw_t - others)
                if high > room:
                    hi_pub = room
                    if room == low and high - low >= 0.05:
                        n.append(f"The pairs that may cross it ({mt(high - low)}) are not added: the 'at least' tonnage of all "
                                 f"{TYPE_NAME[typ]} cargo of the atlas here is already above IMF PortWatch's {latest} estimate")
            if typ in type_note:
                n.append(type_note[typ])
            e = {"k": BL.COMMODITY.get(g, g), "p": g,
                 "f": {"v": round(100 * low / sea, 1), "u": "%", "y": latest, "s": "atlas", "n": ". ".join(n)},
                 "mt": [round(low, 1 if low >= 10 else 3), round(hi_pub, 1 if hi_pub >= 10 else 3)]}
            if round(100 * hi_pub / sea, 1) > e["f"]["v"]:
                top = sorted(alt_by.items(), key=lambda x: -x[1])[:3]
                top = [x for x in top if x[1] >= 0.005] or top[:1]
                adds = ("adds the pairs that may cross it or a parallel passage of similar length, or may load or discharge on "
                        "another coast (largest: " + ", ".join(f"{K._name(o)} {mt(v)}" for o, v in top) + ")")
                hn = f"up to {mt(high)}: {adds}"
                if hi_pub < high:
                    others = by_type[typ][0] - low
                    less = (f" less the 'at least' tonnage of the atlas's other {TYPE_NAME[typ]} groups ({mt(others)})" if others >= 0.05 else
                            f" (the atlas's other {TYPE_NAME[typ]} groups have almost no 'at least' tonnage here)")
                    hn = (f"up to {mt(hi_pub)}: capped at IMF PortWatch's estimate of the cargo of all {TYPE_NAME[typ]} ships through the "
                          f"passage in {latest} ({mt(pw_t)}, IMF PortWatch, data adapted){less}, which this cargo "
                          f"cannot exceed; without the cap, {mt(high)}: {adds}")
                e["hi"] = {"v": round(100 * hi_pub / sea, 1), "u": "%", "y": latest, "s": "atlas", "n": hn}
            est.append(e)
        est.sort(key=lambda e: -e["f"]["v"])
        if est:
            c["estimates"] = est
        else:
            c.pop("estimates", None)
    return k9


class _NotCached(Exception):
    pass


def _no_routing(*args, **kwargs):
    raise _NotCached


def sensitivity(df, pairs, latest):
    """K9 records (QA only) of the parallel passages under the thresholds of SENSITIVITY, recomputed with
    routing.classify() from the option distances that build_lanes.py cached. Nothing is routed here: a pair whose
    plan is not in the caches is skipped and counted."""
    if len(BL._plans) <= 1:
        print("sensitivity: route cache empty or of another version, skipped")
        return []
    tonnes = {(r.group, r.o, r.d): (r.t, r.mode) for r in df[df["year"] == latest].itertuples(index=False)}
    acc = {k: {c: [0.0, 0.0] for c in SENSITIVITY_GATES} for k in SENSITIVITY}
    skipped, real = 0.0, RT.plan
    RT.plan = _no_routing
    try:
        for g, p in pairs.items():
            for r in p["rows"]:
                if r["m"] not in (0, 1) or r["load"] == -1 or not set(SENSITIVITY_GATES) & (r["via"] | r["alt"]):
                    continue
                t, kind = tonnes.get((g, r["o"], r["d"]), (None, None))
                try:
                    rec, _ = BL.route_pair(r["o"], r["d"], g, t, kind) if t else (None, None)
                except _NotCached:
                    rec = None
                if not rec:
                    skipped += r["t"]
                    continue
                for pct, nm in SENSITIVITY:
                    sums = []
                    for s in rec["plans"]:
                        v, va = RT.classify(s["route"], s["par"], rec["classes"], pct, nm)
                        sums.append({"via": v, "viaAlt": va})
                    via, lists = BL.combine(sums)
                    alt = {x for lst in lists for x in lst}
                    for c in SENSITIVITY_GATES:
                        if c in via:
                            acc[(pct, nm)][c][0] += r["t"]
                        if c in via or c in alt:
                            acc[(pct, nm)][c][1] += r["t"]
    finally:
        RT.plan = real
    out = []
    # incomplete when pairs were skipped: every figure is then short by up to the skipped tonnage, and the 5% or 300 nm
    # column does not reproduce the published figures
    complete = round(skipped, 1) == 0
    for (pct, nm), by in acc.items():
        for c, (low, high) in by.items():
            out.append({"check": "K9", "kind": "parallel", "group": None, "year": latest, "chokepoint": c, "pct": pct, "nm": nm,
                        "value": round(low, 1), "high": round(high, 1), "skipped": round(skipped, 1), "complete": complete, "level": "qa",
                        "text": f"{c}: at least {mt(low)}, up to {mt(high)} with parallel passages within {pct:.0%} or {nm} nm"
                                + ("" if complete else f" (incomplete: {mt(skipped)} of pairs not recomputed)")})
    return out


def eia_ratio(chk, latest):
    """K9 records (QA only): EIA's crude oil flow through a passage (mb/d) in Mt a year next to the atlas's range,
    converted with EIA's own barrels-per-tonne ratio (checks.barrels_per_tonne)."""
    try:
        eia = K.eia_series([("57-1", "MT"), ("57-1", "TBPD")])
        bpt = K.barrels_per_tonne(eia) if eia else None
    except Exception as e:  # a QA line only: never stops the build
        print(f"eia ratio skipped ({type(e).__name__}: {e})")
        return []
    if not bpt:
        return []
    out = []
    for c in chk:
        e = next((x for x in c.get("estimates", []) if x["p"] == "crude-oil"), None)
        s = next((x for x in c.get("shares", []) if x["k"] == "crude-oil" and x["f"]["u"] == "mb/d"), None)
        if e and s:
            v = s["f"]["v"] * 1e3 * 365 / bpt / 1e3  # mb/d -> Mt a year
            out.append({"check": "K9", "kind": "eia", "group": "crude-oil", "year": latest, "chokepoint": c["id"], "value": e["mt"][0],
                        "high": e["mt"][1], "reference": round(v, 1), "ratio": round(e["mt"][0] / v, 2), "level": "qa",
                        "text": (f"{c['name']}, crude oil: EIA {s['f']['v']} mb/d ({s['f']['y']}, {s['f']['s']}) is about "
                                 f"{mt(v)} a year at {bpt:.2f} barrels per tonne; the atlas gives at least {mt(e['mt'][0])} and up to "
                                 f"{mt(e['mt'][1])} in {latest} (ratio of the 'at least' figure: {e['mt'][0] / v:.2f})")})
    return out


def bypass_notes(chk, reg):
    """Alternatives that name pipelines of the atlas's layer get their capacities from it, with the source."""
    with open(os.path.join(ROOT, "data", "infrastructure", "pipelines.geojson"), encoding="utf-8") as f:
        layer = {x["properties"]["id"]: x["properties"] for x in json.load(f)["features"]}
    names = {s["id"]: s["name"] for s in reg}
    names["wikipedia"] = "Wikipedia"
    for c in chk:
        for a in c.get("alternatives", []):
            ids = a.pop("pipelines", None)
            if not ids:
                continue
            parts = []
            for i in ids:
                p = layer.get(i)
                if p and p.get("capacity"):
                    cap = p["capacity"]
                    parts.append(f"{p['name']} {cap['v']:,} {cap['u']}")
            if parts:
                # the layer's year of reading: `y`, or `read` (year-month) in the newer infrastructure shape
                src = sorted({f"{names.get(layer[i]['s'], layer[i]['s'])}, {layer[i].get('y') or str(layer[i].get('read', ''))[:4]}"
                              for i in ids if i in layer})
                lead = "Stated capacities in the atlas's pipeline layer: " + "; ".join(parts) + f" ({'; '.join(src)})"
                a["note"] = lead + (". " + a["note"] if a.get("note") else "")


# Time-charter trips and round voyages have delivery/redelivery areas rather than ports.
# They are drawn as their typical laden leg: (load port, discharge port).
ROUTE_PORTS = {
    "C10_14": ("AUPHE", "CNTAO"), "C14": ("BRTUB", "CNTAO"), "P1A_82": ("USMSY", "NLRTM"), "P2A_82": ("USMSY", "TWKHH"),
    "P3A_82": ("CAVAN", "JPCHB"), "P6_82": ("BRSSZ", "SGSIN"), "S2_63": ("AUNTL", "CNTAO"), "S10_63": ("IDSRI", "CNZHA"),
    "HS1_38": ("NLRTM", "BRSSZ"), "HS2_38": ("NLRTM", "USHOU"), "HS3_38": ("ARUPR", "NLRTM"), "HS4_38": ("USMSY", "NLRTM"),
    "HS5_38": ("IDBPN", "JPYOK"), "HS6_38": ("CNTSN", "JPCHB"), "HS7_38": ("CNTSN", "SGSIN"), "TC20": ("SAJUB", "NLRTM"),
    "TC21": ("USHOU", "JMKIN"),
    # partial overrides (None = use the port matched from the route definition)
    "uspnw-asia-grain": ("USKAM", None), "brazil-china-vloc-iron-ore": ("BRPMA", "CNNGB"), "simandou-china-iron-ore": (None, "CNNGB"), "TD34": ("OMMFH", None),
}


def load(name):
    return json.load(open(os.path.join(HERE, name)))


def find_port(name, iso3, group):
    """Match a port name from the route definitions to the port table; fall back to the country gateway."""
    a2 = BL.A2.get(iso3)
    n = name.lower().replace("ã", "a").replace("é", "e")
    for code, (pn, c, x, y) in P.MANUAL.items():
        if c == iso3 and (n in pn.lower() or pn.lower().split(" ")[0] in n):
            return code
    best = None
    for code, (pn, _) in P._sr.items():
        if code[:2] == a2 and (n == pn.lower() or n in pn.lower() or pn.lower() in n):
            if best is None or len(pn) < len(P._sr[best][0]):
                best = code
    return best or BL.gateway(iso3, group)


def main():
    t_start = time.time()
    pairs = load_pairs()  # every recorded pair of the latest year (build_lanes.py)
    latest = max(p["y"] for p in pairs.values())
    years = list(range(BL.LATEST_MIN_YEAR, latest + 1))
    df = frame()
    sea = df[df["mode"].isin(["sea", "transit"])]
    mixed = df[df["mode"] == "mixed"]
    sea_tot = {g: p["seaborne"] for g, p in pairs.items()}  # Mt: the denominator of every share
    main_lanes = []
    for f in sorted(glob.glob(os.path.join(OUT, "lanes", "*.json"))):
        with open(f, encoding="utf-8") as fh:
            main_lanes += [ln for ln in json.load(fh)["lanes"] if ln["set"] == "main" and ln.get("mode") != "mixed"]
    with open(os.path.join(OUT, "caveats.json"), encoding="utf-8") as f:
        active = json.load(f)

    # tonne-miles of every routed seaborne pair of the latest year, by vessel size family (Atlas estimate): tonnes x
    # the routed distance of the pair's main port option, class = its primary class (pairs table)
    pair_tm = {}
    class_tm = defaultdict(float)
    for g, p in pairs.items():
        for r in p["rows"]:
            if r["m"] in (0, 1) and r["nm"] > 0 and r["cls"]:
                pair_tm[(g, r["o"], r["d"])] = r["t"] * r["nm"]
                class_tm[FAMILY.get(r["cls"], r["cls"])] += r["t"] * r["nm"]

    routes, feats = [], []
    for r in load("routes_def.json"):
        cor = r.get("corridor") or []
        k0 = (r.get("cargoes") or [None])[0]
        g0 = (GROUPS_OF.get(k0) or [k0])[0] if k0 else "iron-ore"
        a = b = None
        if r["id"] in ROUTE_PORTS:
            a, b = ROUTE_PORTS[r["id"]]
        if a is None:
            fp = r["from"]["ports"][0]
            a = find_port(fp["name"], fp["c"], g0)
        if b is None:
            tp = r["to"]["ports"][0]
            b = find_port(tp["name"], tp["c"], g0)
        out = {k: r[k] for k in ("id", "name", "benchmark", "vclass", "cargoes", "notes", "s") if k in r}
        if r.get("discontinued"):
            out["discontinued"] = r["discontinued"]
        if r.get("standIn"):
            out["standIn"] = r["standIn"]
        if cor:
            out["corridor"] = cor
        if r.get("roundVoyage"):
            out["roundVoyage"] = True
        if r.get("parcel"):
            out["parcel"] = r["parcel"]
            out["parcelUnit"] = r.get("parcelUnit", "t")
        out["from"] = {"region": r["from"]["region"], "ports": [p["name"] for p in r["from"]["ports"]]}
        out["to"] = {"region": r["to"]["region"], "ports": [p["name"] for p in r["to"]["ports"]]}
        if r["id"] in ROUTE_PORTS and None not in ROUTE_PORTS[r["id"]]:
            out["drawnAs"] = "typical laden leg"
        if not a or not b:
            print("skip (no port)", r["id"])
            continue
        pa, pb = P.port(a), P.port(b)
        spd = VR.speed(r["vclass"])
        s = BL.plan_summary(pa["at"], pb["at"], [r["vclass"]], geometry=True)  # routing.plan(), as the lanes
        if not s:
            print("skip (no path)", r["id"])
            continue
        nm, via = s["nm"], s["via"]
        out.update({"distanceNm": nm, "speedKn": spd, "days": round(nm / (spd * 24), 1), "via": via, "viaAlt": s["viaAlt"],
                    "a": pa["at"], "b": pb["at"]})
        st = BL.status_of(via, {x for lst in s["viaAlt"] for x in lst})
        if st:
            out["status"] = st
        feats.append({"type": "Feature", "properties": {"id": r["id"], "kind": "route"}, "geometry": {"type": "LineString", "coordinates": s["g"]}})
        alts = []
        for x in s["alts"]:
            x = {k: v for k, v in x.items() if k != "g"}
            if x.pop("redSea", False):
                x["status"] = [{"text": BL.DISRUPTIONS[0][2], "event": BL.DISRUPTIONS[0][1]}]
            alts.append(x)
        if alts:
            out["alt"] = alts[0]
            out["alts"] = alts
            feats.append({"type": "Feature", "properties": {"id": r["id"] + ":alt", "kind": "alt"},
                          "geometry": {"type": "LineString", "coordinates": s["alts"][0]["g"]}})
        if s.get("altNote"):
            out["altNote"] = s["altNote"]

        # corridor volumes from customs data (cleaned seaborne pairs; a mixed pair only where the corridor has no
        # seaborne flow, as a customs total for all modes). A customs group is counted once per country pair and
        # route: thermal and metallurgical coal are the same group "coal".
        shares, hist_t, hist_v, cor_tm, tiny, mixed_na = [], defaultdict(float), defaultdict(float), 0.0, [], []
        counted, late = set(), []  # late: (first year, note) of a group whose reading starts after LATEST_MIN_YEAR
        for c in cor:
            groups = GROUPS_OF.get(c["k"], [c["k"]])
            fresh = {(g, o, d) for g in groups for o in c["o"] for d in c["d"]} - counted
            if not fresh:
                continue
            counted |= fresh

            def pick(x):
                x = x[x["group"].isin(groups) & x["o"].isin(c["o"]) & x["d"].isin(c["d"])]
                return x[pd.MultiIndex.from_frame(x[["group", "o", "d"]]).isin(list(fresh))]
            sub, subm = pick(sea), pick(mixed)
            tot = sum(sea_tot.get(g, 0.0) for g in groups)
            v = sub[sub["year"] == latest]["t"].sum() / 1e6
            vm = subm[subm["year"] == latest]["t"].sum() / 1e6
            word = "all-coal (thermal and metallurgical)" if groups == ["coal"] else c["k"].replace("-", " ")
            lead = "Country-pair corridor (all ports and vessel sizes, not this route's ports alone)"
            if v <= 0 and vm > 0:
                # no known seaborne tonnage: no share (its numerator would be all modes over a seaborne total); the
                # all-modes volume is given in shareNa and its history is labelled all modes
                sub = subm
                ends = lambda cs: " and ".join(K._name(x) for x in cs) if len(cs) <= 2 else "these countries"  # noqa: E731
                n = (f"{ends(c['o'])} and {ends(c['d'])} trade {word} both by sea and overland and the split is not known: "
                     f"{vm:.1f} Mt in {latest} for all modes (CEPII BACI customs data)")
                if tot > 0:
                    n += f", which would be {100 * vm / tot:.1f}% of the {tot:,.0f} Mt of seaborne {word} trade only if all of it went by sea"
                mixed_na.append(n)
            else:
                n = f"{lead}: {v:.1f} Mt of {tot:.0f} Mt seaborne {word} trade, CEPII BACI customs data"
                if vm >= 0.05:
                    n += f"; a further {vm:.1f} Mt move both by sea and overland (split not known) and are not counted"
            n += ". Routes that share a country pair show the same tonnes: do not add them up"
            share = round(100 * v / tot, 1) if v > 0 and tot > 0 else 0.0
            if share > 0:
                shares.append({"k": c["k"], "f": {"v": share, "u": "%", "y": latest, "s": "atlas", "n": n}})
            elif v > 0 and tot > 0:
                tiny.append((c["k"], v, tot, groups))
            per_year = sub.groupby("year").agg(t=("t", "sum"), usd=("usd", "sum"))
            late += [BL.FIRST_YEAR[g] for g in groups if g in BL.FIRST_YEAR]
            y0 = max((f[0] for f in late), default=None)
            for y in years:
                if y in per_year.index and not (y0 and y < y0):
                    hist_t[y] += per_year.at[y, "t"] / 1e6
                    hist_v[y] += per_year.at[y, "usd"]
            cor_tm += sum(pair_tm.get(p, 0.0) for p in fresh)
        if shares:
            out["shares"] = shares
            out["shareCommodity"] = shares[0]["f"]
            fam = FAMILY.get(r["vclass"], r["vclass"])
            if fam in CLASS_SHARE_BASIS and class_tm.get(fam) and cor_tm:
                out["shareClass"] = {"v": round(100 * cor_tm / class_tm[fam], 1), "u": "%", "y": latest, "s": "atlas",
                                     "n": f"Atlas estimate: tonne-miles of this corridor (tonnes x routed distance of each pair's main port option) as a share of the tonne-miles of all routed seaborne {CLASS_SHARE_BASIS[fam]} flows whose typical main class is {CLASS_SHARE_NAME[fam]}. It is not a measured fleet share, and routes that share a corridor count the same tonnes"}
        elif cor:
            # no share to show: say why instead of printing 0.0 %
            if r.get("shareNa"):
                out["shareNa"] = r["shareNa"]
            elif mixed_na:
                out["shareNa"] = ". ".join(mixed_na)
            elif tiny:
                k, v, tot, groups = tiny[0]
                out["shareNa"] = f"Corridor volume in {latest} is {v:.2f} Mt, under 0.05% of the {tot:.0f} Mt of seaborne {'coal' if groups == ['coal'] else k.replace('-', ' ')} trade: too small for a meaningful share"
            else:
                out["shareNa"] = f"The atlas's seaborne customs table holds no flow for this country pair in {latest}"
        elif r.get("shareNa"):
            out["shareNa"] = r["shareNa"]
        elif r.get("discontinued"):
            out["shareNa"] = "Discontinued benchmark: no corridor volume is attached to it"
        elif "time-charter" in (r.get("notes") or "").lower():
            out["shareNa"] = "Time-charter benchmark: it is priced between a delivery and a redelivery area, not for one country-pair flow"
        else:
            out["shareNa"] = "No country-pair corridor is attached to this route"
        if any(hist_t.values()) and not r.get("noHistory"):
            # the history rule of the lanes: a year is blanked only on evidence in the unit value
            series, marks = history_flags([round(hist_t[y], 2) for y in years], [hist_v[y] for y in years])
            y0 = max((f[0] for f in late), default=0)
            out["history"] = [{"y": y, "v": v} for y, v in zip(years, series) if v is not None and y >= y0]
            hn = BL.hist_note({str(years[i]): m for i, m in marks.items() if m != "kept"}, years)
            if mixed_na:
                hn = "All modes: the volume includes trade that moves both by sea and overland (split not known)" + (f". {hn}" if hn else "")
            if late:
                hn = max(late)[1] + (f". {hn}" if hn else "")
            if hn:
                out["historyNote"] = hn
            out["historyUnit"] = "Mt"
            out["historySrc"] = "atlas" if any(g in BL.EST_GROUP for c in cor for g in GROUPS_OF.get(c["k"], [c["k"]])) else "baci"
        routes.append(out)

    os.makedirs(OUT, exist_ok=True)
    RC.add_end_countries(routes)  # load / discharge country of each route end (site: country isolation)
    json.dump(routes, open(os.path.join(OUT, "routes.json"), "w"), separators=(",", ":"))
    json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(OUT, "routes.geo.json"), "w"), separators=(",", ":"))
    print("routes", len(routes), "with shares", sum(1 for r in routes if r.get("shares")))

    # vessel classes (with the typical laden speed used for laden days), events: pass through
    vcs = load("vessel_classes.json")
    for vc in vcs:
        vc["speedKn"] = VR.speed(vc["id"])
        vc["speedNote"] = ("Atlas assumption: an assumed typical laden service speed of the class, not a measured speed and not "
                           "from a published source. It is used for laden days (distance divided by speed) on routes and in the "
                           "Route finder")
        # the same figure in the atlas's figure shape (source and year); speedKn and speedNote stay for the site
        vc["speed"] = {"v": vc["speedKn"], "u": "kn", "y": SPEED_YEAR, "s": "atlas", "n": vc["speedNote"]}
    json.dump(vcs, open(os.path.join(OUT, "vessel-classes.json"), "w"), indent=0)
    events = sorted(load("events.json"), key=lambda e: e["date"])
    json.dump(events, open(os.path.join(OUT, "events.json"), "w"), indent=0)
    # active disruptions shown as banners (curated; each links to an event with its source)
    alerts = load("alerts.json")
    ev_ids = {e["id"] for e in events}
    for a in alerts:
        assert a["event"] in ev_ids, f"alert {a['id']} points to unknown event {a['event']}"
        a["src"] = next(e["src"] for e in events if e["id"] == a["event"])
    json.dump(alerts, open(os.path.join(OUT, "alerts.json"), "w"), indent=0)

    # chokepoints: Atlas estimates of the share of every lane group's seaborne trade (pairs table), against PortWatch
    chk = load("chokepoints.json")
    reg = json.load(open(os.path.join(ROOT, "data", "sources.json")))
    bypass_notes(chk, reg)
    rows = BW.read_rows(os.path.join(RAW, "portwatch"))
    pw = pw_volumes(chk, rows)
    k9 = chokepoint_shares(chk, pairs, pw, active, unrecorded_through(df, active, latest), latest, alerts)
    for c in chk:
        # typical detour when this chokepoint is avoided (main seaborne lanes with an alternative that avoids it)
        det = []
        for ln in main_lanes:
            a = next((x for x in ln.get("alts") or [] if c["id"] in (x.get("avoids") or [])), None)
            if a and c["id"] in ln["via"] and ln["flow"]["v"] > 0.5:
                det.append((ln["flow"]["v"], a["distanceNm"] - ln["distanceNm"], a["extraDays"]))
        if len(det) >= 3:
            det.sort(key=lambda x: x[1])
            tot = sum(w for w, _, _ in det)
            acc, med = 0.0, det[0]
            for x in det:
                acc += x[0]
                if acc >= tot / 2:
                    med = x
                    break
            c["detour"] = {"nm": round(med[1]), "days": round(med[2], 1), "lanes": len(det), "y": latest, "s": "atlas",
                           "n": f"Volume-weighted median over {len(det)} mapped lanes that use this passage, at each lane's typical laden speed"}

    # PortWatch weekly transit series per chokepoint (logic shared with build_portwatch.py)
    if rows:
        BW.build(rows, chk, os.path.join(OUT, "portwatch"))
    BCL.build()  # recorded seaborne pairs through each chokepoint, from the pairs files written by build_lanes.py
    # traffic figures always come from the tracked series files, with or without raw/ on this machine
    BW.apply_headlines(chk, os.path.join(OUT, "portwatch"))
    json.dump(chk, open(os.path.join(OUT, "chokepoints.json"), "w"), indent=0)

    # K9 (passages against PortWatch, thresholds of the parallel rule, EIA beside the atlas): a report in
    # trade_checks.json for QA.md, never a failure of the build
    k9 += sensitivity(df, pairs, latest) + eia_ratio(chk, latest)
    K.save(k9, {"K9"}, latest)
    flagged = [r["text"] for r in k9 if r["level"] == "flag"]
    print(f"K9: {len(k9)} records, {len(flagged)} flagged (above PortWatch's volume of the year or of its best year)"
          + "".join("\n  " + t for t in flagged))

    # merge sources
    have = {s["id"] for s in reg}
    for f in glob.glob(os.path.join(HERE, "sources_*.json")):
        for s in json.load(open(f)):
            if s["id"] not in have:
                reg.append(s)
                have.add(s["id"])
    json.dump(reg, open(os.path.join(ROOT, "data", "sources.json"), "w"), indent=1, ensure_ascii=False)
    BL.save_geom_cache()
    print(f"build_freight: {time.time() - t_start:.0f} s")


if __name__ == "__main__":
    main()
