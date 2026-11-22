"""
Extract the atlas commodity groups from a CEPII BACI HS92 zip into one compact table.

    python pipeline/trade/extract_baci.py raw/baci/BACI_HS92_V202601.zip pipeline/cache/baci_flows.csv.gz [first_year]

Output columns: year, group, o (exporter ISO3), d (importer ISO3), t (tonnes), usd (thousand USD).
Rows below 1,000 t AND below 1 million USD are dropped: they are irrelevant for flows and freight.
BACI licence: Etalab Open Licence 2.0 — cite "CEPII BACI".
"""
import io
import sys
import zipfile

import pandas as pd

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from hs_map import build_lookup, group_of  # noqa: E402

zpath, out = sys.argv[1], sys.argv[2]
first_year = int(sys.argv[3]) if len(sys.argv) > 3 else 2000

exact, prefixes = build_lookup()
z = zipfile.ZipFile(zpath)
names = z.namelist()
cc_name = next(n for n in names if n.startswith("country_codes"))
cc = pd.read_csv(z.open(cc_name), dtype=str)
iso = dict(zip(cc["country_code"].astype(int), cc["country_iso3"]))

frames = []
for n in sorted(names):
    if not (n.startswith("BACI_") and n.endswith(".csv")):
        continue
    year = int(n.split("_Y")[1][:4])
    if year < first_year:
        continue
    df = pd.read_csv(
        z.open(n),
        dtype={"t": "int16", "i": "int32", "j": "int32", "k": str, "v": "float64"},
        usecols=["t", "i", "j", "k", "v", "q"],
        na_values=["NA", "           NA"],
    )
    df["k"] = df["k"].str.strip().str.zfill(6)
    codes = df["k"].unique()
    gmap = {c: group_of(c, exact, prefixes) for c in codes}
    df["group"] = df["k"].map(gmap)
    df = df[df["group"].notna()]
    df["q"] = pd.to_numeric(df["q"], errors="coerce")
    g = df.groupby(["group", "i", "j"], as_index=False).agg(t=("q", "sum"), usd=("v", "sum"))
    g = g[(g["t"] >= 1000) | (g["usd"] >= 1000)]
    g.insert(0, "year", year)
    g["o"] = g["i"].map(iso)
    g["d"] = g["j"].map(iso)
    frames.append(g[["year", "group", "o", "d", "t", "usd"]])
    print(year, len(g), flush=True)

res = pd.concat(frames)
res["t"] = res["t"].round(0)
res["usd"] = res["usd"].round(0)
res.to_csv(out, index=False, compression="gzip")
print("rows", len(res), "->", out)
