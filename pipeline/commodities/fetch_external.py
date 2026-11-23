"""
Fetch the two external inputs of build_commodities.py that are not in raw/ and cache the extracted tables.

    .venv/bin/python -I pipeline/commodities/fetch_external.py [--only crops] [--wna-html FILE] [--fao-csv FILE] [--fert-csv FILE]

Outputs (small, committed):
  pipeline/cache/wna_uranium.json            World Nuclear Association, mine production by country (tU)
  pipeline/cache/faostat_cocoa_production.csv  FAOSTAT QCL, cocoa beans (item 661), production (t)
  pipeline/cache/faostat_eu_crops.csv        FAOSTAT QCL (CC BY 4.0), production (element 5510, t) of wheat, maize, rice, soya beans, rape or colza
                                             seed and sugar beet for the 27 member states of the European Union, the FAOSTAT aggregate
                                             "European Union (27)" and the World, from 2015: only what the member-state tables use
                                             (the same bulk file as the cocoa cache: one download)
  pipeline/cache/faostat_fertilizer_production.csv  FAOSTAT Fertilizers by Product (RFB), urea (item 4001) and
                                               potassium chloride (item 4016), production in tonnes of product, from 2015

Without arguments the files are downloaded (one request each):
  WNA     https://world-nuclear.org/information-library/nuclear-fuel-cycle/mining-of-uranium/world-uranium-mining-production
  FAOSTAT https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip
  FAOSTAT https://bulks-faostat.fao.org/production/Inputs_FertilizersProduct_E_All_Data_(Normalized).zip
(the FAOSTAT JSON API at fenixservices.fao.org returned HTTP 521 when this was written, so the bulk file is used.)
Downloaded data is only ever parsed as text/CSV, never executed.
"""
import argparse
import csv
import html
import io
import json
import os
import re
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from common import fetch  # noqa: E402  (the shared downloader: retries, type checks, a truthful User-Agent)
CACHE = os.path.join(HERE, "..", "cache")
WNA_URL = "https://world-nuclear.org/information-library/nuclear-fuel-cycle/mining-of-uranium/world-uranium-mining-production"
FAO_URL = "https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip"
FERT_URL = "https://bulks-faostat.fao.org/production/Inputs_FertilizersProduct_E_All_Data_(Normalized).zip"
FERT_ITEMS = {"4001": "urea", "4016": "potassium chloride"}
# FAOSTAT QCL items of the EU member-state tables and their M49 codes (FAOSTAT writes them with a leading quote)
CROP_ITEMS = {"15": "Wheat", "56": "Maize (corn)", "27": "Rice", "236": "Soya beans", "270": "Rape or colza seed", "157": "Sugar beet"}
CROPS_FROM = 2015
EU_M49 = {"040": "AUT", "056": "BEL", "100": "BGR", "191": "HRV", "196": "CYP", "203": "CZE", "208": "DNK", "233": "EST", "246": "FIN",
          "250": "FRA", "276": "DEU", "300": "GRC", "348": "HUN", "372": "IRL", "380": "ITA", "428": "LVA", "440": "LTU", "442": "LUX",
          "470": "MLT", "528": "NLD", "616": "POL", "620": "PRT", "642": "ROU", "703": "SVK", "705": "SVN", "724": "ESP", "752": "SWE"}
EU_AGG = {"001": "World", "097": "European Union (27)"}


