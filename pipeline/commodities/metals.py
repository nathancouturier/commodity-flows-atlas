"""
Metals pages built from tables that are already on disk (audit M-017, M-018, A-013, A-014, C-043).

    called once by build_commodities.main() after every commodity table is built:  metal_pages(B, docs, us, baci, index)

  * apparent consumption of refined copper, primary aluminium and crude steel, as an Atlas estimate: production plus imports
    minus exports of the same product and year (apparent_consumption), and the apparent consumption the USGS file states for
    the United States, and its net import reliance (published figures, `us` of the commodity file);
  * concentration of every table with a world total: share of the first country, of the first three, Herfindahl index;
  * the customs value and unit value of the rows of the trade tables (`usd`, `uv`);
  * the six-digit split of refined copper (HS 7403 against 7402) and of unwrought aluminium (HS 760110 against 760120),
    from pipeline/cache/baci_hs6_detail.csv.gz (pipeline/trade/extract_hs6_detail.py);
  * short notes on the rows of exporters that the USGS tables do not name as producers;
  * the iron content tables that USGS publishes for iron ore.

The helpers that need no file (herfindahl, concentration, unit_value, apparent_consumption) are pure and tested
(pipeline/tests/test_metals.py). `B` is the module of build_commodities, passed in because it cannot be imported from here.
"""
import math
import os
import re
from collections import defaultdict

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
HS6_DETAIL = os.path.join(ROOT, "pipeline", "cache", "baci_hs6_detail.csv.gz")

UNIT_VALUE_MAX_EST = 0.10  # a row with this share of its tonnage or more estimated from the declared value shows no unit value


def sig(v, digits=3):
    if not v:
        return v
    r = round(v, digits - 1 - int(math.floor(math.log10(abs(v)))))
    return int(r) if abs(r) >= 10 ** (digits - 1) else r


def _n(v, digits=3):
    """A figure with thousands separators and `digits` significant digits at most: 1,234 -> 1,230; 0.4567 -> 0.457."""
    r = sig(v, digits)
    return f"{r:,}" if isinstance(r, int) or abs(r) >= 1000 else f"{r:g}"


# ---------------------------------------------------------------- pure helpers
def herfindahl(shares):
    """Herfindahl-Hirschman index of shares given as fractions of one total: the sum of the squares of the percentages.
    It runs from near 0 (very many equal-sized countries) to 10,000 (one country holds everything)."""
    return sum((100.0 * s) ** 2 for s in shares)


def concentration(table):
    """Share of the first country, of the first three and Herfindahl index of a table of countries, on the table's own world total
    (the sum its shares use). Computed on every country of the table; the source's "Other countries" line is several countries and
    is not counted, so the index is a lower bound where the line is large (`cov`: the share of the total the countries cover).
    `est` when the table or a row is an Atlas estimate. None for a table without a world total."""
    rows, world = table.get("rows") or [], table.get("world")
    if not rows or not world or world != world:
        return None
    sh = sorted(((r["c"], r["v"] / world) for r in rows), key=lambda x: -x[1])
    hhi = herfindahl(s for _, s in sh)
    out = {"top1": {"c": sh[0][0], "p": round(sh[0][1], 4)}, "top3": round(sum(s for _, s in sh[:3]), 4), "hhi": round(hhi),
           "eq": round(10000 / hhi, 1) if hhi else None, "k": len(sh), "cov": round(sum(s for _, s in sh), 4)}
    if table.get("est") or any(r.get("est") for r in rows) or (table.get("s") == "atlas" and str(table.get("n", "")).startswith("Atlas estimate")):
        out["est"] = True
    return out


def _digits(x):
    """Digits of a whole figure: 22 -> 2, 535,511 -> 6 (a figure under 1 counts for one)."""
    return len(str(int(round(x)))) if x >= 1 else 1


