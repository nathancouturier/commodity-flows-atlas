"""
Build country profiles (data/countries/profiles.json) from the commodity files.

    python pipeline/commodities/build_profiles.py

Relevance rule (METHODOLOGY.md §6): a commodity enters a country's profile when the country is in
the world top 10 or holds >= 3% of world production, exports or imports. Within a profile,
exports and imports are ordered by trade value (CEPII BACI, USD) so the country's economically
largest flows come first; production is ordered by world share.

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

TOP_RANK, MIN_SHARE, MAX_ITEMS = 10, 0.03, 8

# atlas commodity -> BACI groups used to value its trade
VALUE_GROUPS = {
    "thermal-coal": ["coal"], "copper": ["copper-ore", "copper-refined"], "bauxite": ["bauxite", "alumina"],
    "nickel": ["nickel-ore", "nickel-int"], "zinc": ["zinc-ore", "zinc-metal"], "lead": ["lead-ore", "lead-metal"],
    "tin": ["tin-ore", "tin-metal"], "phosphate": ["phosphate-rock", "dap"], "met-coal": [],
}

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

    for k, d in tables.items():
        for section in ("exports", "imports", "production"):
            t = d.get(section)
            if not t or not t.get("rows"):
                continue
            world = t.get("world") or sum(r["v"] for r in t["rows"])
            for i, r in enumerate(t["rows"]):
                share = r["v"] / world if world else None
                if (i + 1) <= TOP_RANK or (share or 0) >= MIN_SHARE:
                    e = {"k": k, "v": r["v"], "u": t["u"], "share": round(share, 4) if share else None, "rank": i + 1, "y": t["y"], "s": t["s"]}
                    if section in ("exports", "imports"):
                        val = usd(exp_usd if section == "exports" else imp_usd, r["c"], k)
                        if val:
                            e["usd"] = round(val / 1e9, 3)
                    if r.get("n"):
                        e["n"] = r["n"]
                    add(r["c"], section, e)

    for p in profiles.values():
        p["exports"] = sorted(p["exports"], key=lambda e: -(e.get("usd") or 0) - (e["share"] or 0) * 1e-3)[:MAX_ITEMS]
        p["imports"] = sorted(p["imports"], key=lambda e: -(e.get("usd") or 0) - (e["share"] or 0) * 1e-3)[:MAX_ITEMS]
        p["production"] = sorted(p["production"], key=lambda e: -(e["share"] or 0))[:MAX_ITEMS]

    # ---- country check: top raw-material export outside the catalogue
    hs4p = os.path.join(ROOT, "pipeline", "cache", "hs4_exports.csv.gz")
    if os.path.exists(hs4p):
        h = pd.read_csv(hs4p, dtype={"hs4": str})
        h = h[h["o"].notna()]
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
    for f in glob.glob(os.path.join(ROOT, "data", "infrastructure", "*.geojson")):
        for ft in json.load(open(f))["features"]:
            pr = ft["properties"]
            for iso in {pr.get("c")} | set(pr.get("cs") or []):
                if iso in profiles:
                    profiles[iso].setdefault("infra", []).append(f"{pr['type']}:{pr['id']}")
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
