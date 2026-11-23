"""
Shared cleaning of the BACI flow table, used by build_lanes.py and build_commodities.py so that
lanes, rankings and flows always agree. See METHODOLOGY.md §1.

Rules
  1. Country codes: BACI "S19" (Other Asia, n.e.s.) is Taiwan, except the exporters and groups of
     S19_UNSPECIFIED, whose S19 rows are shown as the pseudo-place XAS ("Asia, not specified").
  2. Missing tonnage with a value: tonnage = value / median unit value of the group and year.
  3. Gross unit errors (unit value < 1/100 or > 100x the group-year median, any size): re-estimated
     the same way. This catches kg/t slips such as rare earths Turkey -> Benin. A row with a tonnage and no
     declared value (USD 0) is not an error of this kind: its tonnage is kept as reported and flagged "no-value".
  4. Moderate inconsistencies (unit value < 1/3 or > 3x the median, flows > USD 50 million) are
     re-estimated ONLY for homogeneous groups (crude oil, LNG, LPG, grains, oilseeds...). Ore and
     concentrate groups mix grades worth 40 to 2,000 USD/t (e.g. laterite vs sulphide nickel), so
     their reported tonnage is kept.
  5. Known misclassifications are dropped (e.g. Israeli pipeline gas to Egypt declared as LNG).
  6. Pairs that appear for one year only in an exporter-year listed in DROP_NEW_PAIRS (Qatari LPG in
     2021 and 2023) are dropped, or flagged "dup-suspect" when LPG_DEDUP is "flag".
  7. Bulk groups (BULK): the reference of rules 2 and 3 is the tonne-weighted median unit value (the
     plain median is set by thousands of small expensive parcels: 152 against 69 USD/t for bauxite in
     2024). That median leaves out the gross errors against the plain median, so that one bad row
     cannot set it (manganese 2002). An isolated unit-value anomaly of a pair (value >= USD 50 million,
     the pair's unit value more than 3x or under 1/3 of both neighbouring years, which agree with each
     other) is flagged "uv-suspect"; when the reported tonnage is itself the outlier, in the direction
     opposite to the unit value, and the neighbours' unit values lie within 1/5 to 5 times the group
     reference ("uv-suspect-t"), and BULK_REPAIR is "estimate", the tonnage is re-estimated from the
     declared value and the pair's own unit value in the neighbouring years ("uv-repair", an Atlas
     estimate). The estimate then always moves the tonnage towards the neighbouring years.

Every row whose tonnage is estimated (rules 2, 3, 4, 7) has imputed = True and a note in `enote` that
starts with "Atlas estimate" and gives the method, the declared value and the tonnage reported.
"""
import math

import pandas as pd

from checks import label  # display names of the groups ("LNG", "crude oil"), one table for every note

CODE_FIX = {"S19": "TWN"}
XAS = "XAS"  # pseudo-place "Asia, not specified" (pipeline/geo/places_extra.json)
# (group, exporter) -> first year from which its S19 rows are not read as Taiwan. Iran's crude to S19
# jumps to 24 Mt a year in 2020-2022 while Taiwan's crude imports jump by the same amount: not Taiwanese.
S19_UNSPECIFIED = {("crude-oil", "IRN"): 2019}

# (group, exporter) -> years in which the pairs with no flow in both neighbouring years are dropped.
# Qatari LPG reads about 10 Mt a year except 39.0 Mt in 2021 and 36.9 Mt in 2023, on pairs that have
# no LPG in the years around; several equal the LNG row of the same pair and year. Hypothesis (no
# source states it): LNG cargoes recorded a second time under the LPG code. Owner decision O7: drop.
DROP_NEW_PAIRS = {("lpg", "QAT"): (2021, 2023)}
LPG_DEDUP = "drop"  # "drop" | "flag"
# rows removed by DROP_NEW_PAIRS in the last clean() call only, for QA.md; each frame returned by clean() also
# carries its own list in df.attrs["dropped"], which a later call on another frame does not erase
LAST_DROPPED = []

