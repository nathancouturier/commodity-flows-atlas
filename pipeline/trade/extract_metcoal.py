"""
Metallurgical coal by pair of countries, from the exporters' own statistics (the "Main flows" block of the Metallurgical coal page,
METHODOLOGY.md §1 and §10). Writes the three tracked cache files that pipeline/trade/metcoal.py reads:

    python pipeline/trade/extract_metcoal.py       # needs raw/; with a raw file missing it leaves that source's rows as they are

    pipeline/cache/metcoal_pairs.csv   src,o,d,year,coal_type,kind,tonnes   exporter -> destination, by coal type
    pipeline/cache/metcoal_ports.csv   src,year,d,port,kind,tonnes          Queensland by port; the United States by customs district
    pipeline/cache/metcoal_meta.json   definitions, dates, credit words, file names and hashes, totals by year (the tests read them)

Two sources, never added to each other and never to the customs file (CEPII BACI), whose coal group is all coal:

  qld-coal-sales  Queensland Government, Department of Natural Resources and Mines, Manufacturing and Regional and Rural Development:
                  dataset "Quarterly coal reports", workbook "Quarterly Coal Sales" (coal-sales-data-2010-2026.xlsx), sheets "Export by
                  country and coal type" and "Export by port and coal type". Sales to export by the producers of Queensland, by first
                  destination, in tonnes; the year is the sum of its four quarters, so only complete calendar years are kept. Metallurgical
                  = Hard Coking + Semi-Soft Coking + PCI (the workbook has no such column: the rule is the atlas's; PCI is inside Semi-Soft
                  before 2022, so only the sum is continuous across 2022). Downloaded by hand by the owner (the site refuses scripts).
                  Licence: Creative Commons Attribution 4.0.
  eia-coal        U.S. Energy Information Administration, bulk file COAL.zip (https://www.eia.gov/opendata/bulk/COAL.zip), annual series
                  COAL.EXPORT_QTY.<rank>-<destination>-<customs district>.A, rank MET (metallurgical) and STM (steam coal): the exports
                  of the United States as declared to the Census Bureau (Monthly Report EM 545), in short tons, here times
                  common.constants.TONNES_PER_SHORT_TON. Public domain.

The extractor stops when a name of a destination cannot be put on an ISO3 code of the atlas (the one name left out on purpose is
Queensland's "Unknown"), when the Queensland country sheet and port sheet disagree by a tonne in 2022 to 2025, when the destinations of
EIA do not add to its world row within 0.5% in a year kept, or when a figure the plan quotes (the 2024 totals) is not reproduced.
"""
import csv
import hashlib
import json
import os
import re
import sys
import zipfile
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from common import constants as CN  # noqa: E402

CACHE = os.path.join(ROOT, "pipeline", "cache")
PAIRS_FILE = os.path.join(CACHE, "metcoal_pairs.csv")
PORTS_FILE = os.path.join(CACHE, "metcoal_ports.csv")
META_FILE = os.path.join(CACHE, "metcoal_meta.json")
RAW_QLD = os.path.join(ROOT, "raw", "australia", "queensland-sales", "coal-sales-data-2010-2026.xlsx")
RAW_EIA = os.path.join(ROOT, "raw", "eia", "coal", "COAL.zip")

QLD, EIA = "qld-coal-sales", "eia-coal"
QLD_TYPES = {"Hard Coking Coal": ("hard-coking", "metallurgical"), "Semi-Soft Coking Coal": ("semi-soft", "metallurgical"),
             "PCI": ("pci", "metallurgical"), "Thermal Coal": ("thermal", "thermal")}
EIA_RANKS = {"MET": ("metallurgical", "metallurgical"), "STM": ("steam", "thermal")}
FIRST_YEAR = 2010
EIA_FILE_DATE = "2026-10-01"  # the Last-Modified date of COAL.zip when it was downloaded (the zip itself holds no date): written by hand at each download
EIA_TOLERANCE = 0.005  # destinations against the world row, districts against "all terminals"
# names of the Queensland file that no table of the atlas spells the same way
ALIASES = {"Taiwan": "TWN", "Hong Kong": "HKG", "Turkey": "TUR", "Viet Nam": "VNM", "Russian Federation": "RUS",
           "Korea, Republic of": "KOR", "Rep. of Korea": "KOR", "South Korea (Republic of Korea)": "KOR",
           "Germany, Federal Republic of": "DEU", "Chinese Taipei": "TWN"}

