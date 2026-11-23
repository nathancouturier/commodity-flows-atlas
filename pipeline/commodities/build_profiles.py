"""
Build the country profiles from the full commodity tables, the customs extracts and the trade-flow engine.

    python pipeline/commodities/build_profiles.py

Outputs (METHODOLOGY.md §6):
  data/countries/profiles/<ISO3>.json  one file per country of the index (and EU27), loaded when its page opens
  data/countries/profiles.json         light index: {ISO3: {"n": lines, "top10": N}} or {ISO3: {"none": text}}

A profile holds:
  lines     every line the country has in any table of any commodity (production, refinery output, consumption,
            reserves, exports, imports and their extra tables), with its world rank and share, read from the full
            tables; exports and imports carry their customs value (CEPII BACI, USD) and are ordered by it, so that
            "Largest export" is the largest in value. Each line carries the country's series from the history
            files (value and rank by year), for the History year and the trend line.
  basket    the ten largest exports and imports by value at HS4 (every chapter), with their share of the country's
            total merchandise exports or imports (pipeline/cache/hs4_*, written by pipeline/trade/extract_hs4.py)
  other     up to five raw-material headings outside the atlas catalogue (diamonds for Botswana, logs for Gabon)
  balance   per traded product: net exporter or importer (same table, unit and year on both sides), the first three
            customers and suppliers with their shares and the Herfindahl index of each side (recorded pairs of
            CEPII BACI, latest year: the pairs tables of the engine, or the cleaned customs frame for the groups that
            have no lanes), and imports over consumption where both tables share unit and year
  freight   from the pairs tables of the engine (data/freight/pairs): mode split, typical ports and the share of the
            seaborne tonnes whose assumed route has to cross ("at least") or may cross ("up to") each passage
  gaps      the caveats of data/freight/caveats.json for this origin (exports customs data miss, hubs)
  hubs      trading or refining hub, a derived label: exports and imports of the same product both large, and no
            production line for it in the atlas
  infra, companies (headquarters in the country, every commodity they are listed for), operators (of the assets)
A country of the index with none of these gets the exact words of what it is (Natural Earth) and why it has no data.
"""
import glob
import json
import os
import sys
from collections import defaultdict

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "trade"))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "freight"))
from hs_map import HS  # noqa: E402
from clean import CODE_FIX, clean  # noqa: E402  (BACI code S19 is Taiwan: one mapping for all builders)

TOP_RANK = 10
CACHE = os.path.join(ROOT, "pipeline", "cache")
OUT_DIR = os.path.join(ROOT, "data", "countries", "profiles")
# basket: headings shown per side; other: raw-material headings outside the catalogue, each at least this share of the
# country's raw-material exports, for a country with at least this much of them (thousand USD)
BASKET_ROWS, OTHER_ROWS, OTHER_MIN_SHARE, OTHER_MIN_TOTAL = 10, 5, 0.05, 200_000
RAW_CHAPTERS = {f"{c:02d}" for c in list(range(1, 28)) + [40, 41, 44, 47, 51, 52, 53, 71] + list(range(72, 82))}
# partners: customers and suppliers listed per product
PARTNERS = 3
# hub: a product whose exports and imports both reach this share of the world total, with no line in a production table
# that lists every producing country (EIA, USDA PSD and FAOSTAT do; a USGS table lists the main producers only, so a
# country missing from it may still produce: no label then)
HUB_MIN_SHARE = 0.01
FULL_PRODUCTION_SOURCES = {"eia-intl", "usda-psd", "faostat"}
# freight: a passage is listed for a country's product when its "up to" share reaches this share of the seaborne tonnes
# (the floor of the chokepoint estimates, pipeline/freight/build_freight.py EST_MIN_SHARE)
PASSAGE_MIN_SHARE = 0.02
PORTS = 3
# the EU27 aggregate of USDA PSD and its member states (the same list as web/src/map/modules/choropleth.ts EU27)
EU27 = ["AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "IRL", "ITA", "LVA", "LTU",
        "LUX", "MLT", "NLD", "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE"]