BULK = {"iron-ore", "coal", "bauxite", "manganese", "alumina"}
# Owner decision O3 (22 November 2026): an isolated anomalous year is re-estimated and published as an
# Atlas estimate. "flag" keeps the reported tonnage and only flags it.
BULK_REPAIR = "estimate"  # "estimate" | "flag"

HOMOGENEOUS = {
    "crude-oil", "refined-products", "lng", "lpg", "wheat", "corn", "soybeans", "soymeal", "soyoil", "rice",
    "sugar", "palm-oil", "rapeseed", "coffee", "cocoa", "cotton", "urea", "potash", "dap",
}

# (group, exporter, importer or None for any) -> reason
DROP = {
    ("lng", "ISR", None): "Israel has no liquefaction plant: this is pipeline gas to Egypt and Jordan declared under HS 2711.11",
}


def _add_flag(df, mask, code):
    df.loc[mask, "flag"] = [f"{f}+{code}" if f else code for f in df.loc[mask, "flag"]]


def _tw_median(rows):
    """Tonne-weighted median of `uvp` per group and year (USD per tonne) over rows with t > 0, usd > 0."""
    s = rows.sort_values(["group", "year", "uvp"])
    cum = s.groupby(["group", "year"])["t"].cumsum()
    half = s.groupby(["group", "year"])["t"].transform("sum") / 2
    return s[cum >= half].groupby(["group", "year"])["uvp"].first()


def _bulk_ref(rows):
    """Reference of the BULK groups: the tonne-weighted median of `uvp` without the gross errors against the plain
    median (rule 3), which can hold most of a group's tonnage (manganese IND-CHE 2002: 23 Mt for USD 0.97 million)."""
    plain = rows.groupby(["group", "year"])["uvp"].transform("median")
    return _tw_median(rows[(rows["uvp"] / plain).between(0.01, 100)])


def _drop_new_pairs(df, mode):
    """Rule 6. Returns the frame without the dropped rows (mode "drop") or with them flagged."""
    out = []
    for (g, o), years in DROP_NEW_PAIRS.items():
        x = df[(df["group"] == g) & (df["o"] == o)]
        by_year = x.groupby("year")["d"].agg(set).to_dict()
        for y in years:
            new = x[(x["year"] == y) & ~x["d"].isin(by_year.get(y - 1, set()) | by_year.get(y + 1, set()))]
            out.append(new.index)
    idx = pd.Index([]).append(out) if out else pd.Index([])
    if mode == "flag":
        _add_flag(df, df.index.isin(idx), "dup-suspect")
        return df, df.iloc[0:0]
    return df.drop(idx), df.loc[idx]


def _num(v, unit=""):
    """Figure for a note: 3 significant digits, thousands separators above 100."""
    return (f"{v:,.0f}" if abs(v) >= 100 else f"{v:.3g}") + unit


def _tonnes(t):
    return _num(t / 1e6, " Mt") if t >= 1e6 else (_num(t / 1e3, " kt") if t >= 1e3 else _num(t, " t"))


def _usd(kusd):
    v = kusd * 1000
    return "USD " + (_num(v / 1e9, " bn") if v >= 1e9 else _num(v / 1e6, " million"))


