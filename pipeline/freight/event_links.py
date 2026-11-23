"""
The links of the events (pipeline/freight/events.json) to commodities, countries and assets: the rule, in one place.

    python pipeline/freight/event_links.py           # lists the events whose links differ from the rule
    python pipeline/freight/event_links.py --write   # sets the ``commodities`` of every event to what the rule gives

An event links to a commodity, a country or an asset when its own text names it: the title, the summary or the impact,
or the name of an asset it links to ("Freeport LNG"). Whole words only: "tin" is not "tinplate", "gas" is not
"gasoline", "oil" is not "oil-fired" or "fuel oil". A passage or a route does not name a commodity by being linked.
An event that names no commodity (a shipping or market event of no particular cargo) gets none, and the site shows it
with every commodity. The events that an alert of data/freight/alerts.json points to are also shown with the commodities of
that alert (web/src/lib/events.ts); that is not written into this file.

``commodities`` are written from the rule. ``countries`` and ``assets`` are listed by hand and checked against the rule by
the tests (pipeline/tests/test_alerts_events.py): every one listed is named, and every one named is listed.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
EVENTS = os.path.join(HERE, "events.json")

# word patterns of the commodities events can name; a pattern is matched case-insensitively unless it is an acronym
_I, _C = re.I, 0
COMMODITY_WORDS = {
    "crude-oil": [(r"\bcrude\b", _I), (r"\bbrent\b", _I), (r"\bWTI\b", _C), (r"(?<!fuel )\boil\b(?!-fired|\s+products?\b)", _I)],
    "refined-products": [(r"\b(?:oil|refined|petroleum)\s+products?\b", _I), (r"\bgasoline\b", _I), (r"\bdiesel\b", _I),
                         (r"\bfuel\s+oil\b", _I), (r"\bjet\s+fuel\b", _I), (r"\bmarine\s+fuel\b", _I), (r"\bbunker\s+fuel\b", _I),
                         (r"\bcrude(?:,|\s+and)\s+products\b", _I)],
    "lng": [(r"\bLNG\b", _C), (r"\bliquefied\s+natural\s+gas\b", _I)],
    "natural-gas": [(r"(?<!liquefied )\bnatural\s+gas\b", _I), (r"\bpipeline\s+gas\b", _I), (r"\bgas\s+pipelines?\b", _I),
                    (r"\bgas\b(?!\s+turbine)", _I)],
    "lpg": [(r"\bLPG\b", _C)],
    "thermal-coal": [(r"(?<!coking )(?<!metallurgical )\bcoal\b", _I)],
    "met-coal": [(r"\bcoking\s+coal\b", _I), (r"\bmetallurgical\s+coal\b", _I)],
    "iron-ore": [(r"\biron\s+ore\b", _I)],
    "nickel": [(r"\bnickel\b", _I)],
    "bauxite": [(r"\bbauxite\b", _I), (r"\balumina\b", _I)],
    "tin": [(r"\btin\b", _I)],
    "cobalt": [(r"\bcobalt\b", _I)],
    "wheat": [(r"\bwheat\b", _I)],
    "corn": [(r"\bcorn\b", _I), (r"\bmaize\b", _I)],
    "soybeans": [(r"\bsoybeans?\b", _I)],
}

# countries are named by the name of the atlas's country index or by one of these (a demonym, an abbreviation)
COUNTRY_ALIASES = {
    "USA": ["US", "U.S.", "American", "Mississippi"], "RUS": ["Russian"], "UKR": ["Ukrainian"], "CHN": ["Chinese"], "JPN": ["Japanese"],
    "IRN": ["Iranian"], "ISR": ["Israeli"], "SAU": ["Saudi"], "LBY": ["Libyan"], "IDN": ["Indonesian"], "PHL": ["Philippine"],
    "BRA": ["Brazilian"], "IND": ["Indian(?! Ocean)"], "TUR": ["Turkish"], "KAZ": ["Kazakh"], "EGY": ["Egyptian"], "YEM": ["Yemeni"],
    "DEU": ["German"], "AUS": ["Australian"], "SOM": ["Somali"], "KOR": ["Korean"], "ROU": ["Romanian"], "BGR": ["Bulgarian"],
    "QAT": ["Qatari"], "GBR": ["UK"], "ARE": ["UAE", "Emirati"], "MNG": ["Mongolian"],
}
# water bodies and the like that carry a country's name
NOT_A_COUNTRY = [r"Gulf of Oman", r"Indian Ocean", r"Gulf of Aden", r"Korea Strait"]

# the name of an asset in a text (the ids are those of data/infrastructure/*.geojson)
ASSET_WORDS = {
    "fujairah": ["Fujairah"], "freeport-lng": ["Freeport LNG"], "odesa": ["Odesa"], "nord-stream-1": ["Nord Stream"],
    "east-west-petroline": ["East-West pipeline"], "simandou": ["Simandou"], "novorossiysk": ["Novorossiysk"], "cpc": ["CPC"],
}


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def text_of(event, asset_names=()):
    """The words an event is read from: title, summary, impact and the names of the assets it links to."""
    return " ".join([event["title"], event["summary"], event.get("impact", ""), *asset_names])


def named_commodities(text):
    """Commodity ids whose word appears in ``text``, sorted."""
    return sorted(k for k, pats in COMMODITY_WORDS.items() if any(re.search(p, text, fl) for p, fl in pats))


def named_countries(text, countries):
    """ISO3 codes of the countries ``text`` names: by the name of ``countries`` (the country index) or an alias; sorted.
    A country in a hyphenated pair ("Brazil-China") counts."""
    for w in NOT_A_COUNTRY:
        text = text.replace(w, " ")
    found = set()
    for c in countries:
        words = [re.escape(c["name"])] + COUNTRY_ALIASES.get(c["c"], [])
        if any(re.search(r"(?<![A-Za-z])" + w + r"(?![A-Za-z])", text) for w in words):
            found.add(c["c"])
    return sorted(found)


def named_assets(text):
    return sorted(a for a, words in ASSET_WORDS.items() if any(re.search(r"(?<![A-Za-z])" + re.escape(w) + r"(?![A-Za-z])", text) for w in words))


def derive(event):
    """The commodities of one event by the rule."""
    names = [w for a in event.get("assets", []) for w in ASSET_WORDS.get(a, [])]
    return named_commodities(text_of(event, names))


def main():
    events = load(EVENTS)
    write = "--write" in sys.argv
    changed = 0
    for e in events:
        want = derive(e)
        have = e.get("commodities", [])
        if want != have:
            changed += 1
            print(f"{e['id']}: {have} -> {want}")
            if write:
                if want:
                    e["commodities"] = want
                else:
                    e.pop("commodities", None)
    if write and changed:
        # the file keeps its layout (indent 1, keys in their order)
        with open(EVENTS, "w", encoding="utf-8") as fh:
            json.dump(events, fh, indent=1, ensure_ascii=False)
    print(f"{changed} event(s) differ from the rule" + (" (rewritten)" if write and changed else ""))
    return changed


if __name__ == "__main__":
    sys.exit(0 if main() == 0 or "--write" in sys.argv else 1)
