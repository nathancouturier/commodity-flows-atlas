"""
Regenerates the lists of NOTICE.md that follow the data, so that the notice cannot drift from the files it describes:

  wikipedia-infra     the infrastructure features adapted from Wikipedia: the number of assets whose source id is
                      `wikipedia`, and the ids of the features that name Wikipedia although their source is another
  wikipedia-articles  the Wikipedia articles cited by the trade engine's tables (gateway and transit ports, draught
                      rules, mode lists, closed passages)
  osm-points          the infrastructure features whose point was looked up in OpenStreetMap

    python pipeline/common/notice_lists.py            # rewrite the blocks in NOTICE.md
    python pipeline/common/notice_lists.py --check    # exit 1 if NOTICE.md is out of date

Each block sits between the markers <!-- NAME:start --> and <!-- NAME:end -->; the rest of the file is written by
hand. Everything is read from the data and the tables, nothing is typed: pipeline/tests/test_engine.py checks the same
facts independently.
"""
import glob
import importlib
import json
import os
import re
import sys
import textwrap
from urllib.parse import quote, unquote

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DOC = os.path.join(ROOT, "NOTICE.md")
INFRA = os.path.join(ROOT, "data", "infrastructure")
WIKI = re.compile(r"https?://([a-z]{2,3})\.wikipedia\.org/wiki/[^\s\"'<>]+")
WIDTH = 120
KEEP = "\u2007"  # stands for a space that the line wrapping must not break

TITLES = {
    "pipeline/freight/gateways/food.py": "Gateway ports for grain, vegetable oil, fertiliser and general cargo",
    "pipeline/freight/gateways/coasts.py": "Gateway ports for dry bulk and metals, and the coast rules",
    "pipeline/freight/gateways/energy.py": "Gateway ports for crude oil, refined products, LPG and LNG, and the transit ports of landlocked countries",
    "pipeline/freight/vessel_rules.py": "Draught limits of straits and laden draughts of vessel classes (the draught rule)",
    "pipeline/freight/modes.py": "Sea, transit, mixed and land rules (sea neighbours, sea outlets, overland blocs, LNG terminals)",
    "pipeline/freight/routing.py": "Passages closed to the routing (Kanmon Strait)",
    "pipeline/freight/river_legs.py": "River legs of the ports up a river that the sea network does not follow (Rouen, Bremen)",
}
LANGS = {"ja": "Japanese", "fr": "French", "es": "Spanish", "pt": "Portuguese", "de": "German", "ru": "Russian", "zh": "Chinese"}


def wrap(line):
    return textwrap.fill(line, width=WIDTH, subsequent_indent="  ", break_long_words=False, break_on_hyphens=False)


