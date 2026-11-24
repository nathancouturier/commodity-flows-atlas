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
     In the groups of UV_KEPT_GROUPS (sunflower seed: seed priced at 11,000 to 14,000 USD/t by some French pairs and oil seed at
     about USD 1,300, the group's median, are one code) a row whose unit value is above the group reference keeps its reported
     tonnage; below it rule 3 applies as everywhere. The rows of KEEP_REPORTED (one by one, with the reason) keep their reported
     tonnage too. Both are flagged "uv-suspect-t", as the isolated unit-value anomalies of rule 7 are in the "flag" mode.
  4. Moderate inconsistencies (unit value < 1/3 or > 3x the median, flows > USD 50 million) are
     re-estimated ONLY for homogeneous groups (crude oil, LNG, LPG, grains, oilseeds...). Ore and
     concentrate groups mix grades worth 40 to 2,000 USD/t (e.g. laterite vs sulphide nickel), so
     their reported tonnage is kept. A row of ESTIMATE_ROWS is treated like a row of a homogeneous group, whatever its group.
  5. Known misclassifications are dropped (e.g. Israeli pipeline gas to Egypt declared as LNG, and Mozambique's exports under the coke code:
     the EIA series of coke production gives it none in any year, so the tonnes are probably coal declared as coke). Each dropped row is
     listed in LAST_DROPPED (rule "misclassified") and in QA.md.
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
  8. Peer unit value (PEER_UV): a row of a listed exporter whose unit value is more than PEER_MAX times that of a
     peer exporter of the same product, to the same destination and year, has its tonnage re-estimated from the
     declared value at the peer's unit value times the exporter's usual ratio to the peer ("est-peer", an Atlas
     estimate). That ratio is the median, over the years in which the exporter's declarations are in line (rows
     above the threshold hold under PEER_CLEAN of its declared value), of its unit value over the peer's. Chile's
     copper concentrate reads 7,000 to 8,000 USD/t in some years against about 2,000 for Peru's, as if its tonnage
     were contained copper; in its other years it reads about 1.1 times Peru's.

  9. Ore price in a chemicals group (DROP_LOW_UV, audit C-036): a row of a group listed there whose reported unit value is
     under the group's threshold is dropped, in every year, unless its tonnage was estimated from value by the rules above.
     Lithium carbonate and hydroxide (HS 283691, 282520) trade at thousands of USD per tonne; Nigeria to China at 286 USD/t
     in 2024 is priced like an ore or concentrate declared under a chemical's code (hypothesis: the code or the weight
     is misdeclared; no source says so). The rule is applied here, after the other rules and with their group median,
     so that lanes, pairs, commodity pages, chokepoint estimates and country profiles read one frame.

