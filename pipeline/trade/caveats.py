"""
Registry of caveats for origins that customs data understate, relabel or route through a hub
(trade-engine plan, section 2.8; METHODOLOGY.md §1). Replaces KNOWN_GAPS of build_lanes.py.

    import caveats
    active = caveats.build(clean(df), checks.run(...), 2024)   # {id: {kind, text, group, o, d, check}}
    caveats.lookup(active, "crude-oil", "MYS", "CHN")          # -> "crude-mys"

Rules of writing (binding for every entry):
  * a text states what the atlas's own data show, with numbers filled by the builder from the frame or
    from a check; no number is typed here;
  * a cause is worded as a hypothesis ("is a plausible cause; it is not established here") unless a cited
    source states it;
  * an entry tied to a check is active only while that check fires;
  * an external figure is shown beside the atlas's own, with its source and year, never mixed into a table.

build_lanes.py writes the active entries to data/freight/caveats.json and tags lanes and pairs;
build_commodities.py feeds them to its caveats() / annotate() mechanism.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common import constants as CN  # noqa: E402
import checks as K  # noqa: E402
from clean import S19_UNSPECIFIED, XAS  # noqa: E402

HYPOTHESIS = "is a plausible cause; it is not established here."
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
TROY_OZ_G = CN.GRAMS_PER_TROY_OZ  # grams in a troy ounce, exact by definition (pipeline/common/constants.py)


def annual_price(series, year, want="USD/troy oz"):
    """Average of the twelve monthly prices of `year` in data/prices/<series>.json (World Bank Pink Sheet, USD per troy
    ounce for the precious metals, `want` for another unit), or None when the file, the unit or a month is missing."""
    try:
        with open(os.path.join(ROOT, "data", "prices", series + ".json"), encoding="utf-8") as f:
            pr = json.load(f)
        with open(os.path.join(ROOT, "data", "prices", "index.json"), encoding="utf-8") as f:
            unit = next(e["unit"] for e in json.load(f) if e["id"] == series)
    except (OSError, ValueError, KeyError, StopIteration):
        return None
    y0, m0 = int(pr["start"][:4]), int(pr["start"][5:7])
    i = (year - y0) * 12 - (m0 - 1)
    vals = pr["v"][i:i + 12] if i >= 0 else []
    if unit != want or len(vals) != 12 or any(v is None for v in vals):
        return None
    return sum(vals) / 12


class Ctx:
    def __init__(self, df, findings, year, psd):
        self.df, self.findings, self.y, self.psd = df, findings, year, psd
        self.ex = df.groupby(["group", "o", "year"])["t"].sum() / 1e6
        self.pair = df.groupby(["group", "o", "d", "year"])["t"].sum() / 1e6

    def exports(self, g, o, y):
        return float(self.ex.get((g, o, y), 0.0))

    def flow(self, g, o, d, y):
        return float(self.pair.get((g, o, d, y), 0.0))

    def imports(self, g, d, y):
        if not hasattr(self, "_imp"):
            self._imp = self.df.groupby(["group", "d", "year"])["t"].sum() / 1e6
        return float(self._imp.get((g, d, y), 0.0))

    def finding(self, check, **kw):
        for r in self.findings:
            if r["check"] == check and all(r.get(k) == v for k, v in kw.items()):
                return r
        return None


def mt(v):
    return K._mt(v)


def name(c):
    return K._name(c)


# ---------------------------------------------------------------- entry texts (None = not active)
def _unrecorded(g, o, ref_year):
    def text(c):
        v, ref = c.exports(g, o, c.y), c.exports(g, o, ref_year)
        if ref <= 0 or v >= 0.5 * ref:
            return None
        s = (f"Customs data record {mt(v) + ' of' if v > 0 else 'no'} {K.label(g)} exports from {name(o)} in {c.y}, "
             f"against {mt(ref)} in {ref_year} (CEPII BACI).")
        xas = [(y, c.flow(g, o, XAS, y)) for y in range(ref_year, c.y + 1) if c.flow(g, o, XAS, y) > 0]
        if xas:
            s += (f" From {xas[0][0]} to {xas[-1][0]}, {mt(sum(v for _, v in xas))} of them were recorded under "
                  f"\"Other Asia, not elsewhere specified\" and are shown as \"Asia, not specified\".")
        return s + " Unrecorded shipments, or cargoes declared under other origins, are a plausible cause; it is not established here."
    return text


def _above_production(o, level, hypothesis):
    def text(c):
        r = c.finding("K3", country=o)
        if not r or (level == "flag" and r["level"] != "flag"):
            return None
        s = (f"Crude oil exports of {name(o)} in customs data ({mt(r['value'])} in {c.y}, CEPII BACI) are {r['ratio']:.0%} of its "
             f"production ({mt(r['reference'])}, EIA International Energy Data).")
        if r.get("est"):
            s += f" {mt(r['est'])} of these exports are Atlas estimates from declared value."
        return f"{s} {hypothesis} {HYPOTHESIS}"
    return text


def _mex_s19(c):
    yrs = [y for y in range(min(S19_UNSPECIFIED.values()) - 1, c.y + 1)]
    vals = [(y, c.flow("crude-oil", "MEX", "TWN", y)) for y in yrs]
    if not vals or vals[-1][1] < 1:  # no year in range when the build year is before the rule's first year
        return None
    series = ", ".join(f"{mt(v)} in {y}" for y, v in vals if v > 0)
    return ("Crude oil from Mexico to \"Other Asia, not elsewhere specified\" (BACI code S19), shown here as Taiwan: "
            f"{series} (CEPII BACI). No source read for the atlas confirms the destination.")


def _absent(g, o, d):
    def text(c):
        if c.flow(g, o, d, c.y) > 0:
            return None
        last = max((y for y in range(2002, c.y) if c.flow(g, o, d, y) > 0), default=None)
        if last is None or c.flow(g, o, d, last) < 1:
            return None
        span = f"{last + 1} to {c.y}" if last + 1 < c.y else str(c.y)
        return (f"No {K.label(g)} from {name(o)} to {name(d)} is recorded in customs data for {span} "
                f"({mt(c.flow(g, o, d, last))} in {last}, CEPII BACI). Incomplete declarations by both sides may be the cause; "
                "it is not established here.")
    return text


_EIA_CRUDE = {}


def _eia_crude_kbd(o, y):
    """EIA International Energy Data crude oil production of country `o` in year `y`, thousand barrels per day (None without the file or the figure)."""
    if "s" not in _EIA_CRUDE:
        try:
            _EIA_CRUDE["s"] = (K.eia_series([("57-1", "TBPD")]) or {}).get(("57-1", "TBPD"), {})
        except (OSError, ValueError):
            _EIA_CRUDE["s"] = {}
    return _EIA_CRUDE["s"].get(o, {}).get(y)


def _fall(g, o, below=0.6, span=3):
    """Customs exports of an origin that fall below `below` of their average over the `span` years before (the exports of Kuwait in 2024),
    with the buyers of the year before that are not recorded this year, and, where the EIA file has the production of the country, its
    production in both years: a hypothesis about the cause, never a measure of it."""
    def text(c):
        v = c.exports(g, o, c.y)
        ys = list(range(c.y - span, c.y))
        ref = sum(c.exports(g, o, y) for y in ys) / span
        if ref < 1 or v >= below * ref:
            return None
        x = c.df[(c.df["group"] == g) & (c.df["o"] == o)]
        a = x[x["year"] == c.y - 1].groupby("d")["t"].sum() / 1e6
        b = x[x["year"] == c.y].groupby("d")["t"].sum() / 1e6
        gone = sorted(((float(t), d) for d, t in a.items() if t >= 1 and float(b.get(d, 0.0)) <= 0), reverse=True)
        s = (f"Customs data record {mt(v)} of {K.label(g)} exports from {name(o)} in {c.y}, against an average of {mt(ref)} a year from {ys[0]} to "
             f"{ys[-1]} (CEPII BACI).")
        if gone:
            s += (f" Of the buyers recorded in {c.y - 1}, {_and_names(gone[:3])} {'is' if len(gone) == 1 else 'are'} not recorded in {c.y}"
                  + (f" ({len(gone)} buyers, {mt(sum(t for t, _ in gone))} in {c.y - 1})" if len(gone) > 1 else "") + ".")
        p1, p0 = _eia_crude_kbd(o, c.y), _eia_crude_kbd(o, c.y - 1)
        if g == "crude-oil" and p1 and p0:
            s += f" Its crude oil production in the EIA International Energy Data file is {p1:,.0f} thousand barrels a day in {c.y} against {p0:,.0f} in {c.y - 1}."
        return s + f" A gap in the importers' declarations for {c.y}, or a change in the recorded origin of the cargoes, {HYPOTHESIS}"
    return text


def _and_names(rows):
    """[(Mt, code), ...] -> "Vietnam (9.01 Mt), the Philippines (2.2 Mt) and Oman (1.5 Mt)"."""
    parts = [f"{name(d)} ({mt(t)})" for t, d in rows]
    return ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1]


def _mirror(g, o, detail=None):
    """`detail(c, v)`: what to add after the customs figure, before the USDA figures (a split of the figure, for instance)."""
    def text(c):
        v = c.exports(g, o, c.y)
        if v <= 0:
            return None
        s = f"Customs data record {mt(v)} of {K.label(g)} exports from {name(o)} in {c.y} (CEPII BACI)"
        if detail:
            s += detail(c, v)
        psd = c.psd or {}
        a, b = psd.get((g, "Exports", c.y - 1), {}).get(o), psd.get((g, "Exports", c.y), {}).get(o)
        if a is not None and b is not None:
            s += (f"; USDA PSD gives {mt(a / 1e3)} for {c.y - 1}/{c.y % 100:02d} and {mt(b / 1e3)} for "
                  f"{c.y}/{(c.y + 1) % 100:02d}")
        return (s + f". These flows may rest on importers' declarations alone, so that destinations which do not report "
                "are missing; this is not established here.")
    return text


def _mirror_k1(g, o):
    inner = _mirror(g, o)

    def text(c):
        return inner(c) if c.finding("K1", group=g, side="exports", country=o) else None
    return text


def _vs(v, ref):
    """How far `v` is from `ref`: "20% below", "3% above"."""
    d = v / ref - 1
    return f"{abs(d):.0%} {'below' if d < 0 else 'above'}"


def _grain_gap(g, o, avg_min=0.5, back=5, gone=3):
    """Russian grain (audit C-045): the sentence of _mirror (the customs figure against the two USDA marketing years), the size of the gap, and
    the importers that took the grain in the three years `back` to `gone` years before the build year (on average `avg_min` million tonnes
    a year or more) and have none recorded in the build year, whose lanes therefore show zero. The
    atlas does not scale the flows or the lanes to the USDA total (whether it should publish such an estimate is the owner's decision).
    Part of the customs tonnage may be the atlas's own estimate from the declared value (cleaning rules, METHODOLOGY.md section 1): the note
    says how much, and gives the gap against USDA on the published total and on the tonnage as reported (review GA1.4)."""
    def est_of(c):
        x = c.df[(c.df["group"] == g) & (c.df["o"] == o) & (c.df["year"] == c.y) & c.df["imputed"].astype(bool)]
        return x, float(x["t"].sum()) / 1e6

    def detail(c, v):
        x, est = est_of(c)
        if est <= 0:
            return ""
        top = (x.groupby("d")["t"].sum() / 1e6).sort_values(ascending=False)[:3]
        return (f", of which {mt(est)} is an Atlas estimate (the tonnage computed by the atlas from the declared value where the declared tonnage was "
                f"implausible: {', '.join(f'{name(d)} {mt(t)}' for d, t in top.items())}) and {mt(v - est)} is as reported")

    inner = _mirror(g, o, detail)

    def text(c):
        s = inner(c)
        if not s:
            return None
        v = c.exports(g, o, c.y)
        est = est_of(c)[1]
        psd = c.psd or {}
        a, b = psd.get((g, "Exports", c.y - 1), {}).get(o), psd.get((g, "Exports", c.y), {}).get(o)
        if a and b:
            s += f" The published customs figure is {_vs(v, a / 1e3)} the first and {_vs(v, b / 1e3)} the second."
            if est > 0:
                s += f" On the tonnage as reported alone ({mt(v - est)}) the gap is {_vs(v - est, a / 1e3)} the first and {_vs(v - est, b / 1e3)} the second."
        x = c.df[(c.df["group"] == g) & (c.df["o"] == o)]
        by = (x.groupby(["d", "year"])["t"].sum() / 1e6).unstack(fill_value=0.0)
        yrs = [y for y in range(c.y - back, c.y - gone + 1)]
        lost = []
        for d in by.index:
            if by.loc[d].get(c.y, 0.0) >= 0.05:
                continue
            avg = sum(by.loc[d].get(y, 0.0) for y in yrs) / len(yrs)
            if avg >= avg_min:
                lost.append((avg, d))
        if lost:
            lost.sort(reverse=True)
            s += (f" Importers that took {K.label(g)} from {name(o)} in {yrs[0]} to {yrs[-1]} and have none recorded in {c.y}: "
                  + ", ".join(f"{name(d)} ({mt(t)} a year on average)" for t, d in lost[:5])
                  + f"; the flows and lanes to them are zero in {c.y}.")
        return s + " The flows and lanes carry the customs figures (an Atlas estimate is marked as such); no further tonnage is added to bring them to the USDA figure."
    return text


def _break(g, o):
    def text(c):
        v, v2 = c.exports(g, o, c.y), c.exports(g, o, c.y - 2)
        past = [(y, c.exports(g, o, y)) for y in range(c.y - 5, c.y)]
        top_y, top = max(past, key=lambda p: p[1])
        if v2 > 0 and v > 2.5 * v2 and v - v2 >= 0.5:
            s = f"{K.cap_label(g)} exports of {name(o)} in customs data rose from {mt(v2)} in {c.y - 2} to {mt(v)} in {c.y} (CEPII BACI)"
        elif top >= 1 and v < 0.4 * top:
            s = f"{K.cap_label(g)} exports of {name(o)} in customs data fell from {mt(top)} in {top_y} to {mt(v)} in {c.y} (CEPII BACI)"
        else:
            return None
        k10 = c.finding("K10", group=g, country=o)
        if k10 and k10["kind"] == "unlisted":
            s += "; the country is not a listed producer in the USGS Mineral Commodity Summaries"
        elif k10:
            s += f"; they are {k10['ratio']:.0%} of its production in the USGS Mineral Commodity Summaries"
        return s + f". A change in the recorded origin of shipments {HYPOTHESIS}"
    return text


_BLR_RAIL = ("https://reform.news/en/belarus-exported-11-6-million-tonnes-of-potash-fertilizers-via-russian-ports")
# Figures of that page (Reform.news, 27 March 2026, citing Kommersant; read on 23 November 2026): potash Belarus exported
# through Russia in 2025 (tonnes: "11.6 million tonnes"), and the share of it that went by rail to China and the CIS countries
BLR_VIA_RUSSIA_2025_T, BLR_RAIL_SHARE_2025 = 11_600_000, 0.09


def _with_rail(base):
    """The Belarusian potash entry, with what the pages say of the rail share (review GL1.11): an external figure beside the
    atlas's own, with its source and year; the atlas counts the pairs as seaborne and subtracts nothing."""
    def text(c):
        s = base(c)
        rail = (f"Of the {BLR_VIA_RUSSIA_2025_T / 1e6:g} Mt of potash that Belarus exported through Russia in 2025, {BLR_RAIL_SHARE_2025:.0%} went "
                "by rail to China and the CIS countries "
                "together and the rest through Russian seaports, half of it from Bronka (Kommersant, as reported by Reform.news on 27 March "
                f"2026, {_BLR_RAIL}). The atlas counts Belarus's recorded potash exports to China as seaborne, through St Petersburg: "
                "the page gives no rail share for China alone, so nothing is subtracted")
        return (s + " " if s else "") + rail + "."
    return text


def _k10(g, o):
    def text(c):
        r = c.finding("K10", group=g, country=o, kind="above-production")
        return f"{r['text'][0].upper()}{r['text'][1:]}. Declaration of cargoes of other origins under {name(o)} {HYPOTHESIS}" if r else None
    return text


def _lab(g):
    return "LPG" if g == "lpg" else K.label(g)


def _unrecorded_peak(g, o, span=6):
    """An origin whose recorded exports fall far below the largest of the `span` years before the build year (for a
    series that has no single reference year, as Iranian LPG: recorded in some years, none in others)."""
    def text(c):
        past = [(y, c.exports(g, o, y)) for y in range(c.y - span, c.y)]
        top_y, top = max(past, key=lambda p: p[1])
        v = c.exports(g, o, c.y)
        if top <= 0 or v >= 0.5 * top:
            return None
        return (f"Customs data record {mt(v) + ' of' if v > 0 else 'no'} {_lab(g)} exports from {name(o)} in {c.y}, "
                f"against {mt(top)} in {top_y} (CEPII BACI). Unrecorded shipments, or cargoes declared under other origins, "
                "are a plausible cause; it is not established here. The atlas has no free source that measures this gap, "
                "so it is not quantified.")
    return text


def _unchecked_pair(g, o, d, missing):
    """A pair whose origin is not checked against an independent source, while the exports of `missing` (an origin that
    customs data no longer record) are absent: the volume may include cargoes of other origins declared under `o`."""
    gap = _unrecorded_peak(g, missing)

    def text(c):
        v, tot = c.flow(g, o, d, c.y), c.exports(g, o, c.y)
        if v <= 0 or tot <= 0 or not gap(c):
            return None
        return (f"Customs data record {mt(v)} of {_lab(g)} from {name(o)} to {name(d)} in {c.y} ({v / tot:.0%} of its "
                "recorded exports, CEPII BACI). The origin of these cargoes is not checked against an independent "
                f"source: while {name(missing)}'s exports are unrecorded, cargoes of other origins declared under {name(o)} "
                "may account for part of this volume; it is not established here, and the atlas has no free source to measure it.")
    return text


def _centre(g, o, d, side):
    """A pair whose declared destination (side "d") or origin (side "o") is a landlocked trading centre (Switzerland): the customs figure is
    kept, and the cargo probably ends (or started) elsewhere. Every figure is computed from the frame, and no cause is stated beyond the
    reading (FNCF, review GV6D.3). The pair is left out of the generated corridors (generated_routes.py), its tonnes stay in the tables and in
    the estimates of the passages, counted on the route to the declared destination."""
    def text(c):
        v, eo, di = c.flow(g, o, d, c.y), c.exports(g, o, c.y), c.imports(g, d, c.y)
        if v <= 0 or eo <= 0 or di <= 0:
            return None
        centre = name(d if side == "d" else o)
        what = {"copper-refined": "refined copper"}.get(g) or K.label(g)  # the label of the checks would read "copper refined"
        reading = ("the cargo probably ends elsewhere" if side == "d" else "the cargo probably started elsewhere")
        route = "to its declared destination" if side == "d" else "from its declared origin"
        return (f"Customs data record {mt(v)} of {what} from {name(o)} to {name(d)} in {c.y} ({v / eo:.1%} of {name(o)}'s recorded "
                f"exports and {v / di:.1%} of {name(d)}'s recorded imports, CEPII BACI). {centre} has no coast and is a trading centre for "
                f"commodities, so {reading} and the customs record only the declared country: a possible reading, not established here. "
                f"The tonnes stay in the tables and are counted at the passages of the route {route}; no generated route is built from this pair.")
    return text


def _hub(g, o, check=None):
    def text(c):
        v = c.exports(g, o, c.y)
        if v < 1 or (check and not c.finding(check, country=o, level="flag")):
            return None
        s = f"Customs data record {mt(v)} of {K.label(g)} exports from {name(o)} in {c.y} (CEPII BACI)"
        if check:
            r = c.finding(check, country=o)
            s += f", {r['ratio']:.0%} of its production (EIA International Energy Data)"
        return (s + ". Where cargoes are blended, stored or re-exported from this country, the recorded origin may be where the cargo "
                "was last shipped from, not where it was produced; the atlas does not measure that share.")
    return text


def _price_gap(g, what, o, d, series, metal, max_ratio=0.5, min_t=10):
    """A precious-metal pair declared far below the price of the metal its code names (tonnes, not Mt): a cargo of
    another, cheaper metal declared under the code is the hypothesis."""
    def text(c):
        x = c.df[(c.df["group"] == g) & (c.df["o"] == o) & (c.df["d"] == d)]
        if x.empty or "usd" not in x:  # a frame without this group, or without values
            return None
        now = x[x["year"] == c.y]
        t, usd = float(now["t"].sum()), float(now["usd"].sum()) * 1000
        price = annual_price(series, c.y)
        if t < min_t or not usd or not price:
            return None
        per_kg, ref = usd / t / 1000, price * 1000 / TROY_OZ_G
        if per_kg > max_ratio * ref:
            return None
        before = x[x["year"] == c.y - 1]["t"].sum()
        return (f"Customs data record {t:,.0f} t of {what} from {name(o)} to {name(d)} in {c.y} (CEPII BACI), "
                f"{t / max(c.df[(c.df['group'] == g) & (c.df['d'] == d) & (c.df['year'] == c.y)]['t'].sum(), 1):.0%} of {name(d)}'s "
                f"recorded imports, against {before:,.1f} t in {c.y - 1}. They are declared at {per_kg:,.0f} USD per kg, "
                f"{per_kg / ref:.0%} of the {c.y} average {metal} price ({ref:,.0f} USD per kg, World Bank Pink Sheet). Gold or "
                f"another cheaper metal declared as a {metal} alloy {HYPOTHESIS}")
    return text


# the monthly price series (World Bank Pink Sheet, USD per tonne) of the metals of K13's groups, quoted beside the pair's unit value
METAL_PRICE = {"aluminium": ("aluminium-m", "aluminium"), "copper-refined": ("copper-m", "copper"), "zinc-metal": ("zinc-m", "zinc"),
               "lead-metal": ("lead-m", "lead"), "tin-metal": ("tin-m", "tin")}


# what a pair declared far below its product's usual unit value may be priced like (the words of the caveat): the metals' own scrap or alloy
# by default; coke is priced like coal, and pig iron and direct-reduced iron like iron ore or scrap (FNCD, D4)
LOW_UV_LIKE = {"coke": "coal", "pig-iron": "iron ore or scrap", "dri": "iron ore or scrap"}


def _low_unit_value(r):
    """A pair of one metal product declared far below the usual unit value of that product (check K13): scrap, alloy or another
    cheaper product declared under the code is the hypothesis; the metal's price is quoted where the repository holds it."""
    s = r["text"]
    series, metal = METAL_PRICE.get(r["group"], (None, None))
    price = annual_price(series, r["year"], "USD/t") if series else None
    if price:
        s += f"; the {r['year']} average {metal} price is {price:,.0f} USD per tonne (World Bank Pink Sheet), and the pair is declared at {r['unitValue'] / price:.0%} of it"
    return (f"{s}. Material priced like {LOW_UV_LIKE.get(r['group'], 'scrap or alloy')}, or another cheaper product, declared under this code {HYPOTHESIS}")


def _no_production(r):
    """An exporter of a group whose product the EIA table of production gives no producer (check K14): what the customs data record, what the EIA
    series reads, and what the tonnes may be. A series that has production in an earlier year gives two readings with the same weight: the series no
    longer covers the country's plants, or part of the tonnes is another product declared under the code (metallurgical coal, where the atlas's tables
    give the country some). A series that reads 0 in every year gives the second reading only. Every figure is read from the finding; no cause is stated."""
    g, o = r["group"], r["o"]
    n = name(o)
    if r["coalExportKt"] > 0:
        coal = (f", metallurgical coal for instance, which the EIA tables of the Metallurgical coal page show {n} exporting "
                f"({r['coalExportKt'] / 1e3:.3g} Mt in {r['eiaYear']})")
    elif r["coalKt"] > 0:
        coal = (f", metallurgical coal for instance, of which the EIA tables of the Metallurgical coal page give {n} a production of "
                f"{r['coalKt'] / 1e3:.3g} Mt in {r['eiaYear']} and no exports")
    else:
        coal = ""
    head = (f"Customs data record {mt(r['value'])} of {K.label(g)} exported from {n} in {r['year']} (CEPII BACI, HS 2704), {r['share']:.1%} of "
            f"the world total. The EIA table of metallurgical coke production on the Metallurgical coal page gives {n} no coke production in "
            f"{r['eiaYear']} (")
    if r["lastYear"] is None:
        return (f"{head}its series reads 0 in every year from {r['firstYear']} to {r['eiaYear']}; EIA International Energy Data). These tonnes may be "
                f"another product declared under the coke code{coal}: a possible reading, not established here.")
    last = f"{r['lastKt']:,.0f} kt in {r['lastYear']}"
    if r.get("priorYear"):
        series = (f"its series reads 0 in {r['eiaYear']}, and its last two years with production are {r['priorKt']:,.0f} kt in {r['priorYear']} and {last}")
        fall = f"a series that falls from {r['priorKt']:,.0f} kt to {r['lastKt']:,.0f} kt and then to nothing"
    else:
        series = f"its series reads 0 in {r['eiaYear']}, and its last year with production is {last}"
        fall = f"a series that ends at {r['lastKt']:,.0f} kt and then reads nothing"
    return (f"{head}{series}; EIA International Energy Data). Two readings fit, with the same weight: the EIA series no longer covers the country's coke "
            f"plants ({fall} may be a series that stopped), or part of these tonnes is another product declared under the coke code{coal}. "
            "Neither is established here.")


REF_YEAR = min(S19_UNSPECIFIED.values()) - 1  # the last year before Iran's crude was recorded under "Other Asia"

# id, kind, group, origin, destination (None = any), check it depends on, text
REGISTRY = [
    ("crude-irn", "unrecorded", "crude-oil", "IRN", None, None, _unrecorded("crude-oil", "IRN", REF_YEAR)),
    ("crude-ven", "unrecorded", "crude-oil", "VEN", None, None, _unrecorded("crude-oil", "VEN", REF_YEAR)),
    ("crude-mys", "above-production", "crude-oil", "MYS", None, "K3", _above_production(
        "MYS", "flag", "Blending, or crude of other origins declared as Malaysian after ship-to-ship transfers,")),
    ("crude-are", "above-production", "crude-oil", "ARE", None, "K3", _above_production(
        "ARE", "watch", "Crude of other origins loaded or blended in the country and declared as Emirati")),
    ("crude-mex-s19", "destination", "crude-oil", "MEX", "TWN", None, _mex_s19),
    ("crude-rus-tur", "unrecorded", "crude-oil", "RUS", "TUR", None, _absent("crude-oil", "RUS", "TUR")),
    ("crude-kwt-vnm", "unrecorded", "crude-oil", "KWT", "VNM", None, _absent("crude-oil", "KWT", "VNM")),
    # a fall of the recorded exports of a producer whose production did not fall (GE1.11): kind "fall" is text only, it does not widen the
    # estimates of the passages (build_freight.unrecorded_through reads the kinds "unrecorded" and "break")
    ("crude-kwt", "fall", "crude-oil", "KWT", None, None, _fall("crude-oil", "KWT")),
    *[(f"grain-rus-{g}", "mirror", g, "RUS", None, None, _grain_gap(g, "RUS"))
      for g in ("wheat", "corn", "soybeans", "rapeseed", "soymeal", "soyoil")],
    ("rice-vnm", "mirror", "rice", "VNM", None, "K1", _mirror_k1("rice", "VNM")),
    ("urea-irn", "break", "urea", "IRN", None, None, _break("urea", "IRN")),
    ("urea-omn", "above-production", "urea", "OMN", None, "K10", _k10("urea", "OMN")),
    ("potash-blr", "break", "potash", "BLR", None, None, _with_rail(_break("potash", "BLR"))),
    ("potash-uzb", "break", "potash", "UZB", None, None, _break("potash", "UZB")),
    ("potash-tkm", "break", "potash", "TKM", None, None, _break("potash", "TKM")),
    ("hub-refined-products-nld", "hub", "refined-products", "NLD", None, None, _hub("refined-products", "NLD")),
    ("hub-refined-products-bel", "hub", "refined-products", "BEL", None, None, _hub("refined-products", "BEL")),
    ("hub-refined-products-sgp", "hub", "refined-products", "SGP", None, None, _hub("refined-products", "SGP")),
    ("hub-crude-oil-nld", "hub", "crude-oil", "NLD", None, "K3", _hub("crude-oil", "NLD", "K3")),
    ("refined-products-rus", "mirror", "refined-products", "RUS", None, None, _mirror("refined-products", "RUS")),
    ("lpg-irn", "unrecorded", "lpg", "IRN", None, None, _unrecorded_peak("lpg", "IRN")),
    ("lpg-omn-chn", "origin-unchecked", "lpg", "OMN", "CHN", None, _unchecked_pair("lpg", "OMN", "CHN", "IRN")),
    ("lpg-are-chn", "origin-unchecked", "lpg", "ARE", "CHN", None, _unchecked_pair("lpg", "ARE", "CHN", "IRN")),
    # a declared destination or origin that is a landlocked trading centre (FNCF, review GV6D.3): text only, no widening of the passages
    ("sulphur-qat-che", "landlocked-centre", "sulphur", "QAT", "CHE", None, _centre("sulphur", "QAT", "CHE", "d")),
    ("copper-refined-zmb-che", "landlocked-centre", "copper-refined", "ZMB", "CHE", None, _centre("copper-refined", "ZMB", "CHE", "d")),
    ("iron-ore-mys-che", "landlocked-centre", "iron-ore", "MYS", "CHE", None, _centre("iron-ore", "MYS", "CHE", "d")),
    ("iron-ore-che-mys", "landlocked-centre", "iron-ore", "CHE", "MYS", None, _centre("iron-ore", "CHE", "MYS", "o")),
    # metals (audit C-035): groups without lanes, built by build_commodities.py from the same registry
    ("pgm-are-ind", "declaration", "pgm", "ARE", "IND", None, _price_gap("pgm", "platinum-group metals", "ARE", "IND", "platinum-m", "platinum")),
]


def build(df, findings, year, psd="load"):
    """Active entries for the latest year: {id: {kind, text, group, o, d, check}}. df is the frame of clean();
    findings the output of checks.run(); psd the table of checks.psd_table() (loaded when not given; None to skip)."""
    if psd == "load":
        try:
            psd = K.psd_table()
        except Exception as e:  # a PSD file with another layout: the entries are built without it
            print(f"caveats: USDA PSD not read ({type(e).__name__}: {e})")
            psd = None
    c = Ctx(df, findings, year, psd)
    out = {}
    for cid, kind, g, o, d, check, fn in REGISTRY:
        text = fn(c)
        if text:
            out[cid] = {"kind": kind, "text": text, "group": g, "o": o, "d": d, **({"check": check} if check else {})}
    out.update(unit_value_entries(c.df, year))
    out.update(no_production_entries(c.df, year))
    return out


def unit_value_entries(df, year):
    """Entries for the pairs K13 finds: one per pair, active only while the pair is that far below the others."""
    return {f"uv-{r['group']}-{r['o']}-{r['d']}": {"kind": "declaration", "text": _low_unit_value(r), "group": r["group"], "o": r["o"], "d": r["d"],
                                                  "check": "K13"} for r in K.k13(df, year)}


def no_production_entries(df, year):
    """Entries for the exporters K14 finds: one per origin and group, active only while the EIA table gives the origin no production."""
    return {f"nop-{r['group']}-{r['o']}": {"kind": "no-production", "text": _no_production(r), "group": r["group"], "o": r["o"], "d": None,
                                           "check": "K14"} for r in K.k14(df, year)}


def lookup(active, group, o, d):
    """Id of the caveat that applies to a pair, or None. An entry for the pair wins over one for the origin."""
    best = None
    for cid, e in active.items():
        if e["group"] == group and e["o"] == o and e["d"] in (None, d):
            if e["d"] == d:
                return cid
            best = best or cid
    return best