# Entries of the country index that CEPII BACI's country list (country_codes_V202601.csv) does not have, as Natural Earth
# 1:50m admin-0 (the base map, raw/naturalearth/ne_50m) describes them: TYPE, SOVEREIGNT, NOTE_BRK.
NE_STATUS = {
    "ALA": ("Country", "Finland", ""), "FRO": ("Dependency", "Denmark", ""), "GGY": ("Country", "United Kingdom", "U.K. crown dependency"),
    "HMD": ("Dependency", "Australia", ""), "IMN": ("Country", "United Kingdom", "U.K. crown dependency"),
    "JEY": ("Country", "United Kingdom", "U.K. crown dependency"), "KOS": ("Disputed", "Kosovo", ""),
    "LIE": ("Sovereign country", "Liechtenstein", ""), "MCO": ("Sovereign country", "Monaco", ""),
    "CYN": ("Sovereign country", "Northern Cyprus", "Self admin.; Claimed by Cyprus"), "PRI": ("Dependency", "United States of America", ""),
    "SGS": ("Dependency", "United Kingdom", ""), "KAS": ("Indeterminate", "Kashmir", "Claimed by Pakistan and India"),
    "SOL": ("Sovereign country", "Somaliland", "Self admin.; Claimed by Somalia"), "MAF": ("Dependency", "France", ""),
    "TWN": ("Sovereign country", "Taiwan", "Self admin.; Claimed by China"), "VIR": ("Dependency", "United States of America", ""),
    "VAT": ("Sovereign country", "Vatican", ""), "ESH": ("Indeterminate", "Western Sahara", "Self admin.; Claimed by Morocco"),
}
SOVEREIGN_NAME = {"United States of America": "the United States", "United Kingdom": "the United Kingdom"}

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
               "bauxite": "Bauxite", "cobalt": "Cobalt intermediates and metal", "tin": "Tin (unwrought)"}
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


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# group of the customs frame -> atlas commodity, for the groups that have no pairs table (the pairs tables carry their own)
GROUP_K = {"natural-gas": "natural-gas", "uranium": "uranium", "zinc-metal": "zinc", "lead-ore": "lead", "lead-metal": "lead",
           "tin-ore": "tin", "tin-metal": "tin", "lithium": "lithium", "cobalt": "cobalt", "rare-earths": "rare-earths",
           "gold": "gold", "silver": "silver", "pgm": "pgm"}
# A traded product of a commodity: its exports and imports tables (section or extra key), the customs group of its
# partners, and the production table that would carry the country if it produced it (None: the atlas has none).
# The main table of each commodity is added in products() with the group MAIN_GROUP gives.
PRODUCTS = [
    ("copper", "refined-exports", "refined-imports", "copper-refined", "refinery"),
    ("nickel", "int-exports", "int-imports", "nickel-int", None),
    ("nickel", "ferro-exports", "ferro-imports", "nickel-fe", None),
    ("bauxite", "alumina-exports", "alumina-imports", "alumina", "refinery"),
    ("zinc", "metal-exports", None, "zinc-metal", None),
    ("lithium", "spodumene-exports", None, "spodumene", None),
    ("thermal-coal", "allcoal-exports", "allcoal-imports", "coal", None),
]
# the customs group of a commodity's main trade table; None: the table is not customs data (EIA) and has no partners here
MAIN_GROUP = {"copper": "copper-ore", "nickel": "nickel-ore", "zinc": "zinc-ore", "lead": "lead-ore", "tin": "tin-metal",
              "phosphate": "phosphate-rock", "thermal-coal": None, "met-coal": None, "natural-gas": None}
# precious metals: declared value, not gross weight, is the basis of the partner shares (dore and bullion weigh alike)
VALUE_SHARE_GROUPS = {"gold", "silver", "pgm"}
# extra tables of a commodity file: section of the profile, BACI value group ("" = no value), label
EXTRA_SIDE = {"refined-exports": ("exports", "copper-refined", "Copper (refined & blister)"),
              "refined-imports": ("imports", "copper-refined", "Copper (refined & blister)"),
              "int-exports": ("exports", "nickel-int", "Nickel (intermediates & metal)"),
              "int-imports": ("imports", "nickel-int", "Nickel (intermediates & metal)"),
              "ferro-exports": ("exports", "nickel-fe", "Nickel (ferro-nickel & NPI)"),
              "ferro-imports": ("imports", "nickel-fe", "Nickel (ferro-nickel & NPI)"),
              "spodumene-exports": ("exports", "spodumene", "Lithium (spodumene to China, Atlas estimate)"),
              "alumina-exports": ("exports", "alumina", "Alumina"),
              "alumina-imports": ("imports", "alumina", "Alumina"),
              "metal-exports": ("exports", "zinc-metal", "Zinc (refined)"),
              "allcoal-exports": ("exports", "coal", ALL_COAL),
              "allcoal-imports": ("imports", "coal", ALL_COAL),
              "tubes-exports": ("exports", "", "Steel tubes and pipes"),
              "lignite-production": ("production", "", "Lignite (part of thermal coal)"),
              "urea-production": ("production", "", "Urea"),
              "k2o-production": ("production", "", "Potash (K2O content)"),
              # the 27 member states of the EU, beside USDA's single European Union row (FAOSTAT production, customs trade); the tables
              # are `norank` and their `world` is the EU total: the share of a line is read on `worldAll`, the world total of its source
              "eu-production": ("production", "", None), "eu-exports": ("exports", None, None), "eu-imports": ("imports", None, None)}