def _notes(df, nb):
    """Text of `enote` for the rows whose tonnage is estimated. nb: neighbour unit values of uv-repair rows."""
    out = {}
    for i, r in df[df["imputed"]].iterrows():
        g, y, codes = r["group"], int(r["year"]), r["flag"].split("+")
        ref = f"the {y} {'tonne-weighted median' if g in BULK else 'median'} unit value of {label(g)}"
        uve = _num(r["uve"], " USD/t")
        if "uv-repair" in codes:
            ya, ua, yb, ub, m = nb[i]
            out[i] = (f"Atlas estimate: CEPII BACI reports {_tonnes(r['t0'])} for {_usd(r['usd'])} ({_num(r['uvp'])} USD/t, against "
                      f"{_num(ua)} and {_num(ub)} USD/t for this pair in {ya} and {yb}); tonnage = declared value divided by {uve}, "
                      f"{ref} ({_num(m, ' USD/t')}) times the pair's usual ratio to that median ({r['uve'] / m:.3f} on average in "
                      f"{ya} and {yb})")
        elif "est-missing" in codes:
            out[i] = f"Atlas estimate: tonnage missing in CEPII BACI; declared value {_usd(r['usd'])} divided by {ref}, {uve}"
        elif "est-gross" in codes:
            how = "more than 100 times" if r["uvr"] > 1 else "under a hundredth of"
            # a bulk row caught against the plain median only (rule 3) says so
            against = ref if not (0.01 <= r["uvr"] <= 100) else f"the {y} median unit value of {label(g)}"
            out[i] = (f"Atlas estimate: CEPII BACI reports {_tonnes(r['t0'])} for {_usd(r['usd'])}, a unit value {how} {against}; "
                      f"tonnage = declared value divided by {ref}, {uve}")
        else:
            out[i] = (f"Atlas estimate: CEPII BACI reports {_tonnes(r['t0'])} for {_usd(r['usd'])} ({_num(r['uvp'])} USD/t, "
                      f"{r['uvr']:.2g} times {ref}); tonnage = declared value divided by that unit value, {uve}")
    return pd.Series(out, dtype=object)


def _isolated(df, latest):
    """Rule 7 detection: isolated unit-value anomalies of bulk pairs, on reported figures.
    Returns a frame indexed like df with rel, rel and t0 of the two neighbours, their years and the group reference."""
    b = df[df["group"].isin(BULK) & (df["t0"] > 0) & (df["usd"] > 0)][["group", "o", "d", "year", "uvp", "t0", "usd"]].copy()
    ref = _bulk_ref(b.assign(t=b["t0"]))
    b = b.join(ref.rename("ref"), on=["group", "year"])
    b["rel"] = b["uvp"] / b["ref"]
    k = ["group", "o", "d", "year"]
    nb = b[k + ["rel", "t0", "uvp"]]
    b["ya"] = b["year"] - 1
    b["yb"] = (b["year"] + 1).where(b["year"] < latest, b["year"] - 2)
    for s in ("a", "b"):
        n = nb.rename(columns={"year": "y" + s, "rel": "rel_" + s, "t0": "t0_" + s, "uvp": "uvp_" + s})
        b = b.assign(_i=b.index).merge(n, on=["group", "o", "d", "y" + s], how="left").set_index("_i")
    b = b.dropna(subset=["rel_a", "rel_b"])
    agree = (b["rel_a"] / b["rel_b"]).between(0.5, 2)
    r1, r2 = b["rel"] / b["rel_a"], b["rel"] / b["rel_b"]
    odd = ((r1 > 3) & (r2 > 3)) | ((r1 < 1 / 3) & (r2 < 1 / 3))
    b = b[agree & odd & (b["usd"] >= 50_000)]
    lo, hi = b[["t0_a", "t0_b"]].min(axis=1), b[["t0_a", "t0_b"]].max(axis=1)
    # The tonnage is the odd figure only when it deviates against the unit value (a low tonnage for a high unit value,
    # or the reverse): then the estimate moves it towards the neighbouring years. Tonnage and unit value both high
    # means the value is the odd figure (iron ore VEN-USA 2008). Neighbours far from the group reference (alumina
    # AUS-OMN 2014, whose neighbours are 30 to 40 times it) give no sound unit value to estimate from. Such rows are
    # only flagged.
    up = b["rel"] > b["rel_a"]
    sound = b["rel_a"].between(0.2, 5) & b["rel_b"].between(0.2, 5)
    b["t_out"] = (((b["t0"] < 0.35 * lo) & up) | ((b["t0"] > 2.8 * hi) & ~up)) & sound
    return b


