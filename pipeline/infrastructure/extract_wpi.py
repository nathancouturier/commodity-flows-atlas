"""
The World Port Index (Publication 150 of the US National Geospatial-Intelligence Agency) as a source of the port panel: the rows that match a
port of the atlas, with the columns the site prints. Writes the two tracked cache files that the builder of the data file reads:

    .venv/bin/python -I pipeline/infrastructure/extract_wpi.py            # needs raw/nga/UpdatedPub150.csv; without it the cache is left as it is
    .venv/bin/python -I pipeline/infrastructure/extract_wpi.py --accept   # also accepts a change that a guard below stopped

    pipeline/cache/wpi_ports.csv    one row per port with a sure match, the columns the site prints (HEADER), sorted by port
    pipeline/cache/wpi_meta.json    the file read (name, hash, rows), the rule and its numbers, the counts, the doubtful and absent matches
                                    with their reasons, the ports whose maximum vessel is held back, the terms found and where

The file is downloaded by a person from the publisher's page, never by a script: this program downloads nothing and its readers name no
other path under raw/ than the one file. The file holds neither an edition nor a date, so the two are typed here (EDITION, DOWNLOADED).

Matching an atlas port to a row of the file (the numbers are constants below and are written to the meta file):
  sure by code   the atlas UN/LOCODE is carried by exactly one row of the file, the code's two letters and the row's country are the port's
                 country, the row lies within CODE_KM of the atlas point, and its names share a form with the atlas name or it lies within
                 NAMELESS_KM;
  sure by name   no row carries the code, and exactly one row of the same country has a main or alternate name equal to the atlas name,
                 within NAME_KM;
  in both cases the match is sure only if no other row of the same country lies nearer to the atlas point than the matched row by more
  than NEARER_MARGIN_KM (a port with several entries, a city harbour and its terminals, would otherwise get the figures of the wrong one);
  doubtful       a code several rows share, a code row too far or of another country, a name several rows carry, a name between NAME_KM and
                 NAME_FAR_KM, a nearer row, or a row within NAMELESS_KM with no code or name in common. Never published;
  none           no candidate.
REVIEW is a short table written by a person who opened the two rows: it promotes a doubtful match with a reason that can be checked, or holds
a sure one. A promoted row is stored with `by` review and its reason; a held one is doubtful.

The maximum vessel figures of a port are held back (meta.held_vessel) when they are not plausible as a ship: a beam above BEAM_MAX_RATIO of the
length or above BEAM_MAX_M, or a beam with no length to compare it with. It is a check on the publication's figures, not an estimate.

Guards (nothing is written, the exit status is not 0, the message says why): a column of COLUMNS missing from the header; a value that is not a
number or is negative, a position outside the globe, a class the site does not know; a row of REVIEW that the file no longer has; a published row
whose country is not the port's. And, unless --accept: fewer rows than ROWS_MIN of the last file read; fewer published ports than the last
cache by more than PUBLISHED_DROP; more than CHANGED_SHARE of the published ports with a figure that moved by more than CHANGED_BY.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import sys
import unicodedata

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RAW = os.path.join(ROOT, "raw", "nga", "UpdatedPub150.csv")
CACHE = os.path.join(ROOT, "pipeline", "cache")
PORTS_CSV = os.path.join(CACHE, "wpi_ports.csv")
META = os.path.join(CACHE, "wpi_meta.json")
PORTS_GEOJSON = os.path.join(ROOT, "data", "infrastructure", "ports.geojson")
COUNTRIES = os.path.join(ROOT, "data", "countries", "index.json")

SOURCE = "nga-wpi"
DOWNLOADED = "2026-11-24"  # the day the owner downloaded the file by hand; the file's modification time agrees; the file holds no date
EDITION = None  # the edition as the publisher's page states it, typed at the download; None until read
EDITION_PAGE = None  # the address of the page that states it
# What was read about the terms, by someone. A sentence on the 26th edition of 2017, not on the CSV used here, whose edition is not stated.
TERMS_QUOTE = "© COPYRIGHT 2017 BY THE UNITED STATES GOVERNMENT / NO COPYRIGHT CLAIMED UNDER TITLE 17 U.S.C."
TERMS_PAGE = "https://web.archive.org/web/20170829062601if_/http://msi.nga.mil/MSISiteContent/StaticFiles/NAV_PUBS/WPI/Pub150bk.pdf"
TERMS_READ_ON = "2026-11-25"
TERMS_SCOPE = "2017 PDF, 26th edition"

# The matching rule. CODE_KM: the farthest a row found by its code may lie from the atlas point. Chosen from the distances the data show: the
# farthest code match kept and the nearest one refused are in meta.rule_basis (a wide radius admitted the city harbour of Rotterdam, two terminal
# rows nearer to the point; the nearer-row guard, not the radius, settles the other doubtful cases).
CODE_KM = 15.0
NAME_KM = 15.0
NAMELESS_KM = 10.0
NAME_FAR_KM = 40.0
NEARER_MARGIN_KM = 2.0
STOP_WORDS = ["port", "of", "de", "do", "da", "terminal", "terminals", "oil", "marine", "offshore", "term", "harbour", "harbor", "ko", "gang", "hang",
              "city", "the"]
BEAM_MAX_RATIO = 0.4
BEAM_MAX_M = 70.0
# guards on a new file
ROWS_MIN = 0.95
PUBLISHED_DROP = 5
CHANGED_SHARE = 0.20
CHANGED_BY = 0.25

RULE = {"code_km": CODE_KM, "name_km": NAME_KM, "nameless_km": NAMELESS_KM, "name_far_km": NAME_FAR_KM, "nearer_margin_km": NEARER_MARGIN_KM,
        "stop_words": STOP_WORDS, "beam_max_ratio": BEAM_MAX_RATIO, "beam_max_m": BEAM_MAX_M}

# file column -> (key of the cache, kind). Number: metres, a 0 or a blank is "not stated". Class and flag: as listed, "Unknown" and blank are left out.
NUMBERS = {
    "Tidal Range (m)": "tide", "Channel Depth (m)": "chan", "Anchorage Depth (m)": "anch", "Cargo Pier Depth (m)": "pier",
    "Oil Terminal Depth (m)": "oil", "Liquified Natural Gas Terminal Depth (m)": "lng",
    "Maximum Vessel Length (m)": "loa", "Maximum Vessel Beam (m)": "beam", "Maximum Vessel Draft (m)": "draft",
    "Offshore Maximum Vessel Length (m)": "oloa", "Offshore Maximum Vessel Beam (m)": "obeam", "Offshore Maximum Vessel Draft (m)": "odraft",
}
CLASSES = {"Harbor Size": ("size", ("Very Small", "Small", "Medium", "Large")), "Harbor Type": ("type", None)}
FLAGS = {"Pilotage - Compulsory": "pilot", "Entrance Restriction - Tide": "tide_res"}
MATCH_COLUMNS = ["World Port Index Number", "Main Port Name", "Alternate Port Name", "UN/LOCODE", "Country Code", "Latitude", "Longitude"]
COLUMNS = MATCH_COLUMNS + list(NUMBERS) + list(CLASSES) + list(FLAGS)
HEADER = ["port", "wpi", "name", "code", "by", "km", "size", "type", "tide", "chan", "anch", "pier", "oil", "lng", "loa", "beam", "draft", "oloa", "obeam",
          "odraft", "pilot", "tide_res", "why"]
FIGURES = ["tide", "chan", "anch", "pier", "oil", "lng", "loa", "beam", "draft", "oloa", "obeam", "odraft"]
# what the panel counts as a limit: a depth or a maximum vessel figure
LIMITS = ["chan", "anch", "pier", "oil", "lng", "loa", "beam", "draft", "oloa", "obeam", "odraft"]

# Promotions and holds, written after opening the two rows: the atlas port's record in data/infrastructure/ports.geojson (its name, its note, the page
# it cites) and the row of the file (number, name, alternate names, position). A row is named by its number and its main name, because numbers repeat
# in the file. A promotion carries `evidence`, a sentence about the names and the other rows nearby; the positions of the two points are added from the
# data. Whoever edits this table opens both rows again; a promotion that cannot be checked stays out, and a doubtful match stays doubtful.
REVIEW = {
    "fujairah": {"action": "promote", "wpi": 48262, "name": "Al Fujayrah",
                 "evidence": "The names are two spellings of Fujairah (the row's alternate name is Fujayrah Harbor) and the next row of the country, Khawr Fakkan, "
                             "is another port; the page the atlas cites is about the Fujairah oil terminal and the entry is the harbour."},
    "basrah-oil-terminal": {"action": "promote", "wpi": 48392, "name": "Al-Basra Oil Terminal",
                            "evidence": "The row's main name is the atlas port's name in another spelling (its alternate name is Mina Al Bakr Terminal); the next row "
                                        "of the country, Khawr Al Amaya, is a separate terminal."},
    "pivdennyi": {"action": "promote", "wpi": 43655, "name": "Yuzhnyy",
                  "evidence": "Yuzhnyy is the Russian spelling of the Ukrainian Pivdennyi (the atlas note gives the PortWatch code UAYUZ for the port); the next "
                              "row of the country, Odesa, is another port."},
    "ruwais": {"action": "promote", "wpi": 48282, "name": "Jabal Az Zannah/ruways",
               "evidence": "The atlas note says the PortWatch database lists the port as Jabal Az Zannah-Ruways, and the row carries the same two names "
                           "(alternate name Jabal Dhanna/ruways); the next row of the country, Mubarraz Oil Terminal, is another port."},
    "loop": {"action": "promote", "wpi": 8980, "name": "Loop Terminal",
             "evidence": "The atlas port is the Louisiana Offshore Oil Port (LOOP) and the row is Loop Terminal; the next row of the country, Grand Isle, "
                         "is another place."},
    "los-angeles-long-beach": {"action": "hold", "why": "the file has one row for each of the two harbours, Los Angeles and Long Beach, with different channel "
                                                        "depths; a single entry would show the figures of one of them for a port that counts both"},
    "rosario-up-river": {"action": "hold", "why": "the atlas port is the up-river hub of several terminals (its note) and the row is the port of the city of Rosario"},
}


class Stop(Exception):
    """A guard: nothing is written."""


def hav(lat1, lon1, lat2, lon2):
    r, p = 6371.0088, math.pi / 180
    x = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\b(" + "|".join(STOP_WORDS) + r")\b", " ", s)
    return " ".join(s.split())


def atlas_heads(name):
    """The forms of an atlas name: without its bracket, each side of " / "."""
    base = re.sub(r"\s*\(.*?\)", "", name)
    return {n for n in (norm(x) for x in re.split(r"\s*/\s*", base)) if n}


def fmt(x):
    """A figure as the cache writes it: 14.0 -> 14, 4.9 -> 4.9."""
    s = repr(float(x))
    return s[:-2] if s.endswith(".0") else s


# ------------------------------------------------------------------------------------------------------------------------------ reading
def number(cell, column, row_no):
    t = (cell or "").strip()
    if t == "":
        return 0.0
    try:
        v = float(t)
    except ValueError:
        raise Stop(f"row {row_no}: {column!r} holds {cell!r}, which is not a number")
    if math.isnan(v) or math.isinf(v) or v < 0:
        raise Stop(f"row {row_no}: {column!r} holds {cell!r}")
    return v


def read_rows(text):
    """The rows of the file as dicts of what is read. Stops on a missing column or a value the rules do not know."""
    rd = csv.DictReader(io.StringIO(text))
    missing = [c for c in COLUMNS if c not in (rd.fieldnames or [])]
    if missing:
        raise Stop("the file has changed shape: column(s) missing from the header: " + ", ".join(missing))
    out = []
    for i, r in enumerate(rd, start=2):
        w = {"row": i, "n": None, "name": re.sub(r"\s+", " ", r["Main Port Name"]).strip(),
             "alt": [re.sub(r"\s+", " ", a).strip() for a in r["Alternate Port Name"].split(";") if a.strip()],
             "code": re.sub(r"\s+", "", r["UN/LOCODE"]), "country": re.sub(r"\s+", " ", r["Country Code"]).strip()}
        try:
            w["n"] = int(float(r["World Port Index Number"]))
        except ValueError:
            raise Stop(f"row {i}: 'World Port Index Number' holds {r['World Port Index Number']!r}")
        w["lat"], w["lon"] = signed(r["Latitude"], "Latitude", i), signed(r["Longitude"], "Longitude", i)
        if abs(w["lat"]) > 90 or abs(w["lon"]) > 180:
            raise Stop(f"row {i}: the position {w['lat']}, {w['lon']} is not on the globe")
        for col, key in NUMBERS.items():
            w[key] = number(r[col], col, i)
        for col, (key, allowed) in CLASSES.items():
            v = re.sub(r"\s+", " ", r[col]).strip()
            if allowed is not None and v and v not in allowed:
                raise Stop(f"row {i}: {col!r} holds {v!r}, a class the atlas does not know")
            w[key] = v
        for col, key in FLAGS.items():
            v = r[col].strip()
            if v not in ("Yes", "No", "Unknown"):
                raise Stop(f"row {i}: {col!r} holds {v!r}, not Yes, No or Unknown")
            w[key] = v if v in ("Yes", "No") else ""
        out.append(w)
    return out


def signed(cell, column, row_no):
    try:
        v = float(cell)
    except ValueError:
        raise Stop(f"row {row_no}: {column!r} holds {cell!r}, which is not a number")
    if math.isnan(v) or math.isinf(v):
        raise Stop(f"row {row_no}: {column!r} holds {cell!r}")
    return v


class Countries:
    """Country of a row of the file: its country name (the column is called Country Code but holds a name), else the letters of its UN/LOCODE."""

    def __init__(self, countries):
        self.by_name = {c["name"]: c["c"] for c in countries}
        self.by_a2 = {c["a2"]: c["c"] for c in countries if c.get("a2")}

    def of_row(self, w):
        return self.by_name.get(w["country"]) or (self.by_a2.get(w["code"][:2]) if w["code"] else None)

    def of_code(self, code):
        return self.by_a2.get(code[:2])


# ------------------------------------------------------------------------------------------------------------------------------ matching
def row_names(w):
    s = {norm(w["name"])} | {norm(a) for a in w["alt"]}
    s.discard("")
    return s


def match(ports, rows, countries):
    """One record per atlas port: grade sure | doubtful | none, with the row, the way, the distance and the reasons."""
    by_code = {}
    for w in rows:
        if w["code"]:
            by_code.setdefault(w["code"], []).append(w)
    for w in rows:
        w["cty"] = countries.of_row(w)
        w["names"] = row_names(w)
    out = []
    for p in ports:
        code, heads = p.get("locode") or "", atlas_heads(p["name"])
        for w in rows:
            w["d"] = hav(p["lat"], p["lon"], w["lat"], w["lon"])
        rec = {"id": p["id"], "c": p["c"], "lat": p["lat"], "lon": p["lon"], "grade": "none", "reasons": []}
        coded = by_code.get(code, []) if code else []
        named = [w for w in rows if w["cty"] == p["c"] and heads & w["names"] and w["d"] <= NAME_KM]
        sure = None
        if len(coded) == 1:
            w = coded[0]
            if (countries.of_code(code) == p["c"] and w["cty"] == p["c"] and w["d"] <= CODE_KM and (heads & w["names"] or w["d"] <= NAMELESS_KM)):
                sure = (w, "code")
        elif not coded and len(named) == 1:
            sure = (named[0], "name")
        if sure:
            w, by = sure
            nearer = sorted((x for x in rows if x is not w and x["cty"] == p["c"] and x["d"] < w["d"] - NEARER_MARGIN_KM), key=lambda x: x["d"])
            if nearer:
                x = nearer[0]
                rec.update(grade="doubtful", row=w, d=w["d"])
                rec["reasons"].append(f"another row of the country is nearer to the atlas point: no. {x['n']} {x['name']}, {x['d']:.1f} km, against "
                                      f"{w['d']:.1f} km for no. {w['n']} {w['name']}" + (f" ({len(nearer)} rows nearer)" if len(nearer) > 1 else ""))
            else:
                rec.update(grade="sure", by=by, row=w, d=w["d"])
        else:
            cand = sorted(coded, key=lambda w: w["d"]) or sorted(named, key=lambda w: w["d"])
            if cand:
                w = cand[0]
                rec.update(grade="doubtful", row=w, d=w["d"])
                r = rec["reasons"]
                if len(coded) > 1:
                    r.append(f"{len(coded)} rows of the file share the code {code}")
                if coded and len(coded) == 1:
                    if countries.of_code(code) != p["c"] or w["cty"] != p["c"]:
                        r.append("the code is another country's")
                    elif w["d"] > CODE_KM and heads & w["names"]:
                        rec["far_code"] = True  # only the distance refuses it
                    if w["d"] > CODE_KM:
                        r.append(f"the row lies {w['d']:.1f} km from the atlas point")
                    elif not (heads & w["names"]) and w["d"] > NAMELESS_KM:
                        r.append(f"the names differ and the row lies {w['d']:.1f} km from the atlas point")
                if not coded and len(named) > 1:
                    r.append(f"{len(named)} rows of the country carry the name within {NAME_KM:g} km")
            else:
                near = sorted((w for w in rows if w["cty"] == p["c"] and ((heads & w["names"] and w["d"] <= NAME_FAR_KM) or w["d"] <= NAMELESS_KM)),
                              key=lambda w: w["d"])
                if near:
                    w = near[0]
                    rec.update(grade="doubtful", row=w, d=w["d"])
                    rec["reasons"].append(f"the name is found {w['d']:.1f} km from the atlas point" if heads & w["names"]
                                          else f"position only: no code or name in common ({len(near)} row(s) within {NAMELESS_KM:g} km)")
                else:
                    rec["reasons"].append("no row of the file by code, by name or by position")
        out.append(rec)
    return out


def where(lat, lon):
    return f"{abs(lat):.2f} {'N' if lat >= 0 else 'S'}, {abs(lon):.2f} {'E' if lon >= 0 else 'W'}"


def apply_review(matches, rows, review):
    """Promote or hold by the review table. A row of the table that the file no longer has stops the run."""
    by_id = {m["id"]: m for m in matches}
    for pid, e in review.items():
        if pid not in by_id:
            raise Stop(f"the review table names {pid!r}, which is not a port of the atlas")
        m = by_id[pid]
        if e["action"] == "promote":
            w = next((x for x in rows if x["n"] == e["wpi"] and x["name"] == e["name"]), None)
            if w is None:
                raise Stop(f"the review table promotes {pid!r} to no. {e['wpi']} {e['name']!r}, which the file no longer has")
            if m["grade"] == "sure":
                continue  # the rule has found it since: the entry is no longer needed
            if not e.get("evidence", "").strip():
                raise Stop(f"the review table promotes {pid!r} without a reason")
            d = hav(m["lat"], m["lon"], w["lat"], w["lon"])
            if any(x is not w and x["cty"] == m["c"] and hav(m["lat"], m["lon"], x["lat"], x["lon"]) < d - NEARER_MARGIN_KM for x in rows):
                raise Stop(f"the review table promotes {pid!r} to a row with another row of the country nearer to the atlas point")
            why = f"Atlas point {where(m['lat'], m['lon'])}, row no. {w['n']} {w['name']} at {where(w['lat'], w['lon'])}. {e['evidence']}"
            m.update(grade="sure", by="review", row=w, d=d, why=why, reasons=[])
        elif e["action"] == "hold":
            if m["grade"] == "sure":
                m.update(grade="doubtful", reasons=[e["why"]], held=True)
        else:
            raise Stop(f"the review table has the action {e['action']!r} for {pid!r}")
    return matches


# ------------------------------------------------------------------------------------------------------------------------------ the rows of the cache
def plausible(loa, beam):
    """The maximum vessel of a port as a ship: the beam within BEAM_MAX_RATIO of the length and under BEAM_MAX_M; a beam with no length cannot be
    checked and is held back. A length alone passes. Returns None when plausible, else the reason."""
    if beam and not loa:
        return "a beam is given with no length to compare it with"
    if beam and loa:
        if beam > BEAM_MAX_M:
            return f"the beam is above {BEAM_MAX_M:g} m"
        if beam > BEAM_MAX_RATIO * loa:
            return f"the beam is above {BEAM_MAX_RATIO:.0%} of the length"
    return None


def cache_row(pid, m):
    w = m["row"]
    r = {"port": pid, "wpi": w["n"], "name": w["name"], "code": w["code"], "by": m["by"], "km": f"{m['d']:.1f}", "size": w["size"], "type": w["type"],
         "pilot": w["pilot"], "tide_res": w["tide_res"], "why": m.get("why", "") if m["by"] == "review" else ""}
    for k in FIGURES:
        r[k] = fmt(w[k]) if w[k] else ""
    held = []
    for group, keys in (("maximum", ("loa", "beam", "draft")), ("offshore", ("oloa", "obeam", "odraft"))):
        why = plausible(w[keys[0]], w[keys[1]])
        if why:
            held.append({"id": pid, "group": group, "reason": why})
            for k in keys:
                r[k] = ""
    return r, held


def build(ports, rows, countries, review):
    """Rows of the cache (a list of dicts), the held vessel figures, the matches with their grades."""
    matches = match(ports, rows, countries)
    apply_review(matches, rows, review)
    out, held = [], []
    for m in matches:
        if m["grade"] != "sure":
            continue
        r, h = cache_row(m["id"], m)
        if not any(r[k] for k in LIMITS):
            # nothing of what the panel prints is left: a row of no use is not published, and says why
            m.update(grade="doubtful", reasons=["the entry has no depth or maximum vessel figure that the atlas keeps"])
            continue
        out.append(r)
        held += h
    out.sort(key=lambda r: r["port"])
    return out, held, matches


def check_countries(out, matches, countries):
    """Guard: each published row is in the port's country (a promotion by review is checked here too)."""
    by_id = {m["id"]: m for m in matches}
    for r in out:
        m = by_id[r["port"]]
        if m["row"]["cty"] != m["c"]:
            raise Stop(f"{r['port']}: the row no. {r['wpi']} {r['name']!r} is of {m['row']['country']!r}, not of the port's country {m['c']}")


