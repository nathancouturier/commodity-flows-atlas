"""
Download the IMF PortWatch ports database once and keep the columns the infrastructure layer uses.

    python pipeline/infrastructure/fetch_portwatch_ports.py

Input   ArcGIS feature service PortWatch_ports_database (IMF PortWatch, IMF and University of Oxford; ArcGIS item
        acc668d199d1472abaaf2467133d4ca4, terms: https://www.imf.org/external/terms.htm, the same as the chokepoint tables)
Output  pipeline/cache/portwatch_ports.csv   portid, name, ISO3, UN/LOCODE, latitude, longitude, page id

Only the identity and the position of each port are kept: no vessel count and no traffic figure. The ports of
data/infrastructure/ports.geojson take their position and their UN/LOCODE from this table (`portwatch` holds the
`portid`, the PortWatch port page is https://portwatch.imf.org/pages/<pageid>). Run it by hand when the table must be
refreshed; no scheduled job calls it.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common.fetch import get_json  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(ROOT, "pipeline", "cache", "portwatch_ports.csv")
URL = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/PortWatch_ports_database/FeatureServer/0/query"
FIELDS = ["portid", "portname", "ISO3", "LOCODE", "lat", "lon", "pageid"]
PAGE = 1000
MIN_INTERVAL_S = 8.0   # the least time between two requests to PortWatch, as in pipeline/freight/fetch_portwatch.py (the owner's rule: slowly, one at a time)


def fetch():
    rows, off = [], 0
    while True:
        d = get_json(URL, params={"where": "1=1", "outFields": ",".join(FIELDS), "returnGeometry": "false", "f": "json",
                                  "orderByFields": "ObjectId", "resultOffset": off, "resultRecordCount": PAGE}, min_interval=MIN_INTERVAL_S)
        feats = d.get("features") or []
        rows += [f["attributes"] for f in feats]
        if not feats or not d.get("exceededTransferLimit"):
            return rows
        off += len(feats)


def main():
    rows = fetch()
    if len(rows) < 1000:
        raise SystemExit(f"only {len(rows)} ports returned: the table was not replaced")
    rows.sort(key=lambda r: int(r["portid"].replace("port", "")) if r["portid"].replace("port", "").isdigit() else 0)
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["portid", "name", "iso3", "locode", "lat", "lon", "pageid"])
        for r in rows:
            w.writerow([r["portid"], (r["portname"] or "").strip(), r["ISO3"] or "", (r["LOCODE"] or "").replace(" ", ""),
                        round(r["lat"], 5), round(r["lon"], 5), r["pageid"] or ""])
    print(f"portwatch ports: {len(rows)} rows, {sum(1 for r in rows if r['LOCODE'])} with a UN/LOCODE -> {OUT}")


if __name__ == "__main__":
    main()
