"""
Monthly series of the EIA International file (raw/eia/INTL.txt, public domain) for the energy pages.

    data/commodities/monthly/crude-oil.json         production by producer, OECD imports by origin, petroleum stocks
    data/commodities/monthly/refined-products.json  oil demand by country (monthly), petroleum stocks
    data/commodities/monthly/lpg.json               natural gas plant liquids production by producer
    data/commodities/monthly/lng.json               nothing: only the list of what the file does not hold

The files are loaded by the page on demand (web/src/components/EnergyMonthly.tsx). They hold the last MONTHS_KEPT months of
each series, and for each series three figures that the page prints and that are arithmetic on published monthly figures:
the average of the baseline year (every month weighted by its number of days: for 2025 it equals EIA's own annual figure),
the lowest month of the latest year and the latest month, each with its month, and the change of the latest month against
that average in per cent. No figure is estimated: a month the source gives as withheld ("w"), not available ("NA") or
absent stays empty, and a figure that needs it is left out.

build_commodities.py calls write_all() with its own reading of the EIA geography codes (iso_of): the same countries as the tables.
"""
import calendar
import json
import os
import re

MONTHS_KEPT = 60
SOURCE = "eia-intl"
# countries on the Persian Gulf, whose crude leaves through the Strait of Hormuz (or, for Saudi Arabia and the Emirates, in part by pipeline)
GULF = ["SAU", "IRQ", "KWT", "QAT", "ARE", "IRN", "BHR"]
# the series that give OECD imports by origin: the importer of each product code ("78" is the OECD total, "78x" one importer)
IMPORTERS = {"78": ("OECD", "OECD"), "781": ("OEEU", "OECD Europe"), "782": ("FRA", "France"), "783": ("DEU", "Germany"),
             "784": ("ITA", "Italy"), "785": ("JPN", "Japan"), "786": ("KOR", "South Korea"), "787": ("USA", "U.S."),
             "788": ("CAN", "Canada"), "789": ("GBR", "United Kingdom")}
# the groups of origin the page shows (OPEC Africa and OPEC South America are left out: one is the sum of the African members, the other is Venezuela)
ORIGIN_LABEL = {"PERG": "Persian Gulf", "OPEC": "OPEC"}
# the petroleum stocks and the oil demand of the OECD: the geographies that EIA publishes month by month
STOCK_ORDER = ["OECD", "OEEU", "USA", "JPN", "DEU", "KOR", "CAN", "FRA", "ITA", "GBR"]
STOCK_LABEL = {"OECD": "OECD", "OEEU": "OECD Europe"}

LINE = re.compile(r'^\{"series_id":"INTL\.(\d+-\d+)-([A-Z0-9]+)-([A-Z0-9]+)\.M"')


def period(p):
    """'202604' -> '2026-04'."""
    return f"{p[:4]}-{p[4:]}"