PAIR_HEADER = ["src", "o", "d", "year", "coal_type", "kind", "tonnes"]
PORT_HEADER = ["src", "year", "d", "port", "kind", "tonnes"]


class Names:
    """Country name -> ISO3 of the atlas: data/countries/index.json, pipeline/geo/places_extra.json, the BACI country list kept in the cache, the aliases."""

    def __init__(self):
        self.by_name, self.codes = {}, set()
        for f in ("data/countries/index.json", "pipeline/geo/places_extra.json"):
            for x in json.load(open(os.path.join(ROOT, f), encoding="utf-8")):
                self.by_name.setdefault(x["name"], x["c"])
                self.codes.add(x["c"])
        self.baci = {}
        for r in csv.DictReader(open(os.path.join(CACHE, "baci_country_codes.csv"), encoding="utf-8")):
            self.baci[r["country_name"]] = r["country_iso3"]

    def iso3(self, name):
        n = re.sub(r"\s+", " ", str(name)).strip()
        code = self.by_name.get(n) or ALIASES.get(n) or self.baci.get(n)
        if code not in self.codes:
            raise SystemExit(f"extract_metcoal: the name {name!r} is not a country of the atlas (add it to ALIASES or stop)")
        return code


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# ---------------------------------------------------------------------------------------------------------------- Queensland
def read_queensland(path, names):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    about = [str(c).strip() for r in wb["About"].iter_rows(values_only=True) for c in r if c is not None]
    credit = next(a for a in about if a.startswith("Source:"))
    through = next(a for a in about if a.startswith("Data through to"))
    current = next(a for a in about if a.startswith("Current as at"))
    revised = next(a for a in about if a.startswith("Please note that the data may be revised"))
    disclaimer_full = next(a for a in about if "Derived conclusions and analysis" in a)
    disclaimer = re.search(r"Derived conclusions and analysis[^.]*\.", disclaimer_full).group(0)
    pci_note = next(a for a in about if a.startswith("Prior to 2022, PCI was included"))
    assert "Department of Natural Resources and Mines, Manufacturing and Regional and Rural Development (NRMMRRD)" in credit, credit

    def table(sheet, first):
        rows = list(wb[sheet].iter_rows(values_only=True))
        h = next(i for i, r in enumerate(rows) if r and r[0] == first)
        return rows[h], [r for r in rows[h + 1:] if r and any(v is not None for v in r)]

    hdr, data = table("Export by country and coal type", "Region")
    assert list(hdr[:6]) == ["Region", "Country", "Year", "Quarter", "Coal type", "Total Tonnes"], hdr
    quarters, pair, unknown = defaultdict(set), defaultdict(float), defaultdict(float)
    for _, country, year, q, ctype, t, *_ in data:
        ct, kind = QLD_TYPES[ctype]
        y = int(year)
        quarters[y].add(q)
        if country == "Unknown":
            unknown[(y, kind)] += t
        else:
            pair[(names.iso3(country), y, ct, kind)] += t
    hdr, data = table("Export by port and coal type", "Year")
    assert list(hdr[:5]) == ["Year", "Quarter", "Port", "Coal type", "Total Tonnes"], hdr
    port, pquarters = defaultdict(float), defaultdict(set)
    for year, q, p, ctype, t in (r[:5] for r in data):
        port[(int(year), p, QLD_TYPES[ctype][1])] += t
        pquarters[int(year)].add(q)
    years = [y for y in sorted(quarters) if len(quarters[y]) == 4 and len(pquarters[y]) == 4 and y >= FIRST_YEAR]
    # the sheets agree to the tonne in 2022 to 2025 (the plan's check); the earlier years are reported, not required
    by_kind = defaultdict(float)
    for (iso, y, ct, kind), t in pair.items():
        by_kind[(y, kind)] += t
    for k, t in unknown.items():
        by_kind[k] += t
    pby = defaultdict(float)
    for (y, p, kind), t in port.items():
        pby[(y, kind)] += t
    gap = {}
    for y in years:
        for kind in ("metallurgical", "thermal"):
            gap[f"{y}-{kind}"] = round(by_kind[(y, kind)] - pby[(y, kind)])
            if y >= 2022 and abs(by_kind[(y, kind)] - pby[(y, kind)]) > 1:
                raise SystemExit(f"extract_metcoal: Queensland {y} {kind}: country sheet {by_kind[(y, kind)]:,.0f} t, port sheet {pby[(y, kind)]:,.0f} t")
    pairs = [(QLD, "AUS", iso, y, ct, kind, round(t)) for (iso, y, ct, kind), t in pair.items() if y in years and round(t)]
    ports = [(QLD, y, "", p, kind, round(t)) for (y, p, kind), t in port.items() if y in years and round(t)]
    meta = {
        "id": QLD, "name": "Queensland coal sales to export, by destination and by port",
        "dataset": "Quarterly coal reports, workbook \"Quarterly Coal Sales\" (coal-sales-data-2010-2026.xlsx), sheets \"Export by country and coal type\" and \"Export by port and coal type\"",
        "publisher": "Queensland Government, Department of Natural Resources and Mines, Manufacturing and Regional and Rural Development (NRMMRRD)",
        "address": "https://www.data.qld.gov.au/dataset/quarterly-coal-reports", "licence": "Creative Commons Attribution 4.0 (CC BY 4.0)",
        "exporter": "AUS", "credit": credit, "data_through": through, "current_as_at": current, "revised": revised, "disclaimer": disclaimer, "disclaimer_full": disclaimer_full, "pci_note": pci_note,
        "definition": "Sales to export of hard coking, semi-soft coking and PCI coal by the producers of Queensland, in tonnes, by first destination; the "
                      "calendar year is the sum of its four quarters. Queensland only: New South Wales has no destinations in the file. Before 2022 PCI is "
                      "inside semi-soft coking coal",
        "rule": "metallurgical = hard coking + semi-soft coking + PCI; thermal = thermal coal (the workbook has no such column: the rule is the atlas's)",
        "file": {"name": os.path.basename(path), "bytes": os.path.getsize(path), "sha256": sha256(path)},
        "years": years, "excluded_years": sorted(set(quarters) - set(years)),
        "totals": {f"{y}-{kind}": round(by_kind[(y, kind)]) for y in years for kind in ("metallurgical", "thermal")},
        "unallocated": {f"{y}-{kind}": round(t) for (y, kind), t in sorted(unknown.items()) if y in years and round(t)},
        "port_gap_country_minus_port": gap,
    }
    return pairs, ports, meta


