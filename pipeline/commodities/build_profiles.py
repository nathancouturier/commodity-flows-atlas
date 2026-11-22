"""
Build country profiles (data/countries/profiles.json) from the commodity files.

    python pipeline/commodities/build_profiles.py

Relevance rule (METHODOLOGY.md §6): a row enters a country's profile when the country is in the world
top 10 of the table (production, exports or imports of a commodity), or holds >= 3% of its world
total, or when the row is worth >= 10% of the country's own trade value across the atlas commodities.
The commodity tables hold their 12 largest countries, so no row exists beyond rank 12. Every row
that passes is published: the page shows the first eight and the rest behind "Show all".
Exports and imports are ordered by trade value (CEPII BACI, USD) so the country's economically
largest flows come first; production is ordered by world share. `top10` counts the catalogue
commodities in which the country ranks in the world top 10 of any table.

"Country check": if a country's largest raw-material export (BACI, HS4, latest year) is not one of
the atlas commodities (e.g. diamonds for Botswana, logs for Gabon), it is added under `other`.
"""
import glob
import json
import os
import sys

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "trade"))
from hs_map import HS  # noqa: E402
from clean import CODE_FIX  # noqa: E402  (BACI "S19" = Taiwan: one mapping for all builders)

TOP_RANK, MIN_SHARE, MIN_WEIGHT = 10, 0.03, 0.10

# atlas commodity -> BACI groups used to value its trade.
# Customs codes do not separate thermal from metallurgical coal: the value of all coal belongs to
# neither row, it is carried by the "Coal (all types)" row built from the all-coal customs tables.
VALUE_GROUPS = {
    "thermal-coal": [], "copper": ["copper-ore"], "bauxite": ["bauxite"], "nickel": ["nickel-ore"],
    "zinc": ["zinc-ore"], "lead": ["lead-ore"], "tin": ["tin-metal"], "phosphate": ["phosphate-rock"], "met-coal": [],
}
COAL = ("thermal-coal", "met-coal")
ALL_COAL = "Coal (all types)"

# What the main trade table of a commodity really is, where the commodity name alone would mislead
# (names as in pipeline/freight/build_lanes.py).
TRADE_LABEL = {"copper": "Copper concentrate", "zinc": "Zinc concentrate", "nickel": "Nickel ore", "lead": "Lead concentrate",
               "bauxite": "Bauxite"}
PRODUCTION_LABEL = {"bauxite": "Bauxite", "urea": "Ammonia"}

HS4_LABEL = {
    "7102": "Diamonds", "4403": "Logs (roundwood)", "4407": "Sawn timber", "4401": "Wood chips and pellets",
    "4418": "Builders' joinery (wood)", "0801": "Cashew and coconuts", "0803": "Bananas", "0306": "Crustaceans",
    "0303": "Frozen fish", "0302": "Fresh fish", "0304": "Fish fillets", "1202": "Groundnuts", "2612": "Uranium ore",
    "2615": "Niobium, tantalum and zirconium ores", "2610": "Chromium ore", "2614": "Titanium ores",
    "2617": "Other ores (e.g. antimony)", "2616": "Precious metal ores", "2611": "Tungsten ores", "2613": "Molybdenum ores",
    "2704": "Coke", "2711": "Petroleum gases", "0805": "Citrus fruit", "0806": "Grapes", "0804": "Dates, figs, avocados, mangoes",
    "0901": "Coffee", "0902": "Tea", "0904": "Pepper", "0907": "Cloves", "0908": "Nutmeg and cardamom",
    "1801": "Cocoa beans", "2401": "Unmanufactured tobacco", "5201": "Cotton", "5101": "Wool", "4001": "Natural rubber",
    "1207": "Oilseeds (sesame and other)", "0713": "Pulses", "1006": "Rice", "0201": "Beef", "0202": "Frozen beef",
    "0204": "Sheep and goat meat", "0102": "Live cattle", "0104": "Live sheep and goats", "2510": "Phosphate rock",
    "2508": "Clays", "2515": "Marble", "2516": "Granite", "2523": "Cement", "7110": "Platinum group metals",
    "7106": "Silver", "7108": "Gold", "7601": "Aluminium", "7202": "Ferro-alloys", "7403": "Refined copper",
    "8105": "Cobalt", "8001": "Tin", "0709": "Vegetables", "0603": "Cut flowers", "2009": "Fruit juices", "1604": "Prepared fish",
    "1511": "Palm oil", "1513": "Coconut and palm kernel oil", "0302 ": "Fish", "4703": "Chemical wood pulp",
    "7201": "Pig iron", "7207": "Semi-finished steel", "2601": "Iron ore", "2603": "Copper ore", "2709": "Crude oil",
    "2710": "Refined petroleum products", "2716": "Electricity", "2701": "Coal",
}


