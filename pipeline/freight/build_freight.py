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
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import unquote

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ports as P  # noqa: E402
import build_lanes as BL  # noqa: E402
import build_portwatch as BW  # noqa: E402
import build_chokepoint_lanes as BCL  # noqa: E402
import build_port_index as BPI  # noqa: E402
import routing as RT  # noqa: E402
import vessel_rules as VR  # noqa: E402
import route_countries as RC  # noqa: E402
import generated_routes as GR  # noqa: E402

sys.path.insert(0, os.path.join(HERE, "..", "trade"))
import caveats as CV  # noqa: E402
sys.path.insert(0, os.path.join(HERE, "..", "infrastructure"))
from route_assets import route_port_assets  # noqa: E402
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
TANKER_GROUPS = {"crude-oil", "refined-products", "lng", "lpg", "palm-oil", "soyoil", "ammonia", "uan", "phosphoric-acid",
                 "sunflower-oil", "rapeseed-oil"}
# Groups whose gateway segment is general cargo (the "box" rows of ports.py: the general port of the country) but which sail in bulk carriers
# and are compared with PortWatch's dry-bulk ships: ferrous scrap, pig iron and direct-reduced iron (A-010)
DRY_BOX = {"ferrous-scrap", "pig-iron", "dri"}
CARGO_GROUPS = {g for g, s in P.SEGMENT.items() if s == "box"} - DRY_BOX
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


def cap_regime(low_sum, pw_t, reason):
    """How the "up to" figures of a vessel type are capped at a passage that has its own PortWatch counter. low_sum: the
    type's summed "at least" tonnage; pw_t: PortWatch's volume of the type in the year; reason: the alert that explains a
    tonnage above that volume, or None.
    "sub": the atlas is well under PortWatch (at most PW_NEAR of it): the cap is PortWatch's volume less the "at least"
    tonnage of the other groups. "none": the atlas is above PortWatch's volume and an alert on the passage explains it
    (the figures are tonnages of the normal route and the year's traffic is not a ceiling for them). "whole": the two sides
    are too close to compare, so the subtraction is not used, but a group cannot exceed the whole volume of its ship type.
    None: no counter figure for the type, no cap."""
    if pw_t is None:
        return None
    if low_sum <= PW_NEAR * pw_t:
        return "sub"
    return "none" if low_sum > pw_t and reason else "whole"
# QA.md: "at least" and "up to" of the parallel passages under other thresholds of the parallel rule (plan 2.5)
SENSITIVITY = ((0.03, 150), (0.05, 300), (0.10, 500))
SENSITIVITY_GATES = ("malacca", "sunda", "lombok", "taiwan-strait", "luzon")
# year the typical laden speeds of vessel_rules.SPEED were set (an Atlas assumption, published with s "atlas")
SPEED_YEAR = 2026


def mt(v):
    return f"{v:,.0f} Mt" if v >= 10 else f"{v:.1f} Mt" if v >= 1 else f"{v:.2f} Mt"


def sig3(v):
    """v to three significant digits, a half rounded up on the decimal figure as the page does (Intl.NumberFormat of the
    shortest decimal of the number): 5.865 is 5.87, where f"{5.865:.3g}" gives 5.86 because the binary double lies just below."""
    d = Decimal(repr(float(v)))
    if d == 0:
        return 0.0
    return float(d.quantize(Decimal(1).scaleb(d.adjusted() - 2), rounding=ROUND_HALF_UP))


def mtn(v):
    """A tonnage of the notes under the chokepoint estimates, to three significant digits like the page that prints
    them (a total of 1,000 Mt or more keeps its integer digits)."""
    return f"{v:,.0f} Mt" if v >= 1000 else f"{sig3(v):,.10g} Mt"


def mtp(v):
    """A tonnage that the page prints too (the headline of an estimate and its range): three significant digits, always, so the
    figure of a note and the figure of the page are the same one (GV6D.9). Give it the figure as the file stores it."""
    return f"{sig3(v):,.10g} Mt"


