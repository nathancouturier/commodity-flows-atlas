"""
Build the freight layer files served by the site (run after build_lanes.py).

    python pipeline/freight/build_freight.py

Inputs (curated, in pipeline/freight/): routes_def.json, vessel_classes.json, chokepoints.json,
events.json, sources_*.json; BACI cache; raw/portwatch/*.json (optional, for transit series).
Outputs (data/freight/): routes.json, routes.geo.json, vessel-classes.json, chokepoints.json,
events.json, portwatch/<chokepoint>.json; merges new sources into data/sources.json.
"""
import glob
import json
import os
import sys
from collections import defaultdict
from datetime import date

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ports as P  # noqa: E402
import build_lanes as BL  # noqa: E402
import build_portwatch as BW  # noqa: E402
import vessel_rules as VR  # noqa: E402

ROOT = BL.ROOT
OUT = os.path.join(ROOT, "data", "freight")
RAW = os.path.join(ROOT, "raw")

# commodity id -> BACI groups used for corridor volumes
GROUPS_OF = {
    "thermal-coal": ["coal"], "met-coal": ["coal"], "copper": ["copper-ore"], "nickel": ["nickel-ore"],
    "phosphate": ["phosphate-rock", "dap"], "bauxite": ["bauxite"],
}
# vessel size families used for the "share of class activity" estimate
FAMILY = {"vloc": "capesize", "newcastlemax": "capesize", "capesize": "capesize", "kamsarmax": "panamax", "panamax": "panamax",
          "ultramax": "supramax", "supramax": "supramax", "handysize": "handysize", "vlcc": "vlcc", "suezmax": "suezmax",
          "aframax": "aframax", "lr2": "lr2", "lr1": "lr1", "mr": "mr", "handy-tanker": "mr", "lng": "lng", "vlgc": "vlgc"}


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
    df = pd.read_csv(os.path.join(BL.CACHE, "sea_flows.csv.gz"))  # cleaned seaborne flows (build_lanes.py)
    totals = json.load(open(os.path.join(BL.CACHE, "seaborne_totals.json")))
    latest = int(df["year"].max())
    years = list(range(BL.LATEST_MIN_YEAR, latest + 1))

    # same imputation as build_lanes: rebuild "sea" flows table once
    lanes_all = []
    for f in glob.glob(os.path.join(ROOT, "data", "freight", "lanes", "*.json")):
        lanes_all += json.load(open(f))["lanes"]
    lane_by = {(ln["p"], ln["o"], ln["d"]): ln for ln in lanes_all}

    # tonne-miles of every seaborne pair in the latest year, by vessel size family (Atlas estimate).
    # Mapped lanes use their routed distance; other pairs use the great-circle distance between
    # gateway ports x 1.3 (typical sea-route detour).
    pair_tm = {}
    class_tm = defaultdict(float)
    for g, o, d, t in df[df["year"] == latest][["group", "o", "d", "t"]].itertuples(index=False):
        ln = lane_by.get((g, o, d))
        if ln:
            nm, fam = ln["distanceNm"], FAMILY.get(ln["vclass"][0], ln["vclass"][0])
        else:
            go, gd = BL.gateway(o, g), BL.gateway(d, g)
            if not go or not gd:
                continue
            a, b = P.port(go)["at"], P.port(gd)["at"]
            nm = BL.km(a[0], a[1], b[0], b[1]) / 1.852 * 1.3
            fam = FAMILY.get(VR.classes(g, o, d, t, nm)[0], "other")
        pair_tm[(g, o, d)] = (t / 1e6) * nm
        class_tm[fam] += (t / 1e6) * nm

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
        coords, nm, via, alt = BL.routing(pa["at"], pb["at"], r["vclass"], spd)
        if not coords:
            print("skip (no path)", r["id"])
            continue
        out.update({"distanceNm": nm, "speedKn": spd, "days": round(nm / (spd * 24), 1), "via": via, "a": pa["at"], "b": pb["at"]})
        for cps, ev, text in BL.DISRUPTIONS:
            if cps & set(via):
                out.setdefault("status", []).append({"text": text, "event": ev})
        feats.append({"type": "Feature", "properties": {"id": r["id"], "kind": "route"}, "geometry": {"type": "LineString", "coordinates": coords}})
        if alt:
            ag = alt.pop("g")
            out["alt"] = alt
            feats.append({"type": "Feature", "properties": {"id": r["id"] + ":alt", "kind": "alt"}, "geometry": {"type": "LineString", "coordinates": ag}})

        # corridor volumes from customs data (cleaned seaborne pairs)
        shares, hist_tot, cor_tm = [], defaultdict(float), 0.0
        for c in cor:
            groups = GROUPS_OF.get(c["k"], [c["k"]])
            sub = df[df["group"].isin(groups) & df["o"].isin(c["o"]) & df["d"].isin(c["d"])]
            per_year = (sub.groupby("year")["t"].sum() / 1e6).to_dict()
            sea_tot = sum(totals[g][str(latest)]["sea"] for g in groups if g in totals) / 1e6
            v = per_year.get(latest, 0.0)
            if v > 0 and sea_tot > 0:
                shares.append({"k": c["k"], "f": {"v": round(100 * v / sea_tot, 1), "u": "%", "y": latest, "s": "atlas",
                                                  "n": f"Country-pair corridor (all ports and vessel sizes): {v:.1f} Mt of {sea_tot:.0f} Mt seaborne {c['k']} trade, CEPII BACI customs data"}})
            for y in years:
                hist_tot[y] += per_year.get(y, 0.0)
            cor_tm += sum(pair_tm.get((g, o, d), 0.0) for g in groups for o in c["o"] for d in c["d"])
        if shares:
            out["shares"] = shares
            out["shareCommodity"] = shares[0]["f"]
            fam = FAMILY.get(r["vclass"], r["vclass"])
            if class_tm.get(fam) and cor_tm:
                out["shareClass"] = {"v": round(100 * cor_tm / class_tm[fam], 1), "u": "%", "y": latest, "s": "atlas",
                                     "n": f"Estimated share of {fam}-size tonne-mile demand (all seaborne flows of the atlas commodities); overlapping routes share the same corridor"}
            series, spikes = BL.despike([round(hist_tot[y], 2) for y in years])
            out["history"] = [{"y": y, "v": v} for y, v in zip(years, series) if v is not None]
            if spikes:
                out["historyNote"] = "Isolated customs outlier removed for " + ", ".join(str(years[i]) for i in spikes)
            out["historyUnit"] = "Mt"
            out["historySrc"] = "baci"
        routes.append(out)

    os.makedirs(OUT, exist_ok=True)
    json.dump(routes, open(os.path.join(OUT, "routes.json"), "w"), separators=(",", ":"))
    json.dump({"type": "FeatureCollection", "features": feats}, open(os.path.join(OUT, "routes.geo.json"), "w"), separators=(",", ":"))
    print("routes", len(routes), "with shares", sum(1 for r in routes if r.get("shares")))

    # vessel classes, events: pass through
    json.dump(load("vessel_classes.json"), open(os.path.join(OUT, "vessel-classes.json"), "w"), indent=0)
    events = sorted(load("events.json"), key=lambda e: e["date"])
    json.dump(events, open(os.path.join(OUT, "events.json"), "w"), indent=0)
    # active disruptions shown as banners (curated; each links to an event with its source)
    alerts = load("alerts.json")
    ev_ids = {e["id"] for e in events}
    for a in alerts:
        assert a["event"] in ev_ids, f"alert {a['id']} points to unknown event {a['event']}"
        a["src"] = next(e["src"] for e in events if e["id"] == a["event"])
    json.dump(alerts, open(os.path.join(OUT, "alerts.json"), "w"), indent=0)

    # chokepoints + Atlas estimate of commodity shares from mapped lanes
    chk = load("chokepoints.json")
    for c in chk:
        est = []
        for g in ("crude-oil", "lng", "lpg", "coal", "iron-ore", "wheat", "corn", "soybeans", "refined-products", "bauxite"):
            tot = totals.get(g, {}).get(str(latest), {}).get("sea", 0) / 1e6
            through = sum(ln["flow"]["v"] for ln in lanes_all if ln["p"] == g and c["id"] in ln["via"])
            if tot and through / tot >= 0.02:
                est.append({"k": BL.COMMODITY.get(g, g), "f": {"v": round(100 * through / tot, 1), "u": "%", "y": latest, "s": "atlas",
                                                              "n": f"{through:.0f} Mt of {tot:.0f} Mt seaborne trade on the atlas's mapped lanes (lower bound)"}})
        if est:
            c["estimates"] = est
        # typical detour when this chokepoint is avoided (mapped lanes with an alternative routing)
        det = [(ln["flow"]["v"], ln["alt"]["distanceNm"] - ln["distanceNm"], ln["alt"]["extraDays"]) for ln in lanes_all
               if c["id"] in ln["via"] and ln.get("alt") and c["id"] in (ln["alt"].get("avoids") or []) and ln["flow"]["v"] > 0.5]
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
    json.dump(chk, open(os.path.join(OUT, "chokepoints.json"), "w"), indent=0)

    # PortWatch weekly transit series per chokepoint (logic shared with build_portwatch.py)
    rows = BW.read_rows(os.path.join(RAW, "portwatch"))
    if rows:
        BW.build(rows, chk, os.path.join(OUT, "portwatch"))

    # merge sources
    reg = json.load(open(os.path.join(ROOT, "data", "sources.json")))
    have = {s["id"] for s in reg}
    for f in glob.glob(os.path.join(HERE, "sources_*.json")):
        for s in json.load(open(f)):
            if s["id"] not in have:
                reg.append(s)
                have.add(s["id"])
    json.dump(reg, open(os.path.join(ROOT, "data", "sources.json"), "w"), indent=1, ensure_ascii=False)
    BL.save_geom_cache()


if __name__ == "__main__":
    main()