Every row whose tonnage is estimated (rules 2, 3, 4, 7, 8) has imputed = True and a note in `enote` that
starts with "Atlas estimate" and gives the method, the declared value and the tonnage reported.
"""
import math

import pandas as pd

from checks import label  # display names of the groups ("LNG", "crude oil"), one table for every note
from checks import _name as country_name

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
# Rule 9. Lithium carbonate and hydroxide trade at thousands of USD per tonne: a flow of the group declared below this unit
# value (USD per tonne) is priced like ore or concentrate, not like a lithium chemical, and is dropped.
LITHIUM_MIN_UV = 1500
DROP_LOW_UV = {"lithium": LITHIUM_MIN_UV}  # group -> minimum reported unit value, USD per tonne
# rows removed by rules 6 and 9 in the last clean() call only, for QA.md; each frame returned by clean() also
# carries its own list in df.attrs["dropped"], which a later call on another frame does not erase. "rule" is
# "new-pair" (rule 6) or "low-uv" (rule 9)
LAST_DROPPED = []

# Rule 3 does not apply, above the group reference, to a group whose pairs are priced by kinds that lie ten times apart: in 2024 the
# group's median is 1,289 USD/t (France's exports as a whole 1,021 USD/t, to Spain, Belgium, Germany and the Netherlands at 420 to 590) while France to Romania,
# Hungary and Ukraine declare 10,900 to 13,900 USD/t, which the atlas reads as seed for sowing under the same code (a hypothesis: the
# code does not separate them). The group median is then no reference for such a pair: its reported tonnage stands and the row is
# flagged "uv-suspect-t". Below the reference there is no such reason (Canada to Trinidad and Tobago 2010 at under 13 USD/t, Kazakhstan to
# Russia 2012 at 7 USD/t are errors of tonnage or value) and rule 3 re-estimates the row as for every group. (Rule 4 leaves the group
# out already: see HOMOGENEOUS.)
UV_KEPT_GROUPS = {"sunflower-seed"}
# Rows of the groups added with M-022, M-023 and A-010 that rule 3 or 4 would re-estimate to more than 50 kt and to more than five times
# the pair's own median of the other years (23 rows, listed by test_fncb.py B2: France to Russia sunflower seed is one, kept by
# UV_KEPT_GROUPS). Each row below keeps its reported tonnage, flagged "uv-suspect-t", for the reason beside it:
# (group, exporter, importer, year) -> reason. The 4 other rows of the list are re-estimated because the estimate is right: the pair's
# declared value is steady over the years and the reported tonnage is the odd figure, or the estimate puts the importer's total in line
# with its other years (sulphur Switzerland to Zambia 2012, DRI Malaysia to Taiwan 2003, sulphur United States to Chile 2004,
# sulphur Saudi Arabia to Papua New Guinea 2019); the reasons are in the test.
KEEP_REPORTED = {
    ("coke", "ZWE", "COD", 2006): "tonnage in line with the years around (11 and 230 kt); the value (USD 680 million, 150 to 400 times the neighbours) is the odd figure",
    ("ammonium-sulphate", "USA", "PER", 2017): "tonnage in line with the pair's other years (50 to 185 kt); the value is five times theirs",
    ("ammonia", "NGA", "BGD", 2010): "one other year only (28.5 kt, USD 9 million); the estimate (546 kt) is 19 times its tonnage, the reported 125 kt 4 times",
    ("sorghum", "ITA", "ETH", 2017): "this pair's unit value is 640 to 750 USD/t in every year it is recorded from 2012: the group median (220) is no reference for it",
    ("monoammonium-phosphate", "RUS", "PAK", 2005): "the pair's unit value is 775 and 590 in the next two years, like the 886 of the row: tonnage and value agree",
    ("ammonium-sulphate", "UKR", "DZA", 2015): "tonnage in line with the pair's only other year (3.4 kt); the value is 80 times that year's",
    ("ammonium-nitrate", "FRA", "OMN", 2010): "tonnage in line with the pair's other years (1 to 4 kt); the value (USD 78 million) is 50 times theirs",
    ("dri", "CHN", "SAU", 2018): "the estimate (181 kt) is four times the pair's largest year (48 kt); value and tonnage are both at odds with the years around",
    ("dri", "CHN", "SAU", 2019): "the estimate (66 kt) is more than the pair's largest year (48 kt); value and tonnage are both at odds with the years around",
    ("barley", "ARE", "ROU", 2022): "tonnage in line with the pair's other year (1.1 kt); the value (USD 60 million) is 240 times that year's",
    ("sulphur", "MYS", "KOR", 2003): "the pair's unit value is 1,100 to 1,450 USD/t in 2004 to 2007, 16 times the group median: the estimate (121 kt) is 16 times the tonnage of the next year (7.5 kt)",
    ("graphite", "JPN", "MEX", 2002): "the estimate (99 kt) would be the whole of Mexico's graphite imports of 2002 (102 kt, against 1 to 5 kt in every other year) and of Japan's exports (101 kt, against 1 to 7 kt)",
    ("ammonium-sulphate", "CHL", "AGO", 2014): "the estimate (99 kt) is Chile's only recorded export of the product and puts Angola's imports at 116 kt, against 5 to 58 kt in the other years",
    ("npk-two-nutrient", "CMR", "NGA", 2002): "Cameroon's recorded exports of the product are 34 t, 6 kt and 1.7 kt in its three years; the estimate (115 kt) is 20 times the largest",
    ("coke", "LBY", "USA", 2004): "Libya's only recorded coke export in 21 years: the estimate (82 kt) has no other year to stand on",
    ("ferrous-scrap", "BWA", "VNM", 2013): "the estimate (64 kt) would put Botswana's scrap exports at 94 kt, against 8 to 45 kt in the other years",
    ("dri", "GBR", "USA", 2004): "the pair's other years are about 600 t; the estimate (62 kt) has nothing to stand on",
    ("ferrous-scrap", "VEN", "CAN", 2002): "the pair's other years are 1.7 to 3.9 kt; the value (USD 7.5 million) is 4 to 36 times theirs",
}

BULK = {"iron-ore", "coal", "bauxite", "manganese", "alumina"}
# Owner decision O3 (22 November 2026): an isolated anomalous year is re-estimated and published as an
# Atlas estimate. "flag" keeps the reported tonnage and only flags it.
BULK_REPAIR = "estimate"  # "estimate" | "flag"

# Rule 8. (group, exporter) -> (peer exporter, product named in the note). The peer's unit value to the same destination
# is the reference when the peer shipped PEER_MIN_T there that year at a unit value within a factor 2 of its own average
# of the year; otherwise the peer's average of the year (all destinations) is used. That reference is multiplied by the
# exporter's usual ratio to the peer: in the years in which its declarations are in line, Chile's unit value is above
# Peru's, so the peer's unit value alone would overstate the estimated tonnage.
PEER_UV = {("copper-ore", "CHL"): ("PER", "copper concentrate")}
PEER_MAX = 1.8
PEER_MIN_T = 50_000
# a year is in line when the exporter's rows above PEER_MAX hold less than this share of its declared value
PEER_CLEAN = 0.2
# (group, exporter) -> (usual ratio, years it was taken from) of the last clean() call; each frame returned by clean()
# also carries its own in df.attrs["peer"]
PEER_RATIO = {}

HOMOGENEOUS = {
    "crude-oil", "refined-products", "lng", "lpg", "wheat", "corn", "soybeans", "soymeal", "soyoil", "rice",
    "sugar", "palm-oil", "rapeseed", "coffee", "cocoa", "cotton", "urea", "potash", "dap",
    # one product each, priced by the product tonne (M-022). Not NPK (a mix of grades), phosphoric acid (declared by the tonne of acid
    # or of P2O5) nor sulphur (crude and sublimed sulphur, at very different prices): only the gross errors of rule 3 are corrected.
    # Nor ammonium nitrate with limestone (310240, FNCB): its pairs keep their own unit values (twelve flows between Belgium, the Netherlands
    # and France declare 700 to 1,900 USD/t in 2006 to 2010, against a group median of 180 to 370), and rule 4 would have trebled their tonnage
    "potassium-sulphate", "monoammonium-phosphate", "superphosphates", "ammonia", "ammonium-nitrate", "uan", "ammonium-sulphate",
    # the grains, oils and meals added with M-023: a grade of one product each. Not sunflower seed (oil seed, seed for sowing
    # and snack seed are priced far apart), pulses (peas, lentils, chickpeas and beans), wheat flour nor brewing and distilling dregs
    # (distillers' grains and brewers' grains in one code): only the gross errors of rule 3 are corrected for these. Not sunflower oil
    # either (FNCD, D6): the one row that rule 4 re-estimates, Ukraine to Nepal 2021, belongs to a pair that declares a unit value above
    # three times the group's in four other years, a price level of its own that the estimate would erase
    "barley", "sorghum", "rapeseed-oil", "sunflower-meal", "rapeseed-meal",
    # Not coke and semi-coke (HS 2704, FNCD D6), although it is one product priced by the tonne (its unit values span a factor 4 from the
    # 5th to the 95th percentile, 140 to 600 USD/t in 2024): seven of the eleven rows that rule 4 would re-estimate, which carry 92% of the tonnes
    # it adds or removes, belong to pairs that declare a unit value beyond the factor 3 of the same side in at least three other years
    # (China to the United States, Mozambique to India and to the United Arab Emirates): the estimate would erase their own price level.
    # Only the gross errors of rule 3 are corrected for coke, as for pig iron and direct-reduced iron (several grades). Mozambique's exports,
    # the pair that FNCB repaired, are out of the frame altogether (DROP, FNCF)
}
# Rows re-estimated by rule 4 in a group that is not in HOMOGENEOUS: (group, exporter, importer, year) -> reason. A row listed here is
# treated as rule 4 treats a row of a homogeneous group (unit value beyond 3 times the group's, flow of more than USD 50 million; flag
# "est-uv"), and only then.
# Empty since FNCF: its only row, Mozambique to India 2016 (coke, repaired by FNCB), is in DROP with the rest of Mozambique's coke.
ESTIMATE_ROWS = {}

# (group, exporter, importer or None for any) -> reason
DROP = {
    ("lng", "ISR", None): "Israel has no liquefaction plant: this is pipeline gas to Egypt and Jordan declared under HS 2711.11",
    # FNCF (decision on FNCD's first question, review GV6B.3): the EIA table of coke production (International Energy Data, series 21-1, the one
    # that check K14 reads) gives Mozambique zero in every year, so its exports under HS 2704 are a product that the country
    # cannot have made: coal declared under the coke code, a hypothesis that no source confirms. Every year, every destination.
    ("coke", "MOZ", None): "the EIA series of coke production gives Mozambique none in any year, so its exports under the coke code are probably coal "
                           "declared as coke; this is a hypothesis, not established",
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
        elif "est-peer" in codes:
            peer, what, where, puv, k, ky = nb[i]
            usual = (f"{k:.3f}, the median ratio of {country_name(r['o'])}'s unit value of {what} to {country_name(peer)}'s in the "
                     f"{len(ky)} year{'s' if len(ky) > 1 else ''} in which its declarations are in line ({year_list(ky)})" if ky else
                     f"1 (no year in which {country_name(r['o'])}'s declarations are in line)")
            out[i] = (f"Atlas estimate: CEPII BACI reports {_tonnes(r['t0'])} for {_usd(r['usd'])} ({_num(r['uvp'])} USD/t), "
                      f"{r['uvp'] / puv:.1f} times the {_num(puv)} USD/t of {what} from {country_name(peer)} {where} in {y}; "
                      f"a tonnage declared in contained metal rather than gross weight is a plausible cause, not established here; "
                      f"tonnage = declared value divided by {uve}, that unit value of {country_name(peer)} times {usual}")
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


def year_list(ys):
    """'2002, 2009, 2014 to 2020 and 2023' from a sorted list of years."""
    runs = []
    for y in ys:
        if runs and y == runs[-1][1] + 1:
            runs[-1][1] = y
        else:
            runs.append([y, y])
    parts = [str(a) if a == b else f"{a} to {b}" for a, b in runs]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _peer(df, fix):
    """Rule 8: {index: (peer, product, where, peer USD/t, usual ratio, years of that ratio, USD/t used)} for the rows
    to re-estimate."""
    out = {}
    for (g, o), (p, what) in PEER_UV.items():
        peer = df[(df["group"] == g) & (df["o"] == p) & (df["uvp"] > 0) & ~fix]
        by_y = peer.groupby("year").agg(t=("t", "sum"), usd=("usd", "sum"))
        uv_y = by_y["usd"] * 1000 / by_y["t"]
        by_d = peer.groupby(["year", "d"]).agg(t=("t", "sum"), usd=("usd", "sum"))
        uv_d = by_d["usd"] * 1000 / by_d["t"]
        rows = df[(df["group"] == g) & (df["o"] == o) & (df["uvp"] > 0) & ~fix]
        hit = {}
        for i, r in rows.iterrows():
            y, d = r["year"], r["d"]
            if y not in uv_y.index:
                continue
            ref, where = uv_y[y], "to all destinations"
            if (y, d) in uv_d.index and by_d.loc[(y, d), "t"] >= PEER_MIN_T and 0.5 <= uv_d[(y, d)] / ref <= 2:
                ref, where = uv_d[(y, d)], f"to {country_name(d)}"
            if r["uvp"] > PEER_MAX * ref:
                hit[i] = (where, ref)
        # the exporter's usual ratio to the peer, over the years in which its rows above the threshold are marginal
        own = rows.groupby("year").agg(t=("t", "sum"), usd=("usd", "sum"))
        above = rows.loc[list(hit)].groupby("year")["usd"].sum().reindex(own.index, fill_value=0)
        ok = own.index[(above < PEER_CLEAN * own["usd"]) & own.index.isin(uv_y.index)]
        ky = sorted(int(y) for y in ok)
        k = float(((own.loc[ok, "usd"] * 1000 / own.loc[ok, "t"]) / uv_y[ok]).median()) if ky else 1.0
        PEER_RATIO[(g, o)] = (k, ky)
        for i, (where, ref) in hit.items():
            out[i] = (p, what, where, ref, k, ky, ref * k)
    return out


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
    misclassified = []
    for (g, o, d), why in DROP.items():
        m = (df["group"] == g) & (df["o"] == o)
        if d:
            m &= df["d"] == d
        misclassified.append(df[m].assign(why=why))
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
    keys = pd.MultiIndex.from_frame(df[["group", "o", "d", "year"]])
    moderate = (has_t & (df["group"].isin(HOMOGENEOUS) | keys.isin(list(ESTIMATE_ROWS))) & (df["usd"] > 50_000) & ((ratio < 1 / 3) | (ratio > 3))
                & df["uv"].notna())
    # rules 3 and 4 leave a row alone that is in KEEP_REPORTED or, above the group reference, in UV_KEPT_GROUPS: reported tonnage kept, flagged
    keep = (gross | moderate) & ~miss & ((df["group"].isin(UV_KEPT_GROUPS) & (ratio > 1)) | keys.isin(list(KEEP_REPORTED)))
    gross, moderate = gross & ~keep, moderate & ~keep
    fix = miss | gross | moderate
    _add_flag(df, keep, "uv-suspect-t")
    df["t0"] = df["t"]
    df.loc[fix, "t"] = df.loc[fix, "usd"] / df.loc[fix, "uv"]
    df["imputed"] = fix
    df["uvr"] = ratio
    df["uve"] = (df["uv"] * 1000).where(fix)
    _add_flag(df, miss, "est-missing")
    _add_flag(df, gross & ~miss, "est-gross")
    _add_flag(df, moderate & ~gross & ~miss, "est-uv")
    _add_flag(df, has_t & ~(df["usd"] > 0), "no-value")
    peer = _peer(df, fix)
    if peer:
        pi = list(peer)
        ref = pd.Series({i: v[6] for i, v in peer.items()})
        df.loc[pi, "t"] = df.loc[pi, "usd"] * 1000 / ref[pi]
        df.loc[pi, "uve"] = ref[pi]
        df.loc[pi, "imputed"] = True
        _add_flag(df, df.index.isin(pi), "est-peer")

    iso = _isolated(df, int(df["year"].max()) if len(df) else 0)
    sus = df.index.isin(iso.index[~iso["t_out"]])
    _add_flag(df, sus, "uv-suspect")
    out = iso[iso["t_out"]]
    nb = {i: v[:6] for i, v in peer.items()}
    if bulk_repair == "estimate":
        uve = out["ref"] * (out["rel_a"] * out["rel_b"]) ** 0.5
        df.loc[out.index, "t"] = df.loc[out.index, "usd"] * 1000 / uve
        df.loc[out.index, "uve"] = uve
        df.loc[out.index, "imputed"] = True
        df.loc[out.index, "flag"] = "uv-repair"
        nb.update({i: (int(r["ya"]), r["uvp_a"], int(r["yb"]), r["uvp_b"], r["ref"]) for i, r in out.iterrows()})
        for i in out.index:  # the earlier year first in the note
            ya, ua, yb, ub, m = nb[i]
            nb[i] = (ya, ua, yb, ub, m) if ya < yb else (yb, ub, ya, ua, m)
    else:
        _add_flag(df, df.index.isin(out.index), "uv-suspect-t")
    # rule 9: after every estimate, so that the group reference of the other rules is the same as before the rule existed
    low = (df["uvp"].astype(float) < df["group"].map(DROP_LOW_UV).astype(float)) & ~df["imputed"].astype(bool)
    cut = df[low]
    df = df[~low].copy()
    df["enote"] = _notes(df, nb).reindex(df.index)

    del LAST_DROPPED[:]
    if len(dropped):
        ref = dropped.join(uv.rename("uvm"), on=["group", "year"])
        for r in ref.itertuples():
            est = r.t <= 0
            LAST_DROPPED.append({"group": r.group, "o": r.o, "d": r.d, "year": int(r.year), "usd": float(r.usd),
                                 "t": float(r.usd / r.uvm) if est and r.uvm == r.uvm else float(r.t), "est": bool(est),
                                 "rule": "new-pair", "reason": "pair with no flow in both neighbouring years (DROP_NEW_PAIRS)"})
    for r in cut.sort_values(["group", "year", "t"], ascending=[True, True, False]).itertuples():
        LAST_DROPPED.append({"group": r.group, "o": r.o, "d": r.d, "year": int(r.year), "usd": float(r.usd), "t": float(r.t), "est": False,
                             "uvp": float(r.uvp), "rule": "low-uv",
                             "reason": f"reported unit value under {DROP_LOW_UV[r.group]:,} USD per tonne (DROP_LOW_UV)"})
    for x in misclassified:
        for r in x.sort_values(["group", "year", "t"], ascending=[True, True, False]).itertuples():
            LAST_DROPPED.append({"group": r.group, "o": r.o, "d": r.d, "year": int(r.year), "usd": float(r.usd), "t": float(r.t), "est": False,
                                 "rule": "misclassified", "reason": r.why})
    df.attrs["dropped"] = [dict(r) for r in LAST_DROPPED]
    df.attrs["peer"] = {key: v for key, v in PEER_RATIO.items()}
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
    est = {"est-missing", "est-gross", "est-uv", "uv-repair", "est-peer"}

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