def ktn(v):
    """A tonnage (Mt) of the notes of a group under 1 Mt a year, in kt with one decimal like its lane file and the page
    (a half rounded up, as sig3 does)."""
    kt = Decimal(repr(round(v * 1e3, 6))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{kt:,} kt" if kt else "under 0.1 kt"


def mt3(v):
    """mt() with one more figure under 100 Mt, for comparisons of two close tonnages."""
    return f"{v:,.0f} Mt" if v >= 100 else f"{v:.1f} Mt" if v >= 1 else f"{v:.2f} Mt"


ACRONYM = {"lng": "LNG", "lpg": "LPG", "dap": "DAP", "uan": "UAN", "npk": "NPK", "monoammonium-phosphate": "MAP",
           "potassium-sulphate": "potassium sulphate (SOP)", "nickel-int": "nickel intermediates", "copper-ore": "copper concentrate",
           "zinc-ore": "zinc concentrate", "copper-refined": "refined copper"}


def label_of(g):
    return ACRONYM.get(g) or K.label(g)


def load_pairs(path=None):
    """Pairs files of build_lanes.py, decoded: {group: {k, y, seaborne (Mt), ports (the file's port table), rows: [{o, d,
    t (Mt), m, load, dis, nm, cls, via (set), alt (set), f}]}}."""
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
        out[p["group"]] = {"k": p["k"], "y": p["y"], "seaborne": p["seaborne"] / 1e3, "rows": rows, "ports": p["ports"]}
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


def passage_type_note(typ, kind, low, ref, best, best_y, year, reason, regime, capped, groups):
    """The note of a ship type at a passage, written once on the passage record (`typeNotes`, GV6D.1) and not in the note of each estimate:
    where the "at least" tonnage of the atlas for the type is above IMF PortWatch's volume of the same year, or within PW_NEAR of it, and
    what the cap on the "up to" figures of the type is (`regime`, see cap_regime). kind: "best" (above K9_MAX of PortWatch's best
    year), "alert" (above its volume of the year, an alert explains it), "noalert" (above it, none does), "near" (within PW_NEAR of it).
    `line` is the line the page prints; `n` the reason, which it folds. capped: groups whose "up to" figure is cut at PortWatch's volume;
    groups: groups of the type that have an estimate here."""
    name = TYPE_NAME[typ]
    head = name[0].upper() + name[1:]
    vs = f"IMF PortWatch's {mtn(ref)} for all {name} ships in {year}" if ref is not None else ""  # only the "best" kind can lack a figure of the year, and it does not use this
    pw_est = (f"IMF PortWatch's volume is an estimate made from ship movements ({mtn(ref) + f' in {year}; ' if ref is not None else ''}"
              f"{mtn(best)} in {best_y}, its best full year since {PW_FIRST_YEAR})")
    subset = "the atlas's groups are not all the cargo these ships carry"
    if kind == "alert":
        s = (f"{head}: 'at least' {mtn(low)}, above {vs}; the atlas routes cargo on the normal itinerary, so this is the tonnage of the normal "
             f"route, not the {year} traffic.")
        n = (f"{pw_est}, and {subset}. The atlas routes cargo on the normal itinerary, so this is the tonnage of the normal route, not the "
             f"{year} traffic. {reason}")
    elif kind == "near":
        s = f"{head}: 'at least' {mtn(low)} is {low / ref:.0%} of {vs}; the ports or routes the atlas assumes may overstate the passage."
        n = (f"{pw_est}, and {subset}, so an 'at least' tonnage this close to it leaves little room: the ports or routes the atlas assumes "
             "may overstate the passage")
    elif kind == "noalert":
        s = f"{head}: 'at least' {mtn(low)}, above {vs}; the ports, routes or ship types the atlas assumes probably overstate the passage."
        n = (f"{pw_est}, and {subset}, so a tonnage of the atlas above it, with no alert that explains it, means that the ports, routes or "
             "ship types the atlas assumes probably overstate the passage")
    else:
        s = (f"{head}: 'at least' {mtn(low)}, above {K9_MAX:.0%} of PortWatch's best full year since {PW_FIRST_YEAR} for all {name} ships "
             f"({mtn(best)} in {best_y}); the ports or routes the atlas assumes probably overstate the passage.")
        n = (f"{pw_est}, and {subset}, so a tonnage of the atlas more than {K9_MAX - 1:.0%} above its best year means that the ports or routes "
             "the atlas assumes probably overstate the passage")
    if regime == "whole":
        # the cap by subtraction compares the atlas with PortWatch: it says nothing once the two are this close
        n += (f". The 'up to' figure of a group cannot exceed the whole of PortWatch's volume of these ships ({mtn(ref)}), and is not reduced by "
              f"the other groups' 'at least' tonnage, because the atlas's own tonnage is above {PW_NEAR:.0%} of that volume and the two are too "
              f"close to compare. The cap binds only where a figure is tagged 'capped at PortWatch volume': "
              f"{'none' if not capped else capped} of the {groups} {name} groups with an estimate at this passage")
    elif regime == "none":
        n += (". The 'up to' figures of these groups are not capped at PortWatch's volume here: they are tonnages of the normal route, "
              f"and the {year} traffic is not a ceiling for them")
    return {"name": name, "y": year, "low": round(low, 1), "ref": None if ref is None else round(ref, 1), "best": round(best, 1),
            "bestY": best_y, "cmp": "near" if kind == "near" else "above", "regime": regime, "capped": capped, "groups": groups, "line": s, "n": n}


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
        # above PortWatch's volume of the same year (written once on the passage, `typeNotes`), and the K9 records
        type_args = {}
        reason_cp = alert_reason(alerts, cid, latest)
        regime = {typ: cap_regime(by_type[typ][0], pw_y.get(typ), reason_cp) if own else None for typ in TYPES}
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
                if cid in K9_NO_COMPARISON:
                    text += f"; the PortWatch counter is the {c.get('portwatchLabel') or 'part of the passage'}: no comparison is valid"
                elif low > K9_MAX * best:
                    level = "flag"
                    text += (f"; above {K9_MAX:.0%} of the best year: the ports or routes the atlas assumes probably overstate it. "
                             "Largest pairs: " + ", ".join(f"{label_of(g)} {K._name(o)} to {K._name(d)} {mt(v)}" for (g, o, d), v in top))
                    type_args[typ] = "best"
                elif ref is not None and low > ref:
                    level = "flag"
                    reason = reason_cp
                    if reason:
                        text += f"; above PortWatch's {latest} volume: the atlas routes cargo on the normal itinerary. {reason}"
                        type_args[typ] = "alert"
                    else:
                        # no diversion explains it: the assumed ports, routes or ship types are the likely cause
                        text += (f"; above PortWatch's {latest} volume and no alert explains it: the ports, routes or ship types the atlas "
                                 "assumes probably overstate it")
                        type_args[typ] = "noalert"
                elif ref and low > PW_NEAR * ref:
                    type_args[typ] = "near"
                if typ in type_args:
                    type_args[typ] = (type_args[typ], low, ref, best, by)
                k9.append({"check": "K9", "kind": "passage", "group": None, "year": latest, "chokepoint": cid, "type": typ,
                           "value": round(low, 1), "high": round(high, 1), "reference": None if ref is None else round(ref, 1),
                           "best": round(best, 1), "bestYear": by, "ratio": round(low / best, 2), "level": level, "text": text})
        # second pass: the entries
        capped_n = defaultdict(int)
        for g, (typ, seaborne_rows, low, high, alt_by) in per_group.items():
            p = pairs[g]
            sea = p["seaborne"]
            # the floor applies to the "up to" figure the page prints: the PortWatch cap (below) can bring it under
            # the floor although the uncapped sum is above it. The cap is PortWatch's volume of the type less the "at
            # least" tonnage of the other groups of the type, never below this group's own "at least"; above PW_NEAR of
            # PortWatch's volume the comparison with the other groups says nothing (the ports or routes the atlas
            # assumes overstate it) and the cap is the whole volume of the type, since a group cannot exceed its ship
            # type; with an alert that explains a tonnage above that volume there is no cap (see cap_regime)
            hi_pub, pw_t = high, pw_y.get(typ) if own else None
            if regime[typ] == "sub":
                hi_pub = min(high, max(low, pw_t - (by_type[typ][0] - low)))
            elif regime[typ] == "whole":
                hi_pub = min(high, max(low, pw_t))
            if not sea or not (hi_pub >= EST_MIN_MT or hi_pub / sea >= EST_MIN_SHARE):
                continue
            label = label_of(g)
            tn = mtn if sea >= BL.SMALL_MT else ktn  # a group under 1 Mt is printed in kt, as its lane and commodity pages
            # the figures of the estimate as the file stores them (`mt`) and as the page prints them: the note says the same figure (GV6D.9)
            tf = mtp if tn is mtn else ktn
            digits = lambda v: 1 if v >= 10 else 3 if tn is mtn else 4
            low_s, hi_s, high_s = round(low, digits(low)), round(hi_pub, digits(hi_pub)), round(high, digits(high))
            # the part that has to cross rounds to nothing at the precision printed (e["mt"] below): said in words, not "at least 0.0"
            zero = round(low, 3 if tn is mtn else 4) == 0
            if zero:
                n = [f"no cargo has to cross it: no recorded seaborne pair of the {tn(sea)} of seaborne {label} has an assumed route that has to "
                     f"cross this passage (CEPII BACI {latest}, Atlas routing)"]
            else:
                n = [f"at least {tf(low_s)} of {tn(sea)} of seaborne {label}: {DEFINITION} (CEPII BACI {latest}, Atlas routing)"]
            unr = sum(r["t"] for r in seaborne_rows if r["load"] == -1)
            if unr >= 0.05:
                n.append(f"{tn(unr)} of seaborne {label} could not be routed (no gateway, no sourced transit port, or one port at both ends)")
            mixed = sum(r["t"] for r in p["rows"] if r["m"] == 2 and cid in r["via"] | r["alt"])
            if mixed >= 0.05:
                n.append(f"{tn(mixed)} of {label} that moves both by sea and overland (split not known) would cross it by sea and is not counted")
            names = [K._name(o) for o in unrec.get((g, cid), [])]
            if names:
                n.append(f"Exports that customs data do not record for {latest}, or record only in part, are missing: {', '.join(names)} "
                         "(see the caveat of each origin; before the gap, the routes to their main buyers cross this passage or may cross it)")
            e = {"k": BL.COMMODITY.get(g, g), "p": g,
                 "f": {"v": round(100 * low / sea, 1), "u": "%", "y": latest, "s": "atlas", "n": ". ".join(n)},
                 "mt": [low_s, hi_s]}
            if round(100 * hi_pub / sea, 1) > e["f"]["v"]:
                top = sorted(alt_by.items(), key=lambda x: -x[1])[:3]
                top = [x for x in top if x[1] >= 0.005] or top[:1]
                adds = ("adds the pairs that may cross it or a parallel passage of similar length, or may load or discharge on "
                        "another coast (largest: " + ", ".join(f"{K._name(o)} {tn(v)}" for o, v in top) + ")")
                hn = f"up to {tf(high_s)}{' may cross it' if zero else ''}: {adds}"
                if hi_pub < high:
                    others = by_type[typ][0] - low
                    if regime[typ] == "whole":
                        less = ""
                    else:
                        less = (f" less the 'at least' tonnage of the atlas's other {TYPE_NAME[typ]} groups ({mtn(others)})" if others >= 0.05 else
                                f" (the atlas's other {TYPE_NAME[typ]} groups have almost no 'at least' tonnage here)")
                    hn = (f"up to {tf(hi_s)}{' may cross it' if zero else ''}: capped at IMF PortWatch's estimate of the cargo of all {TYPE_NAME[typ]} ships through the "
                          f"passage in {latest} ({mtn(pw_t)}, IMF PortWatch, data adapted){less}, which this cargo "
                          f"cannot exceed; without the cap, {tf(high_s)}: {adds}")
                    capped_n[typ] += 1
                e["hi"] = {"v": round(100 * hi_pub / sea, 1), "u": "%", "y": latest, "s": "atlas", "n": hn}
            est.append(e)
        est.sort(key=lambda e: -e["f"]["v"])
        if est:
            c["estimates"] = est
        else:
            c.pop("estimates", None)
        notes = {typ: passage_type_note(typ, *args, latest, reason_cp, regime[typ], capped_n[typ], sum(vessel_type(e["p"]) == typ for e in est))
                 for typ, args in type_args.items()}
        if notes:
            c["typeNotes"] = {typ: notes[typ] for typ in TYPES if typ in notes}
        else:
            c.pop("typeNotes", None)
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
    "HS5_38": ("IDBPN", "JPYOK"), "HS6_38": ("CNTSN", "JPCHB"), "HS7_38": ("CNTSN", "SGSIN"),
    "C8_182": ("COPBO", "NLRTM"), "C9_182": ("BRTUB", "CNTAO"), "C10_182": ("AUPHE", "CNTAO"), "C14_182": ("BRTUB", "CNTAO"),
    "C16_182": ("AUPHE", "NLRTM"), "P4_82": ("AUNTL", "NLRTM"), "P5_82": ("IDSRI", "CNFOC"), "S1B_63": ("ROCND", "CNTAO"),
    "S3_63": ("CNTSN", "NGLOS"), "S4B_63": ("NLRTM", "USHOU"), "S5_63": ("BRSSZ", "CNTAO"), "S8_63": ("IDSRI", "INPRT"),
    "S9_63": ("BRSSZ", "NLRTM"), "S15_63": ("ZARCB", "CNTAO"),
    # partial overrides (None = use the port matched from the route definition)
    "uspnw-asia-grain": ("USKAM", None), "brazil-china-vloc-iron-ore": ("BRPMA", "CNNGB"), "TD34": ("OMMFH", None),
    # TD6 loads at the CPC terminal, not at the port of Novorossiysk; Kaarsto, Port Jerome and "the Thames" (TC26, TD31,
    # TC25) are not in the port table: the notes name the port drawn instead
    "TD6": ("KZCPC", None), "TC26": ("NOSVG", None), "TD31": ("FRLEH", None), "TC25": (None, "GBTIL"),
}

