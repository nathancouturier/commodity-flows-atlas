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
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checks as K  # noqa: E402
from clean import S19_UNSPECIFIED, XAS  # noqa: E402

HYPOTHESIS = "is a plausible cause; it is not established here."


class Ctx:
    def __init__(self, df, findings, year, psd):
        self.df, self.findings, self.y, self.psd = df, findings, year, psd
        self.ex = df.groupby(["group", "o", "year"])["t"].sum() / 1e6
        self.pair = df.groupby(["group", "o", "d", "year"])["t"].sum() / 1e6

    def exports(self, g, o, y):
        return float(self.ex.get((g, o, y), 0.0))

    def flow(self, g, o, d, y):
        return float(self.pair.get((g, o, d, y), 0.0))

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
        return (f"No {K.label(g)} from {name(o)} to {name(d)} is recorded in customs data for {last + 1} to {c.y} "
                f"({mt(c.flow(g, o, d, last))} in {last}, CEPII BACI). Incomplete declarations by both sides may be the cause; "
                "it is not established here.")
    return text


def _mirror(g, o):
    def text(c):
        v = c.exports(g, o, c.y)
        if v <= 0:
            return None
        s = f"Customs data record {mt(v)} of {K.label(g)} exports from {name(o)} in {c.y} (CEPII BACI)"
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


def _break(g, o):
    def text(c):
        v, v2 = c.exports(g, o, c.y), c.exports(g, o, c.y - 2)
        past = [(y, c.exports(g, o, y)) for y in range(c.y - 5, c.y)]
        top_y, top = max(past, key=lambda p: p[1])
        if v2 > 0 and v > 2.5 * v2 and v - v2 >= 0.5:
            s = f"{K.label(g).capitalize()} exports of {name(o)} in customs data rose from {mt(v2)} in {c.y - 2} to {mt(v)} in {c.y} (CEPII BACI)"
        elif top >= 1 and v < 0.4 * top:
            s = f"{K.label(g).capitalize()} exports of {name(o)} in customs data fell from {mt(top)} in {top_y} to {mt(v)} in {c.y} (CEPII BACI)"
        else:
            return None
        k10 = c.finding("K10", group=g, country=o)
        if k10 and k10["kind"] == "unlisted":
            s += "; the country is not a listed producer in the USGS Mineral Commodity Summaries"
        elif k10:
            s += f"; they are {k10['ratio']:.0%} of its production in the USGS Mineral Commodity Summaries"
        return s + f". A change in the recorded origin of shipments {HYPOTHESIS}"
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


def _hub(g, o, check=None):
    def text(c):
        v = c.exports(g, o, c.y)
        if v < 1 or (check and not c.finding(check, country=o, level="flag")):
            return None
        s = f"Customs data record {mt(v)} of {K.label(g)} exports from {name(o)} in {c.y} (CEPII BACI)"
        if check:
            r = c.finding(check, country=o)
            s += f", {r['ratio']:.0%} of its production (EIA International Energy Data)"
        return (s + ". As a trading, blending and re-export hub, the recorded origin may be where the cargo was last shipped "
                "from, not where it was produced.")
    return text


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
    *[(f"grain-rus-{g}", "mirror", g, "RUS", None, None, _mirror(g, "RUS"))
      for g in ("wheat", "corn", "soybeans", "rapeseed", "soymeal", "soyoil")],
    ("rice-vnm", "mirror", "rice", "VNM", None, "K1", _mirror_k1("rice", "VNM")),
    ("urea-irn", "break", "urea", "IRN", None, None, _break("urea", "IRN")),
    ("urea-omn", "above-production", "urea", "OMN", None, "K10", _k10("urea", "OMN")),
    ("potash-blr", "break", "potash", "BLR", None, None, _break("potash", "BLR")),
    ("potash-uzb", "break", "potash", "UZB", None, None, _break("potash", "UZB")),
    ("potash-tkm", "break", "potash", "TKM", None, None, _break("potash", "TKM")),
    ("hub-refined-products-nld", "hub", "refined-products", "NLD", None, None, _hub("refined-products", "NLD")),
    ("hub-refined-products-bel", "hub", "refined-products", "BEL", None, None, _hub("refined-products", "BEL")),
    ("hub-refined-products-sgp", "hub", "refined-products", "SGP", None, None, _hub("refined-products", "SGP")),
    ("hub-crude-oil-nld", "hub", "crude-oil", "NLD", None, "K3", _hub("crude-oil", "NLD", "K3")),
    ("lpg-irn", "unrecorded", "lpg", "IRN", None, None, _unrecorded_peak("lpg", "IRN")),
    ("lpg-omn-chn", "origin-unchecked", "lpg", "OMN", "CHN", None, _unchecked_pair("lpg", "OMN", "CHN", "IRN")),
    ("lpg-are-chn", "origin-unchecked", "lpg", "ARE", "CHN", None, _unchecked_pair("lpg", "ARE", "CHN", "IRN")),
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
    return out


def lookup(active, group, o, d):
    """Id of the caveat that applies to a pair, or None. An entry for the pair wins over one for the origin."""
    best = None
    for cid, e in active.items():
        if e["group"] == group and e["o"] == o and e["d"] in (None, d):
            if e["d"] == d:
                return cid
            best = best or cid
    return best