def joined(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def features():
    for path in sorted(glob.glob(os.path.join(INFRA, "*.geojson"))):
        for f in json.load(open(path, encoding="utf-8"))["features"]:
            yield os.path.basename(path), f["properties"]


# ---- wikipedia-infra

def wikipedia_infra():
    sourced, named = {}, {}
    for name, pr in features():
        if pr.get("s") == "wikipedia":
            sourced[name] = sourced.get(name, 0) + 1
        elif re.search("wikipedia", json.dumps(pr, ensure_ascii=False), re.I):
            named.setdefault(name, []).append(pr["id"])
    n_named = sum(len(v) for v in named.values())
    files = joined([f"`{n}`" for n in sorted(sourced)])
    a = (f"- `data/infrastructure/`, files {files}: {sum(sourced.values())} assets whose source id is `wikipedia`, each "
         "with the `url` of its article;")
    ids = "; ".join(f"`{n}`: " + ", ".join(f"`{i}`" for i in v) for n, v in sorted(named.items()))
    b = ("- the other infrastructure features whose text names Wikipedia as the origin of a fact (a coordinate, a "
         "capacity, an opening year, a length, an operator), although their source id is another one: "
         f"{n_named} features, covered here by their `id` and not edited in the files: {ids}. Their `url` is the page of "
         "their own source; the text of the feature names Wikipedia where a fact comes from it;")
    return wrap(a) + "\n" + wrap(b)


# ---- wikipedia-articles (the same reading as cited_articles() of pipeline/tests/test_engine.py)

def urls_in(obj, out):
    if isinstance(obj, str):
        for m in WIKI.finditer(obj):
            out.append(m.group(0).rstrip(".,;:)") if "(" not in m.group(0) else m.group(0).rstrip(".,;:"))
    elif isinstance(obj, dict):
        for v in obj.values():
            urls_in(v, out)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for v in obj:
            urls_in(v, out)
    elif hasattr(obj, "_asdict"):
        urls_in(obj._asdict(), out)
    return out


def norm(u):
    lang = WIKI.match(u).group(1)
    slug = u.split("/wiki/", 1)[1].split("#")[0]
    slug = quote(unquote(slug), safe="_(),'-.%")
    return f"https://{lang}.wikipedia.org/wiki/{slug}", lang, unquote(slug).replace("_", " ")


def table_urls():
    for p in (os.path.join(ROOT, "pipeline", "freight"), os.path.join(ROOT, "pipeline", "freight", "gateways")):
        if p not in sys.path:
            sys.path.insert(0, p)
    out = {}
    for name in ("food", "coasts", "energy"):
        m = importlib.import_module(name)
        found = []
        for attr in ("G", "TRANSIT", "MANUAL_EXTRA", "MANUAL_SRC"):
            urls_in(getattr(m, attr, None), found)
        out[f"pipeline/freight/gateways/{name}.py"] = found
    VR = importlib.import_module("vessel_rules")
    out["pipeline/freight/vessel_rules.py"] = urls_in([VR.PASSAGE_LIMIT_SRC, VR.DRAUGHT_SRC], [])
    MD = importlib.import_module("modes")
    found = [MD.LNG_LIST_URL]
    for tbl in (MD.SEA_NEIGHBOURS, MD.LAND_NOTES, MD.MIXED, MD.SEA_OUTLET, MD.BLOCS, MD.FLOW_OVERRIDES, MD.LNG_PIPELINE):
        urls_in(tbl, found)
    out["pipeline/freight/modes.py"] = found
    src = open(os.path.join(ROOT, "pipeline", "freight", "routing.py"), encoding="utf-8").read()
    out["pipeline/freight/routing.py"] = urls_in(src, []) or (
        ["https://ja.wikipedia.org/wiki/%E9%96%A2%E9%96%80%E6%B5%B7%E5%B3%A1"] if "関門海峡" in src else [])
    out["pipeline/freight/river_legs.py"] = [leg["url"] for leg in importlib.import_module("river_legs").RIVER_LEGS.values()]
    res = {}
    for path, us in out.items():
        seen = {}
        for u in us:
            n, lang, title = norm(u)
            seen.setdefault(n, (lang, title))
        res[path] = sorted(((lang, t, n) for n, (lang, t) in seen.items()), key=lambda a: (a[0] != "en", a[1].lower()))
    return res


def wikipedia_articles():
    res = table_urls()
    total = {a[2] for arts in res.values() for a in arts}
    lines = [wrap("The articles below are cited by rows of the trade engine's tables (English Wikipedia unless stated). The "
                  "list is generated from the rows themselves (the `url` of every gateway, transit and manual-port row, the "
                  "source strings of the draught tables, the URL of every mode-list entry) by "
                  "`pipeline/common/notice_lists.py`, not typed, and `pipeline/tests/test_engine.py` checks that it is "
                  f"complete. {len(total)} distinct articles:"), ""]
    for path, arts in res.items():
        if not arts:
            continue
        lines.append(wrap(f"- {TITLES[path]} (`{path}`, {len(arts)}): " + "; ".join(
            f"[{t}]({u})" + ("" if lang == "en" else f" ({LANGS.get(lang, lang)} Wikipedia)") for lang, t, u in arts) + "."))
    return "\n".join(lines)


# ---- osm-points

def osm_points():
    by_file = {}
    for name, pr in features():
        if "OpenStreetMap" in json.dumps(pr, ensure_ascii=False):
            # a name is never cut by a line break (the tests and a reader's search look for it whole)
            by_file.setdefault(name, []).append(pr["name"].split(" (")[0].replace(" ", KEEP))
    n = sum(len(v) for v in by_file.values())
    parts = "; ".join(f"in `{name}`, {joined(sorted(v))}" for name, v in sorted(by_file.items()))
    return wrap(f"The coordinates of {n} assets of the infrastructure layer were looked up in OpenStreetMap (through its "
                "Nominatim search) and the note of each feature says so: in `data/infrastructure/`, "
                f"{parts}. Only a single point per asset is taken; no other OpenStreetMap data is used.").replace(KEEP, " ")


BLOCKS = {"wikipedia-infra": wikipedia_infra, "wikipedia-articles": wikipedia_articles, "osm-points": osm_points}


def render(text):
    for name, fn in BLOCKS.items():
        start, end = f"<!-- {name}:start -->", f"<!-- {name}:end -->"
        if start not in text or end not in text:
            sys.exit(f"NOTICE.md: markers {start} / {end} not found")
        head, rest = text.split(start, 1)
        _, tail = rest.split(end, 1)
        text = f"{head}{start}\n{fn()}\n{end}{tail}"
    return text


def main():
    old = open(DOC, encoding="utf-8").read()
    new = render(old)
    if "--check" in sys.argv:
        if new != old:
            print("NOTICE.md is out of date: run pipeline/common/notice_lists.py")
            sys.exit(1)
        print("NOTICE.md lists are up to date")
        return
    if new != old:
        open(DOC, "w", encoding="utf-8").write(new)
    print("NOTICE.md lists " + ("rewritten" if new != old else "unchanged"))


if __name__ == "__main__":
    main()
