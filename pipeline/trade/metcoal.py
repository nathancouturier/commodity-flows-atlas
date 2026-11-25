"""
Reader of the tracked cache of metallurgical coal by pair of countries (pipeline/cache/metcoal_*.csv, metcoal_meta.json), written by
pipeline/trade/extract_metcoal.py. The builders and the tests read this cache only, never raw/: the checks on GitHub and the scheduled
jobs run without it.

    import metcoal
    metcoal.pairs("qld-coal-sales", 2024)            # {"IND": 35418930, ...}: metallurgical tonnes by destination, the coal types added
    metcoal.coal_types("qld-coal-sales", 2024, "IND")  # {"hard-coking": ..., "semi-soft": ..., "pci": ...}
    metcoal.ports("qld-coal-sales", 2024)            # {"Gladstone Port": ...}: Queensland by port of loading, no destination
    metcoal.districts("eia-coal", 2024, "IND")       # {"Norfolk, VA": ...}: the United States by customs district, for one destination
    metcoal.meta("eia-coal")

A year that a source does not hold raises: a new customs year must not be published beside a layer that stops before it.
"""
import csv
import json
import os
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CACHE = os.path.join(ROOT, "pipeline", "cache")
SOURCES = ("qld-coal-sales", "eia-coal")
_DOC = {}


def load():
    if not _DOC:
        with open(os.path.join(CACHE, "metcoal_pairs.csv"), encoding="utf-8") as f:
            _DOC["pairs"] = [(r["src"], r["o"], r["d"], int(r["year"]), r["coal_type"], r["kind"], int(r["tonnes"])) for r in csv.DictReader(f)]
        with open(os.path.join(CACHE, "metcoal_ports.csv"), encoding="utf-8") as f:
            _DOC["ports"] = [(r["src"], int(r["year"]), r["d"], r["port"], r["kind"], int(r["tonnes"])) for r in csv.DictReader(f)]
        with open(os.path.join(CACHE, "metcoal_meta.json"), encoding="utf-8") as f:
            _DOC["meta"] = json.load(f)
    return _DOC


def meta(src):
    return load()["meta"][src]


def require(src, year):
    if year not in meta(src)["years"]:
        raise ValueError(f"metcoal: the cache of {src} holds {meta(src)['years'][0]} to {meta(src)['years'][-1]}, not {year}: "
                         "run pipeline/trade/extract_metcoal.py with the newer file in raw/ before publishing the year")


def pairs(src, year, kind="metallurgical"):
    """{destination ISO3: tonnes} of a source, a year and a kind, summed over the coal types."""
    require(src, year)
    out = defaultdict(int)
    for s, o, d, y, ct, k, t in load()["pairs"]:
        if s == src and y == year and k == kind:
            out[d] += t
    return dict(out)


def coal_types(src, year, d, kind="metallurgical"):
    """{coal type: tonnes} of one destination."""
    require(src, year)
    return {ct: t for s, o, dd, y, ct, k, t in load()["pairs"] if s == src and y == year and dd == d and k == kind}


def ports(src, year, kind="metallurgical"):
    """{port or customs district: tonnes}, all destinations: Queensland by port of loading, the United States by customs district."""
    require(src, year)
    return {p: t for s, y, d, p, k, t in load()["ports"] if s == src and y == year and not d and k == kind}


def districts(src, year, d, kind="metallurgical"):
    """{customs district: tonnes} of the exports to one destination (the United States only)."""
    require(src, year)
    return {p: t for s, y, dd, p, k, t in load()["ports"] if s == src and y == year and dd == d and k == kind}


def exporter(src):
    return meta(src)["exporter"]