REFINERY_LABEL = {"copper": "Refined copper (refinery output)", "bauxite": "Alumina (refinery output)"}
SECTIONS = ("production", "refinery", "consumption", "reserves", "exports", "imports")


def series_at(h, iso):
    """The country's series of a history table, with its rank and the world total of each year under the rules of the
    site's past-year table (web/src/lib/tableYears.ts tableAt): a value out of line with the years around it is not
    ranked, and the world total of that year leaves it out."""
    vals = h["c"].get(iso)
    if not vals or not any(v for v in vals if v):
        return None
    out = h.get("out") or {}
    ranks, worlds = [], []
    for i in range(len(h["years"])):
        odd = [c for c, ix in out.items() if i in ix]
        oddv = sum(h["c"][c][i] or 0 for c in odd)
        worlds.append(round(h["world"][i] - oddv, 4) if h["world"][i] is not None else None)
        v = vals[i]
        if v is None or v <= 0 or iso in odd:
            ranks.append(None)
            continue
        ranks.append(1 + sum(1 for c, s in h["c"].items() if c not in odd and s[i] is not None and s[i] > v))
    e = {"hv": vals, "hr": ranks}
    for key, short in (("est", "hest"), ("out", "hout"), ("brk", "hbrk"), ("srcEst", "hsrc")):
        if (h.get(key) or {}).get(iso):
            e[short] = h[key][iso]
    if (h.get("cl") or {}).get(iso) and any(h["cl"][iso]):
        e["hcl"] = h["cl"][iso]
    return e, worlds


def hhi(shares):
    """Herfindahl index of a set of shares (0 to 1), on the usual scale of 0 to 10,000 (10,000: one partner only)."""
    return round(sum(s * s for s in shares) * 10000)


def partner_table(df, side, value=False):
    """{country: [(partner, amount, est), ...] largest first} of one product, for customers (side "o": the country exports)
    or suppliers (side "d")."""
    other = "d" if side == "o" else "o"
    col = "usd" if value else "t"
    g = df.groupby([side, other]).agg(v=(col, "sum"), est=("est", "max")).reset_index()
    out = defaultdict(list)
    for a, b, v, e in zip(g[side], g[other], g["v"], g["est"]):
        if v > 0:
            out[a].append((b, float(v), bool(e)))
    for a in out:
        out[a].sort(key=lambda x: -x[1])
    return out


def partner_rows(rows):
    """The first PARTNERS of one country's customers or suppliers with their shares, the Herfindahl index over every
    partner, and whether an Atlas estimate enters them."""
    tot = sum(v for _, v, _ in rows)
    if not tot:
        return None
    out = {"rows": [{"c": c, "share": round(v / tot, 4), **({"est": True} if e else {})} for c, v, e in rows[:PARTNERS]],
           "n": len(rows), "hhi": hhi([v / tot for _, v, _ in rows])}
    est = sum(v for _, v, e in rows if e)
    if est:
        out["est"] = True
        out["estShare"] = round(est / tot, 4)
    return out


def ne_text(iso, name, has_code):
    """What a country of the index is when it has no data, in Natural Earth's words, and why it has none."""
    st = NE_STATUS.get(iso)
    if st:
        typ, sov, note = st
        sov_name = SOVEREIGN_NAME.get(sov, sov)
        if "Claimed by" in note:
            claim = note.split("Claimed by ", 1)[1]
            what = (f"{name} is drawn by the base map (Natural Earth) as self-administered and claimed by {claim}" if "Self admin" in note
                    else f"{name} is drawn by the base map (Natural Earth) as an area claimed by {claim}")
        elif typ == "Disputed":
            what = f"{name} is drawn by the base map (Natural Earth) as a disputed area"
        elif "crown dependency" in note:
            what = f"{name} is drawn by the base map (Natural Earth) as a crown dependency of the United Kingdom"
        elif sov != name and typ in ("Dependency", "Country"):
            what = f"{name} is drawn by the base map (Natural Earth) as a dependency of {sov_name}"
        else:
            what = f"{name} is drawn by the base map (Natural Earth) as a sovereign country"
        why = "the customs data the atlas uses (CEPII BACI) have no code of their own for it"
    else:
        what = f"{name} is a territory of the base map (Natural Earth)"
        why = "the customs data (CEPII BACI) record no trade for it in the latest year" if has_code else "the customs data (CEPII BACI) have no code for it"
    return f"{what}. It has no data in the atlas: {why}, and no table of the atlas, no lane and no asset names it."


def no_code_note(iso, name):
    """For a country of the index with data but no customs code of its own (Taiwan has one, mapped by CODE_FIX)."""
    if iso not in NE_STATUS or iso == "TWN":
        return None
    return (f"The customs data the atlas uses (CEPII BACI) have no code of their own for {name}: its trade is not shown under "
            "its name, and its lanes and partners, if any, are those of another code.")