# ---------------------------------------------------------------------------------------------------------------- EIA
def read_eia(path, names):
    f_st = CN.TONNES_PER_SHORT_TON
    dest, world, dist_all, pair_d = defaultdict(float), {}, {}, defaultdict(float)
    dist_names, outside, last_updated, source = {}, defaultdict(float), set(), set()
    pat = re.compile(r"COAL\.EXPORT_QTY\.(MET|STM)-([A-Z0-9]{2,3})-([A-Z0-9_]+)\.A")
    with zipfile.ZipFile(path) as z, z.open("COAL.txt") as fh:
        for line in fh:
            if not line.startswith(b'{"series_id":"COAL.EXPORT_QTY.'):
                continue
            o = json.loads(line)
            m = pat.fullmatch(o["series_id"])
            if not m:
                continue
            rank, cc, dist = m.groups()
            assert o["units"] == "short tons", o["units"]
            nm = o["name"].split(" : ")
            assert len(nm) == 5 and nm[1] in ("metallurgical", "steam coal"), nm
            last_updated.add(o["last_updated"])
            source.add(o["source"])
            if cc == "TOT":
                iso = None
            else:
                iso = o.get("iso3166")
                if not iso:
                    raise SystemExit(f"extract_metcoal: EIA series {o['series_id']} has no iso3166")
                if iso not in names.codes:
                    iso = "~" + nm[2]  # a destination the atlas has no country for (the Netherlands Antilles, a territory)
            for p, v in o["data"]:
                if v is None or int(p) < FIRST_YEAR:
                    continue
                y = int(p)
                if cc == "TOT" and dist == "TOT":
                    world[(rank, y)] = v
                elif cc == "TOT":
                    dist_names[dist] = nm[3]
                    dist_all[(rank, y, dist)] = v
                elif dist == "TOT":
                    dest[(rank, y, iso)] += v
                else:
                    dist_names[dist] = nm[3]
                    pair_d[(rank, y, iso, dist)] += v
    # the years kept: those whose destinations add to the world row and districts to the world row ("all terminals"), for both ranks
    sums, dsums = defaultdict(float), defaultdict(float)
    for (rk, y, iso), v in dest.items():
        sums[(rk, y)] += v
    for (rk, y, d), v in dist_all.items():
        dsums[(rk, y)] += v
    check, years = {}, []
    for y in range(FIRST_YEAR, 2100):
        if ("MET", y) not in world:
            break
        ok = True
        for rk in ("MET", "STM"):
            gd = abs(world[(rk, y)] - sums[(rk, y)]) / world[(rk, y)]
            gt = abs(world[(rk, y)] - dsums[(rk, y)]) / world[(rk, y)]
            check[f"{y}-{rk}"] = {"world_short_tons": world[(rk, y)], "destinations_gap": round(world[(rk, y)] - sums[(rk, y)]),
                                  "districts_gap": round(world[(rk, y)] - dsums[(rk, y)])}
            ok &= gd <= EIA_TOLERANCE and gt <= EIA_TOLERANCE
        if ok:
            years.append(y)
    if years != list(range(years[0], years[-1] + 1)):
        raise SystemExit(f"extract_metcoal: the years of EIA that pass the checks have a hole: {years}")

    def tonnes(st):
        return round(st * f_st)

    pairs = []
    for (rk, y, iso), v in sorted(dest.items()):
        if y not in years:
            continue
        if iso.startswith("~"):
            outside[(y, EIA_RANKS[rk][1], iso[1:])] += tonnes(v)
        elif tonnes(v):
            pairs.append((EIA, "USA", iso, y, EIA_RANKS[rk][0], EIA_RANKS[rk][1], tonnes(v)))
    ports = []
    for (rk, y, d), v in sorted(dist_all.items()):
        if y in years and tonnes(v):
            ports.append((EIA, y, "", dist_names[d], EIA_RANKS[rk][1], tonnes(v)))
    for (rk, y, iso, d), v in sorted(pair_d.items()):
        if y in years and not iso.startswith("~") and tonnes(v):
            ports.append((EIA, y, iso, dist_names[d], EIA_RANKS[rk][1], tonnes(v)))
    totals = {f"{y}-{EIA_RANKS[rk][1]}": {"short_tons": world[(rk, y)], "tonnes": tonnes(world[(rk, y)])} for rk in ("MET", "STM") for y in years}
    meta = {
        "id": EIA, "name": "U.S. coal exports by rank, destination and customs district (EIA bulk file COAL)",
        "dataset": "COAL.zip, annual series COAL.EXPORT_QTY.<rank>-<destination>-<customs district>.A",
        "publisher": "U.S. Energy Information Administration; underlying source: U.S. Census Bureau, Monthly Report EM 545",
        "address": "https://www.eia.gov/opendata/bulk/COAL.zip", "licence": "Public domain (US Government)",
        "exporter": "USA", "credit": "Source: U.S. Energy Information Administration", "source_of_series": sorted(source),
        "file_date": EIA_FILE_DATE, "series_last_updated": sorted(last_updated),
        "definition": "Exports of coal of rank \"metallurgical\" as declared at export, by destination country, in short tons converted to metric tonnes; the file "
                      "does not define the rank. The rank \"steam coal\" is kept apart",
        "tonnes_per_short_ton": f_st,
        "file": {"name": os.path.basename(path), "bytes": os.path.getsize(path), "sha256": sha256(path)},
        "years": years, "totals": totals,
        "outside_atlas": {f"{y}-{kind}": {n: t} for (y, kind, n), t in sorted(outside.items())},
        "checks": check,
    }
    return pairs, ports, meta