# Route port names the name match resolves to another place (Portland, Oregon is not Portland, Maine; Huelva is not
# the Spanish gateway): an explicit engine code, or "port:<id>", a port asset of data/infrastructure whose sourced
# position is used, for a port the engine table lacks or places far from the port (Dos Bocas, Kashima)
PORT_CODE = {
    ("Portland", "USA"): "port:portland-oregon", ("Huelva", "ESP"): "port:huelva", ("Acu", "BRA"): "port:acu",
    ("Dongying", "CHN"): "port:dongying", ("Majishan", "CHN"): "port:majishan", ("Dalrymple Bay", "AUS"): "AUHPT",
    ("Busan", "KOR"): "KRPUS", ("St Petersburg", "RUS"): "RULED", ("Novorossiysk", "RUS"): "RUNVS",
    ("Port Klang", "MYS"): "MYPKG", ("Dos Bocas", "MEX"): "port:dos-bocas", ("Kashima", "JPN"): "port:kashima",
}
# A drawn line starts and ends at a node of the sea network. When that node is more than REACH_KM from a hand-written
# route's port, the line is joined to the port by a straight segment that crosses no land (sea_start, reach_ports).
REACH_KM = 100
# Waypoints of a hand-written route whose shortest network path a ship of its class cannot sail: TD6 rounds the
# Peloponnese (the network's path through the Gulf of Corinth crosses the isthmus)
WAYPOINTS = {"TD6": [(22.866, 35.805)]}
_ASSETS = None


