"""
The World Port Index entry of each port that has one, as the site reads it when a port panel opens.

    python pipeline/infrastructure/wpi_limits.py          # writes data/infrastructure/wpi.json

Input   pipeline/cache/wpi_ports.csv    one row per published match (written by extract_wpi.py, by hand)
        pipeline/cache/wpi_meta.json    the file's date, the ports held back, the ports the match left out
        data/infrastructure/ports.geojson   only the ids of the port assets, to check that each entry belongs to one
Output  data/infrastructure/wpi.json
          {"s": "nga-wpi", "read": "YYYY-MM", "captured"?: "YYYY-MM-DD", "edition": text | null,
           "ports": {port id: {n, name, lc?, by, km, why?, size?, type?, tide?, chan?, anch?, pier?, oil?, lng?, loa?, beam?,
                               draft?, oloa?, obeam?, odraft?, pilot?, tideRes?}}}
        `s` is the source id, `read` the month the file was taken, `captured` the day the Internet Archive captured the
        publisher's address the file is a copy of (absent when the file comes from the publisher itself; the file holds no
        date of its own), `edition` the text typed from the publisher's page or null. An entry has the publication's own name for the place (`name`) and its number (`n`),
        the UN/LOCODE the file gives (`lc`), how the entry was matched to the port (`by`: code, name or review, with `km`
        from the atlas point and, for a review, its sentence `why`), and the columns read: harbour size and type, tidal
        range, the four depths, the maximum vessel, the offshore maximum vessel, pilotage and tide restriction. A figure is
        a positive number as the file gives it: a depth is one of the publication's bands and the page prints it as one, so
        nothing here turns it into text. A figure the file does not state is absent: no zero, no null, no empty text. The
        maximum vessel of a port the meta holds back is absent. No key of an entry is `s`, `y` or `v`: the data validator
        reads those as a source id and a figure.

The file is built from the tracked cache alone: nothing under raw/ is read, so it builds where the raw download does not
exist. It stops, and writes nothing, when the cache is not what the extractor writes: a different header, an entry of a
port the atlas lacks or the match left out, a number that is not positive, a count that differs from the meta's.
Run twice, it gives the same bytes. The file is loaded when a port panel opens, never at map start.
"""
import csv
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CACHE = os.path.join(ROOT, "pipeline", "cache")
PORTS_CSV = os.path.join(CACHE, "wpi_ports.csv")
META = os.path.join(CACHE, "wpi_meta.json")
PORTS = os.path.join(ROOT, "data", "infrastructure", "ports.geojson")
OUT = os.path.join(ROOT, "data", "infrastructure", "wpi.json")

# the cache's columns, typed here: a column added to the cache fails the build until this list and the validator know it
HEADER = ["port", "wpi", "name", "code", "by", "km", "size", "type", "tide", "chan", "anch", "pier", "oil", "lng", "loa", "beam", "draft", "oloa",
          "obeam", "odraft", "pilot", "tide_res", "why"]
FIGURES = ["tide", "chan", "anch", "pier", "oil", "lng", "loa", "beam", "draft", "oloa", "obeam", "odraft"]
LIMITS = ["chan", "anch", "pier", "oil", "lng", "loa", "beam", "draft", "oloa", "obeam", "odraft"]  # a row needs at least one of these
VESSEL = ["loa", "beam", "draft"]  # the group a port is held back for (the `maximum` group)
BY = ("code", "name", "review")
SIZES = ("Very Small", "Small", "Medium", "Large")
FLAGS = ("Yes", "No")
# the order of the keys of an entry, which is also the order of the cache's columns
KEYS = [("n", "wpi"), ("name", "name"), ("lc", "code"), ("by", "by"), ("km", "km"), ("why", "why"), ("size", "size"), ("type", "type"), ("tide", "tide"),
        ("chan", "chan"), ("anch", "anch"), ("pier", "pier"), ("oil", "oil"), ("lng", "lng"), ("loa", "loa"), ("beam", "beam"), ("draft", "draft"),
        ("oloa", "oloa"), ("obeam", "obeam"), ("odraft", "odraft"), ("pilot", "pilot"), ("tideRes", "tide_res")]


class Stop(Exception):
    pass


def num(cell, where):
    """A cell as a number (an integer when it is one); a text that is not a positive number stops the build."""
    if not re.fullmatch(r"\d+(\.\d+)?", cell):
        raise Stop(f"{where}: {cell!r} is not a number")
    x = float(cell)
    if not x > 0:
        raise Stop(f"{where}: {cell!r} is not positive")
    return int(x) if x.is_integer() else x