# ---------------------------------------------------------------------------------------------------------------- files
def read_cache():
    pairs, ports = [], []
    if os.path.exists(PAIRS_FILE):
        pairs = [(r["src"], r["o"], r["d"], int(r["year"]), r["coal_type"], r["kind"], int(r["tonnes"])) for r in csv.DictReader(open(PAIRS_FILE, encoding="utf-8"))]
    if os.path.exists(PORTS_FILE):
        ports = [(r["src"], int(r["year"]), r["d"], r["port"], r["kind"], int(r["tonnes"])) for r in csv.DictReader(open(PORTS_FILE, encoding="utf-8"))]
    meta = json.load(open(META_FILE, encoding="utf-8")) if os.path.exists(META_FILE) else {}
    return pairs, ports, meta


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


# The 2024 totals the page notes were written for (Queensland: tonnes; EIA: short tons). They are a guard against a changed definition (a coal type
# or a rank that moved in the file), not against a revision: Queensland says that its data may be revised, and EIA that the latest year is
# preliminary. A 2024 total that differs by more than GUARD_TOLERANCE stops the extraction; a smaller difference is printed and written to the
# meta file (key guard_2024), and the extraction goes on.
GUARD_2024 = {QLD: 136985537, EIA: 56586866}
GUARD_UNIT = {QLD: "t", EIA: "short tons"}
GUARD_TOLERANCE = 0.02