def route_port(code):
    """P.port() for an engine code; for "port:<id>", the port asset's name, country and sourced position."""
    global _ASSETS
    if not code.startswith("port:"):
        return P.port(code)
    if _ASSETS is None:
        with open(os.path.join(ROOT, "data", "infrastructure", "ports.geojson"), encoding="utf-8") as f:
            _ASSETS = {x["properties"]["id"]: x for x in json.load(f)["features"]}
    x = _ASSETS[code[5:]]
    return {"id": code, "name": x["properties"]["name"], "c": x["properties"]["c"], "at": [round(v, 3) for v in x["geometry"]["coordinates"]]}


def _km(a, b):
    return P._km(a[0], a[1], b[0], b[1])


def _land():
    """Land polygons of the base map (route_countries), as one geometry."""
    from shapely.ops import unary_union
    shapes, _ = RC._country_shapes()
    return unary_union(shapes)


_LAND = None
# land within this distance of a port does not count against a segment to it: ports sit on the coast line, often inside
# the generalised 1:50m polygons
COAST_KM = 15


def sea_start(at, rid=None):
    """(point to plan from, port to join the line to, or None) for a route port at [lon, lat]. The plan starts at the
    port, whose nearest network node is where its line begins; when that node is more than REACH_KM away, the plan
    starts at the nearest node (within 3 x REACH_KM) from which a straight segment reaches the port without crossing land,
    and the segment is added to the line."""
    global _LAND
    from shapely.geometry import LineString, Point
    nodes = sorted((_km(u, at), u) for u in RT.graph().adj)
    if nodes[0][0] <= REACH_KM:
        return at, None
    if _LAND is None:
        _LAND = _land()
    near = Point(at).buffer(COAST_KM / 111.0)
    for d, u in nodes:
        if d > 3 * REACH_KM:
            break
        wet = LineString([u, at]).intersection(_LAND).difference(near)
        if wet.length * 111.0 < 0.5:
            return [u[0], u[1]], at
    print("line end left at its network node (no segment to the port without land):", rid, round(nodes[0][0]), "km")
    return at, None