def get(url, kind="zip"):
    """The bytes of ``url``, downloaded through common/fetch.py (an HTML error page is never taken for a zip)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "download")
        fetch.download(url, path, kind=kind, min_bytes=1000, timeout=(20, 300))
        with open(path, "rb") as fh:
            return fh.read()


def num(s):
    s = s.strip().replace(",", "")
    return float(s) if re.fullmatch(r"\d+(\.\d+)?", s) else None


def parse_wna(text):
    i = text.find("<table")
    j = text.find("</table>", i)
    tab = text[i:j]
    rows = []
    for tr in re.findall(r"<tr.*?</tr>", tab, flags=re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)]
        if cells:
            rows.append(cells)
    head = rows[0]
    assert head[0] == "Country" and head[-1].isdigit(), head
    years = [int(y) for y in head[1:]]
    out = {"years": years, "rows": {}, "updated": None}
    m = re.search(r"Updated\s+\w+,\s+(\d+ \w+ \d{4})", text)
    out["updated"] = m.group(1) if m else None
    for r in rows[1:]:
        vals = [num(c) for c in r[1:]]
        if r[0].startswith("World total tU") and not r[0].startswith("World total tU3O8"):
            out["rows"]["World total tU"] = vals
        elif r[0].startswith("World total") or r[0].startswith("%"):
            continue
        else:
            out["rows"][r[0]] = vals
    return out


def fertilizer(fert_csv=None):
    if fert_csv:
        f = open(fert_csv, encoding="utf-8", newline="")
    else:
        z = zipfile.ZipFile(io.BytesIO(get(FERT_URL)))
        name = [n for n in z.namelist() if n.endswith("Normalized).csv")][0]
        f = io.TextIOWrapper(z.open(name), encoding="utf-8", newline="")
    out = []
    for r in csv.DictReader(f):
        if r["Item Code"] in FERT_ITEMS and r["Element"] == "Production" and int(r["Year"]) >= 2015 and r["Value"].strip():
            out.append([r["Area Code (M49)"].lstrip("'"), r["Area"], r["Item Code"], r["Year"], r["Value"], r["Flag"]])
    assert any(x[2] == "4001" for x in out) and any(x[2] == "4016" for x in out), "urea or potassium chloride production missing"
    with open(os.path.join(CACHE, "faostat_fertilizer_production.csv"), "w", newline="", encoding="utf-8") as g:
        wr = csv.writer(g)
        wr.writerow(["m49", "area", "item", "year", "value_t", "flag"])
        wr.writerows(out)
    print("faostat fertilizer rows:", len(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["crops"], help="crops: only the FAOSTAT crop caches (cocoa and the EU member-state crops), no other download")
    ap.add_argument("--wna-html")
    ap.add_argument("--fao-csv", help="extracted Production_Crops_Livestock_E_All_Data_(Normalized).csv")
    ap.add_argument("--fert-csv", help="extracted Inputs_FertilizersProduct_E_All_Data_(Normalized).csv")
    a = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)

    if not a.only:
        text = open(a.wna_html, encoding="utf-8").read() if a.wna_html else fetch.get_text(WNA_URL)
        w = parse_wna(text)
        assert "Kazakhstan" in w["rows"] and "World total tU" in w["rows"]
        json.dump(w, open(os.path.join(CACHE, "wna_uranium.json"), "w"), indent=1)
        print("wna rows:", len(w["rows"]), "years", w["years"][0], "-", w["years"][-1])

    if a.fao_csv:
        f = open(a.fao_csv, encoding="utf-8", newline="")
    else:
        z = zipfile.ZipFile(io.BytesIO(get(FAO_URL)))
        name = [n for n in z.namelist() if n.endswith("Normalized).csv")][0]
        f = io.TextIOWrapper(z.open(name), encoding="utf-8", newline="")
    rd = csv.DictReader(f)
    out, crops = [], []
    for r in rd:
        if r["Item Code"] == "661" and r["Element"] == "Production" and int(r["Year"]) >= 2020:
            out.append([r["Area Code (M49)"].lstrip("'"), r["Area"], r["Year"], r["Value"], r["Flag"]])
        m49 = r["Area Code (M49)"].lstrip("'")
        if r["Item Code"] in CROP_ITEMS and r["Element Code"] == "5510" and int(r["Year"]) >= CROPS_FROM and (m49 in EU_M49 or m49 in EU_AGG) and r["Value"].strip():
            crops.append([m49, r["Area"], r["Item Code"], r["Year"], r["Value"], r["Flag"]])
    assert {x[0] for x in crops} >= set(EU_M49) | set(EU_AGG), "an EU member state or the world is missing from the crop production file"
    with open(os.path.join(CACHE, "faostat_cocoa_production.csv"), "w", newline="", encoding="utf-8") as g:
        wr = csv.writer(g)
        wr.writerow(["m49", "area", "year", "value_t", "flag"])
        wr.writerows(out)
    print("faostat cocoa rows:", len(out))

    with open(os.path.join(CACHE, "faostat_eu_crops.csv"), "w", newline="", encoding="utf-8") as g:
        wr = csv.writer(g)
        wr.writerow(["m49", "area", "item", "year", "value_t", "flag"])
        wr.writerows(crops)
    print("faostat EU crop rows:", len(crops))

    if not a.only:
        fertilizer(a.fert_csv)


if __name__ == "__main__":
    main()
