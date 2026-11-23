"""
Builds the companies files the site reads from the hand-curated source files of this folder.

    python pipeline/companies/build_companies.py            # write the published files
    python pipeline/companies/build_companies.py --check    # exit 1 if a published file is out of date

Sources (one JSON object per file, keyed by commodity id, or by shipping segment for shipping.json):
  energy.json, metals.json, agri.json  ->  data/commodities/companies.json
  shipping.json                        ->  data/freight/shipping-companies.json

Nobody edits the published files by hand. The schema of an entry is in README.md of this folder: every entry is
checked against it (problems()) and nothing is written while one entry fails.
"""
import json
import os
import re
import sys
import time
from urllib.parse import unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FAMILIES = ("energy", "metals", "agri")
OUT = os.path.join(ROOT, "data", "commodities", "companies.json")
OUT_SHIPPING = os.path.join(ROOT, "data", "freight", "shipping-companies.json")
SOURCES = os.path.join(ROOT, "data", "sources.json")
COMMODITIES = os.path.join(ROOT, "data", "commodities", "index.json")
COUNTRIES = os.path.join(ROOT, "data", "countries", "index.json")
CLASSES = os.path.join(ROOT, "pipeline", "freight", "vessel_classes.json")

GROUPS = ("producers", "processors", "traders")
SEGMENTS = ("dry-bulk", "tankers", "gas", "charterers", "brokers", "terminals")
FIELDS = ("name", "hq", "role", "own", "parent", "parentUrl", "detail", "fig", "sanction", "s", "url", "y", "read")
REQUIRED = ("name", "hq", "role", "s", "url", "read")
OWN = ("state", "state-listed", "listed", "private", "cooperative")
UNITS = ("Mt", "kt", "t", "kb/d", "Mboe/d", "bcm", "Mtpa", "Mt/y", "ships", "Mdwt", "Mcbm", "TEU")
FIG_FIELDS = ("v", "u", "what", "y", "s", "url", "n")
# the registry entry of each sanctions authority (its official list or journal)
SANCTION_BY = {"OFAC": "ofac", "EU": "eu-sanctions", "UK": "uk-sanctions"}
# a claim of rank needs the dated figure that supports it on the same entry
SUPERLATIVE = re.compile(r"\b(largest|biggest|leading|foremost|top|number one|no\. ?1|world-leading|second-largest|"
                         r"third-largest|most important|dominant)\b", re.I)
# a home page is not a source: an empty path, a language code or an index page only
HOME_PATH = re.compile(r"^/?((?:[a-z]{2}(?:[-_][a-z]{2})?)/?)?(index\.(?:html?|php|aspx?)|home/?|default\.aspx)?$", re.I)
# nor, for a figure, a generic page ("about us", "investors") with nothing after it: its text changes from year to year,
# so the figure could not be read there again
GENERIC_PATH = re.compile(r"^/?((?:[a-z]{2}(?:[-_][a-z]{2})?)/?)?(about(?:-us)?|about-[a-z]+|who-we-are|our-company|company|corporate|"
                          r"investors?|investor-relations)(/|\.(?:html?|php|aspx?))?$", re.I)
# a share in `parent` is the share a page states: the entry's Wikipedia article, or the page named by `parentUrl`
SHARE = re.compile(r"\d\s*%")
# "largest shareholder" says who the parent is, not a rank of the company
SHAREHOLDER = re.compile(r"\blargest shareholder\b", re.I)
# a figure counts one commodity: "oil and gas production", "crude and products traded" or "hydrocarbons" count two
TWO_COMMODITIES = re.compile(r"\b(oil|crude|gas|lng|lpg|coal|products|copper|gold|silver|zinc|lead|nickel|cobalt|iron ore)\b[^,(]*\band\b[^,(]*"
                             r"\b(oil|crude|gas|lng|lpg|ngl|condensate|coal|products|copper|gold|silver|zinc|lead|nickel|cobalt|iron ore)\b|"
                             r"\bhydrocarbons?\b|\boil equivalent\b", re.I)