def catalogue_hs():
    codes = []
    for g, lst in HS.items():
        if g in ("diamonds", "wood"):
            continue
        codes += [c.rstrip("*") for c in lst]
    return codes


def covered(hs4, codes):
    return any(c.startswith(hs4) or hs4.startswith(c[:4]) for c in codes if len(c) >= 4) or any(hs4.startswith(c) for c in codes if len(c) < 4)


def main():
    idx = json.load(open(os.path.join(ROOT, "data", "commodities", "index.json")))
    tables = {}
    for c in idx:
        p = os.path.join(ROOT, "data", "commodities", f"{c['id']}.json")
        if os.path.exists(p):
            tables[c["id"]] = json.load(open(p))
    baci = pd.read_csv(os.path.join(ROOT, "pipeline", "cache", "baci_flows.csv.gz"))
    baci["o"] = baci["o"].replace(CODE_FIX)
    baci["d"] = baci["d"].replace(CODE_FIX)
    latest = int(baci["year"].max())
    b = baci[baci["year"] == latest]
    exp_usd = b.groupby(["o", "group"])["usd"].sum()
    imp_usd = b.groupby(["d", "group"])["usd"].sum()

    def usd(series, iso, k):
        groups = VALUE_GROUPS.get(k, [k])
        return float(sum(series.get((iso, g), 0.0) for g in groups)) * 1000  # thousand USD -> USD

    profiles = {}

    def add(iso, section, entry):
        p = profiles.setdefault(iso, {"c": iso, "exports": [], "imports": [], "production": []})
        p[section].append(entry)

    # extra trade tables (refined copper, nickel intermediates, alumina, zinc metal) count as exports/imports
    EXTRA_SIDE = {"refined-exports": ("exports", "copper-refined", "Copper (refined & blister)"),
                  "refined-imports": ("imports", "copper-refined", "Copper (refined & blister)"),
                  "int-exports": ("exports", "nickel-int", "Nickel (intermediates & metal)"),
                  "int-imports": ("imports", "nickel-int", "Nickel (intermediates & metal)"),
                  "alumina-exports": ("exports", "alumina", "Alumina"),
                  "metal-exports": ("exports", "zinc-metal", "Zinc (refined)"),
                  "allcoal-exports": ("exports", "coal", ALL_COAL),
                  "allcoal-imports": ("imports", "coal", ALL_COAL)}
    candidates = []  # (iso, section, entry)
    for k, d in tables.items():
        sections = [(sec, d.get(sec), None, None) for sec in ("exports", "imports", "production")]
        for ex in d.get("extra") or []:
            if ex["key"] in EXTRA_SIDE:
                side, grp, label = EXTRA_SIDE[ex["key"]]
                sections.append((side, ex["table"], grp, label))
        for section, t, grp, label in sections:
            if not t or not t.get("rows"):
                continue
            world = t.get("world") or sum(r["v"] for r in t["rows"])
            for i, r in enumerate(t["rows"]):
                share = r["v"] / world if world else None
                e = {"k": k, "v": r["v"], "u": t["u"], "share": round(share, 4) if share else None, "rank": i + 1, "y": t["y"], "s": t["s"]}
                label = label or (PRODUCTION_LABEL.get(k) if section == "production" else TRADE_LABEL.get(k))
                if label:
                    e["label"] = label
                if t.get("basis"):
                    e["basis"] = t["basis"]
                if section in ("exports", "imports"):
                    series = exp_usd if section == "exports" else imp_usd
                    val = float(sum(series.get((r["c"], g), 0.0) for g in [grp])) * 1000 if grp else usd(series, r["c"], k)
                    if val:
                        # the value has its own source and year, whatever the tonnage comes from
                        e["usd"], e["usdS"], e["usdY"] = round(val / 1e9, 3), "baci", latest
                if r.get("n"):
                    e["n"] = r["n"]
                if t.get("caveat"):
                    e["warn"] = t["caveat"]  # warning of the whole table (trade hubs, gross weight...)
                candidates.append((r["c"], section, e))

    # relevance rule (METHODOLOGY.md §6): world top 10, or >= 3% of world, or >= 10% of the
    # country's own trade value across atlas commodities
    own = {}
    for iso, section, e in candidates:
        if section != "production" and e.get("usd"):
            own[(iso, section)] = own.get((iso, section), 0.0) + e["usd"]
    for iso, section, e in candidates:
        tot = own.get((iso, section)) or 0
        weight = (e.get("usd") or 0) / tot if tot else 0
        if e["rank"] <= TOP_RANK or (e["share"] or 0) >= MIN_SHARE or weight >= MIN_WEIGHT:
            add(iso, section, e)

    # KPI "World top-10 in N commodities": counted on every table row, before any selection
    top10 = {}
    for iso, section, e in candidates:
        if e["rank"] <= TOP_RANK:
            top10.setdefault(iso, set()).add(e["k"])

    def by_value(rows):
        # thermal and metallurgical coal carry no value of their own: they follow the all-coal row
        coal = next((e["usd"] for e in rows if e.get("label") == ALL_COAL and e.get("usd")), None)

        def key(e):
            v = e.get("usd") or 0
            if not v and coal and e["k"] in COAL:
                return (-coal, 1, -(e["share"] or 0))
            return (-v, 0, -(e["share"] or 0))
        return sorted(rows, key=key)

    for iso, p in profiles.items():
        p["exports"] = by_value(p["exports"])
        p["imports"] = by_value(p["imports"])
        p["production"] = sorted(p["production"], key=lambda e: -(e["share"] or 0))
        if top10.get(iso):
            p["top10"] = len(top10[iso])

    # ---- country check: top raw-material export outside the catalogue
    hs4p = os.path.join(ROOT, "pipeline", "cache", "hs4_exports.csv.gz")
    if os.path.exists(hs4p):
        h = pd.read_csv(hs4p, dtype={"hs4": str})
        h = h[h["o"].notna()]
        h["o"] = h["o"].replace(CODE_FIX)
        desc = pd.read_csv(hs4p.replace(".csv.gz", "_desc.csv"), dtype={"hs4": str}).set_index("hs4")["description"].to_dict()
        world_hs4 = h.groupby("hs4")["usd"].sum()
        rank_hs4 = h.assign(r=h.groupby("hs4")["usd"].rank(ascending=False)).set_index(["o", "hs4"])["r"]
        codes = catalogue_hs()
        yr = int(h["t"].max())
        for iso, g in h.groupby("o"):
            tot = g["usd"].sum()
            top = g.sort_values("usd", ascending=False).iloc[0]
            if tot < 200_000 or covered(top["hs4"], codes):  # < USD 200 million of raw-material exports: skip
                continue
            label = HS4_LABEL.get(top["hs4"]) or str(desc.get(top["hs4"], top["hs4"])).split(";")[0].split(":")[0][:48]
            e = {"k": f"hs{top['hs4']}", "label": label, "v": round(top["usd"] / 1e6, 2), "u": "bn USD exports",
                 "share": round(top["usd"] / world_hs4[top["hs4"]], 4), "rank": int(rank_hs4.get((iso, top["hs4"]), 0)) or None,
                 "y": yr, "s": "baci", "n": f"{top['usd'] / tot:.0%} of the country's raw-material exports (HS {top['hs4']})"}
            profiles.setdefault(iso, {"c": iso, "exports": [], "imports": [], "production": []})["other"] = [e]

    # ---- infrastructure and companies
    by_country = {}
    for f in glob.glob(os.path.join(ROOT, "data", "infrastructure", "*.geojson")):
        for ft in json.load(open(f))["features"]:
            pr = ft["properties"]
            for iso in {pr.get("c")} | set(pr.get("cs") or []):
                if iso in profiles:
                    cap = (pr.get("capacity") or {}).get("v") or 0
                    by_country.setdefault(iso, {}).setdefault(pr["type"], []).append((cap, f"{pr['type']}:{pr['id']}"))
    TYPE_ORDER = ["field", "refinery", "lng-export", "mine", "pipeline", "port", "smelter", "lng-import"]
    for iso, types in by_country.items():
        queues = [sorted(types[t], key=lambda x: -x[0]) for t in TYPE_ORDER if t in types]
        ordered = []
        while any(queues):  # one asset per type in turn, largest first: every type is represented
            for q in queues:
                if q:
                    ordered.append(q.pop(0)[1])
        profiles[iso]["infra"] = ordered
    cp = os.path.join(ROOT, "data", "commodities", "companies.json")
    if os.path.exists(cp):
        seen = set()
        for k, groups in json.load(open(cp)).items():
            for role in ("producers", "processors", "traders"):
                for co in groups.get(role) or []:
                    iso = co.get("hq")
                    if iso in profiles and (iso, co["name"]) not in seen:
                        seen.add((iso, co["name"]))
                        profiles[iso].setdefault("companies", []).append({k2: co[k2] for k2 in ("name", "hq", "role", "detail", "s", "y") if k2 in co} | {"k": k})
        for p in profiles.values():
            if "companies" in p:
                p["companies"] = p["companies"][:10]

    out = os.path.join(ROOT, "data", "countries", "profiles.json")
    json.dump(profiles, open(out, "w"), separators=(",", ":"), ensure_ascii=False)
    print("profiles", len(profiles), "with other", sum(1 for p in profiles.values() if p.get("other")), f"{os.path.getsize(out) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
