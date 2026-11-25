"""Builds data/coverage.json: which blocks each commodity page has, and why a block it lacks is missing.

One row per page of data/commodities/index.json, one cell per block. A cell is
  p            the page has the block (the rules are the table BLOCKS below, read from the files of data/)
  m            the block is missing: the work list
  na:<id>      not applicable, for the reason <id> of coverage_reasons.json (the nature of the commodity)
  nf:<id>      not available for free, for the reason <id> (a publisher's page was read, and the alternatives)
A block that a page cannot have by family (monthly series outside energy, the crop balance outside the softs) is no
cell of that page: it is not drawn and not counted.

Reads only tracked files (data/, coverage_reasons.json, coverage_floor.json, release.json), never raw/, so it runs on
GitHub. The same files give the same bytes: the file carries the release number of release.json and no time of day.
In a scheduled run the data win: a typed reason on a block that is present is not an error, the cell is written as
present and a warning says that the reason is stale.

  python pipeline/commodities/build_coverage.py                 build and write data/coverage.json
  python pipeline/commodities/build_coverage.py --raise-floor   add the blocks present now to coverage_floor.json
  python pipeline/commodities/build_coverage.py --summary       print the matrix and the work list, write nothing
"""
import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REASONS_FILE = os.path.join("pipeline", "commodities", "coverage_reasons.json")
FLOOR_FILE = os.path.join("pipeline", "commodities", "coverage_floor.json")
OUT_FILE = os.path.join("data", "coverage.json")
VERSION = 1

# id, label, the families whose pages can have the block (None: every page), what makes a cell present
BLOCKS = [
    ("production", "Production", None, "A production table with at least one row."),
    ("reserves", "Reserves", None, "A reserves table with at least one row."),
    ("consumption", "Consumption", None, "A consumption table with at least one row."),
    ("trade", "Trade", None, "An exports table and an imports table, each with at least one row."),
    ("lanes", "Lanes", None, "At least one sea lane."),
    ("routes", "Routes", None,
     "At least one route that carries the commodity. It counts the Atlas corridors generated from customs pairs "
     "as well as the benchmark routes and the routes written by hand."),
    ("price", "Price", None, "At least one price series."),
    ("assets", "Assets", None, "At least one infrastructure asset."),
    ("companies", "Companies", None, "At least one company entry."),
    ("monthly", "Monthly", ["energy"], "A monthly series."),
    ("balance", "Balance", ["softs"], "A balance of stocks and use, with at least one row."),
]
BLOCK_IDS = [b[0] for b in BLOCKS]
STATES = {"na": "na", "nofree": "nf"}  # status of a reason -> prefix of the cell
ID = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


class CoverageError(Exception):
    """The inputs are wrong (a page or block that does not exist, two reasons for one cell, a missing file)."""