def unit_value(usd_thousand, tonnes, est_share=0.0):
    """USD per tonne of a customs value in thousand USD and a tonnage (both unrounded), to three significant digits at most: customs
    give whole tonnes and whole thousands of USD, so a row of 22 t or of 5 thousand USD carries fewer digits than that and shows
    fewer. None where 10% or more of the tonnage is an Atlas estimate: the declared value was used to compute it, so the quotient
    would only return the reference unit value of the estimate."""
    if est_share >= UNIT_VALUE_MAX_EST or not tonnes or tonnes <= 0 or not usd_thousand or usd_thousand <= 0:
        return None
    return sig(float(usd_thousand) * 1000 / float(tonnes), min(3, _digits(tonnes), _digits(usd_thousand)))


def apparent_consumption(production, imports, exports):
    """Production plus imports minus exports, by country. Each argument is {iso: value} in one unit. A country enters when it has
    the three terms and the result is positive. -> (rows [(iso, value, (production, imports, exports))] largest first,
    missing [iso: a term is missing], negative [iso])."""
    rows, missing, negative = [], [], []
    for c in sorted(production):
        if c not in imports or c not in exports:
            missing.append(c)
            continue
        v = production[c] + imports[c] - exports[c]
        if v > 0:
            rows.append((c, v, (production[c], imports[c], exports[c])))
        else:
            negative.append(c)
    rows.sort(key=lambda r: -r[1])
    return rows, missing, negative


# ---------------------------------------------------------------- USGS figures of the United States
US_NAMES = {  # atlas id -> (salient statistics names of the USGS file, names of Fig2 "net import reliance")
    "iron-ore": (["Iron Ore"], []), "steel": (["Iron And Steel"], []), "copper": (["Copper"], ["COPPER, refined"]),
    "aluminium": (["Aluminum"], ["ALUMINUM"]), "bauxite": (["Bauxite", "Alumina"], ["BAUXITE", "ALUMINA"]), "nickel": (["Nickel"], ["NICKEL"]),
    "zinc": (["Zinc"], ["ZINC, refined"]), "lead": (["Lead"], ["LEAD, refined"]), "tin": (["Tin"], ["TIN, refined"]),
    "lithium": (["Lithium"], ["LITHIUM"]), "cobalt": (["Cobalt"], ["COBALT"]), "rare-earths": (["Rare Earths"], ["RARE EARTHS, compounds and metals"]),
    "manganese": (["Manganese"], ["MANGANESE"]), "gold": (["Gold"], []), "silver": (["Silver"], ["SILVER"]),
    "pgm": (["Platinum", "Palladium"], ["PLATINUM", "PALLADIUM"]),
}
US_UNIT = {"thousand metric tons": "kt", "metric tons": "t", "million metric tons": "Mt", "kilograms": "kg"}
_USGS_CACHE = {}


def _usgs_all(path):
    if path not in _USGS_CACHE:
        d = pd.read_csv(path, encoding="latin-1", dtype=str)
        _USGS_CACHE[path] = d[d["Section"].str.contains("Salient", na=False)].copy()
    return _USGS_CACHE[path]


def _num(v):
    v = (v or "").replace(",", "").strip()
    return float(v) if re.fullmatch(r"\d+(\.\d+)?", v) else None


def us_consumption(path, names, years):
    """The apparent consumption of the United States that the USGS file states (lines 'Consumption ... apparent'), for each year
    of `years`. A value USGS withholds (W) is not a figure and is left out. -> [{label, u, vals: [{y, v, est}], n}]"""
    d = _usgs_all(path)
    d = d[d["Commodity"].isin(names) & (d["Statistics"] == "Consumption") & d["Statistics_detail"].str.contains("pparent", na=False)]
    out = []
    for (com, det, unit), g in d.groupby(["Commodity", "Statistics_detail", "Unit"], sort=False):
        vals, note = [], ""
        for _, r in g.sort_values("Year").iterrows():
            v = _num(r["Value"])
            if v is None or int(r["Year"]) not in years:
                continue
            n = r["Notes"] if isinstance(r["Notes"], str) else ""
            vals.append({"y": int(r["Year"]), "v": v, "est": n.startswith("Estimated")})
            note = n.replace("Estimated. -- ", "").replace("Estimated.", "").replace("\x96", "-").replace("\x80\x93", "-").strip() or note
        if vals:
            out.append({"label": det if len(names) == 1 else f"{com}: {det}", "u": US_UNIT.get(unit, unit), "vals": vals, **({"n": note} if note else {})})
    return out


