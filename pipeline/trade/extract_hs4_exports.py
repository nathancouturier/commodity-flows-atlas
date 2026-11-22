"""
Exports by country and HS4 heading for raw-material chapters, latest BACI year only.
Used for the light "country check": a country's top raw-material export that is not in the
atlas catalogue (e.g. diamonds for Botswana) is added to its profile.

    python pipeline/trade/extract_hs4_exports.py raw/baci/BACI_HS92_V202601.zip pipeline/cache/hs4_exports.csv.gz
"""
import sys
import zipfile

import pandas as pd

RAW_CHAPTERS = {f"{c:02d}" for c in list(range(1, 28)) + [40, 41, 44, 47, 51, 52, 53, 71] + list(range(72, 82))}

z = zipfile.ZipFile(sys.argv[1])
names = sorted(n for n in z.namelist() if n.startswith("BACI_") and n.endswith(".csv"))
latest = names[-1]
cc = pd.read_csv(z.open(next(n for n in z.namelist() if n.startswith("country_codes"))), dtype=str)
iso = dict(zip(cc["country_code"].astype(int), cc["country_iso3"]))
pc = pd.read_csv(z.open(next(n for n in z.namelist() if n.startswith("product_codes"))), dtype=str)
df = pd.read_csv(z.open(latest), dtype={"k": str}, usecols=["t", "i", "k", "v", "q"])
df["k"] = df["k"].str.strip().str.zfill(6)
df = df[df["k"].str[:2].isin(RAW_CHAPTERS)]
df["hs4"] = df["k"].str[:4]
g = df.groupby(["t", "i", "hs4"], as_index=False).agg(usd=("v", "sum"), tonnes=("q", "sum"))
g["o"] = g["i"].map(iso)
g[["t", "o", "hs4", "usd", "tonnes"]].to_csv(sys.argv[2], index=False, compression="gzip")
# HS4 descriptions (first six-digit description under each heading, trimmed)
pc["hs4"] = pc["code"].str.zfill(6).str[:4]
desc = pc.groupby("hs4")["description"].first()
desc.to_csv(sys.argv[2].replace(".csv.gz", "_desc.csv"))
print(latest, len(g))
