"""
Australia's LNG exports by market, from the Australian Government's Resources and Energy Quarterly (LNG page, METHODOLOGY.md §1).

    python pipeline/trade/aus_req_lng.py      # read the workbook in raw/australia/disr-req and write pipeline/cache/aus_req_lng.json
    import aus_req_lng; aus_req_lng.load()     # the cache only

Source: Department of Industry, Science and Resources, Commonwealth of Australia, "Resources and Energy Quarterly", December 2025, historical
data workbook, sheet "41" (principal markets for Australia's commodity exports, by volume, calendar years): the LNG block, a total and five
fixed principal markets, in Mt. Licence: Creative Commons Attribution 4.0 International; the About sheet asks for this attribution, in these
words: "Department of Industry, Science, and Resources, Commonwealth of Australia Resources and Energy Quarterly, December 2025."
The workbook is downloaded by hand (the site refuses scripted downloads): no scheduled job fetches it, and the page says the edition it
reads. The refresh is the owner's: a newer workbook put in the same folder and this script run again.
"""
import json
import os
import re

import openpyxl

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CACHE_FILE = os.path.join(ROOT, "pipeline", "cache", "aus_req_lng.json")
RAW = os.path.join(ROOT, "raw", "australia", "disr-req", "resources-and-energy-quarterly-december-2025-historical-data.xlsx")
ISO = {"China": "CHN", "Japan": "JPN", "South Korea": "KOR", "Taiwan": "TWN", "India": "IND"}
URL = "https://www.industry.gov.au/sites/default/files/2025-12/resources-and-energy-quarterly-december-2025-historical-data.xlsx"
EDITION = "December 2025"
ATTRIBUTION = "Department of Industry, Science, and Resources, Commonwealth of Australia Resources and Energy Quarterly, December 2025."


def build(path=RAW, year=None):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    about = [c for r in wb["About"].iter_rows(values_only=True) for c in r if isinstance(c, str)]
    assert ATTRIBUTION in [a.strip() for a in about], "the About sheet no longer gives the attribution line the atlas prints"
    rows = list(wb["41"].iter_rows(values_only=True))
    head = next(i for i, r in enumerate(rows) if r[6] == "Unit")
    years = {i: v for i, v in enumerate(rows[head]) if isinstance(v, int)}
    col = next(i for i, y in years.items() if y == (year or max(years.values())))
    i0 = next(i for i, r in enumerate(rows) if i > head and isinstance(r[5], str) and re.fullmatch(r"LNG\s*[a-z]?", r[5].strip()))
    total, markets, y = rows[i0][col], {}, years[col]
    for r in rows[i0 + 1:]:
        if r[5] is None and r[6] is None:
            break
        name = re.sub(r"\s+[a-z]$", "", r[5].strip())
        assert name in ISO, name
        assert r[6].strip() == "Mt"
        markets[ISO[name]] = r[col]
    assert rows[i0][6].strip() == "Mt" and len(markets) == 5
    cells = [c for r in rows[::-1] for c in r if isinstance(c, str)]
    foot = next(c for c in cells if c.startswith("n "))
    source = next(c for c in cells if c.startswith("Source:"))
    doc = {"source": "Department of Industry, Science and Resources, Resources and Energy Quarterly", "edition": EDITION, "url": URL,
           "attribution": ATTRIBUTION, "licence": "CC BY 4.0", "year": y, "unit": "Mt", "total": round(float(total), 4),
           "markets": {k: round(float(v), 4) for k, v in markets.items()}, "total_note": foot.strip(), "table_source": source.strip()}
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    return doc


_DOC = {}


def load():
    if not _DOC:
        with open(CACHE_FILE, encoding="utf-8") as f:
            _DOC.update(json.load(f))
    return _DOC


if __name__ == "__main__":
    d = build()
    print("wrote", os.path.relpath(CACHE_FILE, ROOT), d["year"], d["total"], d["markets"])