def us_reliance(fig2_path, names):
    """Net import reliance of the United States as USGS publishes it (Fig2 of the Mineral Commodity Summaries), with its main
    import sources. The percentage is kept as published (">75", "57"). The year of the percentage and the period of the sources are
    read from the names of the file's columns (Net_Import_Reliance_pct_2025, Major_Import_Sources_2021_24)."""
    import csv
    out = []
    with open(fig2_path, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        pct_col = next((c for c in rd.fieldnames if re.fullmatch(r"Net_Import_Reliance_pct_\d{4}", c)), None)
        src_col = next((c for c in rd.fieldnames if re.fullmatch(r"Major_Import_Sources_\d{4}_\d{2}", c)), None)
        if not pct_col:
            raise SystemExit(f"{fig2_path}: no column Net_Import_Reliance_pct_<year>: the file's layout changed")
        by = {r["Commodity"].strip(): r for r in rd}
    year = int(pct_col[-4:])
    period = None
    if src_col:
        a, b = src_col.split("_")[-2:]
        period = f"{a} to {a[:2]}{b}"
    for n in names:
        r = by.get(n)
        if not r:
            continue
        pct = r[pct_col].strip()
        srcs = r[src_col].strip() if src_col else ""
        out.append({"what": n[:1] + n[1:].lower() if n.isupper() or n.split(",")[0].isupper() else n, "pct": pct, "y": year,
                    **({"src": srcs, "srcYears": period} if srcs not in ("", "NA") else {}),
                    **({"n": r["Notes"].strip()} if r.get("Notes") else {})})
    return out


# ---------------------------------------------------------------- six-digit split of a group
SPLITS = {  # group -> {derived group: (hs6 codes, label)}
    "copper-refined": {"copper-7403": (("740311", "740312", "740313", "740319"), "refined copper (HS 7403)"),
                       "copper-7402": (("740200",), "unrefined copper, anodes and blister (HS 7402)")},
    "aluminium": {"aluminium-760110": (("760110",), "unwrought aluminium, not alloyed (HS 760110)"),
                  "aluminium-760120": (("760120",), "unwrought aluminium alloys (HS 760120)")},
}


def derive_groups(baci, B, path=HS6_DETAIL):
    """Adds to baci.df the groups of SPLITS: each pair of the cleaned frame is split between the codes by the shares of the raw
    six-digit rows of the same pair and year (tonnes; value for the value), so that the atlas's cleaning rules are kept.
    -> the years the split covers (empty when the extract is absent)."""
    if not os.path.exists(path):
        return []
    h = pd.read_csv(path, dtype={"hs6": str})
    h = h[h["o"].notna() & h["d"].notna()].copy()
    for c in ("o", "d"):
        h[c] = h[c].replace(B.BACI_OVERRIDE)  # BACI's "Other Asia, nes" is read as Taiwan, as the cleaned frame has it
    frames, years = [], set()
    for g, subs in SPLITS.items():
        x = h[h["group"] == g]
        if x.empty:
            continue
        key = ["year", "o", "d"]
        tot = x.groupby(key)[["t", "usd"]].sum().rename(columns={"t": "tt", "usd": "tv"})
        parent = baci.df[(baci.df["group"] == g) & baci.df["year"].isin(x["year"].unique())]
        for sg, (codes, _) in subs.items():
            part = x[x["hs6"].isin(codes)].groupby(key)[["t", "usd"]].sum()
            m = parent.join(part.rename(columns={"t": "pt", "usd": "pv"}), on=key).join(tot, on=key)
            fv = (m["pv"] / m["tv"]).where(m["tv"] > 0)
            ft = (m["pt"] / m["tt"]).where(m["tt"] > 0).fillna(fv).fillna(0.0)
            fv = fv.fillna(ft).fillna(0.0)
            keep = (ft > 0) | (fv > 0)
            n = m[keep].copy()
            n["group"] = sg
            for c in ("t", "t0", "t_est", "t0_est", "t_susp"):
                if c in n:
                    n[c] = n[c] * ft[keep]
            n["usd"] = n["usd"] * fv[keep]
            frames.append(n[baci.df.columns])
        years |= set(int(y) for y in x["year"].unique())
    if frames:
        baci.df = pd.concat([baci.df] + frames, ignore_index=True)
    return sorted(years)


# ---------------------------------------------------------------- the pages
CONSUMPTION = {  # id -> (USGS production table, trade source, words)
    "copper": dict(prod=("Copper", "Refinery production", 1.0, "kt Cu"), prod_label="refined copper production, primary and secondary (USGS)",
                   trade=("copper-7403", "refined copper (HS 7403)"), unit="kt", basis="refined copper, apparent consumption",
                   title="Apparent consumption — refined copper, {y} (Atlas estimate)", what="refined copper",
                   caveat="Trade is refined copper only (HS 7403, cathodes and refined forms); HS 7402, unrefined copper and anodes that refineries import, is left out. "
                          "Refinery output counts primary and secondary refined copper, trade in scrap is not known."),
    "aluminium": dict(prod=("Aluminum", "Smelter production", 1.0, "kt"), prod_label="primary aluminium smelter production (USGS)",
                      trade=("aluminium", "unwrought aluminium (HS 7601)"), unit="kt", basis="primary aluminium and unwrought trade, apparent consumption",
                      title="Apparent consumption — primary aluminium and unwrought trade, {y} (Atlas estimate)", what="primary aluminium",
                      caveat="Trade is unwrought aluminium, alloyed or not (HS 7601), which includes alloys made from scrap; production is primary smelter output only. "
                             "The result is smelter output plus net trade in unwrought metal, not the use of primary metal alone."),
    "steel": dict(prod=("Iron And Steel", "Raw steel", 1.0, "Mt"), prod_label="raw steel production (USGS)",
                  trade=("steel", "steel products, HS 72 without 7201 to 7205"), unit="Mt", basis="crude steel and steel products, apparent consumption",
                  title="Apparent consumption — crude steel and steel products, {y} (Atlas estimate)", what="steel",
                  caveat="Production is crude steel; trade is steel products in product weight, which the atlas does not convert to crude-steel equivalent "
                         "(it has no conversion read on a page). Trade between EU member states is counted."),
}


def _tab(d, key):
    t = d.get(key)
    return t if isinstance(t, dict) else next((x["table"] for x in d.get("extra") or [] if x["key"] == key), None)


def customs_by_country(B, baci, g, side):
    """{iso: (tonnes, tonnes that are an Atlas estimate)} of one side of a group, unrounded, for the countries of the atlas, as the
    ranked tables count them. A country with no flow in the extract (flows below 1,000 t and 1 million USD are not in it) has no entry."""
    d = baci.group(g)
    col = "o" if side == "exports" else "d"
    out = {}
    for code, r in d.groupby(col).agg(t=("t", "sum"), te=("t_est", "sum")).iterrows():
        iso = None if code in B.EXTRA_CODES else baci.iso(code)
        if iso and r["t"] > 0:
            t0, e0 = out.get(iso, (0.0, 0.0))
            out[iso] = (t0 + float(r["t"]), e0 + float(r["te"]))
    return out


def no_row_words(missing, imports, exports, name):
    """What is missing for the countries USGS names that have no consumption row for want of a customs row: -> text or ''."""
    no_i = [c for c in missing if c not in imports and c in exports]
    no_e = [c for c in missing if c in imports and c not in exports]
    both = [c for c in missing if c not in imports and c not in exports]
    names = lambda l: ", ".join(name(c) for c in sorted(l, key=name))
    parts = ([f"no import row: {names(no_i)}"] if no_i else []) + ([f"no export row: {names(no_e)}"] if no_e else []) + \
            ([f"no import and no export row: {names(both)}"] if both else [])
    return "; ".join(parts)


def not_listed(production, imports, exports, k=6):
    """The largest countries that have customs rows and no USGS production line, by net imports (imports minus exports, tonnes of the
    same product and year): [(iso, net)] largest first, net positive only. Their production is not known, and is not counted as zero
    in any table: this is the customs part of their apparent consumption, which is at least this much."""
    out = [(c, imports.get(c, 0.0) - exports.get(c, 0.0)) for c in set(imports) | set(exports) if c not in production]
    return sorted((x for x in out if x[1] > 0), key=lambda x: -x[1])[:k]


def consumption_tables(B, docs, us, baci):
    """Apparent consumption of the three products. Returns a report {id: (n listed, n missing, n negative)}.
    Imports and exports are summed from the cleaned customs frame in full precision (not from the rounded tables), so that no country
    is lost to a rounding and the figures reproduce by hand."""
    report = {}
    USGS = f"USGS MCS {B.USGS_EDITION}"
    y = str(B.BACI_YEAR)
    if str(int(B.USGS_YEAR) - 1) != y:  # USGS and customs year must be the same year
        return report
    for cid, spec in CONSUMPTION.items():
        d = docs.get(cid)
        if not d:
            continue
        com, det, fac, pu = spec["prod"]
        t = us.table(com, det, year=y, factor=fac)
        prod = dict(t["rows"])
        g, trade_label = spec["trade"]
        if g == "copper-7403" and baci.group(g).empty:  # the six-digit extract is absent: refined copper cannot be told from HS 7402
            continue
        ex_t, im_t = customs_by_country(B, baci, g, "exports"), customs_by_country(B, baci, g, "imports")
        if not ex_t or not im_t:
            continue
        u = spec["unit"]
        per = {"kt": 1e3, "Mt": 1e6}[u]  # tonnes in one unit of the table
        world = us.ranked(com, det, pu, fac, spec["prod_label"], year=y)[0]["world"]
        e = {c: v[0] / per for c, v in ex_t.items()}
        i = {c: v[0] / per for c, v in im_t.items()}
        rows, missing, negative = apparent_consumption(prod, i, e)
        est = lambda m, c: m[c][1] >= 0.5 * m[c][0]  # as the ranked tables mark a row that is mostly an Atlas estimate
        out_rows = []
        for c, v, (p, imp, exp) in rows:
            note = (f"production {_n(p)} {u} ({USGS} {y}) + imports {_n(imp)} {u} - exports {_n(exp)} {u} (CEPII BACI {y})"
                    + ("; the tonnage of its exports or imports is itself an Atlas estimate from the declared value" if est(ex_t, c) or est(im_t, c) else ""))
            out_rows.append((c, v, "Atlas estimate: " + note, True))
        names = lambda l: ", ".join(B.cname(c) for c in sorted(l, key=B.cname))
        n = [f"Atlas estimate: apparent consumption of {spec['what']} in {y}, by country: production plus imports minus exports of the same product and year, in {u}. "
             f"Production: {spec['prod_label']}, {USGS} {y} column. Imports and exports: CEPII BACI {y}, {trade_label}, gross weight, "
             f"with the atlas's cleaning rules, summed before any rounding. {spec['caveat']} Stock changes are not known, so this is apparent consumption, not measured use."]
        gap = no_row_words(missing, i, e, B.cname)
        n.append(f"Only the countries for which USGS gives production are listed ({len(prod)}); this is not a ranking of the world's consumers. "
                 f"{len(missing)} of them are left out for want of a customs row" + (f" ({gap}): the extract omits flows below 1,000 t and 1 million USD, "
                 "so this is a small flow or none, not a gap in USGS production, and it is not counted as zero" if missing else "")
                 + f"; {len(negative)} are left out because the result is negative" + (f" ({names(negative)})" if negative else "") + ".")
        nl = not_listed(prod, i, e)
        if nl:
            n.append("Not listed because USGS names no production for them: the largest of them by customs net imports (imports minus exports) are "
                     + ", ".join(f"{B.cname(c)} {_n(v)} {u}" for c, v in nl)
                     + f". Their apparent consumption is that plus their own production, which USGS does not name (it may sit in its 'Other countries' line): "
                       "they are absent because the table needs a production figure, not because they consume less than the countries listed.")
        n.append(f"World: the world production of the same product in {y} as USGS gives it ({_n(world)} {u}, the sum of its countries and its 'Other countries' line): "
                 "trade nets out in the world, so apparent consumption of the world is its production apart from changes in stocks, which are not known. "
                 "The shares are computed on it, and 'Countries not listed' is the world total minus the countries listed.")
        tab = B.ranked(out_rows, int(y), "atlas", u, world=world, n=" ".join(n), digits=3)
        tab["est"] = True
        tab["norank"] = True
        B.set_basis(tab, spec["basis"])
        d["consumption"] = tab
        d.setdefault("labels", {})["consumption"] = spec["title"].format(y=y)
        report[cid] = (len(rows), len(missing), len(negative))
    return report


def us_blocks(B, docs, us):
    d_all = B.USGS_FILE
    fig2 = os.path.join(os.path.dirname(d_all), "MCS2026_Fig2_Net_Import_Reliance.csv")
    for cid, (names, rel) in US_NAMES.items():
        d = docs.get(cid)
        if not d:
            continue
        years = {int(B.USGS_YEAR) - 1, int(B.USGS_YEAR)}
        cons = us_consumption(d_all, names, years)
        reliance = us_reliance(fig2, rel) if os.path.exists(fig2) else []
        if cons or reliance:
            d["us"] = {"s": "usgs-mcs", **({"consumption": cons} if cons else {}), **({"reliance": reliance} if reliance else {})}
        # the Atlas estimate of the United States, beside the figure USGS states
        t = d.get("consumption")
        if t and cons and t.get("s") == "atlas":
            main = cons[0]
            y = str(B.BACI_YEAR)
            v = next((x for x in main["vals"] if str(x["y"]) == y), None)
            r = next((r for r in t["rows"] if r["c"] == "USA"), None)
            if v and r:
                r["n"] += f"; USGS states the apparent consumption of the United States for {y} as {_n(v['v'])} {main['u']} ({main['label']}; a different definition: see the United States block)"


def iron_content(B, docs, us):
    d = docs.get("iron-ore")
    if not d:
        return
    pairs = (("fe-production", "Iron ore producers — Mt of iron content, as published by USGS", "Mine production: Iron content", "production", "iron content of the mine production"),
             ("fe-reserves", "Iron ore reserves — Mt of iron content, as published by USGS", "Reserves (million metric tons): Iron content", "reserves", "iron ore reserves, iron content"))
    for key, title, det, kind, label in pairs:
        fac = 1e-3 if kind == "production" else 1.0
        t, _ = us.ranked("Iron Ore", det, "Mt Fe", fac, label, kind=kind)
        B.set_basis(t, "iron content")
        d.setdefault("extra", []).append({"key": key, "title": title, "table": t})


def hs_split_tables(B, docs, baci, years):
    """Unwrought aluminium by code (HS 760110 not alloyed, HS 760120 alloys): exporters and importers, and a note on the largest
    pairs; refined copper (HS 7403) against HS 7402 in a note of the copper page."""
    d = docs.get("aluminium")
    if not d or B.BACI_YEAR not in years:
        return
    extra = d.setdefault("extra", [])
    for sg, (codes, label) in SPLITS["aluminium"].items():
        for side, word in (("exports", "exporters"), ("imports", "importers")):
            t, _ = baci.ranked(sg, side, "Mt", 1e6, label)
            t.pop("_hist", None)
            t.pop("_hn", None)
            B.set_basis(t, "gross weight")
            extra.append({"key": f"{sg.split('-')[1]}-{side}", "title": f"Unwrought aluminium {word}: " + ("not alloyed (HS 760110)" if codes[0] == "760110" else "alloys (HS 760120)"), "table": t})
    a, b = (baci.group(sg)["t"].sum() / 1e6 for sg in SPLITS["aluminium"])
    d.setdefault("notes", []).append(
        f"Unwrought aluminium is two customs codes of nearly equal weight in {B.BACI_YEAR}: HS 760110, not alloyed, {a:.1f} Mt, and HS 760120, alloys, {b:.1f} Mt. "
        "Each pair of the main tables is split between them in proportion to the six-digit rows of the same pair (CEPII BACI); "
        "alloys include ingot made from scrap, so the second code is where recycled metal is traded.")
    c = docs.get("copper")
    if c:
        x7, x2 = (baci.group(sg)["t"].sum() / 1e6 for sg in ("copper-7403", "copper-7402"))
        c.setdefault("notes", []).append(
            f"The 'refined and blister copper' tables add HS 7403 (refined copper, {x7:.1f} Mt in {B.BACI_YEAR}) and HS 7402 (unrefined copper and anodes, {x2:.1f} Mt, "
            "the feed of refineries). The apparent consumption table uses HS 7403 only.")


def add_values(B, docs, index):
    """`usd` (customs value, USD) and `uv` (USD per tonne) on the rows of the trade tables of the metals pages, from the declared values
    of the cleaned customs frame. A table that is not customs data, or a row whose tonnage is 10% or more estimated, has no unit value."""
    ids = [e["id"] for e in index if e.get("family") == "metals"]
    for cid in ids:
        d = docs.get(cid) or {}
        tabs = [d.get("exports"), d.get("imports")] + [x["table"] for x in d.get("extra") or []]
        for t in tabs:
            if not isinstance(t, dict) or "_usd" not in t:
                continue
            div = {"Mt": 1e6, "kt": 1e3, "t": 1.0}.get(t["u"])
            if not div:
                continue
            customs = t["s"] == "baci"  # a table of the atlas's own estimate (fine metal) shows the declared value and no unit value
            es = t.get("_es", {})
            # the unit value is the quotient of the unrounded value and tonnage (the table's tonnage is rounded to 4 decimals of its unit:
            # a row of 100 t is 0.0001 Mt), as the flows compute it
            tons = t.get("_t", {})
            for r in t["rows"]:
                usd = t["_usd"].get(r["c"])
                if usd is None:
                    continue
                r["usd"] = round(usd * 1000)
                uv = unit_value(usd, tons.get(r["c"], r["v"] * div), 1.0 if r.get("est") else es.get(r["c"], 0.0)) if customs else None
                if uv:
                    r["uv"] = uv
            if t.get("_usdw"):
                t["usd"] = round(t["_usdw"] * 1000)
                uv = None if t.get("_west") or not customs else unit_value(t["_usdw"], t.get("_tw", t["world"] * div))
                if uv:
                    t["uv"] = uv


# pairs of tables (exports, imports) of one product whose countries that both import and export it, in similar tonnages, get a note
HUB_PAIRS = {"iron-ore": ("exports", "imports"), "copper": ("exports", "imports", "refined-exports", "refined-imports"),
             "bauxite": ("exports", "imports"), "nickel": ("exports", "imports"),
             "zinc": ("exports", "imports"), "lead": ("exports", "imports"), "tin": ("exports", "imports"), "manganese": ("exports", "imports"),
             "cobalt": ("exports", "imports"), "aluminium": ("exports", "imports")}
HUB_MIN_SHARE = 0.015  # of the table, on both sides
HUB_MIN_RATIO = 0.5    # the smaller of the two tonnages over the larger
ORE_WORDS = re.compile(r"\bores?\b|concentrates?|bauxite")


def hub_reading(cid, basis):
    """The possible reading of a trade that is as large in imports as in exports, in the words of what the table counts: ore or
    concentrate is bought, blended or shipped on; metal is bought, stored or shipped on."""
    if cid in ("iron-ore", "bauxite") or ORE_WORDS.search(basis or ""):
        return "ore or concentrate bought, blended or shipped on there rather than mined or used there"
    return "metal bought, stored or shipped on there rather than made or used there"


def hub_notes(B, docs):
    """A note on the rows of countries that both import and export the same product in similar tonnages (audit C-043: Switzerland, the
    Netherlands, Singapore, Malaysia): what the atlas's own tables show; a country named as a producer by the page's USGS tables is
    left out (a producer USGS does not name, such as Thailand for tin, is not: it carries the note). The cause (metal or ore bought,
    stored, blended or transhipped there) is a hypothesis. Rows that already carry such a note are left alone."""
    hint = "a possible reading, not established here"
    done = []
    for cid, (ek, ik, *more) in ((c, (k[0], k[1], *([k[2], k[3]] if len(k) > 2 else []))) for c, k in HUB_PAIRS.items()):
        d = docs.get(cid)
        if not d:
            continue
        # a country the page's USGS tables name as a producer makes the metal it trades: no note
        named = {r["c"] for k in ("production", "refinery") for r in (d.get(k) or {}).get("rows", [])}
        for e_key, i_key in [(ek, ik)] + ([(more[0], more[1])] if more else []):
            e, i = _tab(d, e_key), _tab(d, i_key)
            if not e or not i or not e.get("world") or not i.get("world"):
                continue
            im = {r["c"]: (rank, r) for rank, r in enumerate(i["rows"], 1)}
            for rank, r in enumerate(e["rows"][:15], 1):
                if r["c"] not in im or r["c"] in named:
                    continue
                irank, ir = im[r["c"]]
                lo, hi = sorted((r["v"], ir["v"]))
                if r["v"] / e["world"] < HUB_MIN_SHARE or ir["v"] / i["world"] < HUB_MIN_SHARE or lo / hi < HUB_MIN_RATIO:
                    continue
                if "possible reading" in (r.get("n") or "") or "possible reading" in (ir.get("n") or ""):
                    continue
                txt = (f"{B.cname(r['c'])} is both an exporter (rank {rank}, {_n(r['v'])} {e['u']}) and an importer (rank {irank}, {_n(ir['v'])} {i['u']}) of this product, "
                       f"in similar tonnages: part of its trade may be {hub_reading(cid, e.get('basis'))} ({hint})")
                r["n"] = B.joinn(r.get("n"), txt)
                ir["n"] = B.joinn(ir.get("n"), txt)
                done.append(f"{cid}/{e_key}/{r['c']}")
    return done


def add_concentration(docs):
    for d in docs.values():
        out = {}
        for k in ("production", "refinery", "reserves", "exports", "imports"):
            c = concentration(d[k]) if isinstance(d.get(k), dict) and d[k].get("scope") in (None, "world") else None
            if c:
                out[k] = c
        for x in d.get("extra") or []:
            if x["table"].get("scope") not in (None, "world"):  # a table of the member states of the EU: its shares are of the EU total, not of the world
                continue
            c = concentration(x["table"])
            if c:
                out[x["key"]] = c
        if out:
            d["concentration"] = out


def metal_pages(B, docs, us, baci, index):
    """Entry point. Returns a short report (for the log)."""
    years = derive_groups(baci, B)
    hs_split_tables(B, docs, baci, years)
    rep = consumption_tables(B, docs, us, baci)
    iron_content(B, docs, us)
    us_blocks(B, docs, us)
    hubs = hub_notes(B, docs)
    add_values(B, docs, index)
    add_concentration(docs)
    return {"hs6_years": years, "consumption": rep, "hub_notes": hubs}
