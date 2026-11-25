"""
China's declared imports of tin ores and concentrates (HS 260900) from UN Comtrade, and the flows that the atlas adds from them to the
customs table (METHODOLOGY.md §1, rule 11 of clean.py).

    python pipeline/trade/comtrade_tin.py        # read raw/comtrade and write pipeline/cache/comtrade_tin_china.json
    import comtrade_tin; comtrade_tin.load()      # the cache only

Why: CEPII BACI reconciles the two declarations of a flow and, for China's imports of tin concentrate from Myanmar, keeps a figure of
39 to 161 t a year where China declares 76 to 187 kt (2021 to 2024): the first supplier is missing from the atlas's customs table.

Source: UN Comtrade public preview (https://comtradeapi.un.org/public/v1/preview/C/A/HS, no key): one call per year, reporter China
(156), flow imports, HS 260900, all partners, annual. The answers stay in raw/comtrade (git ignores raw/): the cache holds only what the pages
print, for each year China's declared total, the Myanmar figure, and the five largest origins, in tonnes (net weight; the answer is in kg) and
the declared value (CIF, USD), with the flags the answer carries (`est`: Comtrade estimated the net weight of the row). UN Comtrade's terms
allow "publication of limited amounts of UN Comtrade data in a few tables, graphs, visualization", with the attribution "Source: UN Comtrade",
and not a download of the data: the answers are not published.

Myanmar's own declaration (reporter Myanmar, exports, HS 260900) is read the same way when its files are on disk (`myanmar_exports`).
"""
import datetime
import glob
import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CACHE_FILE = os.path.join(ROOT, "pipeline", "cache", "comtrade_tin_china.json")
RAW = os.path.join(ROOT, "raw", "comtrade")
URL = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
CHINA, MYANMAR, WORLD = 156, 104, 0
TOP = 5

# Added flows (rule 11 of clean.py): (group, exporter, importer) -> what the importer declares and CEPII BACI lacks. The flow is taken from
# China's import declaration in every year of the cache; a year where the customs table has the pair at under REPLACE_BELOW of the declared
# tonnage has that row replaced, a year with no row gets one. Pair by pair: nothing else is added.
ADDED_FLOWS = {("tin-ore", "MMR", "CHN"): "myanmar"}
SOURCE_ID = "comtrade"  # the registry id (data/sources.json) of the rows rule 11 adds
REPLACE_BELOW = 0.1  # the customs row is replaced where it holds less than this share of the declared tonnage


