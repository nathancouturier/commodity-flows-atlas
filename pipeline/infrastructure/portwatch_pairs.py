"""
The IMF PortWatch port that each port asset of the atlas is paired with.

    python pipeline/infrastructure/portwatch_pairs.py --report   # prints the pair of each port, or why it has none; writes nothing
    python pipeline/infrastructure/portwatch_pairs.py --apply    # adds the `portwatch` id the rule gives to the ports that lack one

Input   data/infrastructure/ports.geojson        the port assets: `id`, `name`, `c` (ISO3), `locode`, the point, `portwatch`
        pipeline/cache/portwatch_ports.csv       the PortWatch ports table: portid, name, iso3, locode, lat, lon, pageid
Output  with --apply only: a `"portwatch": "portNNN"` line in each port that gains an id, inserted into the text of
        ports.geojson (the file keeps its order and its format). Nothing is downloaded and nothing else is written.

The rule. Candidates are the rows of the same country as the asset (`c` = the row's ISO3) whose id starts with `port`
(`fso` rows are offshore terminals and are never offered). A row is at most 15 km from the asset's point.
- R1, UN/LOCODE: the asset's `locode` equals the row's `locode`. Where several rows share it, the nearest one.
- R2, name: no row answers R1, and the asset's name equals a row's name once both are lower-cased, stripped of accents,
  of their parenthesis and of the words port, terminal, harbor, oil, marine, of, de and international. A row whose own name
  has a parenthesis ("Skikda (Port Methanier)") is not offered. The nearest such row.
Nothing else pairs a port: a nearer row of another name is not evidence that it is the same port.

One PortWatch port serves at most one asset. Where two assets would take the same row, or an asset would take a row that
another asset already holds, the asset that has no id takes none; the report lists them. A port with an id keeps it
whatever the rule says: the rule is a test of the published pairs, and a pair that sits at 0 km from its row because the
asset's position was copied from that row is by construction the same place.

Not paired: "no row" when the table has no `port` row of the asset's country within 15 km; "rule gives none" when it has a
row but neither R1 nor R2 pairs it, or the row is claimed twice.
"""
import argparse
import csv
import json
import math
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common import constants as CN  # noqa: E402  (the Earth radius, with the page that gives it)

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PORTS = os.path.join(ROOT, "data", "infrastructure", "ports.geojson")
TABLE = os.path.join(ROOT, "pipeline", "cache", "portwatch_ports.csv")
MAX_KM = 15.0
STOP_WORDS = r"\b(port|of|de|terminal|harbor|oil|marine|international)\b"


def km_between(lat1, lon1, lat2, lon2):
    """Great-circle distance in km (haversine, with the mean Earth radius of common/constants.py)."""
    p = math.pi / 180
    x = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 2 * CN.EARTH_RADIUS_KM * math.asin(math.sqrt(x))


def norm(name):
    """A port name for comparison: no accent, no parenthesis, no generic word, lower case."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(STOP_WORDS, " ", s)
    return " ".join(s.split())


def load_table(path=TABLE):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_assets(path=PORTS):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["features"]


def candidates(asset, table):
    """(km, row) of the rows of the asset's country, nearest first."""
    lon, lat = asset["geometry"]["coordinates"]
    c = asset["properties"]["c"]
    near = [(km_between(lat, lon, float(r["lat"]), float(r["lon"])), r) for r in table if r["iso3"] == c and r["portid"].startswith("port")]
    return sorted(near, key=lambda t: t[0])


def rule(asset, table):
    """The pair the rule gives for one asset: {"rule": "R1" | "R2", "row": row, "km": km}, or None."""
    p = asset["properties"]
    cands = [t for t in candidates(asset, table) if t[0] <= MAX_KM]
    if p.get("locode"):
        for km, row in cands:
            if row["locode"] == p["locode"]:
                return {"rule": "R1", "row": row, "km": km}
    want = norm(p["name"])
    if want:
        for km, row in cands:
            if "(" not in row["name"] and norm(row["name"]) == want:
                return {"rule": "R2", "row": row, "km": km}
    return None