def read(path, wanted):
    """({(product-activity, unit): {geo: {'YYYY-MM': value}}}, {(product-activity, unit): {geo: name}}) for the monthly series of `wanted`
    ({(product-activity, unit)}). A value that is not a number (withheld 'w', not available 'NA', '--') is left out."""
    out, names = {}, {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = LINE.match(line)
            if not m or (m.group(1), m.group(3)) not in wanted:
                continue
            o = json.loads(line)
            key, geo = (m.group(1), m.group(3)), m.group(2)
            out.setdefault(key, {})[geo] = {period(p): float(v) for p, v in o["data"] if isinstance(v, (int, float))}
            names.setdefault(key, {})[geo] = o["name"]
    return out, names


def scan(path):
    """({(product-activity, frequency): name} of every family of series of the file, {(product-activity, unit): last year of the World
    annual series}): what the file holds, to say on the page what it does not."""
    fam, ends = {}, {}
    pat = re.compile(r'^\{"series_id":"INTL\.(\d+-\d+)-([A-Z0-9]+)-([A-Z0-9]+)\.([AMQ])","name":"([^"]*)"')
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = pat.match(line)
            if not m:
                continue
            fam.setdefault((m.group(1), m.group(4)), m.group(5).rsplit(", ", 2)[0])
            if m.group(2) == "WORL" and m.group(4) == "A":
                o = json.loads(line)
                ys = [int(y) for y, v in o["data"] if isinstance(v, (int, float))]
                if ys:
                    ends[(m.group(1), m.group(3))] = max(ys)
    return fam, ends


def axis(last, n=MONTHS_KEPT):
    """The n months ending at `last` ('YYYY-MM'), oldest first."""
    y, m = int(last[:4]), int(last[5:])
    out = []
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def avg_year(vals, year):
    """Average of the months of `year`, each weighted by its number of days (None unless the twelve months are given): for a series
    of average daily rates this is the rate of the year, equal to the annual figure of the same file."""
    tot = days = 0
    for m in range(1, 13):
        v = vals.get(f"{year}-{m:02d}")
        if v is None:
            return None
        d = calendar.monthrange(year, m)[1]
        tot += v * d
        days += d
    return tot / days


def stats(vals, to, base_year=None):
    """{'v': the last MONTHS_KEPT months (None where the source gives none), 'b': average of the baseline year, 'lo': lowest month of the
    year of the latest month, 'la': latest month, 'p': change of the latest month against the baseline, per cent} for one series."""
    ax = axis(to)
    have = sorted(m for m, v in vals.items() if m <= to)
    if not have or have[-1] < axis(to, 12)[0]:  # a series whose last month is more than a year before `to` has stopped: no latest month
        return None
    last = have[-1]
    year = int(last[:4])
    base_year = base_year or year - 1
    b = avg_year(vals, base_year)
    cur = [(vals[m], m) for m in have if m.startswith(str(year))]
    lo = min(cur, key=lambda x: (x[0], x[1]))
    r = {"v": [None if vals.get(m) is None else round(vals[m], 3) for m in ax],
         "b": None if b is None else round(b, 4),
         "lo": {"v": round(lo[0], 3), "m": lo[1]}, "la": {"v": round(vals[last], 3), "m": last}}
    if b:
        r["p"] = round((vals[last] / b - 1) * 100, 1)
    return r


def total(series, members):
    """Month-by-month sum of the series of `members`, for the months in which all of them have a figure."""
    months = set.intersection(*(set(series[c]) for c in members if c in series)) if all(c in series for c in members) else set()
    return {m: sum(series[c][m] for c in members) for m in months}


def producers(series, names_ok, to, base_year=None, min_base=0.1):
    """Rows {c, ...stats} of the countries (names_ok(code) -> ISO3 or None) that have a baseline average above min_base (0.1 kb/d: under it
    the rounding of a published figure is a large part of it), largest first."""
    rows = []
    for code, vals in series.items():
        iso = names_ok(code)
        if not iso:
            continue
        s = stats(vals, to, base_year)
        if s and s.get("b") and s["b"] > min_base:
            rows.append({"c": iso, **s})
    rows.sort(key=lambda r: -r["b"])
    return rows


def last_month(*sets):
    return max(m for s in sets for vals in s.values() for m in vals)


def stocks_block(stocks, cons, iso_of):
    """Petroleum stocks of the geographies that publish them, in million barrels, with the days of cover: the stock of a month over
    the oil demand of the same month in the same file (stocks x 1000 / thousand barrels per day), arithmetic on two published figures."""
    to = last_month(stocks)
    rows, withheld = [], []
    for code in STOCK_ORDER:
        vals = stocks.get(code)
        if not vals:
            continue
        s = stats(vals, to)
        if not s:
            continue
        la = s["la"]
        cv = cons.get(code, {}).get(la["m"])
        row = {"c": code if code in STOCK_LABEL else iso_of(code), **s}
        if code in STOCK_LABEL:
            row["name"] = STOCK_LABEL[code]
        y = int(la["m"][:4])
        prev = vals.get(f"{y - 1}-12")
        if prev is not None:
            row["end"] = {"v": round(prev, 3), "m": f"{y - 1}-12"}
        year_ago = vals.get(f"{y - 1}-{la['m'][5:]}")
        if year_ago is not None:
            row["ya"] = {"v": round(year_ago, 3), "m": f"{y - 1}-{la['m'][5:]}"}
        if cv:
            row["cover"] = round(la["v"] * 1000 / cv, 1)
            row["cons"] = round(cv, 1)
        rows.append(row)
    shown = set(STOCK_ORDER)
    for code, vals in stocks.items():
        iso = iso_of(code)
        if iso and code not in shown and not vals:
            withheld.append(iso)
    return {"u": "Mbbl", "from": axis(to)[0], "to": to, "rows": rows, "withheld": sorted(withheld)}


def build(path, iso_of):
    """{commodity id: file content} from the EIA file at `path`. iso_of(code) -> ISO3 of an EIA geography code that is a country, else None."""
    wanted = {("57-1", "TBPD"), ("5-5", "MBBL"), ("54-2", "TBPD"), ("58-1", "TBPD")} | {(f"{p}-3", "TBPD") for p in IMPORTERS}
    series, names = read(path, wanted)
    out = {}
    ok = lambda code: iso_of(code)  # noqa: E731

    # ---------------------------------------------------------------- crude oil
    crude = series[("57-1", "TBPD")]
    to = last_month(crude)
    rows = producers(crude, ok, to)
    world = stats(crude["WORL"], to)
    gulf = [c for c in GULF if c in crude]
    g = total(crude, gulf)
    gs = stats(g, to) if g and len(gulf) == len(GULF) else None
    prod = {"u": "kb/d", "from": axis(to)[0], "to": to, "baseYear": int(to[:4]) - 1, "rows": rows, "world": world,
            "gulf": {"members": [ok(c) for c in gulf], **gs} if gs else None}
    imports = []
    for p, (imp, label) in IMPORTERS.items():
        key = (f"{p}-3", "TBPD")
        s = series.get(key, {})
        if not s:
            continue
        for code, nm in names[key].items():
            if not nm.startswith(label):  # the product codes are EIA's: a changed numbering is a failure, not a silent mislabel
                raise ValueError(f"EIA series {key} {code}: '{nm}' does not start with '{label}'")
        ito = last_month(s)
        orows = []
        for code, vals in s.items():
            st = stats(vals, ito)
            # the aggregates of origin (Persian Gulf, OPEC) and the origins with a baseline above 1 kb/d or a recent flow
            if st and (st.get("b") or 0) > 1 and (code in ORIGIN_LABEL or ok(code)):
                orows.append({"o": code, **({"name": ORIGIN_LABEL[code]} if code in ORIGIN_LABEL else {"c": ok(code)}), **st})
        orows.sort(key=lambda r: ("name" not in r, -r["b"]))
        imports.append({"id": imp, "name": label, "to": ito, "from": axis(ito, 36)[0], "rows": [_trim(r, 36) for r in orows]})
    stocks = stocks_block(series[("5-5", "MBBL")], series[("54-2", "TBPD")], ok)
    out["crude-oil"] = {"id": "crude-oil", "s": SOURCE, "production": prod, "imports": {"u": "kb/d", "importers": imports}, "stocks": stocks}

    fam, ends = scan(path)
    monthly = {k[0]: n for k, n in fam.items() if k[1] == "M"}
    prod_end, lpg_end = ends.get(("54-1", "TBPD")), ends.get(("67-1", "TBPD"))

    # ---------------------------------------------------------------- refined products
    cons = series[("54-2", "TBPD")]
    cto = last_month(cons)
    crow = []
    for code in STOCK_ORDER:
        s = stats(cons.get(code, {}), cto) if cons.get(code) else None
        if s:
            r = {"c": code if code in STOCK_LABEL else ok(code), **s}
            if code in STOCK_LABEL:
                r["name"] = STOCK_LABEL[code]
            crow.append(r)
    crow.sort(key=lambda r: ("name" not in r, -r["b"]))  # the groups first, then the countries, largest first
    gaps = ["Refined-product production and trade have no monthly series in the EIA file on disk: its production series "
            + (f"end in {prod_end}" if prod_end else "are annual") + " and its trade series are annual."]
    out["refined-products"] = {"id": "refined-products", "s": SOURCE,
                               "consumption": {"u": "kb/d", "from": axis(cto)[0], "to": cto, "baseYear": int(cto[:4]) - 1, "rows": crow},
                               "stocks": stocks, "gaps": gaps}

    # ---------------------------------------------------------------- LPG and natural gas plant liquids
    ngl = series[("58-1", "TBPD")]
    nto = last_month(ngl)
    out["lpg"] = {"id": "lpg", "s": SOURCE,
                  "ngl": {"u": "kb/d", "from": axis(nto)[0], "to": nto, "baseYear": int(nto[:4]) - 1, "rows": producers(ngl, ok, nto),
                          "world": stats(ngl["WORL"], nto)},
                  "gaps": ["LPG consumption and trade have no monthly series in the EIA file on disk: they are annual, and its LPG production series "
                           + (f"end in {lpg_end}." if lpg_end else "are annual.")]}

    # ---------------------------------------------------------------- LNG: nothing monthly, said only while the file holds no such series
    gas = [n for n in monthly.values() if re.search(r"\bLNG\b|liquefied natural gas|^(dry |gross )?natural gas (production|consumption|imports|exports)", n, re.I)]
    out["lng"] = {"id": "lng", "s": SOURCE,
                  "gaps": [] if gas else ["No monthly LNG series is on disk: the EIA file holds annual natural gas trade and no monthly gas series, and the customs and industry "
                                          "sources of the atlas are annual. The atlas does not estimate one."]}
    return out


def _trim(r, n):
    """The row of an import series keeps the last n months."""
    r = dict(r)
    r["v"] = r["v"][-n:]
    return r


def write_all(path, out_dir, iso_of):
    """Write the files of build() into out_dir; returns the QA lines."""
    os.makedirs(out_dir, exist_ok=True)
    docs = build(path, iso_of)
    qa = []
    for cid, d in docs.items():
        with open(os.path.join(out_dir, cid + ".json"), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
        n = os.path.getsize(os.path.join(out_dir, cid + ".json"))
        qa.append(f"monthly/{cid}.json: {n / 1e3:.0f} KB")
    return qa
