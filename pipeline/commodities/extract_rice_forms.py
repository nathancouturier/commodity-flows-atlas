"""
Extract paddy and husked rice flows from a CEPII BACI HS92 zip, so that build_commodities.py can put
paddy on the milled basis used by the USDA tables of the rice page.

    .venv/bin/python -I pipeline/commodities/extract_rice_forms.py [raw/baci/BACI_HS92_V202601.zip] [first_year]

The shared BACI extract (pipeline/cache/baci_flows.csv.gz) sums HS 1006.10 (paddy), 1006.20 (husked),
1006.30 (milled) and 1006.40 (broken) into one "rice" group in gross weight. This script keeps the
first two apart, per country pair, for the latest year of the zip (or from first_year on).

Output: pipeline/cache/baci_rice_forms.csv, columns year, o, d, hs6, t (tonnes). Rows below 1,000 t
are dropped, as in pipeline/trade/extract_baci.py. Run it again whenever the BACI extract is renewed:
build_commodities.py leaves the rice flows unconverted, and says so, when the year is missing here.
BACI licence: Etalab Open Licence 2.0, cite "CEPII BACI".
"""
import glob
import os
import sys
import zipfile

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
FORMS = {"100610": "paddy", "100620": "husked"}


def main():
    zips = sorted(glob.glob(os.path.join(ROOT, "raw", "baci", "BACI_HS92_V*.zip")))
    zpath = sys.argv[1] if len(sys.argv) > 1 else (zips[-1] if zips else None)
    if not zpath or not os.path.exists(zpath):
        raise SystemExit("no BACI zip found under raw/baci/")
    z = zipfile.ZipFile(zpath)
    names = z.namelist()
    cc = pd.read_csv(z.open(next(n for n in names if n.startswith("country_codes"))), dtype=str)
    iso = dict(zip(cc["country_code"].astype(int), cc["country_iso3"]))
    years = sorted((int(n.split("_Y")[1][:4]), n) for n in names if n.startswith("BACI_") and n.endswith(".csv"))
    first = int(sys.argv[2]) if len(sys.argv) > 2 else years[-1][0]
    frames = []
    for year, n in years:
        if year < first:
            continue
        df = pd.read_csv(z.open(n), dtype={"i": "int32", "j": "int32", "k": str}, usecols=["i", "j", "k", "q"],
                         na_values=["NA", "           NA"])
        df["k"] = df["k"].str.strip().str.zfill(6)
        df = df[df["k"].isin(FORMS)]
        df["q"] = pd.to_numeric(df["q"], errors="coerce")
        g = df.groupby(["i", "j", "k"], as_index=False).agg(t=("q", "sum"))
        g = g[g["t"] >= 1000]
        g.insert(0, "year", year)
        g["o"] = g["i"].map(iso)
        g["d"] = g["j"].map(iso)
        g["hs6"] = g["k"]
        g["t"] = g["t"].round(0).astype("int64")
        frames.append(g[["year", "o", "d", "hs6", "t"]])
        print(year, len(g), flush=True)
    out = os.path.join(ROOT, "pipeline", "cache", "baci_rice_forms.csv")
    res = pd.concat(frames).sort_values(["year", "hs6", "t"], ascending=[True, True, False])
    res.to_csv(out, index=False)
    print("rows", len(res), "->", out)


if __name__ == "__main__":
    main()