def main():
    data = os.path.join(ROOT, "data")
    idx = load_json(os.path.join(data, "commodities", "index.json"))
    names = {c["c"]: c["name"] for c in load_json(os.path.join(data, "countries", "index.json"))}
    tables, hist = {}, {}
    for c in idx:
        p = os.path.join(data, "commodities", f"{c['id']}.json")
        if os.path.exists(p):
            tables[c["id"]] = load_json(p)
        hp = os.path.join(data, "commodities", "history", f"{c['id']}.json")
        if os.path.exists(hp):
            hist[c["id"]] = load_json(hp)["t"]
    baci = pd.read_csv(os.path.join(CACHE, "baci_flows.csv.gz"))
    raw_baci = baci
    baci = baci.assign(o=baci["o"].replace(CODE_FIX), d=baci["d"].replace(CODE_FIX))
    latest = int(baci["year"].max())
    b = baci[baci["year"] == latest]
    exp_usd = b.groupby(["o", "group"])["usd"].sum()
    imp_usd = b.groupby(["d", "group"])["usd"].sum()

    def usd(series, iso, k):
        groups = VALUE_GROUPS.get(k, [k])
        return float(sum(series.get((iso, g), 0.0) for g in groups)) * 1000  # thousand USD -> USD

    profiles = {}

    def prof(iso):
        return profiles.setdefault(iso, {"c": iso, "exports": [], "imports": [], "production": [], "consumption": [], "reserves": []})

    years_of = {}  # history key -> {"y": years, "l": labels, "w": world per year}

    # ---- lines: every row of every table
    lines = []  # (iso, section, entry, table key)
    for k, d in tables.items():
        sections = [(sec, d.get(sec), None, None, sec) for sec in SECTIONS]
        for ex in d.get("extra") or []:
            if ex["key"] in EXTRA_SIDE:
                side, grp, label = EXTRA_SIDE[ex["key"]]
                sections.append((side, ex["table"], grp, label, ex["key"]))
        for section, t, grp, label, tkey in sections:
            if not t or not t.get("rows"):
                continue
            world = t.get("worldAll") or t.get("world") or sum(r["v"] for r in t["rows"])
            h = (hist.get(k) or {}).get(tkey)
            hk = f"{k}/{tkey}"
            for i, r in enumerate(t["rows"]):
                share = r["v"] / world if world else None
                e = {"k": k, "v": r["v"], "u": t["u"], "share": round(share, 4) if share else None, "rank": i + 1,
                     "y": r.get("y", t["y"]), "s": r.get("s", t["s"])}
                if r.get("est") or t["s"] == "atlas":
                    # most of the row's tonnage is an Atlas estimate, or the table is the atlas's own: the row is credited
                    # to the atlas. A table that only converts a published figure to another unit ("Atlas conversion") is
                    # not an estimate and carries no estimate mark.
                    e["s"] = "atlas"
                    if r.get("est") or not str(t.get("n") or "").startswith("Atlas conversion"):
                        e["est"] = True
                lab = label or (REFINERY_LABEL.get(k) if section == "refinery" else PRODUCTION_LABEL.get(k) if section == "production" else
                                TRADE_LABEL.get(k) if section in ("exports", "imports") else None)
                if lab:
                    e["label"] = lab
                if t.get("basis"):
                    e["basis"] = t["basis"]
                if section in ("exports", "imports") and grp != "":
                    series = exp_usd if section == "exports" else imp_usd
                    val = float(series.get((r["c"], grp), 0.0)) * 1000 if grp else usd(series, r["c"], k)
                    if val:
                        # the value has its own source and year, whatever the tonnage comes from
                        e["usd"], e["usdS"], e["usdY"] = round(val / 1e9, 3), "baci", latest
                if r.get("n"):
                    e["n"] = r["n"]
                if t.get("caveat"):
                    e["warn"] = t.get("caveatShort") or t["caveat"]  # warning of the whole table (trade hubs, gross weight...), short form for a profile row
                if t.get("norank"):
                    e["_norank"] = True  # the order of the table is not a world ranking (LNG customs tonnage): no rank is printed
                e["t"] = tkey
                if h:
                    sa = series_at(h, r["c"])
                    if sa:
                        ser, worlds = sa
                        e.update(ser)
                        e["hk"] = hk
                        if hk not in years_of:
                            years_of[hk] = {"y": h["years"], "w": worlds, **({"l": h["labels"]} if h.get("labels") else {})}
                lines.append((r["c"], "production" if section == "refinery" else section, e, tkey))

    top10 = {}
    for iso, section, e, _ in lines:
        if e["rank"] <= TOP_RANK and not e.get("_norank"):
            top10.setdefault(iso, set()).add(e["k"])
        if e.get("_norank"):
            e.pop("rank", None)
            e.pop("hr", None)
        e.pop("_norank", None)
        prof(iso)[section].append(e)

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
        for sec in ("production", "consumption", "reserves"):
            p[sec] = sorted(p[sec], key=lambda e: -(e["share"] or 0))
        if top10.get(iso):
            p["top10"] = len(top10[iso])

    # ---- reserves over production, where both are USGS lines of the same unit (years at the latest production rate)
    for iso, p in profiles.items():
        prod = {e["k"]: e for e in p["production"] if e.get("t") == "production"}
        for e in p["reserves"]:
            q = prod.get(e["k"])
            if q and q["u"] == e["u"] and q["s"] == e["s"] and q["v"]:
                e["rp"] = round(e["v"] / q["v"], 1)
                e["rpY"] = q["y"]

    # ---- basket: largest exports and imports at HS4 (every chapter) and raw materials outside the catalogue
    hs4_year = None
    hs4p, hs4i, hs4t = (os.path.join(CACHE, f) for f in ("hs4_exports.csv.gz", "hs4_imports.csv.gz", "hs4_totals.csv"))
    if all(os.path.exists(f) for f in (hs4p, hs4i, hs4t)):
        he = pd.read_csv(hs4p, dtype={"hs4": str})
        hi = pd.read_csv(hs4i, dtype={"hs4": str})
        tot = pd.read_csv(hs4t)
        hs4_year = int(he["t"].max())
    if hs4_year is not None and hs4_year != latest:
        # the HS4 extract and the customs frame come from different BACI versions: the basket would mix two years
        print(f"WARNING: HS4 extract of {hs4_year} against customs frame of {latest}: basket and other headings left out")
        hs4_year = None
    if hs4_year is not None:
        desc = pd.read_csv(os.path.join(CACHE, "hs4_exports_desc.csv"), dtype={"hs4": str}).set_index("hs4")["description"].to_dict()
        codes = catalogue_hs()
        head_k = defaultdict(set)  # HS4 heading -> atlas commodities whose codes sit under it
        group_k = dict(GROUP_K)
        for f in glob.glob(os.path.join(data, "freight", "pairs", "*.json")):
            pf = load_json(f)
            group_k[pf["group"]] = pf["k"]
        for g, lst in HS.items():
            k = group_k.get(g, g if g in tables else None)
            for c in lst:
                c = c.rstrip("*")
                heads = {c[:4]} if len(c) >= 4 else {h for h in desc if h.startswith(c)}
                for hd in heads:
                    head_k[hd].add(k)

        def label_of(hs4):
            text = str(desc.get(hs4, hs4))
            return HS4_LABEL.get(hs4) or text.split(":")[0].split(";")[0][:60], text

        for frame, who, side in ((he, "o", "exports"), (hi, "d", "imports")):
            frame = frame[frame[who].notna()].assign(**{who: frame[who].replace(CODE_FIX)})
            totals = tot.assign(c=tot["c"].replace(CODE_FIX)).set_index("c")[side]
            for iso, g in frame.groupby(who):
                total = float(totals.get(iso, 0) or 0)
                if not total:
                    continue
                top = g.sort_values("usd", ascending=False).head(BASKET_ROWS)
                rows = []
                for r in top.itertuples():
                    lab, text = label_of(r.hs4)
                    ks = head_k.get(r.hs4) or set()
                    row = {"hs4": r.hs4, "label": lab, "usd": round(r.usd / 1e6, 3), "share": round(r.usd / total, 4)}
                    if len(ks) == 1 and None not in ks:
                        row["k"] = next(iter(ks))
                    if text != lab:
                        row["d"] = text[:160]
                    rows.append(row)
                prof(iso).setdefault("basket", {"y": hs4_year, "s": "baci"})[side] = {"total": round(total / 1e6, 3), "rows": rows}
        # raw materials outside the catalogue (the "country check": diamonds for Botswana, logs for Gabon)
        raw = he[he["o"].notna() & he["hs4"].str[:2].isin(RAW_CHAPTERS)]
        raw = raw.assign(o=raw["o"].replace(CODE_FIX))
        world_hs4 = raw.groupby("hs4")["usd"].sum()
        rank_hs4 = raw.assign(r=raw.groupby("hs4")["usd"].rank(ascending=False, method="min")).set_index(["o", "hs4"])["r"]
        for iso, g in raw.groupby("o"):
            total = g["usd"].sum()
            if total < OTHER_MIN_TOTAL:  # < USD 200 million of raw-material exports: skip
                continue
            out = []
            for r in g.sort_values("usd", ascending=False).itertuples():
                if len(out) >= OTHER_ROWS or r.usd / total < OTHER_MIN_SHARE:
                    break
                if covered(r.hs4, codes):
                    continue
                lab, _ = label_of(r.hs4)
                out.append({"k": f"hs{r.hs4}", "label": lab, "v": round(r.usd / 1e6, 2), "u": "bn USD exports",
                            "share": round(r.usd / world_hs4[r.hs4], 4), "rank": int(rank_hs4.get((iso, r.hs4), 0)) or None,
                            "y": hs4_year, "s": "baci", "n": f"{r.usd / total:.0%} of the country's raw-material exports (HS {r.hs4})"})
            if out:
                prof(iso)["other"] = out

    # ---- partners and balance
    pairs_dir = os.path.join(data, "freight", "pairs")
    pair_frames, pair_meta = {}, {}
    for f in sorted(glob.glob(os.path.join(pairs_dir, "*.json"))):
        pf = load_json(f)
        cols = pf["cols"]
        rows = [dict(zip(cols, r)) for r in pf["rows"]]
        df = pd.DataFrame(rows)
        df["t"] = df["kt"] * 1000.0
        df["est"] = (df["f"].astype(int) & 1).astype(bool)
        pair_frames[pf["group"]] = df
        pair_meta[pf["group"]] = pf
    other_groups = sorted(set(GROUP_K) - set(pair_frames))
    cf = clean(raw_baci[raw_baci["group"].isin(other_groups)])
    cf = cf[cf["year"] == latest].assign(est=lambda x: x["imputed"].astype(bool))
    clean_frames = {g: x for g, x in cf.groupby("group")}

    def group_frame(g):
        return pair_frames.get(g) if g in pair_frames else clean_frames.get(g)

    def products():
        out = []
        for k in tables:
            g = MAIN_GROUP.get(k, k)
            out.append((k, "exports", "imports", g, "production"))
        return out + PRODUCTS

    for k, ek, ik, g, prod_key in products():
        d = tables.get(k) or {}
        etab = d.get(ek) or next((x["table"] for x in d.get("extra") or [] if x["key"] == ek), None)
        itab = (d.get(ik) or next((x["table"] for x in d.get("extra") or [] if x["key"] == ik), None)) if ik else None
        prod_tab = d.get(prod_key) if prod_key else None
        frame = group_frame(g) if g else None
        if frame is not None:
            value = g in VALUE_SHARE_GROUPS
            ptab = {side: partner_table(frame, side, value) for side in ("o", "d")}
        isos = set()
        for t in (etab, itab):
            isos |= {r["c"] for r in (t or {}).get("rows", [])}
        for iso in isos:
            if iso not in profiles:
                continue
            p = profiles[iso]
            el = next((e for e in p["exports"] if e["k"] == k and e["t"] == ek), None)
            il = next((e for e in p["imports"] if e["k"] == k and e["t"] == ik), None) if ik else None
            line = el or il
            row = {"k": k, "t": ek}
            if line.get("label"):
                row["label"] = line["label"]
            if etab and itab and etab["u"] == itab["u"] and str(etab["y"]) == str(itab["y"]):
                ev, iv = (el or {}).get("v", 0.0), (il or {}).get("v", 0.0)
                row["net"] = {"v": round(ev - iv, 4), "exp": ev if el else None, "imp": iv if il else None, "u": etab["u"],
                              "y": etab["y"], "s": (el or il)["s"], **({"est": True} if (el or {}).get("est") or (il or {}).get("est") else {})}
            cons = next((e for e in p["consumption"] if e["k"] == k), None) if ek == "exports" else None
            if il and cons and il["u"] == cons["u"] and str(il["y"]) == str(cons["y"]) and cons["v"] and round(il["v"] / cons["v"], 4) > 0:
                row["dep"] = {"v": round(il["v"] / cons["v"], 4), "y": il["y"], "s": il["s"], "u": il["u"], "imp": il["v"], "cons": cons["v"]}
            if frame is not None:
                for side, key in (("o", "customers"), ("d", "suppliers")):
                    pr = partner_rows(ptab[side].get(iso, []))
                    if pr:
                        row[key] = {**pr, "g": g, "y": latest, "s": "baci", **({"basis": "declared value"} if value else {})}
            # trading or refining hub: a derived label, where the atlas's own data show it
            full = prod_tab is not None and prod_tab.get("s") in FULL_PRODUCTION_SOURCES and not prod_tab.get("other")
            if full and el and il and (el.get("share") or 0) >= HUB_MIN_SHARE and (il.get("share") or 0) >= HUB_MIN_SHARE:
                if not any(r["c"] == iso for r in prod_tab.get("rows", [])):
                    row["hub"] = {"exp": el["share"], "imp": il["share"], "prodS": prod_tab["s"], "prodY": prod_tab["y"]}
            if len(row) > 3 or (len(row) == 3 and "label" not in row):
                p.setdefault("balance", []).append(row)

    # ---- freight: mode split, typical ports and passages, from the pairs tables of the engine
    for g, df in pair_frames.items():
        pf = pair_meta[g]
        ports, bases = pf["ports"], pf.get("bases") or []
        gates = pf["gates"]
        for side, port_col in (("o", "load"), ("d", "dis")):
            for iso, mine in df.groupby(side):
                if iso not in profiles and iso not in names:
                    continue
                total = float(mine["kt"].sum())
                if total <= 0:
                    continue
                modes = {m: float(mine.loc[mine["m"] == i, "kt"].sum()) for i, m in enumerate(("sea", "transit", "mixed", "land"))}
                sea_rows = mine[mine["m"].isin([0, 1])]
                sea = float(sea_rows["kt"].sum())
                x = {"g": g, "k": pf["k"], "kt": round(total, 1), "modes": {m: round(v / total, 4) for m, v in modes.items() if v},
                     **({"est": True} if bool(mine["est"].any()) else {})}
                if sea > 0:
                    routed = sea_rows[sea_rows[port_col] >= 0]
                    unrouted = sea - float(routed["kt"].sum())
                    if unrouted >= 0.5:
                        x["unrouted"] = round(unrouted / sea, 4)
                    by_port = routed.groupby(port_col)["kt"].sum().sort_values(ascending=False)
                    pl = []
                    for pi, v in by_port.head(PORTS).items():
                        pr = ports[int(pi)]
                        bi = pr[5] if port_col == "dis" and len(pr) > 5 else pr[4]
                        pl.append({"name": pr[1], "c": pr[2], "share": round(float(v) / sea, 4),
                                   **({"basis": bases[bi]} if bi is not None and bi < len(bases) else {})})
                    x["ports"] = pl
                    via, every = [], {}
                    vm, am, kt = (sea_rows[c].to_numpy() for c in ("via", "alt", "kt"))
                    for gi, gate in enumerate(gates):
                        must = (vm.astype("int64") >> gi) & 1 == 1
                        may = ((am.astype("int64") >> gi) & 1 == 1) & ~must
                        low, high = float(kt[must].sum()), float(kt[must].sum() + kt[may].sum())
                        if high:
                            every[gate] = (low, high)
                        if high / sea >= PASSAGE_MIN_SHARE:
                            via.append({"id": gate, "low": round(low / sea, 4), "high": round(high / sea, 4)})
                    x["via"] = sorted(via, key=lambda v: (-v["low"], -v["high"]))
                    x["_every"] = every
                    x["seaKt"] = round(sea, 1)
                fr = prof(iso).setdefault("freight", {"y": int(pf["y"]), "s": "baci", "exports": [], "imports": []})
                fr["exports" if side == "o" else "imports"].append(x)
    for p in profiles.values():
        fr = p.get("freight")
        if not fr:
            continue
        for side in ("exports", "imports"):
            rows = sorted(fr[side], key=lambda x: -x["kt"])
            fr[side] = rows
            sea = sum(x.get("seaKt", 0) for x in rows)
            allkt = sum(x["kt"] for x in rows)
            if not allkt:
                continue
            tot = {"kt": round(allkt, 1), "sea": round(sum(x["kt"] * (x["modes"].get("sea", 0) + x["modes"].get("transit", 0)) for x in rows) / allkt, 4),
                   "mixed": round(sum(x["kt"] * x["modes"].get("mixed", 0) for x in rows) / allkt, 4)}
            if sea:
                low, high = defaultdict(float), defaultdict(float)
                for x in rows:
                    for gid, (lo, hi) in x.get("_every", {}).items():
                        low[gid] += lo
                        high[gid] += hi
                tot["seaKt"] = round(sea, 1)
                tot["via"] = sorted(({"id": gid, "low": round(low[gid] / sea, 4), "high": round(high[gid] / sea, 4)} for gid in high
                                     if high[gid] / sea >= PASSAGE_MIN_SHARE), key=lambda v: (-v["low"], -v["high"]))
            fr[side + "Total"] = tot
        for side in ("exports", "imports"):
            for x in fr[side]:
                x.pop("_every", None)

    # ---- gaps: what customs data miss for this origin (caveats of the engine)
    cav_path = os.path.join(data, "freight", "caveats.json")
    if os.path.exists(cav_path):
        gk = {g: m["k"] for g, m in pair_meta.items()}
        for cid, cv in load_json(cav_path).items():
            if cv.get("d") is None and cv.get("o"):
                p = prof(cv["o"])
                p.setdefault("gaps", []).append({"id": cid, "k": gk.get(cv["group"], GROUP_K.get(cv["group"], cv["group"])), "g": cv["group"],
                                                 "kind": cv["kind"], "text": cv["text"]})

    # ---- infrastructure, operators and companies
    by_country, operators = {}, defaultdict(lambda: defaultdict(set))
    for f in sorted(glob.glob(os.path.join(data, "infrastructure", "*.geojson"))):
        for ft in load_json(f)["features"]:
            pr = ft["properties"]
            for iso in {pr.get("c")} | set(pr.get("cs") or []):
                if iso:
                    by_country.setdefault(iso, {}).setdefault(pr["type"], []).append(f"{pr['type']}:{pr['id']}")
                    if pr.get("operator"):
                        operators[iso][pr["operator"]].add(f"{pr['type']}:{pr['id']}")
    TYPE_ORDER = ["field", "refinery", "lng-export", "mine", "pipeline", "port", "smelter", "lng-import"]
    for iso, types in by_country.items():
        # No ranking here: capacities come in different units (kb/d, Mt/y, kt/y...) and a raw number says nothing across
        # them. The page ranks the assets among comparable figures (web/src/components/views/InfraList.tsx).
        queues = [sorted(types[t]) for t in TYPE_ORDER if t in types] + [sorted(types[t]) for t in sorted(types) if t not in TYPE_ORDER]
        ordered = []
        while any(queues):  # one asset per type in turn: every type is represented
            for q in queues:
                if q:
                    ordered.append(q.pop(0))
        p = prof(iso)
        p["infra"] = ordered
        if operators.get(iso):
            p["operators"] = sorted(({"name": n, "assets": sorted(a)} for n, a in operators[iso].items()), key=lambda o: (-len(o["assets"]), o["name"]))
    cp = os.path.join(data, "commodities", "companies.json")
    if os.path.exists(cp):
        found = {}
        role_rank = {"producers": 0, "processors": 1, "traders": 2}
        order = 0
        for k, groups in load_json(cp).items():
            for role in ("producers", "processors", "traders"):
                for co in groups.get(role) or []:
                    iso = co.get("hq")
                    if not iso:
                        continue
                    key = (iso, co["name"])
                    if key not in found:
                        found[key] = ({k2: co[k2] for k2 in ("name", "hq", "role", "detail", "s", "y", "url") if k2 in co} | {"k": []},
                                      role_rank[role], order)
                        order += 1
                    if k not in found[key][0]["k"]:
                        found[key][0]["k"].append(k)
        for (iso, _), (co, rr, o) in sorted(found.items(), key=lambda x: (-len(x[1][0]["k"]), x[1][1], x[1][2])):
            prof(iso).setdefault("companies", []).append(co)

    # ---- the EU: member states and the EU27 aggregate of USDA PSD link to each other
    if "EU27" in profiles:
        profiles["EU27"]["members"] = EU27
        for iso in EU27:
            prof(iso)["eu"] = "EU27"

    # ---- write: one file per country of the index, and the light index
    has_code = set(pd.read_csv(os.path.join(CACHE, "baci_country_codes.csv"), dtype=str)["country_iso3"].dropna()) | {"TWN"}
    os.makedirs(OUT_DIR, exist_ok=True)
    index, size = {}, 0
    for iso in sorted(set(names) | {c for c in profiles if c == "EU27"}):
        p = profiles.get(iso)
        if p is None:
            p = {"c": iso, "none": ne_text(iso, names.get(iso, iso), iso in has_code)}
            index[iso] = {"none": p["none"]}
        else:
            note = no_code_note(iso, names.get(iso, iso))
            if note:
                p["noCode"] = note
            for sec in ("exports", "imports", "production", "consumption", "reserves"):
                for e in p[sec]:
                    e.pop("t", None)
            p["years"] = {hk: years_of[hk] for hk in sorted({e["hk"] for sec in ("exports", "imports", "production", "consumption", "reserves")
                                                              for e in p[sec] if e.get("hk")})}
            n = sum(len(p[sec]) for sec in ("exports", "imports", "production", "consumption", "reserves"))
            index[iso] = {"n": n, **({"top10": p["top10"]} if p.get("top10") else {})}
        path = os.path.join(OUT_DIR, f"{iso}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(p, fh, separators=(",", ":"), ensure_ascii=False)
        size += os.path.getsize(path)
    for f in glob.glob(os.path.join(OUT_DIR, "*.json")):  # a code that left the index keeps no file
        if os.path.basename(f)[:-5] not in index:
            os.remove(f)
    stray = sorted(set(profiles) - set(index))
    if stray:
        print("WARNING: profiles for codes outside the index, not written:", stray)
    out = os.path.join(data, "countries", "profiles.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(index, fh, separators=(",", ":"), ensure_ascii=False)
    with_data = sum(1 for v in index.values() if "n" in v)
    print(f"profiles {with_data} with data, {len(index) - with_data} without; files {size / 1024:.0f} KB in all, "
          f"largest {max(os.path.getsize(f) for f in glob.glob(os.path.join(OUT_DIR, '*.json'))) / 1024:.0f} KB; index {os.path.getsize(out) / 1024:.0f} KB")

if __name__ == "__main__":
    main()