def pair_all(assets, table):
    """One result per asset: {"id", "name", "have", "rule", "row", "km", "gives", "outcome", "why"}.

    outcome: "has" (already carries an id), "new" (gains the id in `gives`), "shared" (the rule's row is claimed by
    another asset), "none" (no row within 15 km: "no row"), "unpaired" (a row is near but the rule gives none)."""
    results = []
    for a in assets:
        p = a["properties"]
        r = rule(a, table)
        results.append({"id": p["id"], "name": p["name"], "have": p.get("portwatch"), "rule": r["rule"] if r else None,
                        "row": r["row"] if r else None, "km": r["km"] if r else None,
                        "gives": r["row"]["portid"] if r else None, "outcome": None, "why": ""})
    claims = {}
    for x in results:
        pid = x["have"] or x["gives"]
        if pid:
            claims.setdefault(pid, []).append(x["id"])
    by_id = {a["properties"]["id"]: a for a in assets}
    for x in results:
        if x["have"]:
            x["outcome"] = "has"
        elif x["gives"] and len(claims[x["gives"]]) == 1:
            x["outcome"] = "new"
        elif x["gives"]:
            x["outcome"] = "shared"
            x["why"] = "%s is also claimed by %s" % (x["gives"], ", ".join(i for i in claims[x["gives"]] if i != x["id"]))
        else:
            near = [t for t in candidates(by_id[x["id"]], table) if t[0] <= MAX_KM]
            if near:
                x["outcome"] = "unpaired"
                x["why"] = "nearest row %s %s at %.1f km: neither LOCODE nor name pairs it" % (near[0][1]["portid"], near[0][1]["name"], near[0][0])
            else:
                x["outcome"] = "none"
                far = candidates(by_id[x["id"]], table)
                x["why"] = "no PortWatch port row of %s within %d km" % (by_id[x["id"]]["properties"]["c"], MAX_KM)
                if far:
                    x["why"] += " (nearest: %s %s at %.0f km)" % (far[0][1]["portid"], far[0][1]["name"], far[0][0])
    return results


def summary(results):
    n = lambda o: sum(1 for x in results if x["outcome"] == o)
    has, new = n("has"), n("new")
    return {"assets": len(results), "have": has, "new": new, "with_id": has + new, "shared": n("shared"),
            "unpaired": n("unpaired"), "none": n("none"),
            "rule_reproduces": sum(1 for x in results if x["outcome"] == "has" and x["gives"] == x["have"])}


def report(results, out=sys.stdout):
    w = lambda s="": out.write(s + "\n")
    for x in results:
        row = x["row"]
        if x["outcome"] == "has":
            mark = "has %-9s" % x["have"] + ("rule agrees (%s, %.1f km)" % (x["rule"], x["km"]) if x["gives"] == x["have"] else
                                                ("rule gives %s" % x["gives"] if x["gives"] else "rule gives none") + " (kept)")
        elif x["outcome"] == "new":
            mark = "NEW %-9s %s %.1f km  PortWatch \"%s\"" % (x["gives"], x["rule"], x["km"], row["name"])
        else:
            mark = "%s: %s" % ({"shared": "SHARED", "unpaired": "UNPAIRED", "none": "NO ROW"}[x["outcome"]], x["why"])
        w("%-28s %s" % (x["id"], mark))
    s = summary(results)
    w()
    w("%d ports: %d carry an id, the rule adds %d, so %d have one." % (s["assets"], s["have"], s["new"], s["with_id"]))
    w("The rule reproduces %d of the %d existing ids; the other %d are kept." % (s["rule_reproduces"], s["have"], s["have"] - s["rule_reproduces"]))
    for outcome, title in (("shared", "Left without an id because one PortWatch port may serve only one asset"),
                           ("unpaired", "Without an id: the rule cannot pair them"),
                           ("none", "Without an id: no PortWatch row within %d km" % MAX_KM)):
        ids = [x["id"] for x in results if x["outcome"] == outcome]
        w()
        w("%s (%d): %s" % (title, len(ids), ", ".join(ids) if ids else "none"))


def apply(results, assets, path=PORTS):
    """Insert a `"portwatch"` line after the `locode` line of each port that gains an id (after its `c` line where it has
    no locode). The rest of the file is copied byte for byte. Returns the number of lines added."""
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    has_locode = {a["properties"]["id"]: "locode" in a["properties"] for a in assets}
    gains = {x["id"]: x["gives"] for x in results if x["outcome"] == "new"}
    out, current = [], None
    for line in text.split("\n"):
        out.append(line)
        m = re.match(r'^    "id": "([^"]+)",$', line)
        if m:
            current = m.group(1)
        elif current in gains and re.match(r'^    "%s": ".*",$' % ("locode" if has_locode[current] else "c"), line):
            out.append('    "portwatch": "%s",' % gains.pop(current))
            current = None
    if gains:
        raise SystemExit("no place to insert the id of: " + ", ".join(gains))
    added = len(out) - len(text.split("\n"))
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(out))
    return added


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1].strip())
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--report", action="store_true", help="print each port's pair; write nothing")
    mode.add_argument("--apply", action="store_true", help="add the ids the rule gives to ports.geojson")
    args = ap.parse_args()
    assets = load_assets()
    results = pair_all(assets, load_table())
    if args.report:
        report(results)
        return
    n = apply(results, assets)
    print("%d ids added to %s" % (n, os.path.relpath(PORTS, ROOT)))


if __name__ == "__main__":
    main()
