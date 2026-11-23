"""
Exports and imports by country and HS4 heading, and each country's total merchandise trade, for the latest year of a
CEPII BACI HS92 archive, in one streaming pass over that year's file.

    python pipeline/trade/extract_hs4.py <BACI_HS92_Vyyyymm.zip> [cache dir, default pipeline/cache]

Writes, in the cache directory:
  hs4_exports.csv.gz   t, o (exporter ISO3), hs4, usd (thousand USD), tonnes: every heading of every chapter
  hs4_imports.csv.gz   t, d (importer ISO3), hs4, usd, tonnes
  hs4_totals.csv       t, c, exports, imports: thousand USD over every product the archive holds
  hs4_exports_desc.csv hs4, description: the first six-digit description under each heading, from the archive's
                       product codes file (BACI gives no four-digit wording)
Country codes are the archive's own ISO3 codes (S19 is Taiwan: the builders map it). Nothing is cleaned or dropped:
the headings are CEPII BACI as published. Run by pipeline/annual/update_annual.py after a new BACI version.
BACI licence: Etalab Open Licence 2.0 — cite "CEPII BACI".
"""
import os
import re
import sys
import zipfile

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CHUNK = 2_000_000


def main(zpath, cache):
    z = zipfile.ZipFile(zpath)
    years = {int(m.group(1)): n for n in z.namelist() if (m := re.fullmatch(r"BACI_HS92_Y(\d{4})_V\d{6}\.csv", n))}
    if not years:
        raise SystemExit(f"{zpath}: no yearly BACI file")
    year = max(years)
    cc = pd.read_csv(z.open(next(n for n in z.namelist() if n.startswith("country_codes"))), dtype=str)
    iso = dict(zip(cc["country_code"].astype(int), cc["country_iso3"]))
    exp, imp, tot_e, tot_i = [], [], [], []
    reader = pd.read_csv(z.open(years[year]), dtype={"t": "int16", "i": "int32", "j": "int32", "k": str, "v": "float64"},
                         usecols=["t", "i", "j", "k", "v", "q"], na_values=["NA", "           NA"], chunksize=CHUNK)
    for df in reader:
        df["q"] = pd.to_numeric(df["q"], errors="coerce")
        df["hs4"] = df["k"].str.strip().str.zfill(6).str[:4]
        exp.append(df.groupby(["i", "hs4"])[["v", "q"]].sum(min_count=1))
        imp.append(df.groupby(["j", "hs4"])[["v", "q"]].sum(min_count=1))
        tot_e.append(df.groupby("i")["v"].sum())
        tot_i.append(df.groupby("j")["v"].sum())

    def side(parts, who):
        g = pd.concat(parts).groupby(level=[0, 1]).sum(min_count=1).reset_index()
        g.columns = ["code", "hs4", "usd", "tonnes"]
        g.insert(0, "t", year)
        g.insert(1, who, g.pop("code").map(iso))
        g[["usd", "tonnes"]] = g[["usd", "tonnes"]].round(3)  # the archive's own precision, without float noise
        return g.sort_values([who, "hs4"])

    os.makedirs(cache, exist_ok=True)
    e, i = side(exp, "o"), side(imp, "d")
    e.to_csv(os.path.join(cache, "hs4_exports.csv.gz"), index=False, compression="gzip")
    i.to_csv(os.path.join(cache, "hs4_imports.csv.gz"), index=False, compression="gzip")
    te = pd.concat(tot_e).groupby(level=0).sum()
    ti = pd.concat(tot_i).groupby(level=0).sum()
    tot = pd.DataFrame({"exports": te, "imports": ti}).fillna(0).round(0)
    tot.index = tot.index.map(iso)
    tot = tot[tot.index.notna()].rename_axis("c").reset_index().sort_values("c")
    tot.insert(0, "t", year)
    tot.to_csv(os.path.join(cache, "hs4_totals.csv"), index=False)
    pc = pd.read_csv(z.open(next(n for n in z.namelist() if n.startswith("product_codes"))), dtype=str)
    pc["hs4"] = pc["code"].str.zfill(6).str[:4]
    pc.groupby("hs4")["description"].first().to_csv(os.path.join(cache, "hs4_exports_desc.csv"))
    print(os.path.basename(years[year]), "exports", len(e), "imports", len(i), "countries", len(tot))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "pipeline", "cache"))
