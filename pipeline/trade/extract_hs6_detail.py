"""
Six-digit detail of the groups whose two codes are different products, from a CEPII BACI HS92 zip: refined copper
(HS 7403, cathodes and refined forms) against unrefined copper (HS 7402, anodes and blister), and unwrought aluminium
not alloyed (HS 760110) against alloys (HS 760120). The main extract (extract_baci.py) adds the codes of a group; this
one keeps them apart, so that the commodity pages can split a pair's tonnage between them (audit C-043, M-017).

    python pipeline/trade/extract_hs6_detail.py raw/baci/BACI_HS92_V202601.zip pipeline/cache/baci_hs6_detail.csv.gz [first_year]

Output columns: year, group (of hs_map.HS), hs6, o and d (ISO3), t (tonnes), usd (thousand USD).
A pair is kept when the group's tonnes or value of the pair pass the thresholds of extract_baci.py (1,000 t or 1 million USD),
so that every pair of the main extract has its detail. Default first year: 2019. BACI licence: Etalab Open Licence 2.0.
"""
import sys
import zipfile

import pandas as pd

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from hs_map import HS  # noqa: E402

GROUPS = ("copper-refined", "aluminium")
CODES = {c: g for g in GROUPS for c in HS[g]}

zpath, out = sys.argv[1], sys.argv[2]
first_year = int(sys.argv[3]) if len(sys.argv) > 3 else 2019

z = zipfile.ZipFile(zpath)
names = z.namelist()
cc = pd.read_csv(z.open(next(n for n in names if n.startswith("country_codes"))), dtype=str)
iso = dict(zip(cc["country_code"].astype(int), cc["country_iso3"]))

frames = []
for n in sorted(names):
    if not (n.startswith("BACI_") and n.endswith(".csv")):
        continue
    year = int(n.split("_Y")[1][:4])
    if year < first_year:
        continue
    df = pd.read_csv(z.open(n), dtype={"t": "int16", "i": "int32", "j": "int32", "k": str, "v": "float64"},
                     usecols=["t", "i", "j", "k", "v", "q"], na_values=["NA", "           NA"])
    df["k"] = df["k"].str.strip().str.zfill(6)
    df = df[df["k"].isin(CODES)].copy()
    df["group"] = df["k"].map(CODES)
    df["q"] = pd.to_numeric(df["q"], errors="coerce")
    tot = df.groupby(["group", "i", "j"])[["q", "v"]].transform("sum")
    df = df[(tot["q"] >= 1000) | (tot["v"] >= 1000)]
    g = df.groupby(["group", "k", "i", "j"], as_index=False).agg(t=("q", "sum"), usd=("v", "sum"))
    g.insert(0, "year", year)
    g["o"] = g["i"].map(iso)
    g["d"] = g["j"].map(iso)
    g = g.rename(columns={"k": "hs6"})
    frames.append(g[["year", "group", "hs6", "o", "d", "t", "usd"]])
    print(year, len(g), flush=True)

res = pd.concat(frames)
res["t"] = res["t"].round(0)
res["usd"] = res["usd"].round(0)
res.to_csv(out, index=False, compression="gzip")
print("rows", len(res), "->", out)