def write_csv_text(out):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(HEADER)
    for r in out:
        w.writerow([r[k] for k in HEADER])
    return buf.getvalue()


def read_cache_csv(text):
    return list(csv.DictReader(io.StringIO(text)))


# ------------------------------------------------------------------------------------------------------------------------------ guards on a new file
def compare(prev_rows, prev_meta, out, n_rows):
    """The guards that need the last cache: (the reasons to stop, the lines of the report). The caller stops on the reasons unless --accept was given."""
    stops, report = [], []
    old = {r["port"]: r for r in prev_rows}
    new = {r["port"]: r for r in out}
    if prev_meta:
        before = prev_meta["file"]["rows"]
        if n_rows < ROWS_MIN * before:
            stops.append(f"the file has {n_rows} rows against {before} at the last read (less than {ROWS_MIN:.0%})")
        if len(new) < prev_meta["published"] - PUBLISHED_DROP:
            stops.append(f"{len(new)} ports are published against {prev_meta['published']} at the last read (more than {PUBLISHED_DROP} fewer)")
    both = sorted(set(old) & set(new))
    moved = []
    for pid in both:
        for k in FIGURES:
            a, b = old[pid][k], new[pid][k]
            if a and b and abs(float(b) - float(a)) > CHANGED_BY * float(a):
                moved.append(pid)
                break
    if both and len(moved) > CHANGED_SHARE * len(both):
        stops.append(f"{len(moved)} of the {len(both)} ports kept show a figure that moved by more than {CHANGED_BY:.0%} (a re-coded scale?)")
    report.append(f"ports published: {len(new)} (before: {len(old)}); gained {len(set(new) - set(old))}, lost {len(set(old) - set(new))}")
    changed = [pid for pid in both if any(str(old[pid][k]) != str(new[pid][k]) for k in HEADER if k != "km")]
    report.append(f"ports kept whose row changed: {len(changed)}")
    return stops, report