def month(date):
    m = re.fullmatch(r"(\d{4}-(?:0[1-9]|1[0-2]))-\d{2}", date or "")
    if not m:
        raise Stop(f"the meta's `downloaded` is {date!r}, not a date YYYY-MM-DD")
    return m.group(1)


def day(date, name):
    if not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])", date or ""):
        raise Stop(f"the meta's `{name}` is {date!r}, not a date YYYY-MM-DD")
    return date


def entry(r):
    """The entry of one cache row."""
    where = r["port"]
    out = {}
    for key, col in KEYS:
        cell = r[col]
        if cell == "":
            continue
        if key == "n":
            if not re.fullmatch(r"[1-9]\d*", cell):
                raise Stop(f"{where}: the entry number {cell!r} is not a positive integer")
            v = int(cell)
        elif key == "km":
            if not re.fullmatch(r"\d+(\.\d+)?", cell):
                raise Stop(f"{where}: km {cell!r} is not a number")
            v = float(cell)
            v = int(v) if v.is_integer() else v
        elif col in FIGURES:
            v = num(cell, f"{where} {col}")
        else:
            v = cell
        out[key] = v
    return out


def build(csv_text, meta, port_ids):
    """The document wpi.json holds, from the text of the cache, its meta and the ids of the atlas's port assets."""
    cells = list(csv.reader(csv_text.splitlines()))
    if not cells or cells[0] != HEADER:
        raise Stop(f"the cache header is {cells[0] if cells else None}, not {HEADER}")
    if any(len(c) != len(HEADER) for c in cells):
        raise Stop("a row of the cache has the wrong number of cells")
    rows = [dict(zip(HEADER, c)) for c in cells[1:]]
    left_out = {d["id"] for d in meta["doubtful"]} | {d["id"] for d in meta["none"]}
    held = {h["id"] for h in meta["held_vessel"] if h["group"] == "maximum"}
    ids = [r["port"] for r in rows]
    if ids != sorted(set(ids)):
        raise Stop("the cache rows are not sorted by port, or a port is there twice")
    if len(rows) != meta["published"]:
        raise Stop(f"the cache has {len(rows)} rows, the meta says {meta['published']}")
    ports = {}
    for r in rows:
        pid = r["port"]
        if pid not in port_ids:
            raise Stop(f"{pid} is not a port asset of ports.geojson")
        if pid in left_out:
            raise Stop(f"{pid} is doubtful or without a match in the meta and is in the cache")
        if r["by"] not in BY:
            raise Stop(f"{pid}: by is {r['by']!r}")
        if bool(r["why"].strip()) != (r["by"] == "review"):
            raise Stop(f"{pid}: a reason is given if and only if the match was reviewed")
        if r["size"] and r["size"] not in SIZES:
            raise Stop(f"{pid}: size {r['size']!r}")
        for k in ("pilot", "tide_res"):
            if r[k] and r[k] not in FLAGS:
                raise Stop(f"{pid}: {k} {r[k]!r}")
        if not any(r[k] for k in LIMITS):
            raise Stop(f"{pid} has no depth and no maximum vessel figure")
        if pid in held and any(r[k] for k in VESSEL):
            raise Stop(f"{pid} is held back for its maximum vessel and the cache holds a figure of it")
        ports[pid] = entry(r)
    head = {"s": meta["source"], "read": month(meta["downloaded"])}
    if meta.get("captured") is not None:
        head["captured"] = day(meta["captured"], "captured")
    return {**head, "edition": meta["edition"], "ports": ports}


def render(doc):
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def port_ids(path=PORTS):
    with open(path, encoding="utf-8") as fh:
        return {f["properties"]["id"] for f in json.load(fh)["features"] if f["properties"].get("type") == "port"}


def main(csv_path=PORTS_CSV, meta_path=META, ports_path=PORTS, out_path=OUT):
    with open(csv_path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    try:
        doc = build(text, meta, port_ids(ports_path))
    except Stop as e:
        print(f"World Port Index: nothing written ({e})", file=sys.stderr)
        return 1
    body = render(doc)
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(body)
    os.replace(tmp, out_path)
    print(f"World Port Index: {len(doc['ports'])} ports, {len(body.encode('utf-8')):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