def _rows(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    assert d.get("error") in ("", None), (path, d.get("error"))
    assert d["count"] == len(d["data"]) < 500, (path, d["count"], len(d["data"]))  # under the cap of the preview: the answer is whole
    return d["data"]


def _check(rows, year, reporter, flow):
    for r in rows:
        assert (r["refYear"], r["reporterCode"], r["flowCode"], r["cmdCode"]) == (year, reporter, flow, "260900"), r
        assert r["partner2Code"] == 0 and r["motCode"] == 0 and r["customsCode"] == "C00", r
        assert r["qtyUnitCode"] == 8, r  # 8 is the kilogram: it equals BACI's tonnes x 1000 where both give the pair


def build():
    with open(os.path.join(RAW, "reference", "partnerAreas.json"), encoding="utf-8") as f:
        iso = {a["PartnerCode"]: a["PartnerCodeIsoAlpha3"] for a in json.load(f)["results"]}
    years, stamp, no_weight = {}, [], {}
    for path in sorted(glob.glob(os.path.join(RAW, "tin-china-imports", "[0-9][0-9][0-9][0-9].json"))):
        y = int(os.path.basename(path)[:4])
        rows = _rows(path)
        _check(rows, y, CHINA, "M")
        stamp.append(os.path.getmtime(path))
        world = next(r for r in rows if r["partnerCode"] == WORLD)
        parts = [r for r in rows if r["partnerCode"] != WORLD]
        if world["netWgt"] == 0:
            # an answer that carries no net weight (2016 and before: Comtrade gives a quantity it estimated and a value): the year is not used, and said so
            mm0 = [r for r in parts if r["partnerCode"] == MYANMAR]
            no_weight[str(y)] = {"estimated_quantity_t": round(world["qty"] / 1e3, 1), "usd": round(world["primaryValue"]),
                                 "myanmar_estimated_quantity_t": round(mm0[0]["qty"] / 1e3, 1) if mm0 else None}
            continue
        assert abs(sum(r["netWgt"] for r in parts) - world["netWgt"]) < 1.0, (y, "the origins do not add up to the World row")
        parts.sort(key=lambda r: -r["netWgt"])
        item = lambda r: {"c": iso[r["partnerCode"]], "t": round(r["netWgt"] / 1e3, 3), "usd": round(r["primaryValue"]),  # noqa: E731
                          "est": bool(r["isNetWgtEstimated"])}
        mm = [r for r in parts if r["partnerCode"] == MYANMAR]
        years[str(y)] = {"world": {"t": round(world["netWgt"] / 1e3, 3), "usd": round(world["primaryValue"]), "est": bool(world["isNetWgtEstimated"]),
                                   "origins": len(parts)},
                         "myanmar": item(mm[0]) if mm else None, "top": [item(r) for r in parts[:TOP]]}
    mexp = {}
    for path in sorted(glob.glob(os.path.join(RAW, "tin-myanmar-exports", "[0-9][0-9][0-9][0-9].json"))):
        y = int(os.path.basename(path)[:4])
        rows = _rows(path)
        _check(rows, y, MYANMAR, "X")
        stamp.append(os.path.getmtime(path))
        to_china = [r for r in rows if r["partnerCode"] == CHINA]
        world = [r for r in rows if r["partnerCode"] == WORLD]
        mexp[str(y)] = {"to_china_t": round(to_china[0]["netWgt"] / 1e3, 3) if to_china else None,
                        "world_t": round(world[0]["netWgt"] / 1e3, 3) if world else None, "rows": len(rows)}
    doc = {"source": "UN Comtrade", "url": URL, "reporter": "China", "flow": "imports", "hs": "260900", "unit": "t, net weight; USD, CIF",
           "retrieved": datetime.datetime.fromtimestamp(max(stamp), datetime.timezone.utc).date().isoformat(), "years": dict(sorted(years.items())),
           "no_net_weight": dict(sorted(no_weight.items())), "myanmar_exports": dict(sorted(mexp.items()))}
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    return doc


_DOC = {}


def load():
    if not _DOC:
        with open(CACHE_FILE, encoding="utf-8") as f:
            _DOC.update(json.load(f))
    return _DOC


def declared(year, key="myanmar"):
    """China's declared imports from the origin of ADDED_FLOWS in a year of the cache: {"t", "usd", "est"} or None."""
    y = load()["years"].get(str(year))
    return y and y.get(key)


def years():
    return sorted(int(y) for y in load()["years"])


def note(year, customs_t):
    """The note of an added row (the words of the page). customs_t: tonnes in the customs table (None when it has no row)."""
    d = load()
    x = d["years"][str(year)]["myanmar"]
    est = ", a net weight that Comtrade estimated" if x["est"] else ""
    have = f"CEPII BACI has {customs_t:,.0f} t for the pair" if customs_t else "CEPII BACI has no row for the pair"
    return (f"Added from China's import declaration (UN Comtrade, HS 260900, {year}); not in CEPII BACI: {x['t']:,.0f} t, CIF USD {x['usd'] / 1e6:,.0f} million{est}; "
            f"{have}. Source: UN Comtrade")


if __name__ == "__main__":
    d = build()
    print("wrote", os.path.relpath(CACHE_FILE, ROOT), "years", list(d["years"]), "myanmar exports", list(d["myanmar_exports"]))
    for y, v in d["years"].items():
        print(y, "world", v["world"]["t"], "t; Myanmar", v["myanmar"] and v["myanmar"]["t"], "t;", [(x["c"], x["t"]) for x in v["top"]])