def reach_ports(s, a, b):
    """The plan summary `s` (a cached dict: a copy is returned) with the segments to the ports `a` and `b` added to its line
    and their length to its distance (`a` or `b` is None for an end that needs no segment)."""
    if not a and not b:
        return s
    g, nm = [list(p) for p in s["g"]], s["nm"]
    for at, i in ((a, 0), (b, -1)):
        if not at:
            continue
        end = g[i]
        q = [round(at[0] + 360 * round((end[0] - at[0]) / 360), 2), round(at[1], 2)]  # the line's longitudes are continuous
        nm += round(_km(end, q) / BL.CN.KM_PER_NAUTICAL_MILE)
        g = [q] + g if i == 0 else g + [q]
    return {**s, "g": g, "nm": nm}


def plan_via(a, b, ws, classes):
    """BL.plan_summary() through waypoints: the legs joined (line, distance, passages); no alternative is offered."""
    pts = [a] + [list(w) for w in ws] + [b]
    legs = [BL.plan_summary(pts[i], pts[i + 1], classes, geometry=True) for i in range(len(pts) - 1)]
    if not all(legs):
        return None
    out = {"g": [], "nm": 0, "via": [], "viaAlt": [], "route": [], "alts": [], "altNote": None}
    for x in legs:
        out["g"] += x["g"] if not out["g"] else x["g"][1:]
        out["nm"] += x["nm"]
        out["via"] += [v for v in x["via"] if v not in out["via"]]
        out["route"] += [v for v in x["route"] if v not in out["route"]]
        out["viaAlt"] += [lst for lst in x["viaAlt"] if lst not in out["viaAlt"]]
    return out


def load(name):
    return json.load(open(os.path.join(HERE, name)))


def doc_year(doc):
    """Year of a definition's document: "... (December 2025) ..." or "Circular 03/26"."""
    import re
    m = re.search(r"\((?:\w+ )?((?:19|20)\d\d)\)", doc) or re.search(r"Circular \d+/(\d\d)\b", doc)
    if not m:
        raise ValueError(f"no year in the document name {doc!r}")
    return int(m.group(1)) if len(m.group(1)) == 4 else 2000 + int(m.group(1))


def index_membership(defs):
    """The Baltic indices (baltic_indices.json) each benchmark belongs to: its weight, every member with a flag for those the
    atlas has, and `covered`, the weight of the index whose routes the atlas has (a page must not suggest 100% when it is less)."""
    have = {r["id"] for r in defs}
    out = defaultdict(list)
    for ix in load("baltic_indices.json"):
        ms = ix.get("members") or []
        weight = (lambda m: 100 / len(ms)) if ix.get("equal") else (lambda m: m.get("w"))
        for m in ms:
            if m["r"] not in have:
                continue
            x = {"id": ix["id"], "name": ix["name"], "w": None if weight(m) is None else round(weight(m), 2)}
            x.update({k: True for k in ("equal", "tce") if ix.get(k)})
            x["members"] = [{"r": y["r"], **({"w": y["w"]} if "w" in y else {}), "in": y["r"] in have} for y in ms]
            if weight(m) is not None:
                x["covered"] = round(sum(weight(y) for y in ms if y["r"] in have), 2)
            x.update({k: ix[k] for k in ("since", "note", "url", "doc") if ix.get(k)})
            out[m["r"]].append(x)
    return out


def corridor_groups(c):
    """Customs groups of a corridor entry: the one a generated corridor names (`g`), else those of its commodity."""
    return [c["g"]] if c.get("g") else GROUPS_OF.get(c["k"], [c["k"]])


