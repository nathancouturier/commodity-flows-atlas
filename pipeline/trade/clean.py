"""
Shared cleaning of the BACI flow table, used by build_lanes.py and build_commodities.py so that
lanes, rankings and flows always agree. See METHODOLOGY.md §1.

Rules
  1. Country codes: BACI "S19" (Other Asia, n.e.s.) is Taiwan.
  2. Missing tonnage with a value: tonnage = value / median unit value of the group and year.
  3. Gross unit errors (unit value < 1/100 or > 100x the group-year median, any size): re-estimated
     the same way. This catches kg/t slips such as rare earths Turkey -> Benin.
  4. Moderate inconsistencies (unit value < 1/3 or > 3x the median, flows > USD 50 million) are
     re-estimated ONLY for homogeneous groups (crude oil, LNG, LPG, grains, oilseeds...). Ore and
     concentrate groups mix grades worth 40 to 2,000 USD/t (e.g. laterite vs sulphide nickel), so
     their reported tonnage is kept.
  5. Known misclassifications are dropped (e.g. Israeli pipeline gas to Egypt declared as LNG).
"""
import pandas as pd

CODE_FIX = {"S19": "TWN"}

HOMOGENEOUS = {
    "crude-oil", "refined-products", "lng", "lpg", "wheat", "corn", "soybeans", "soymeal", "soyoil", "rice",
    "sugar", "palm-oil", "rapeseed", "coffee", "cocoa", "cotton", "urea", "potash", "dap",
}

# (group, exporter, importer or None for any) -> reason
DROP = {
    ("lng", "ISR", None): "Israel has no liquefaction plant: this is pipeline gas to Egypt and Jordan declared under HS 2711.11",
}


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Return a cleaned copy with columns t (tonnes, repaired), t0 (reported), imputed (bool), uvr (ratio)."""
    df = df[df["o"].notna() & df["d"].notna()].copy()
    df["o"] = df["o"].replace(CODE_FIX)
    df["d"] = df["d"].replace(CODE_FIX)
    df = df[df["o"] != df["d"]]
    for (g, o, d), _ in DROP.items():
        m = (df["group"] == g) & (df["o"] == o)
        if d:
            m &= df["d"] == d
        df = df[~m]
    has_t = df["t"] > 0
    uv = df[has_t & (df["usd"] > 0)].assign(u=lambda x: x["usd"] / x["t"]).groupby(["group", "year"])["u"].median()
    df = df.join(uv.rename("uv"), on=["group", "year"])
    ratio = (df["usd"] / df["t"].where(has_t)) / df["uv"]
    miss = ~has_t & (df["usd"] > 0) & df["uv"].notna()
    gross = has_t & df["uv"].notna() & ((ratio < 0.01) | (ratio > 100))
    moderate = has_t & df["group"].isin(HOMOGENEOUS) & (df["usd"] > 50_000) & ((ratio < 1 / 3) | (ratio > 3)) & df["uv"].notna()
    fix = miss | gross | moderate
    df["t0"] = df["t"]
    df.loc[fix, "t"] = df.loc[fix, "usd"] / df.loc[fix, "uv"]
    df["imputed"] = fix
    df["uvr"] = ratio
    return df


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