def read_json(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise CoverageError(f"{rel}: {e}") from e


def rows(table):
    return len(table.get("rows") or []) if isinstance(table, dict) else 0


def applicable(block, family):
    families = block[2]
    return families is None or family in families


# ---------------------------------------------------------------- what each page has (from the files of data/)

def read_presence(root=ROOT):
    """(pages of index.json, {page: {block: bool}} for the blocks the page can have)."""
    pages = read_json(root, "data/commodities/index.json")
    ids = {p["id"] for p in pages}

    lanes = set()
    for path in glob.glob(os.path.join(root, "data", "freight", "lanes", "*.json")):
        f = read_json(root, os.path.relpath(path, root))
        if f.get("lanes"):
            lanes.add(f["k"])

    routes = set()
    for r in read_json(root, "data/freight/routes.json"):
        routes.update(r.get("cargoes") or [])

    prices = {m["k"] for m in read_json(root, "data/prices/index.json") if not m.get("hidden")}

    assets = set()
    for path in glob.glob(os.path.join(root, "data", "infrastructure", "*.geojson")):
        for feat in read_json(root, os.path.relpath(path, root))["features"]:
            assets.update(feat["properties"].get("k") or [])

    companies = {k for k, roles in read_json(root, "data/commodities/companies.json").items()
                 if any(roles.values())}

    monthly = set()
    for path in glob.glob(os.path.join(root, "data", "commodities", "monthly", "*.json")):
        m = read_json(root, os.path.relpath(path, root))
        # a file that holds only a statement of what is missing (LNG: "gaps") has no series
        if any(v for k, v in m.items() if k not in ("id", "s", "gaps")):
            monthly.add(os.path.basename(path)[:-5])

    presence = {}
    for page in pages:
        pid = page["id"]
        d = read_json(root, f"data/commodities/{pid}.json")
        extra = {x["key"]: x["table"] for x in d.get("extra") or []}

        def has(plain, with_extra):
            if any(rows(d.get(k)) for k in plain):
                return True
            return any(rows(t) for key, t in extra.items() if with_extra(key))

        have = {
            "production": has(("production", "refinery"),
                              lambda k: k.endswith("-production") and not k.startswith("eu-")),
            "reserves": has(("reserves",), lambda k: k.endswith("-reserves")),
            "consumption": has(("consumption",), lambda k: k.endswith("-consumption")),
            "trade": rows(d.get("exports")) > 0 and rows(d.get("imports")) > 0,
            "lanes": pid in lanes,
            "routes": pid in routes,
            "price": pid in prices,
            "assets": pid in assets,
            "companies": pid in companies,
            "monthly": pid in monthly,
            "balance": rows(d.get("balance")) > 0,
        }
        presence[pid] = {b[0]: have[b[0]] for b in BLOCKS if applicable(b, page["family"])}
    # a price series may belong to a product that has no page (coconut oil, freight indices): not an error there
    unknown = (lanes | routes | assets | companies | monthly) - ids
    return pages, presence, unknown


# ---------------------------------------------------------------- the reasons table

def check_table(table, pages, presence=None):
    """Hard errors of a hand-typed table: the structure, never the data. Returns {(page, block): entry}."""
    if not isinstance(table, dict) or table.get("version") != VERSION or not isinstance(table.get("entries"), list):
        raise CoverageError(f"{REASONS_FILE}: expected {{\"version\": {VERSION}, \"entries\": [...]}}")
    family = {p["id"]: p["family"] for p in pages}
    block = {b[0]: b for b in BLOCKS}
    seen, cell = set(), {}
    for e in table["entries"]:
        where = f"{REASONS_FILE}, entry {e.get('id')!r}"
        extra = set(e) - {"id", "blocks", "pages", "status", "reason", "evidence"}
        if extra:
            raise CoverageError(f"{where}: unknown key {sorted(extra)}")
        if not isinstance(e.get("id"), str) or not ID.fullmatch(e["id"]) or e["id"] in seen:
            raise CoverageError(f"{where}: the id must be a new lower-case word with hyphens")
        seen.add(e["id"])
        if e.get("status") not in STATES:
            raise CoverageError(f"{where}: status is 'na' or 'nofree'; a missing block is never typed")
        if not isinstance(e.get("reason"), str) or not 20 <= len(e["reason"]) <= 200 or e["reason"] != e["reason"].strip():
            raise CoverageError(f"{where}: the reason is one sentence of 20 to 200 characters")
        if re.search(r"no free (file|source) (is )?loaded|not loaded|not read", e["reason"], re.I):
            raise CoverageError(f"{where}: 'not loaded by the atlas' is a missing block, not a reason")
        check_evidence(e, where)
        if not e.get("blocks") or not e.get("pages"):
            raise CoverageError(f"{where}: needs blocks and pages")
        for b in e["blocks"]:
            if b not in block:
                raise CoverageError(f"{where}: no block {b!r}")
            for p in e["pages"]:
                if p not in family:
                    raise CoverageError(f"{where}: no page {p!r}")
                if not applicable(block[b], family[p]):
                    raise CoverageError(f"{where}: {p} cannot have the block {b} (it is not a cell of that page)")
                if (p, b) in cell:
                    raise CoverageError(f"{where}: {p}/{b} already has the reason {cell[(p, b)]['id']!r}")
                cell[(p, b)] = e
    return cell


def check_evidence(e, where):
    ev = e.get("evidence")
    if e["status"] == "na":
        ok = isinstance(ev, list) and ev and all(
            isinstance(x, dict) and set(x) == {"file", "text"} and all(isinstance(v, str) and v for v in x.values())
            for x in ev)
        if not ok:
            raise CoverageError(f"{where}: a not-applicable reason needs evidence: a list of {{file, text}} "
                                "naming where the repository says what the reason says")
    else:
        ok = (isinstance(ev, dict) and set(ev) == {"page", "month", "alternatives"}
              and isinstance(ev["page"], str) and ev["page"].startswith("https://")
              and isinstance(ev["month"], str) and MONTH.fullmatch(ev["month"])
              and isinstance(ev["alternatives"], list) and ev["alternatives"]
              and all(isinstance(a, dict) and set(a) == {"what", "why"} and all(isinstance(v, str) and v for v in a.values())
                      for a in ev["alternatives"]))
        if not ok:
            raise CoverageError(f"{where}: a not-available-for-free reason needs evidence: the address of the "
                                "publisher's page, the month it was read, and the alternatives looked at, each with "
                                "why it fails")


# ---------------------------------------------------------------- the build

def seaborne_mt(root, page, kind_files):
    """Seaborne tonnes of a page in Mt: summary.seaborne of the page, else the latest year of its lane files, else 0."""
    d = read_json(root, f"data/commodities/{page}.json")
    s = (d.get("summary") or {}).get("seaborne")
    factor = {"Mt": 1.0, "kt": 0.001}
    if s and s.get("u") in factor and isinstance(s.get("v"), (int, float)):
        return s["v"] * factor[s["u"]]
    total = 0.0
    for f in kind_files.get(page, []):
        series = f.get("seaborne") or []
        if series and f.get("unit") in factor:
            total += series[-1] * factor[f["unit"]]
    return total


def lane_files_by_page(root):
    out = {}
    for path in sorted(glob.glob(os.path.join(root, "data", "freight", "lanes", "*.json"))):
        f = read_json(root, os.path.relpath(path, root))
        out.setdefault(f["k"], []).append(f)
    return out


def build(root=ROOT, warnings=None, table=None):
    """The document of data/coverage.json, in memory. Warnings (stale reasons, a page below its floor) are appended.
    `table` replaces the reasons file (the tests)."""
    warnings = [] if warnings is None else warnings
    pages, presence, unknown = read_presence(root)
    if unknown:
        raise CoverageError(f"a lane, route, asset, company or monthly file names pages that are not in "
                            f"commodities/index.json: {sorted(unknown)}")
    release = read_json(root, "release.json").get("release")
    if not isinstance(release, int) or isinstance(release, bool):
        raise CoverageError("release.json has no integer 'release'")
    table = read_json(root, REASONS_FILE) if table is None else table
    typed = check_table(table, pages)

    out_pages, work = [], []
    for page in pages:
        cells, missing = {}, []
        for b in BLOCKS:
            if not applicable(b, page["family"]):
                continue
            pid, bid = page["id"], b[0]
            e = typed.get((pid, bid))
            if presence[pid][bid]:
                cells[bid] = "p"
                if e:
                    warnings.append(f"stale reason: {pid}/{bid} is present now, the reason {e['id']!r} is not used "
                                    f"(remove it from {REASONS_FILE})")
            elif e:
                cells[bid] = f"{STATES[e['status']]}:{e['id']}"
            else:
                cells[bid] = "m"
                missing.append(bid)
        out_pages.append({"id": page["id"], "cells": cells})
        if missing:
            work.append((page, missing))

    files = lane_files_by_page(root)
    tonnes = {page["id"]: seaborne_mt(root, page["id"], files) for page, _ in work}
    work.sort(key=lambda w: (-tonnes[w[0]["id"]], w[0].get("rank", 0)))

    doc = {
        "version": VERSION,
        "release": release,
        "blocks": [{"id": i, "label": l, "text": t, **({"families": f} if f else {})} for i, l, f, t in BLOCKS],
        "reasons": {e["id"]: {"st": e["status"], "t": e["reason"]} for e in table["entries"]},
        "pages": out_pages,
        "work": {page["id"]: missing for page, missing in work},
    }
    for pid, bid in below_floor(doc, read_floor(root)):
        warnings.append(f"page {pid} lost block {bid}: it is in {FLOOR_FILE}")
    return doc


def below_floor(doc, floor):
    """[(page, block)] the floor lists that the document does not show as present."""
    cells = {p["id"]: p["cells"] for p in doc["pages"]}
    return [(pid, bid) for pid, blocks in floor.items() for bid in blocks if cells.get(pid, {}).get(bid) != "p"]


def render(doc):
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def read_floor(root=ROOT):
    path = os.path.join(root, FLOOR_FILE)
    if not os.path.exists(path):
        return {}
    f = read_json(root, FLOOR_FILE)
    if f.get("version") != VERSION or not isinstance(f.get("present"), dict):
        raise CoverageError(f"{FLOOR_FILE}: expected {{\"version\": {VERSION}, \"present\": {{page: [blocks]}}}}")
    return f["present"]


def render_floor(present):
    """One line a page: the file stays short and a change to one page is one changed line."""
    lines = ",\n".join(f'  "{pid}": {json.dumps(blocks)}' for pid, blocks in present.items())
    return '{\n "version": %d,\n "present": {\n%s\n }\n}\n' % (VERSION, lines)


def raised(floor, doc):
    """The floor and the blocks present in the document, together: it only ever grows."""
    out = {}
    for page in doc["pages"]:
        have = {b for b, c in page["cells"].items() if c == "p"} | set(floor.get(page["id"], []))
        if have:
            out[page["id"]] = [b for b in BLOCK_IDS if b in have]
    return out


def raise_floor(root=ROOT):
    doc = build(root, [])
    floor = read_floor(root)
    for pid in floor:
        if pid not in {p["id"] for p in doc["pages"]}:
            raise CoverageError(f"{FLOOR_FILE} names {pid}, which is not a page: lower the floor by hand")
    out = raised(floor, doc)
    with open(os.path.join(root, FLOOR_FILE), "w", encoding="utf-8", newline="\n") as f:
        f.write(render_floor(out))
    return out


def summary(doc):
    """{'pages', 'cells', 'present', 'na', 'nofree', 'missing', 'by_block': {block: [p, na, nf, m]}}"""
    count = {"p": 0, "na": 0, "nf": 0, "m": 0}
    by_block = {b: dict(count) for b in BLOCK_IDS}
    for page in doc["pages"]:
        for b, c in page["cells"].items():
            key = c.split(":")[0]
            count[key] += 1
            by_block[b][key] += 1
    return {"pages": len(doc["pages"]), "cells": sum(count.values()), "present": count["p"], "na": count["na"],
            "nofree": count["nf"], "missing": count["m"], "by_block": by_block}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--raise-floor", action="store_true", help="add the blocks present now to the floor file")
    ap.add_argument("--summary", action="store_true", help="print the matrix and the work list, write nothing")
    args = ap.parse_args(argv)
    try:
        if args.raise_floor:
            floor = raise_floor()
            print(f"floor: {sum(len(v) for v in floor.values())} present blocks on {len(floor)} pages")
            return 0
        warnings = []
        doc = build(ROOT, warnings)
    except CoverageError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    s = summary(doc)
    line = (f"{s['pages']} pages, {s['cells']} cells: {s['present']} present, {s['na']} not applicable, "
            f"{s['nofree']} not available for free, {s['missing']} missing")
    if args.summary:
        print(line)
        for b, c in s["by_block"].items():
            print(f"  {b:12s} present {c['p']:2d}  na {c['na']:2d}  nofree {c['nf']:2d}  missing {c['m']:2d}")
        for pid, missing in doc["work"].items():
            print(f"  {pid}: {', '.join(missing)}")
        return 0
    with open(os.path.join(ROOT, OUT_FILE), "w", encoding="utf-8", newline="\n") as f:
        f.write(render(doc))
    print(f"data/coverage.json: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