def finder_pair(cor, pairs, a, b):
    """The largest recorded seaborne pair of a corridor, as the Route finder runs it, when its ports are not the route's own
    (`a`, `b`: port codes): the route page and the finder then give two distances, and the page says why."""
    best = None
    for c in cor:
        for g in corridor_groups(c):
            p = pairs.get(g)
            for r in p["rows"] if p else []:
                if r["m"] in (0, 1) and r["load"] >= 0 and r["nm"] > 0 and r["o"] in c["o"] and r["d"] in c["d"] and (best is None or r["t"] > best[0]["t"]):
                    best = (r, g, p)
    if not best:
        return None
    r, g, p = best
    lo, di = p["ports"][r["load"]], p["ports"][r["dis"]]
    if (lo[0], di[0]) == (a, b):
        return None
    return {"g": g, "o": r["o"], "d": r["d"], "mt": round(r["t"], 1), "y": p["y"], "from": lo[1], "to": di[1], "nm": r["nm"]}


def cargo_names(g):
    """(name in a generated route's name, noun in its note) of a customs group."""
    what = label_of(g)
    return GR.CARGO_NAME.get(g) or what[0].upper() + what[1:], what


def find_port(name, iso3, group):
    """Match a port name from the route definitions to the port table; fall back to the country gateway."""
    if (name, iso3) in PORT_CODE:
        return PORT_CODE[(name, iso3)]
    a2 = BL.A2.get(iso3)
    n = name.lower().replace("ã", "a").replace("é", "e")
    for code, (pn, c, x, y) in P.MANUAL.items():
        # a terminal named for its cargo is not the port that its name mentions for another cargo ("Qingdao" is not
        # the Dongjiakou LNG terminal on the Qingdao coast: it is the port the Route finder uses for ore, coal and grain)
        if "lng" in pn.lower() and group != "lng":
            continue
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

    main_lane = {ln["id"]: ln for ln in main_lanes}
    pair_row = {(g, r["o"], r["d"]): r for g, p in pairs.items() for r in p["rows"] if r["m"] in (0, 1)}
    defs = load("routes_def.json")
    in_index = index_membership(defs)
    # generated corridors (generated_routes.py): a route for each large seaborne corridor that no hand-written route names
    latest_t = {(g, o, d): t for g, o, d, t in df[df["year"] == latest][["group", "o", "d", "t"]].itertuples(index=False)}
    hand = defaultdict(set)
    for r in defs:
        for c in [] if r.get("discontinued") else r.get("corridor") or []:
            for g in corridor_groups(c):
                for o in c["o"]:
                    for d in c["d"]:
                        hand[(g, o, d)].add(r["id"])
    hand = {k: sorted(v) for k, v in hand.items()}
    zones = json.load(open(os.path.join(OUT, "zones.json"), encoding="utf-8"))
    gen, gen_report = GR.generate(
        pairs, {g: p["ports"] for g, p in pairs.items()}, hand, zones, lambda code: P.port(code)["at"], cargo_names,
        {r["id"]: r["name"] for r in defs}, K._name,
        excluded={(e["group"], e["o"], e["d"]) for e in active.values() if e["kind"] == "landlocked-centre"})
    defs = defs + gen

    routes, feats = [], []
    for r in defs:
        cor = r.get("corridor") or []
        k0 = (r.get("cargoes") or [None])[0]
        g0 = (GROUPS_OF.get(k0) or [k0])[0] if k0 else "iron-ore"
        a = b = None
        if r.get("_ports"):
            a, b = r["_ports"]
        elif r["id"] in ROUTE_PORTS:
            a, b = ROUTE_PORTS[r["id"]]
        if a is None:
            fp = r["from"]["ports"][0]
            a = find_port(fp["name"], fp["c"], g0)
        if b is None:
            tp = r["to"]["ports"][0]
            b = find_port(tp["name"], tp["c"], g0)
        out = {k: r[k] for k in ("id", "name", "benchmark", "vclass", "cargoes", "cargoNote", "notes", "s") if k in r}
        if r.get("generated"):
            out["generated"] = True
        if r.get("discontinued"):
            out["discontinued"] = r["discontinued"]
        if r.get("standIn"):
            out["standIn"] = r["standIn"]
        if cor:
            # an entry that does not name its customs group lists those of its commodity (`gs`), so that the site never
            # matches a lane of another group (refined copper is not copper concentrate)
            out["corridor"] = [c if c.get("g") else {**c, "gs": corridor_groups(c)} for c in cor]
        if r.get("roundVoyage"):
            out["roundVoyage"] = True
        if r.get("parcel"):
            out["parcel"] = r["parcel"]
            if r.get("parcelMax"):
                out["parcelMax"] = r["parcelMax"]
            out["parcelUnit"] = r.get("parcelUnit", "t")
        if r.get("definition"):
            # the benchmark's published definition, with the indices it belongs to
            out["definition"] = {**r["definition"], **({"index": in_index[r["id"]]} if in_index.get(r["id"]) else {})}
            out["definition"]["y"] = doc_year(r["definition"]["doc"])  # the year of the document, shown with its figures
        out["from"] = {"region": r["from"]["region"], "ports": [p["name"] for p in r["from"]["ports"]]}
        out["to"] = {"region": r["to"]["region"], "ports": [p["name"] for p in r["to"]["ports"]]}
        # the infrastructure asset each port is ("port:primorsk", or None), for the links of the route page
        out["from"]["assets"] = route_port_assets(r["from"], r.get("cargoes"))
        out["to"]["assets"] = route_port_assets(r["to"], r.get("cargoes"))
        if r["id"] in ROUTE_PORTS and None not in ROUTE_PORTS[r["id"]]:
            out["drawnAs"] = "typical laden leg"
        if not a or not b:
            print("skip (no port)", r["id"])
            continue
        pa, pb = (P.port(a), P.port(b)) if r.get("_pair") else (route_port(a), route_port(b))
        spd = VR.speed(r["vclass"])
        if r.get("_pair"):
            # a generated route is planned as its largest pair is (classes of vessel_rules, same ports): the Route finder and the
            # route page give the same ports, distance and passages for that pair
            g, o, d, _ = r["_pair"]
            classes, s = BL._classes_and_plan(g, o, d, latest_t[(g, o, d)], pa["at"], pb["at"], geometry=True)
            if s and (classes[0] != r["vclass"] or round(s["nm"]) != round(r["_nm"])):
                print("generated route differs from its pair", r["id"], classes, s["nm"], r["vclass"], r["_nm"])
            if s:
                # the passages are the pair's own, as the Route finder gives them: those every port option crosses, and those
                # some option or a parallel passage may cross (the drawn line is the main option's, which may cross more)
                lane = main_lane.get(f"{g}:{o}-{d}")
                if lane:
                    s = {**s, "via": list(lane["via"]), "viaAlt": [list(x) for x in lane.get("viaAlt") or []]}
                else:
                    row = pair_row[(g, o, d)]
                    s = {**s, **dict(zip(("via", "viaAlt"), GR.pair_passages(s["via"], row["via"], row["alt"])))}
        else:
            (sa, ja), (sb, jb) = sea_start(pa["at"], r["id"]), sea_start(pb["at"], r["id"])
            if r["id"] in WAYPOINTS:
                s = plan_via(sa, sb, WAYPOINTS[r["id"]], [r["vclass"]])
            else:
                s = BL.plan_summary(sa, sb, [r["vclass"]], geometry=True)  # routing.plan(), as the lanes
            if s:
                s = reach_ports(s, ja, jb)
        if not s:
            print("skip (no path)", r["id"])
            continue
        nm, via = s["nm"], s["via"]
        out.update({"distanceNm": nm, "speedKn": spd, "days": round(nm / (spd * 24), 1), "via": via, "viaAlt": s["viaAlt"],
                    "a": pa["at"], "b": pb["at"]})
        rivers = [{"port": pt["name"], **BL.RL.public(c, pt["name"])} for c, pt in ((a, pa), (b, pb)) if c in BL.RL.RIVER_LEGS]
        if rivers:  # a port up a river (river_legs.py): the distance includes the leg and the line is straight to the mouth
            out["rivers"] = rivers
        if not r.get("_pair"):
            # the country of a terminal the table or an asset records (an offshore terminal is often nearer another country's coast)
            out["_ends"] = [p["c"] if len(p["c"]) == 3 else None for p in (pa, pb)]
        ref = None if r.get("_pair") else finder_pair(cor, pairs, a, b)
        if ref:
            out["finder"] = ref
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
        # the entries of a generated corridor (one per exporter) are one corridor of one customs group: one share, one history
        units = []
        for c in cor:
            want = {(g, o, d) for g in corridor_groups(c) for o in c["o"] for d in c["d"]}
            if c.get("g") and units and units[-1][0].get("g") == c["g"]:
                prev, prev_want = units[-1]
                units[-1] = ({**prev, "o": sorted({*prev["o"], *c["o"]}), "d": sorted({*prev["d"], *c["d"]})}, prev_want | want)
            else:
                units.append((c, want))
        for c, want in units:
            groups = corridor_groups(c)
            fresh = want - counted
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
            word = "all-coal (thermal and metallurgical)" if groups == ["coal"] else label_of(c["g"]) if c.get("g") else c["k"].replace("-", " ")
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
                # a small cargo keeps its decimals (a corridor of 0.96 Mt of 7.7 Mt of cotton)
                n = (f"{lead}: {v:.1f} Mt of " if v >= 1 else f"{lead}: {v:.2f} Mt of ") + (f"{tot:,.0f}" if tot >= 10 else f"{tot:.1f}") + f" Mt seaborne {word} trade, CEPII BACI customs data"
                if vm >= 0.05:
                    n += f"; a further {vm:.1f} Mt move both by sea and overland (split not known) and are not counted"
            n += ". Routes that share a country pair show the same tonnes: do not add them up"
            share = round(100 * v / tot, 1) if v > 0 and tot > 0 else 0.0
            if share > 0:
                shares.append({"k": c["k"], **({"g": c["g"]} if c.get("g") else {}), "f": {"v": share, "u": "%", "y": latest, "s": "atlas", "n": n}})
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
                out["shareNa"] = f"Corridor volume in {latest} is {v:.2f} Mt, under 0.05% of the {tot:,.0f} Mt of seaborne {'coal' if groups == ['coal'] else k.replace('-', ' ')} trade: too small for a meaningful share"
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
        if r.get("shareOn"):
            out["shareOn"] = r["shareOn"]  # the generated corridor that counts this route's flow (shareNa says so)
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
            out["historySrc"] = "atlas" if any(g in BL.EST_GROUP for c in cor for g in corridor_groups(c)) else "baci"
        routes.append(out)

    os.makedirs(OUT, exist_ok=True)
    RC.add_end_countries(routes)  # load / discharge country of each route end (site: country isolation)
    json.dump(routes, open(os.path.join(OUT, "routes.json"), "w"), separators=(",", ":"))
    json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(OUT, "routes.geo.json"), "w"), separators=(",", ":"))
    print("routes", len(routes), "with shares", sum(1 for r in routes if r.get("shares")), "with history", sum(1 for r in routes if r.get("history")),
          "generated", sum(1 for r in routes if r.get("generated")))
    for g, x in gen_report.items():
        print(f"  {g:17s} {x['seaborne']:7.1f} Mt  named by hand {x['handShare']:5.1f}%  with generated {x['share']:5.1f}%  generated routes {x['generated']:2d}"
              + (f"  ({x['why']})" if x["why"] else ""))
    tot = sum(x["seaborne"] for x in gen_report.values())
    print(f"  all groups: hand-written {sum(x['seaborne'] * x['handShare'] for x in gen_report.values()) / tot:.1f}%, "
          f"with generated {sum(x['seaborne'] * x['share'] for x in gen_report.values()) / tot:.1f}% of {tot:,.0f} Mt")
    # the same report, with what the caps left out, as a tracked file (the same text on every run over the same data)
    with open(os.path.join(HERE, "QA_routes.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(GR.qa_markdown(gen_report))

    # vessel classes (with the typical laden speed used for laden days), events: pass through
    vcs = load("vessel_classes.json")
    for vc in vcs:
        # the routes of a class page: the curated list (it may name another class's benchmarks, as Panamax does for
        # the Kamsarmax ones), then every other route of the class: the hand-written ones the list does not name,
        # then the generated corridors (the list `routes` is in that order)
        vc["routes"] = list(vc["routes"]) + [r["id"] for r in routes if r["vclass"] == vc["id"] and r["id"] not in vc["routes"]]
        vc["speedKn"] = VR.speed(vc["id"])
        vc["speedNote"] = ("Atlas assumption: an assumed typical laden service speed of the class, not a measured speed and not "
                           "from a published source. It is used for laden days (distance divided by speed) on routes and in the "
                           "Route finder")
        # the same figure in the atlas's figure shape (source and year); speedKn and speedNote stay for the site
        vc["speed"] = {"v": vc["speedKn"], "u": "kn", "y": SPEED_YEAR, "s": "atlas", "n": vc["speedNote"]}
    json.dump(vcs, open(os.path.join(OUT, "vessel-classes.json"), "w"), indent=0)
    events = sorted(load("events.json"), key=lambda e: e["date"])
    json.dump(events, open(os.path.join(OUT, "events.json"), "w"), indent=0)
    # active disruptions: the curated text quoted in the chokepoint notes below. data/freight/alerts.json, the banners of
    # the site, is written by build_alerts.py (figures, severity, commodities and countries from the data)
    alerts = load("alerts.json")
    ev_ids = {e["id"] for e in events}
    for a in alerts:
        assert a["event"] in ev_ids, f"alert {a['id']} points to unknown event {a['event']}"
        a["src"] = next(e["src"] for e in events if e["id"] == a["event"])

    # chokepoints: Atlas estimates of the share of every lane group's seaborne trade (pairs table), against PortWatch
    chk = load("chokepoints.json")
    reg = json.load(open(os.path.join(ROOT, "data", "sources.json")))
    bypass_notes(chk, reg)
    # the daily table kept by fetch_portwatch.py (pipeline/cache/portwatch, not in git), else the saved raw pages
    rows = BW.read_rows()
    if not rows:
        print("PortWatch daily table not found (pipeline/cache/portwatch, raw/portwatch): annual tonnages are read from "
              "the weekly series of data/freight/portwatch and those series are not rebuilt")
    pw = pw_volumes(chk, rows)
    k9 = chokepoint_shares(chk, pairs, pw, active, unrecorded_through(df, active, latest), latest, alerts)
    for c in chk:
        # typical detour when this chokepoint is avoided (main seaborne lanes with an alternative that avoids it)
        det = []
        for ln in main_lanes:
            a = next((x for x in ln.get("alts") or [] if c["id"] in (x.get("avoids") or [])), None)
            v = ln["flow"]["v"] / (1e3 if ln["flow"]["u"] == "kt" else 1)  # Mt (a group under 1 Mt is published in kt)
            if a and c["id"] in ln["via"] and v > 0.5:
                det.append((v, a["distanceNm"] - ln["distanceNm"], a["extraDays"]))
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
    BPI.build()  # typical ports of the lanes, for the site's search field (same pairs files)
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