def clean(df: pd.DataFrame, lpg_dedup=None, bulk_repair=None) -> pd.DataFrame:
    """Return a cleaned copy with columns t (tonnes, repaired), t0 (reported), imputed (bool), uvr (ratio to the
    group reference), uv (group reference, thousand USD per tonne), uvp (reported USD per tonne), uve (USD per
    tonne used for an estimate), flag ("+"-joined codes, empty for an untouched row) and enote (note of an
    estimated tonnage). lpg_dedup and bulk_repair override LPG_DEDUP and BULK_REPAIR."""
    lpg_dedup = lpg_dedup or LPG_DEDUP
    bulk_repair = {"repair": "estimate"}.get(bulk_repair or BULK_REPAIR, bulk_repair or BULK_REPAIR)
    df = df[df["o"].notna() & df["d"].notna()].copy()
    if not df.index.is_unique:
        df = df.reset_index(drop=True)
    df["flag"] = ""
    for (g, o), y0 in S19_UNSPECIFIED.items():
        m = (df["group"] == g) & (df["o"] == o) & (df["d"] == "S19") & (df["year"] >= y0)
        df.loc[m, "d"] = XAS
        _add_flag(df, m, "xas")
    df["o"] = df["o"].replace(CODE_FIX)
    df["d"] = df["d"].replace(CODE_FIX)
    df = df[df["o"] != df["d"]]
    for (g, o, d), _ in DROP.items():
        m = (df["group"] == g) & (df["o"] == o)
        if d:
            m &= df["d"] == d
        df = df[~m]
    df, dropped = _drop_new_pairs(df, lpg_dedup)
    has_t = df["t"] > 0
    pos = has_t & (df["usd"] > 0)
    df["uvp"] = (df["usd"] * 1000 / df["t"]).where(pos)
    uv = df[pos].assign(u=lambda x: x["usd"] / x["t"]).groupby(["group", "year"])["u"].median()
    df = df.join(uv.rename("uv"), on=["group", "year"])
    bulk = df["group"].isin(BULK)
    tw = _bulk_ref(df[pos & bulk]) / 1000
    twj = df.loc[bulk].join(tw.rename("tw"), on=["group", "year"])["tw"]
    df.loc[bulk, "uv"] = twj.where(twj.notna(), df.loc[bulk, "uv"])
    ratio = (df["usd"] / df["t"].where(has_t)) / df["uv"]
    plain = (df["usd"] / df["t"].where(has_t)) / df.join(uv.rename("uvm"), on=["group", "year"])["uvm"]
    miss = ~has_t & (df["usd"] > 0) & df["uv"].notna()
    # a bulk row that is a gross error against either reference stays one (coal MOZ-POL 2019: 201 Mt at 0.94 USD/t)
    gross = pos & df["uv"].notna() & ((ratio < 0.01) | (ratio > 100) | (bulk & ((plain < 0.01) | (plain > 100))))
    moderate = has_t & df["group"].isin(HOMOGENEOUS) & (df["usd"] > 50_000) & ((ratio < 1 / 3) | (ratio > 3)) & df["uv"].notna()
    fix = miss | gross | moderate
    df["t0"] = df["t"]
    df.loc[fix, "t"] = df.loc[fix, "usd"] / df.loc[fix, "uv"]
    df["imputed"] = fix
    df["uvr"] = ratio
    df["uve"] = (df["uv"] * 1000).where(fix)
    _add_flag(df, miss, "est-missing")
    _add_flag(df, gross & ~miss, "est-gross")
    _add_flag(df, moderate & ~gross & ~miss, "est-uv")
    _add_flag(df, has_t & ~(df["usd"] > 0), "no-value")

    iso = _isolated(df, int(df["year"].max()) if len(df) else 0)
    sus = df.index.isin(iso.index[~iso["t_out"]])
    _add_flag(df, sus, "uv-suspect")
    out = iso[iso["t_out"]]
    nb = {}
    if bulk_repair == "estimate":
        uve = out["ref"] * (out["rel_a"] * out["rel_b"]) ** 0.5
        df.loc[out.index, "t"] = df.loc[out.index, "usd"] * 1000 / uve
        df.loc[out.index, "uve"] = uve
        df.loc[out.index, "imputed"] = True
        df.loc[out.index, "flag"] = "uv-repair"
        nb = {i: (int(r["ya"]), r["uvp_a"], int(r["yb"]), r["uvp_b"], r["ref"]) for i, r in out.iterrows()}
        for i in out.index:  # the earlier year first in the note
            ya, ua, yb, ub, m = nb[i]
            nb[i] = (ya, ua, yb, ub, m) if ya < yb else (yb, ub, ya, ua, m)
    else:
        _add_flag(df, df.index.isin(out.index), "uv-suspect-t")
    df["enote"] = _notes(df, nb).reindex(df.index)

    del LAST_DROPPED[:]
    if len(dropped):
        ref = dropped.join(uv.rename("uvm"), on=["group", "year"])
        for r in ref.itertuples():
            est = r.t <= 0
            LAST_DROPPED.append({"group": r.group, "o": r.o, "d": r.d, "year": int(r.year), "usd": float(r.usd),
                                 "t": float(r.usd / r.uvm) if est and r.uvm == r.uvm else float(r.t), "est": bool(est),
                                 "reason": "pair with no flow in both neighbouring years (DROP_NEW_PAIRS)"})
    df.attrs["dropped"] = [dict(r) for r in LAST_DROPPED]
    return df