# ------------------------------------------------------------------------------------------------------------------------------ the whole run
def atlas_ports(path=PORTS_GEOJSON):
    out = []
    with open(path, encoding="utf-8") as fh:
        features = json.load(fh)["features"]
    for f in features:
        p = dict(f["properties"])
        p["lon"], p["lat"] = f["geometry"]["coordinates"][:2]
        out.append(p)
    return out


def extract(raw_path, ports, countries, review, prev_csv=None, prev_meta=None, accept=False):
    """The cache as (csv text, meta dict, report lines) from the raw file; raises Stop on a guard."""
    with open(raw_path, encoding="utf-8-sig", newline="") as f:
        text = f.read()
    rows = read_rows(text)
    ctry = Countries(countries)
    out, held, matches = build(ports, rows, ctry, review)
    check_countries(out, matches, ctry)
    stops, report = compare(read_cache_csv(prev_csv) if prev_csv else [], prev_meta, out, len(rows))
    if stops and not accept:
        raise Stop("; ".join(stops) + " (run again with --accept if the change is real)")
    counts = {"sure_code": sum(1 for r in out if r["by"] == "code"), "sure_name": sum(1 for r in out if r["by"] == "name"),
              "sure_review": sum(1 for r in out if r["by"] == "review"),
              "doubtful": sum(1 for m in matches if m["grade"] == "doubtful"), "none": sum(1 for m in matches if m["grade"] == "none"),
              "ports": len(matches)}
    kept = max((m for m in matches if m.get("by") == "code"), key=lambda m: m["d"], default=None)
    refused = min((m for m in matches if m.get("far_code")), key=lambda m: m["d"], default=None)
    basis = {"code_km": "the farthest code match kept and the nearest code match refused for its distance",
             "farthest_kept": kept and {"id": kept["id"], "km": round(kept["d"], 1)},
             "nearest_refused": refused and {"id": refused["id"], "km": round(refused["d"], 1)}}
    why_of = {m["id"]: m["why"] for m in matches if m.get("by") == "review" and m["grade"] == "sure"}
    doubtful = []
    for m in matches:
        if m["grade"] == "doubtful":
            e = {"id": m["id"], "reason": "; ".join(m["reasons"])}
            if m.get("row"):
                e["candidate"] = {"wpi": m["row"]["n"], "name": m["row"]["name"], "km": round(m["d"], 1)}
            doubtful.append(e)
    meta = {
        "file": {"name": os.path.basename(raw_path), "sha256": sha256(raw_path), "bytes": os.path.getsize(raw_path), "rows": len(rows),
                 "columns": len(next(csv.reader(io.StringIO(text))))},
        "source": SOURCE, "downloaded": DOWNLOADED, "edition": EDITION, "edition_page": EDITION_PAGE,
        "terms_quote": TERMS_QUOTE, "terms_page": TERMS_PAGE, "terms_read_on": TERMS_READ_ON, "terms_scope": TERMS_SCOPE,
        "rule": RULE, "rule_basis": basis, "counts": counts,
        "review": {pid: ({"action": "promote", "wpi": e["wpi"], "name": e["name"], "why": why_of[pid]} if e["action"] == "promote" else
                         {"action": "hold", "why": e["why"]}) for pid, e in sorted(review.items()) if e["action"] == "hold" or pid in why_of},
        "doubtful": doubtful,
        "none": [{"id": m["id"], "reason": "; ".join(m["reasons"])} for m in matches if m["grade"] == "none"],
        "held_vessel": held,
        "columns_used": COLUMNS, "published": len(out),
    }
    report.append("sure by code {sure_code}, by name {sure_name}, by review {sure_review}; doubtful {doubtful}; none {none}".format(**counts))
    report.append(f"maximum vessel held back for {len(held)} group(s) of {len({h['id'] for h in held})} port(s)")
    return write_csv_text(out), meta, report