# Wikipedia pages that are not an article about one company
WIKI_NOT_ARTICLE = re.compile(r"^/wiki/((Special|Talk|User|File|Template|Category|Help|Wikipedia|Portal|Draft):|.*_\(disambiguation\)$)", re.I)
# the order of the commodities in the published file (new ids follow, in the order of the source files)
ORDER = ["crude-oil", "refined-products", "lng", "natural-gas", "thermal-coal", "met-coal", "iron-ore", "copper", "aluminium",
         "bauxite", "nickel", "cobalt", "lithium", "zinc", "gold", "pgm", "uranium", "rare-earths", "steel", "potash",
         "phosphate", "urea", "wheat", "corn", "soybeans", "soymeal", "soyoil", "rapeseed", "rice", "sugar", "coffee",
         "cocoa", "cotton", "palm-oil", "lpg", "tin", "lead", "silver", "manganese"]


def load(name):
    with open(os.path.join(HERE, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def merged():
    out, seen = {}, {}
    for fam in FAMILIES:
        for k, v in load(fam).items():
            if k in seen:
                sys.exit(f"{k} is in {seen[k]}.json and in {fam}.json")
            seen[k] = fam
            out[k] = v
    return {k: out[k] for k in ORDER if k in out} | {k: v for k, v in out.items() if k not in ORDER}


def dump(obj):
    return json.dumps(obj, indent=1, ensure_ascii=False) + "\n"


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def is_year(y):
    return isinstance(y, int) and not isinstance(y, bool) and 1900 <= y <= 2100


def url_problem(url, dated=False):
    """What is wrong with a source address; `dated`: it must hold a dated figure (no generic "about" or "investors" page)."""
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        return "url is not a web address"
    u = urlparse(url)
    if not u.netloc:
        return "url has no host"
    if "wikipedia.org" in u.netloc:
        if not u.path.startswith("/wiki/") or len(u.path) <= len("/wiki/"):
            return "a Wikipedia url must name the article (/wiki/<title>)"
        if WIKI_NOT_ARTICLE.match(unquote(u.path)):
            return "a Wikipedia url must be an article, not a special, talk or disambiguation page"
        return None
    if HOME_PATH.match(u.path or "/") and not u.query:
        return "url is a home page, not a dated document or page"
    if dated and GENERIC_PATH.match(u.path) and not u.query:
        return "url is a generic page (about, investors), not a dated document: a figure needs one"
    return None


def entries(companies, shipping):
    """Every entry with where it stands: (place, entry, is_shipping)."""
    for k, groups in companies.items():
        for g, lst in groups.items():
            for i, e in enumerate(lst):
                yield f"{k}/{g}[{i}]", e, False
    for seg, lst in shipping.items():
        for i, e in enumerate(lst):
            yield f"shipping/{seg}[{i}]", e, True


def problems(companies, shipping, source_ids, commodity_ids, iso3, class_ids, month=None):
    """Every breach of the schema of README.md, as 'place name: problem' lines (an empty list when all entries pass).
    `month`: the current month, "YYYY-MM" (a page cannot have been read later)."""
    month = month or time.strftime("%Y-%m")
    out = []
    for k, groups in companies.items():
        if k not in commodity_ids:
            out.append(f"{k}: not a commodity id of data/commodities/index.json")
        for g in groups:
            if g not in GROUPS:
                out.append(f"{k}/{g}: group must be one of {', '.join(GROUPS)}")
    for seg in shipping:
        if seg not in SEGMENTS:
            out.append(f"shipping/{seg}: segment must be one of {', '.join(SEGMENTS)}")
    identity = {}
    seen_in_group = set()
    for place, e, ship in entries(companies, shipping):
        name = e.get("name", "?")
        where = f"{place} {name}"
        group = place.rsplit("[", 1)[0]
        if (group, name) in seen_in_group:
            out.append(f"{where}: listed twice in the same group")
        seen_in_group.add((group, name))
        allowed = FIELDS + (("classes",) if ship else ())
        for f in e:
            if f not in allowed:
                out.append(f"{where}: unknown field {f!r}")
        for f in REQUIRED:
            if e.get(f) in (None, ""):
                out.append(f"{where}: {f} is required")
        if e.get("hq") is not None and e["hq"] not in iso3:
            out.append(f"{where}: hq {e['hq']!r} is not an ISO3 code of data/countries/index.json")
        if "own" in e and e["own"] not in OWN:
            out.append(f"{where}: own {e['own']!r} must be one of {', '.join(OWN)}")
        if e.get("s") is not None and e["s"] not in source_ids:
            out.append(f"{where}: source {e['s']!r} is not in data/sources.json")
        if "url" in e and url_problem(e["url"], dated="fig" in e):
            out.append(f"{where}: {url_problem(e['url'], dated='fig' in e)} ({e['url']})")
        if "y" in e and not is_year(e["y"]):
            out.append(f"{where}: y must be a year (the year of the facts, not of the reading)")
        if e.get("read") is not None and not re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", str(e["read"])):
            out.append(f"{where}: read must be YYYY-MM, the month the page was read")
        elif e.get("read") is not None and str(e["read"]) > month:
            out.append(f"{where}: read {e['read']} is later than the current month ({month})")
        parent = e.get("parent") or ""
        if "parentUrl" in e:
            if not parent:
                out.append(f"{where}: parentUrl without a parent")
            if url_problem(e["parentUrl"]):
                out.append(f"{where}: parentUrl: {url_problem(e['parentUrl'])} ({e['parentUrl']})")
        if SHARE.search(parent) and e.get("s") != "wikipedia" and not e.get("parentUrl"):
            out.append(f"{where}: the share in parent ({parent!r}) needs the page that states it: parentUrl, or the entry's Wikipedia article")
        fig = e.get("fig")
        if fig is not None:
            if not isinstance(fig, dict):
                out.append(f"{where}: fig must be an object")
                fig = {}
            for f in fig:
                if f not in FIG_FIELDS:
                    out.append(f"{where}: unknown fig field {f!r}")
            for f in ("v", "u", "what", "y", "s", "url"):
                if fig.get(f) in (None, ""):
                    out.append(f"{where}: fig.{f} is required")
            if "v" in fig and (not isinstance(fig["v"], (int, float)) or isinstance(fig["v"], bool) or fig["v"] <= 0):
                out.append(f"{where}: fig.v must be a positive number")
            if "u" in fig and fig["u"] not in UNITS:
                out.append(f"{where}: fig.u {fig['u']!r} is not a unit of the schema ({', '.join(UNITS)}); say what is counted in fig.what")
            if "y" in fig and not is_year(fig["y"]):
                out.append(f"{where}: fig.y must be the year the figure refers to")
            if fig.get("s") is not None and fig["s"] not in source_ids:
                out.append(f"{where}: fig source {fig['s']!r} is not in data/sources.json")
            if "url" in fig and url_problem(fig["url"], dated=True):
                out.append(f"{where}: fig {url_problem(fig['url'], dated=True)} ({fig['url']})")
            if "y" in e and fig.get("y") != e["y"]:
                out.append(f"{where}: y must be the year of fig ({fig.get('y')}) when the entry has a figure")
            if ship and fig.get("u") not in (None, "ships", "Mdwt", "Mcbm", "TEU"):
                out.append(f"{where}: a shipping company's figure is its fleet (ships, Mdwt, Mcbm or TEU)")
        for sanc in ([e["sanction"]] if isinstance(e.get("sanction"), dict) else e.get("sanction") or []):
            if not isinstance(sanc, dict) or set(sanc) != {"by", "since", "url"}:
                out.append(f"{where}: sanction must be {{by, since, url}} (or a list of them, one per authority)")
            else:
                if sanc.get("by") not in SANCTION_BY:
                    out.append(f"{where}: sanction.by must be one of {', '.join(SANCTION_BY)}")
                elif SANCTION_BY[sanc["by"]] not in source_ids:
                    out.append(f"{where}: the {sanc['by']} list ({SANCTION_BY[sanc['by']]}) is not in data/sources.json")
                if not re.fullmatch(r"(19|20)\d\d(-(0[1-9]|1[0-2]))?", str(sanc.get("since", ""))):
                    out.append(f"{where}: sanction.since must be YYYY or YYYY-MM")
                if url_problem(sanc.get("url")):
                    out.append(f"{where}: sanction {url_problem(sanc.get('url'))}")
        if SUPERLATIVE.search(e.get("detail") or "") and not fig:
            out.append(f"{where}: a superlative ({SUPERLATIVE.search(e['detail']).group(0)!r}) needs the dated figure that supports it")
        for f, text in (("role", e.get("role") or ""), ("parent", SHAREHOLDER.sub("", parent))):
            if SUPERLATIVE.search(text):
                out.append(f"{where}: no superlative in {f} ({SUPERLATIVE.search(text).group(0)!r}); a rank goes in detail with its figure")
        fig_text = (fig.get("what"), fig.get("n")) if isinstance(fig, dict) else ()
        for text in (e.get("name"), e.get("role"), parent, e.get("detail"), *fig_text):
            if isinstance(text, str) and re.search(r"\bsanction(ed|s)?\b", text, re.I):
                out.append(f"{where}: a sanction is written in the sanction field only, from the authority's notice ({text!r})")
                break
        if isinstance(fig, dict) and isinstance(fig.get("what"), str) and TWO_COMMODITIES.search(fig["what"]):
            out.append(f"{where}: fig.what {fig['what']!r} counts more than one commodity; write it in detail with its date")
        if ship:
            cl = e.get("classes")
            if cl is not None and (not isinstance(cl, list) or any(c not in class_ids for c in cl)):
                out.append(f"{where}: classes must be ids of pipeline/freight/vessel_classes.json")
        ident = tuple(json.dumps(e.get(f), sort_keys=True) for f in ("hq", "own", "parent", "parentUrl", "sanction"))
        if name in identity and identity[name][0] != ident:
            out.append(f"{where}: hq, own, parent, parentUrl and sanction differ from {identity[name][1]} (one identity per company)")
        identity.setdefault(name, (ident, place))
    return out


def context():
    source_ids = {s["id"] for s in read_json(SOURCES)}
    commodity_ids = {c["id"] for c in read_json(COMMODITIES)}
    iso3 = {c["c"] for c in read_json(COUNTRIES)}
    class_ids = {c["id"] for c in read_json(CLASSES)}
    return source_ids, commodity_ids, iso3, class_ids


def main():
    companies, shipping = merged(), load("shipping")
    errs = problems(companies, shipping, *context())
    if errs:
        print(f"{len(errs)} problem(s) in pipeline/companies/*.json (nothing written):")
        print("\n".join("  " + p for p in errs))
        sys.exit(1)
    targets = [(OUT, dump(companies)), (OUT_SHIPPING, dump(shipping))]
    stale = []
    for path, text in targets:
        old = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if old != text:
            stale.append(os.path.relpath(path, ROOT))
            if "--check" not in sys.argv:
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
    if "--check" in sys.argv:
        if stale:
            print("out of date: " + ", ".join(stale) + " (run pipeline/companies/build_companies.py)")
            sys.exit(1)
        print("companies files are up to date")
        return
    print("companies files " + ("written: " + ", ".join(stale) if stale else "unchanged"))


if __name__ == "__main__":
    main()