def history_flags(tonnes, values, flags=None, min_abs=2.0):
    """The history rule of a pair's yearly series (METHODOLOGY.md §1). tonnes and values are lists of the
    same length (tonnes in the series' unit, values in any currency unit; None or 0 when nothing is
    recorded); flags, when given, are the `flag` codes of clean() for the same years.

    Returns (series, marks) with marks = {index: code}:
      "est"     tonnage estimated from value (kept; every such year is marked);
      "suspect" flagged "uv-suspect-t" by clean(), or a sharp one-year change (the test of despike())
                whose unit value is off by more than 2.5 times against the neighbours: blanked (None);
      "nodata"  a sharp one-year dip with no record at all: blanked;
      "kept"    a sharp one-year change whose value moved with the tonnage: kept as reported.
    Sustained changes (two years or more) are never touched.
    """
    out, marks = list(tonnes), {}
    codes = [set((f or "").split("+")) for f in (flags or [""] * len(tonnes))]
    est = {"est-missing", "est-gross", "est-uv", "uv-repair"}

    def uv(i):
        t, v = tonnes[i], values[i]
        return v / t if t and v and t > 0 and v > 0 else None

    for i, c in enumerate(codes):
        if c & est:
            marks[i] = "est"
        elif "uv-suspect-t" in c:
            out[i], marks[i] = None, "suspect"
    for i in range(1, len(tonnes) - 1):
        if i in marks:
            continue
        a, v, b = tonnes[i - 1], tonnes[i], tonnes[i + 1]
        if a is None or b is None or min(a, b) <= 0:
            continue
        v = v or 0.0
        lo, hi = min(a, b), max(a, b)
        if not ((v < 0.35 * lo and lo - v > min_abs) or (v > 2.8 * hi and v - hi > min_abs)):
            continue
        if v == 0 and not values[i]:
            out[i], marks[i] = None, "nodata"
            continue
        ua, ub, u = uv(i - 1), uv(i + 1), uv(i)
        if u and ua and ub and not (0.4 <= u / math.sqrt(ua * ub) <= 2.5):
            out[i], marks[i] = None, "suspect"
        else:
            marks[i] = "kept"
    return out, marks


def despike(values, min_abs=2.0):
    """Blank isolated one-year spikes or dips in an annual series (customs reporting glitches).

    A point is removed (None) when it is below 35% of both neighbours or above 2.8x both
    neighbours, and differs from them by more than `min_abs` units. Sustained changes (e.g.
    China's 2021-22 ban on Australian coal) span two or more years and are kept.
    Returns (new_values, removed_indexes).
    """
    out, removed = list(values), []
    for i in range(1, len(values) - 1):
        a, v, b = values[i - 1], values[i], values[i + 1]
        if a is None or v is None or b is None or min(a, b) <= 0:
            continue
        lo, hi = min(a, b), max(a, b)
        if (v < 0.35 * lo and lo - v > min_abs) or (v > 2.8 * hi and v - hi > min_abs):
            out[i] = None
            removed.append(i)
    return out, removed