def check_2024(pairs, meta):
    """Compare the 2024 totals of the metallurgical coal read with GUARD_2024. Stops beyond GUARD_TOLERANCE, with the message that says what to look at;
    a smaller difference is printed and recorded in meta[src]["guard_2024"]."""
    def tot(src, kind, year=2024):
        return sum(r[6] for r in pairs if r[0] == src and r[3] == year and r[5] == kind)
    for src in (QLD, EIA):
        if src not in meta or 2024 not in meta[src]["years"]:
            continue
        read = tot(QLD, "metallurgical") if src == QLD else meta[EIA]["totals"]["2024-metallurgical"]["short_tons"]
        ref = GUARD_2024[src]
        diff = read / ref - 1
        unit = GUARD_UNIT[src]
        if abs(diff) > GUARD_TOLERANCE:
            raise SystemExit(
                f"extract_metcoal: the 2024 metallurgical total of {src} is {read:,} {unit}, {diff:+.1%} from the {ref:,} {unit} the guard holds (the limit is "
                f"{GUARD_TOLERANCE:.0%}). A revision of the publisher rarely moves a year by that much: look first at what the file counts as metallurgical "
                + ("(the coal types of the sheet 'Export by country and coal type', and where PCI is counted)" if src == QLD else
                   "(the rank codes of the COAL.EXPORT_QTY series, MET and STM, and the unit)")
                + f". If the new figure is right, change GUARD_2024[{src!r}] in pipeline/trade/extract_metcoal.py and say why in docs/UPDATING.md; nothing was written.")
        if read != ref:
            print(f"extract_metcoal: {src}: the 2024 metallurgical total is {read:,} {unit}, {diff:+.2%} from the {ref:,} the guard holds (within {GUARD_TOLERANCE:.0%}: "
                  "a revision of the publisher; written to the meta file)")
        meta[src]["guard_2024"] = {"reference": ref, "read": read, "unit": unit, "difference_pct": round(diff * 100, 3), "tolerance_pct": GUARD_TOLERANCE * 100}
    if EIA in meta and 2024 in meta[EIA]["years"]:
        # the tonnes are the short tons at the file's factor: a rounding of a few tonnes at most
        st = meta[EIA]["totals"]["2024-metallurgical"]["short_tons"]
        if abs(tot(EIA, "metallurgical") - st * meta[EIA]["tonnes_per_short_ton"]) > 100:
            raise SystemExit(f"extract_metcoal: EIA metallurgical 2024 is {st:,} short tons but {tot(EIA, 'metallurgical'):,} t in the pairs: the conversion has changed")


def main():
    pairs, ports, meta = read_cache()
    names = None
    for src, raw, reader in ((QLD, RAW_QLD, read_queensland), (EIA, RAW_EIA, read_eia)):
        if not os.path.exists(raw):
            print(f"extract_metcoal: {os.path.relpath(raw, ROOT)} is not here; the rows of {src} stay as they are")
            continue
        names = names or Names()
        p, q, m = reader(raw, names)
        pairs = [r for r in pairs if r[0] != src] + p
        ports = [r for r in ports if r[0] != src] + q
        meta[src] = m
        print(f"extract_metcoal: {src}: {len(p)} pair rows, {len(q)} port rows, years {m['years'][0]} to {m['years'][-1]}")
    pairs.sort(key=lambda r: (r[0], r[3], r[2], r[4]))
    ports.sort(key=lambda r: (r[0], r[1], r[2], r[3], r[4]))
    check_2024(pairs, meta)
    write_csv(PAIRS_FILE, PAIR_HEADER, pairs)
    write_csv(PORTS_FILE, PORT_HEADER, ports)
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump({k: meta[k] for k in sorted(meta)}, f, indent=1, ensure_ascii=False, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    main()
