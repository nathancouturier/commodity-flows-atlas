"""
World merchant fleet by type of ship (UNCTADstat), for the "World fleet" block of the vessel class pages.

    python pipeline/freight/fleet.py                  # download the bulk file, rebuild the cache and the JSON
    python pipeline/freight/fleet.py --from FILE.7z   # same, from a bulk file already downloaded

Source  UNCTADstat, "Merchant fleet by flag of registration and by type of ship" (US.MerchantFleet), annual. The bulk
        download is a 7z archive holding one CSV; it is decoded with the standard library (one LZMA2 stream).
Terms   UNCTADstat terms of use: materials under the Creative Commons Attribution 3.0 IGO licence; data "may be copied
        freely, duplicated and further distributed provided that United Nations Trade and Development Data Hub is cited
        as the source" (https://unctadstat.unctad.org/EN/About.html#TERMS_OF_USE). The atlas keeps the world rows only.
Output  pipeline/cache/unctad_fleet_world.csv (the world rows, tracked) and data/freight/fleet.json: for each ship type
        of the table, the ships, the deadweight and the average age of the latest year, and the last YEARS years.

The ship types are UNCTADstat's (oil tankers, bulk carriers, general cargo, container ships, other types of ships),
not the commercial classes of the atlas (Capesize, VLCC...): their fleet, age and orderbook are not published for free.
A failed download keeps the cache and rebuilds the JSON from it; the script always exits 0.
"""
import csv
import io
import json
import lzma
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

URL = "https://unctadstat-api.unctad.org/bulkdownload/US.MerchantFleet/US_MerchantFleet"
PAGE = "https://unctadstat.unctad.org/datacentre/dataviewer/US.MerchantFleet"
CACHE = os.path.join(ROOT, "pipeline", "cache", "unctad_fleet_world.csv")
OUT = os.path.join(ROOT, "data", "freight", "fleet.json")
SRC = "unctadstat-fleet"
YEARS = 10
WORLD = "0000"
FIELDS = ("Year", "ShipType", "ShipType Label", "Number of ships", "Dead weight tons in thousands",
          "Average age of vessels (years)")


def decode_7z(blob):
    """The CSV inside a 7z archive of one LZMA2-compressed file (the UNCTADstat bulk format)."""
    if blob[:6] != b"7z\xbc\xaf\x27\x1c":
        raise ValueError("not a 7z archive")
    head_off = int.from_bytes(blob[12:20], "little")
    header = blob[32 + head_off:]
    k = header.find(b"\x21\x21\x01")  # coder record: flags (id size 1, has properties), LZMA2 id 0x21, 1 property byte
    if k < 0:
        raise ValueError("the archive does not use the LZMA2 coder")
    p = header[k + 3]
    dict_size = (2 | (p & 1)) << (p // 2 + 11)
    d = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[{"id": lzma.FILTER_LZMA2, "dict_size": dict_size}])
    return d.decompress(blob[32:32 + head_off]).decode("utf-8-sig")


def world_rows(text):
    rows = [{f: r[f] for f in FIELDS} for r in csv.DictReader(io.StringIO(text)) if r["Economy"] == WORLD]
    if not rows or any(f not in rows[0] for f in FIELDS):
        raise ValueError("no world rows or a missing column")
    return rows


def num(s):
    return float(s) if s not in ("", None) else None


def count(s):
    return None if num(s) is None else int(num(s))


def build(rows):
    years = sorted({int(r["Year"]) for r in rows})
    last = years[-1]
    keep = years[-YEARS:]
    types = []
    for code in sorted({r["ShipType"] for r in rows}, key=int):
        if code == "0":
            continue  # the total of all types
        by_year = {int(r["Year"]): r for r in rows if r["ShipType"] == code}
        r = by_year.get(last)
        if r is None:
            continue
        name = r["ShipType Label"]
        n = f"World fleet of the ship type '{name}', UNCTADstat (Merchant fleet by flag of registration and by type of ship), year {last}"
        fig = lambda v, u: None if v is None else {"v": v, "u": u, "y": last, "s": SRC, "n": n}  # noqa: E731
        dwt = num(r["Dead weight tons in thousands"])
        types.append({
            "name": name,
            "ships": fig(count(r["Number of ships"]), "ships"),
            "dwt": fig(None if dwt is None else round(dwt / 1000, 1), "million dwt"),
            "age": fig(None if num(r["Average age of vessels (years)"]) is None else round(num(r["Average age of vessels (years)"]), 1), "years"),
            "hist": {
                "years": keep,
                "ships": [count(by_year[y]["Number of ships"]) if y in by_year else None for y in keep],
                "dwt": [round(num(by_year[y]["Dead weight tons in thousands"]) / 1000, 1)
                        if y in by_year and num(by_year[y]["Dead weight tons in thousands"]) is not None else None for y in keep],
            },
        })
    return {"s": SRC, "url": PAGE, "y": last, "types": types}


def save_cache(rows):
    with open(CACHE, "w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (int(r["Year"]), int(r["ShipType"]))))


def load_cache():
    with open(CACHE, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    rows = None
    src = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else None
    try:
        if src:
            blob = open(src, "rb").read()
        else:
            from common.fetch import download
            with tempfile.TemporaryDirectory() as tmp:
                dest = os.path.join(tmp, "fleet.7z")
                download(URL, dest, min_bytes=100_000)
                blob = open(dest, "rb").read()
        rows = world_rows(decode_7z(blob))
        save_cache(rows)
        print(f"fleet: {len(rows)} world rows from the bulk file")
    except Exception as e:  # keep the cache
        print(f"fleet: bulk file not used ({str(e)[:160]}); building from the cache")
    if rows is None:
        if not os.path.exists(CACHE):
            print("fleet: no cache either; nothing written")
            return
        rows = load_cache()
    doc = build(rows)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    print(f"fleet: {OUT} written, year {doc['y']}, {len(doc['types'])} ship types")


if __name__ == "__main__":
    main()