def meta_text(meta):
    return json.dumps(meta, indent=1, ensure_ascii=False) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--accept", action="store_true", help="write although a guard on the size of the change stopped the run")
    args = ap.parse_args(argv)
    if not os.path.exists(RAW):
        print(f"extract_wpi: {os.path.relpath(RAW, ROOT)} is not here; the cache stays as it is")
        return 0
    prev_csv = prev_meta = None
    if os.path.exists(PORTS_CSV):
        with open(PORTS_CSV, encoding="utf-8") as f:
            prev_csv = f.read()
    if os.path.exists(META):
        with open(META, encoding="utf-8") as f:
            prev_meta = json.load(f)
    with open(COUNTRIES, encoding="utf-8") as f:
        countries = json.load(f)
    try:
        csv_text, meta, report = extract(RAW, atlas_ports(), countries, REVIEW, prev_csv, prev_meta, args.accept)
    except Stop as e:
        print(f"extract_wpi: {e}\nextract_wpi: the table was not replaced", file=sys.stderr)
        return 1
    # both files or none: written beside and moved into place together
    tmp = [(PORTS_CSV + ".tmp", csv_text), (META + ".tmp", meta_text(meta))]
    for path, text in tmp:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    for path, _ in tmp:
        os.replace(path, path[:-4])
    print("\n".join("extract_wpi: " + line for line in report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
