"""
Fetch the two external inputs of build_commodities.py that are not in raw/ and cache the extracted tables.

    .venv/bin/python -I pipeline/commodities/fetch_external.py [--wna-html FILE] [--fao-csv FILE]

Outputs (small, committed):
  pipeline/cache/wna_uranium.json            World Nuclear Association, mine production by country (tU)
  pipeline/cache/faostat_cocoa_production.csv  FAOSTAT QCL, cocoa beans (item 661), production (t)

Without arguments the files are downloaded (one request each):
  WNA     https://world-nuclear.org/information-library/nuclear-fuel-cycle/mining-of-uranium/world-uranium-mining-production
  FAOSTAT https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip
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
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "..", "cache")
WNA_URL = "https://world-nuclear.org/information-library/nuclear-fuel-cycle/mining-of-uranium/world-uranium-mining-production"
FAO_URL = "https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip"
UA = "Mozilla/5.0 (research data download)"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wna-html")
    ap.add_argument("--fao-csv", help="extracted Production_Crops_Livestock_E_All_Data_(Normalized).csv")
    a = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)

    text = open(a.wna_html, encoding="utf-8").read() if a.wna_html else get(WNA_URL).decode("utf-8")
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
    out = []
    for r in rd:
        if r["Item Code"] == "661" and r["Element"] == "Production" and int(r["Year"]) >= 2020:
            out.append([r["Area Code (M49)"].lstrip("'"), r["Area"], r["Year"], r["Value"], r["Flag"]])
    with open(os.path.join(CACHE, "faostat_cocoa_production.csv"), "w", newline="", encoding="utf-8") as g:
        wr = csv.writer(g)
        wr.writerow(["m49", "area", "year", "value_t", "flag"])
        wr.writerows(out)
    print("faostat cocoa rows:", len(out))


if __name__ == "__main__":
    main()
