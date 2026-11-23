"""
Build the country profiles from the full commodity tables, the customs extracts and the trade-flow engine.

    python pipeline/commodities/build_profiles.py

Outputs (METHODOLOGY.md §6):
  data/countries/profiles/<ISO3>.json  one file per country of the index (and EU27), loaded when its page opens
  data/countries/years.json            the years, year labels and world totals of every series the lines point to
                                       (`hk`), the same for every country: one file, loaded once with the first profile

A profile holds:
  lines     every line the country has in any table of any commodity (production, refinery output, consumption,
            reserves, ending stocks, capacity, exports, imports: the main tables and every extra table, its section
            read from the last word of its key), with its world rank and share, read from the full tables; exports
            and imports carry their customs value (CEPII BACI, USD) and are ordered by it, so that "Largest
            raw-material export" is the largest in value. Each line carries the country's series from the history
            files (value and rank by year; the rank of the latest year is the rank printed on the line), for the History year and the
            trend line. The `balance` block of a crop
            file is a world balance sheet with no country row: it gives no line.
  basket    the ten largest exports and imports by value at HS4 (every chapter), with their share of the country's
            total merchandise exports or imports (pipeline/cache/hs4_*, written by pipeline/trade/extract_hs4.py);
            the first export is the page's "Largest export, all goods"
  other     up to five headings of the raw-material chapters outside the atlas catalogue (diamonds for Botswana, logs
            for Gabon); the chapters hold articles too (tyres, screws, jewellery), and the block is named so
  balance   per traded product: net exporter or importer (same table, unit and year on both sides; the net carries its
            note, and three significant digits when a line is an estimate), the first three
            customers and suppliers with their shares and the Herfindahl index of each side (recorded pairs of
            CEPII BACI, latest year: the pairs tables of the engine, or the cleaned customs frame for the groups that
            have no lanes), and imports over consumption where both tables share unit and year
  freight   from the pairs tables of the engine (data/freight/pairs): mode split, typical ports and the share of the
            seaborne tonnes whose assumed route has to cross ("at least") or may cross ("up to") each passage; no
            "up to" where the chokepoint page of the passage caps its own "up to" for that group at IMF PortWatch; a
            group that is an Atlas estimate as a whole (spodumene) is marked and credited to the atlas on every row
  gaps      the caveats of data/freight/caveats.json for this origin (exports customs data miss, hubs)
  hubs      trading or refining hub, a derived label: exports and imports of the same product both large, and no
            production line for it in the atlas
  infra, companies (headquarters in the country, every commodity they are listed for), operators (of the assets)
A country of the index with none of these gets the exact words of what it is (Natural Earth) and why it has no data.
"""
import glob
import json
import os
import re
import sys
from collections import defaultdict

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "trade"))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "freight"))
from hs_map import HS  # noqa: E402
from clean import CODE_FIX, clean  # noqa: E402  (BACI code S19 is Taiwan: one mapping for all builders)

TOP_RANK = 10
CACHE = os.path.join(ROOT, "pipeline", "cache")
OUT_DIR = os.path.join(ROOT, "data", "countries", "profiles")
# basket: headings shown per side; other: raw-material headings outside the catalogue, each at least this share of the
# country's raw-material exports, for a country with at least this much of them (thousand USD)
BASKET_ROWS, OTHER_ROWS, OTHER_MIN_SHARE, OTHER_MIN_TOTAL = 10, 5, 0.05, 200_000
RAW_CHAPTERS = {f"{c:02d}" for c in list(range(1, 28)) + [40, 41, 44, 47, 51, 52, 53, 71] + list(range(72, 82))}
# partners: customers and suppliers listed per product
PARTNERS = 3
# hub: a product whose exports and imports both reach this share of the world total, with no line in a production table
# that lists every producing country (EIA, USDA PSD and FAOSTAT do; a USGS table lists the main producers only, so a
# country missing from it may still produce: no label then)
HUB_MIN_SHARE = 0.01
FULL_PRODUCTION_SOURCES = {"eia-intl", "usda-psd", "faostat"}
# freight: a passage is listed for a country's product when the figure printed for it ("up to", or "at least" where no "up
# to" is printed) reaches this share of the seaborne tonnes or 1 Mt (the floor of the chokepoint estimates,
# pipeline/freight/build_freight.py EST_MIN_SHARE and EST_MIN_MT)
PASSAGE_MIN_SHARE = 0.02
PASSAGE_MIN_KT = 1000  # or 1 Mt (build_freight.py EST_MIN_MT)
PORTS = 3
# the EU27 aggregate of USDA PSD and its member states (the same list as web/src/map/modules/choropleth.ts EU27)
EU27 = ["AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "IRL", "ITA", "LVA", "LTU",
        "LUX", "MLT", "NLD", "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE"]
# Entries of the country index that CEPII BACI's country list (country_codes_V202601.csv) does not have, as Natural Earth
# 1:50m admin-0 (the base map, raw/naturalearth/ne_50m) describes them: TYPE, SOVEREIGNT, NOTE_BRK.
NE_STATUS = {
    "ALA": ("Country", "Finland", ""), "FRO": ("Dependency", "Denmark", ""), "GGY": ("Country", "United Kingdom", "U.K. crown dependency"),
    "HMD": ("Dependency", "Australia", ""), "IMN": ("Country", "United Kingdom", "U.K. crown dependency"),
    "JEY": ("Country", "United Kingdom", "U.K. crown dependency"), "KOS": ("Disputed", "Kosovo", ""),
    "LIE": ("Sovereign country", "Liechtenstein", ""), "MCO": ("Sovereign country", "Monaco", ""),
    "CYN": ("Sovereign country", "Northern Cyprus", "Self admin.; Claimed by Cyprus"), "PRI": ("Dependency", "United States of America", ""),
    "SGS": ("Dependency", "United Kingdom", ""), "KAS": ("Indeterminate", "Kashmir", "Claimed by Pakistan and India"),
    "SOL": ("Sovereign country", "Somaliland", "Self admin.; Claimed by Somalia"), "MAF": ("Dependency", "France", ""),
    "TWN": ("Sovereign country", "Taiwan", "Self admin.; Claimed by China"), "VIR": ("Dependency", "United States of America", ""),
    "VAT": ("Sovereign country", "Vatican", ""), "ESH": ("Indeterminate", "Western Sahara", "Self admin.; Claimed by Morocco"),
}
SOVEREIGN_NAME = {"United States of America": "the United States", "United Kingdom": "the United Kingdom"}

# atlas commodity -> BACI groups used to value its trade.
# Customs codes do not separate thermal from metallurgical coal: the value of all coal belongs to
# neither row, it is carried by the "Coal (all types)" row built from the all-coal customs tables.
VALUE_GROUPS = {
    "thermal-coal": [], "copper": ["copper-ore"], "bauxite": ["bauxite"], "nickel": ["nickel-ore"],
    "zinc": ["zinc-ore"], "lead": ["lead-ore"], "tin": ["tin-metal"], "phosphate": ["phosphate-rock"], "met-coal": [],
}
COAL = ("thermal-coal", "met-coal")
ALL_COAL = "Coal (all types)"

# What the main trade table of a commodity really is, where the commodity name alone would mislead
# (names as in pipeline/freight/build_lanes.py).
TRADE_LABEL = {"copper": "Copper concentrate", "zinc": "Zinc concentrate", "nickel": "Nickel ore", "lead": "Lead concentrate",
               "bauxite": "Bauxite", "cobalt": "Cobalt intermediates and metal", "tin": "Tin (unwrought)"}
PRODUCTION_LABEL = {"bauxite": "Bauxite", "urea": "Ammonia"}

# Names of HS4 headings. The heading texts of the HS are not reused: the free list on disk is UN Comtrade's, whose terms
# ("Policy on Comtrade Data Use", https://uncomtrade.org/docs/policy-on-comtrade-data-use/, read 23 November 2026) allow
# internal use only. A heading is named from the six-digit descriptions of CEPII BACI's product list (Etalab 2.0) under
# it, never from one of them alone (METHODOLOGY.md §6).
SMALL_WORDS = {"a", "an", "and", "or", "of", "the", "for", "in", "on", "with", "by", "to", "not", "other", "than", "whether",
               "being", "its", "their", "but", "as", "at", "from", "no", "heading", "item", "nes", "n.e.s", "n.e.c", "excluding",
               "including", "kind", "used", "thereof"}
NEGATORS = {"than", "excluding", "not", "except", "non", "nes", "n.e.s", "n.e.c"}
HEADING_NAME_MAX = 72
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.'/-]*")


def _short(text, n=HEADING_NAME_MAX):
    text = text.strip(" ,;:")
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0].rstrip(" ,;:(") + "…"


def _common_phrase(texts):
    """The longest run of words that every text has, with a word that is not a small word and no word that a text negates
    ("other than durum", "not mounted or set"), as the first text writes it."""
    toks, negated = [], set()
    for t in texts:
        ts = [(m.group(0).lower().rstrip("."), m.start(), m.end()) for m in _TOKEN.finditer(t)]
        toks.append(ts)
        for a, (w, _, e) in enumerate(ts):
            if w in NEGATORS:  # the words after it, up to the next punctuation, are negated
                for w2, s2, e2 in ts[a + 1:]:
                    if re.search(r"[,;:()]", t[e:s2]):
                        break
                    negated.add(w2)
                    e = e2
    seqs = [[w for w, _, _ in ts] for ts in toks]
    best = None
    for i in range(len(seqs[0])):
        for j in range(len(seqs[0]), i, -1):
            if best and j - i <= best[1] - best[0]:
                break
            run = seqs[0][i:j]
            if any(w in negated for w in run) or not any(w not in SMALL_WORDS and len(w) > 2 and not w.isdigit() for w in run):
                continue
            if all(any(s[x:x + len(run)] == run for x in range(len(s) - len(run) + 1)) for s in seqs[1:]):
                best = (i, j)
                break
    if not best:
        return None
    i, j = best
    while i < j and seqs[0][i] in SMALL_WORDS:  # a run neither starts nor ends on a small word
        i += 1
    while j > i and seqs[0][j - 1] in SMALL_WORDS:
        j -= 1
    phrase = texts[0][toks[0][i][1]:toks[0][j - 1][2]].split(":")[-1].strip()
    return phrase if phrase and phrase.count("(") == phrase.count(")") else None


def heading_name(descs):
    """(name, detail) of an HS4 heading from the six-digit descriptions under it ("Vehicles: parts, gear boxes"). One
    subheading: its description. One first part before ':' shared by all: that part, with the words every subheading
    shares after it ("Vehicles: transport of goods"), or the kinds they list in a word or two ("Metals: platinum,
    palladium..."). Different first parts: all of them ("Helicopters; aeroplanes and other aircraft; spacecraft"), with
    the words every subheading shares. `detail` lists the first parts when there are several."""
    descs = [re.sub(r"\s*\*\*[^*]*\*\*\s*", " ", str(d)).strip() for d in descs if str(d).strip()]
    if not descs:
        return None, None
    if len(descs) == 1:
        return _short(descs[0]), None
    heads, seen = [], set()
    for d in descs:
        h = d.split(":", 1)[0].strip()
        if h.lower() not in seen:
            seen.add(h.lower())
            heads.append(h)
    if len(heads) == 1:
        rests = [d.split(":", 1)[1].strip() if ":" in d else "" for d in descs]
        phrase = _common_phrase(rests) if all(rests) else None
        if not phrase and all(rests):
            kinds = []
            for r in rests:
                k = r.split(",", 1)[0].strip()
                if len(k.split()) > 2:
                    kinds = []
                    break
                if k.lower() not in (x.lower() for x in kinds):
                    kinds.append(k)
            phrase = ", ".join(kinds[:4]) + (", …" if len(kinds) > 4 else "") if len(kinds) > 1 else None
        return _short(f"{heads[0]}: {phrase}" if phrase else heads[0]), None
    # a first part that a later one only lengthens ("Electronic circuits", "... and microassemblies") is dropped
    heads = [h for a, h in enumerate(heads) if not any(o.lower().startswith(h.lower()) and o != h for o in heads[a + 1:])]
    listing = "; ".join([heads[0]] + [h if h[:2].isupper() else h[0].lower() + h[1:] for h in heads[1:]])
    phrase = _common_phrase(descs)
    if phrase and phrase.lower() not in listing.lower():
        tail = f" ({phrase})"  # what every subheading shares: "parts and accessories" of 8473
        return _short(listing, HEADING_NAME_MAX - len(tail)) + tail, "; ".join(heads)
    return _short(listing), "; ".join(heads)

def catalogue_hs():
    codes = []
    for g, lst in HS.items():
        if g in ("diamonds", "wood"):
            continue
        codes += [c.rstrip("*") for c in lst]
    return codes


def covered(hs4, codes):
    return any(c.startswith(hs4) or hs4.startswith(c[:4]) for c in codes if len(c) >= 4) or any(hs4.startswith(c) for c in codes if len(c) < 4)


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# group of the customs frame -> atlas commodity, for the groups that have no pairs table (the pairs tables carry their own)
GROUP_K = {"natural-gas": "natural-gas", "uranium": "uranium", "zinc-metal": "zinc", "lead-ore": "lead", "lead-metal": "lead",
           "tin-ore": "tin", "tin-metal": "tin", "lithium": "lithium", "cobalt": "cobalt", "rare-earths": "rare-earths",
           "gold": "gold", "silver": "silver", "pgm": "pgm"}
# A traded product of a commodity: its exports and imports tables (section or extra key), the customs group of its
# partners, and the production table that would carry the country if it produced it (None: the atlas has none).
# The main table of each commodity is added in products() with the group MAIN_GROUP gives.
PRODUCTS = [
    ("copper", "refined-exports", "refined-imports", "copper-refined", "refinery"),
    ("nickel", "int-exports", "int-imports", "nickel-int", None),
    ("nickel", "ferro-exports", "ferro-imports", "nickel-fe", None),
    ("bauxite", "alumina-exports", "alumina-imports", "alumina", "refinery"),
    ("zinc", "metal-exports", None, "zinc-metal", None),
    ("lithium", "spodumene-exports", None, "spodumene", None),
    ("thermal-coal", "allcoal-exports", "allcoal-imports", "coal", None),
]
# the customs group of a commodity's main trade table; None: the table is not customs data (EIA) and has no partners here
MAIN_GROUP = {"copper": "copper-ore", "nickel": "nickel-ore", "zinc": "zinc-ore", "lead": "lead-ore", "tin": "tin-metal",
              "phosphate": "phosphate-rock", "thermal-coal": None, "met-coal": None, "natural-gas": None}
# precious metals: declared value, not gross weight, is the basis of the partner shares (dore and bullion weigh alike)
VALUE_SHARE_GROUPS = {"gold", "silver", "pgm"}
# Extra tables of a commodity file. Every one gives lines: its section is the last word of its key (extra_section), its
# label comes from its title (extra_label) and a customs table (CEPII BACI) carries the USD value of its own rows. The
# tables below were there first: the section they name is checked against the key, and they keep their value group of the
# customs frame ("" = no value; None = the commodity's own groups) and their label.
EXTRA_SIDE = {"refined-exports": ("exports", "copper-refined", "Copper (refined & blister)"),
              "refined-imports": ("imports", "copper-refined", "Copper (refined & blister)"),
              "int-exports": ("exports", "nickel-int", "Nickel (intermediates & metal)"),
              "int-imports": ("imports", "nickel-int", "Nickel (intermediates & metal)"),
              "ferro-exports": ("exports", "nickel-fe", "Nickel (ferro-nickel & NPI)"),
              "ferro-imports": ("imports", "nickel-fe", "Nickel (ferro-nickel & NPI)"),
              "spodumene-exports": ("exports", "spodumene", "Lithium (spodumene to China, Atlas estimate)"),
              "alumina-exports": ("exports", "alumina", "Alumina"),
              "alumina-imports": ("imports", "alumina", "Alumina"),
              "metal-exports": ("exports", "zinc-metal", "Zinc (refined)"),
              "allcoal-exports": ("exports", "coal", ALL_COAL),
              "allcoal-imports": ("imports", "coal", ALL_COAL),
              "tubes-exports": ("exports", "", "Steel tubes and pipes"),
              "lignite-production": ("production", "", "Lignite (part of thermal coal)"),
              "urea-production": ("production", "", "Urea"),
              "k2o-production": ("production", "", "Potash (K2O content)"),
              # the 27 member states of the EU, beside USDA's single European Union row (FAOSTAT production, customs trade); the tables
              # are `norank` and their `world` is the EU total: the share of a line is read on `worldAll`, the world total of its source
              "eu-production": ("production", "", None), "eu-exports": ("exports", None, None), "eu-imports": ("imports", None, None)}
REFINERY_LABEL = {"copper": "Refined copper (refinery output)", "bauxite": "Alumina (refinery output)"}
SECTIONS = ("production", "refinery", "consumption", "reserves", "exports", "imports")
# sections of a profile, in the order of the page; ending stocks (USDA PSD) and capacity (EIA nuclear) come from extra tables
LINE_SECTIONS = ("exports", "imports", "production", "consumption", "reserves", "stocks", "capacity")
# the sections that "World top-10 in" counts and its sources line names (CountryView.tsx)
TOP10_SECTIONS = ("production", "exports", "imports")


def extra_section(key):
    """The profile section of an extra table, from the last word of its key: refined-exports, coke-production, stocks,
    nuclear-capacity. None for a key that names no section (the table is then left out, with a warning)."""
    last = key.rsplit("-", 1)[-1]
    return last if last in LINE_SECTIONS else None


def extra_label(title, section):
    """A line's name from its table's title: "Top consumers — motor gasoline, EIA 2025" -> "Motor gasoline", "Unwrought
    aluminium exporters: not alloyed (HS 760110)" -> "Unwrought aluminium: not alloyed (HS 760110)". None where the title
    names no product of its own ("Ending stocks"): the line then carries the commodity's name."""
    t = str(title or "").strip()
    m = re.match(r"^Top \w+ — (.*)$", t)
    t = m.group(1) if m else t.split(" — ")[0]
    t = re.split(r",\s*(?:EIA|customs data|USGS|FAOSTAT|USDA)\b", t)[0]
    t = re.sub(r"\s+\((?:included above|not LPG alone)[^)]*\)?", "", t)
    t = re.sub(r"\b(?:producers|exporters|importers|consumers|reserves)\b", "", t)
    t = re.sub(r"\s+([:,])", r"\1", re.sub(r"\s{2,}", " ", t)).strip(" ,:")
    if not t or t.lower() in ("ending stocks", "stocks", section):
        return None
    return t[0].upper() + t[1:]


def net_note(est, has_exp, has_imp):
    """The note of a net balance, which the atlas computes: what is subtracted from what, and that it is an estimate only
    when one of the two lines is."""
    n = "Exports minus imports, computed by the atlas"
    if not has_exp or not has_imp:
        n += f"; no {'exports' if not has_exp else 'imports'} line, taken as 0"
    return n + ("; an Atlas estimate, as at least one of the two lines is one" if est else "; not an estimate")


def series_at(h, iso, last_rank=None):
    """The country's series of a history table, with its rank and the world total of each year under the rules of the
    site's past-year table (web/src/lib/tableYears.ts tableAt): a value out of line with the years around it is not
    ranked, and the world total of that year leaves it out. A rank is a position in the table, not a tie-sharing rank
    (GR4D.6): the countries with the same value follow each other in the order of the history file, which is the order
    in which tableAt sorts them (a stable sort). The latest year is the latest table itself, so it takes the rank
    printed on the line (`last_rank`)."""
    vals = h["c"].get(iso)
    if not vals or not any(v for v in vals if v):
        return None
    out = h.get("out") or {}
    ranks, worlds = [], []
    for i in range(len(h["years"])):
        odd = [c for c, ix in out.items() if i in ix]
        oddv = sum(h["c"][c][i] or 0 for c in odd)
        worlds.append(round(h["world"][i] - oddv, 4) if h["world"][i] is not None else None)
        v = vals[i]
        if v is None or v <= 0 or iso in odd:
            ranks.append(None)
            continue
        ahead, seen = 0, False
        for c, s in h["c"].items():
            if c == iso:
                seen = True
            elif c not in odd and s[i] is not None and (s[i] > v or (s[i] == v and not seen)):
                ahead += 1
        ranks.append(1 + ahead)
    if last_rank is not None and ranks and ranks[-1] is not None:
        ranks[-1] = last_rank
    e = {"hv": vals, "hr": ranks}
    for key, short in (("est", "hest"), ("out", "hout"), ("brk", "hbrk"), ("srcEst", "hsrc"), ("conv", "hconv")):
        if (h.get(key) or {}).get(iso):
            e[short] = h[key][iso]
    if (h.get("cl") or {}).get(iso) and any(h["cl"][iso]):
        e["hcl"] = h["cl"][iso]
    return e, worlds


def caveat_concerns(t, iso, names):
    """Whether the warning of a table belongs on the line of `iso`. A warning about one country ("The United States is
    converted from...", "Kyrgyzstan: EIA raised its estimate...") goes on that country's line only; a table without a short
    form whose warning opens with a country's name is such a warning. Any other warning is about the whole table."""
    if t.get("caveatShort"):
        return True
    text = re.sub(r"^The ", "", str(t["caveat"]))
    about = [c for c, n in names.items() if re.match(rf"{re.escape(re.sub(r'^The ', '', n))}\b", text)]
    return not about or iso in about


def hs4_year_of(frames, latest):
    """The year of the HS4 extract (exports, imports, totals) when all three hold that one year and it is the customs
    frame's; None otherwise (an interrupted extract, another BACI version): the basket would mix two years."""
    years = {int(y) for f in frames for y in f["t"].unique()}
    return latest if years == {latest} else None


def hhi(shares):
    """Herfindahl index of a set of shares (0 to 1), on the usual scale of 0 to 10,000 (10,000: one partner only)."""
    return round(sum(s * s for s in shares) * 10000)


def partner_table(df, side, value=False):
    """{country: [(partner, amount, est), ...] largest first} of one product, for customers (side "o": the country exports)
    or suppliers (side "d")."""
    other = "d" if side == "o" else "o"
    col = "usd" if value else "t"
    g = df.groupby([side, other]).agg(v=(col, "sum"), est=("est", "max")).reset_index()
    out = defaultdict(list)
    for a, b, v, e in zip(g[side], g[other], g["v"], g["est"]):
        if v > 0:
            out[a].append((b, float(v), bool(e)))
    for a in out:
        out[a].sort(key=lambda x: -x[1])
    return out


def partner_rows(rows):
    """The first PARTNERS of one country's customers or suppliers with their shares, the Herfindahl index over every
    partner, and whether an Atlas estimate enters them."""
    tot = sum(v for _, v, _ in rows)
    if not tot:
        return None
    out = {"rows": [{"c": c, "share": round(v / tot, 4), **({"est": True} if e else {})} for c, v, e in rows[:PARTNERS]],
           "n": len(rows), "hhi": hhi([v / tot for _, v, _ in rows])}
    est = sum(v for _, v, e in rows if e)
    if est:
        out["est"] = True
        out["estShare"] = round(est / tot, 4)
    return out


def ne_text(iso, name, has_code):
    """What a country of the index is when it has no data, in Natural Earth's words, and why it has none."""
    st = NE_STATUS.get(iso)
    if st:
        typ, sov, note = st
        sov_name = SOVEREIGN_NAME.get(sov, sov)
        if "Claimed by" in note:
            claim = note.split("Claimed by ", 1)[1]
            what = (f"{name} is drawn by the base map (Natural Earth) as self-administered and claimed by {claim}" if "Self admin" in note
                    else f"{name} is drawn by the base map (Natural Earth) as an area claimed by {claim}")
        elif typ == "Disputed":
            what = f"{name} is drawn by the base map (Natural Earth) as a disputed area"
        elif "crown dependency" in note:
            what = f"{name} is drawn by the base map (Natural Earth) as a crown dependency of the United Kingdom"
        elif sov != name and typ == "Country":
            # Natural Earth's TYPE "Country" with another sovereign (Åland): its own words, not "dependency"
            what = f"{name} is listed by the base map (Natural Earth) as a country under the sovereignty of {sov_name}"
        elif sov != name and typ == "Dependency":
            what = f"{name} is drawn by the base map (Natural Earth) as a dependency of {sov_name}"
        else:
            what = f"{name} is drawn by the base map (Natural Earth) as a sovereign country"
        why = "the customs data the atlas uses (CEPII BACI) have no code of their own for it"
    else:
        what = f"{name} is a territory of the base map (Natural Earth)"
        why = "the customs data (CEPII BACI) record no trade for it in the latest year" if has_code else "the customs data (CEPII BACI) have no code for it"
    return f"{what}. It has no data in the atlas: {why}, and no table of the atlas, no lane and no asset names it."


def no_code_note(iso, name):
    """For a country of the index with data but no customs code of its own (Taiwan has one, mapped by CODE_FIX)."""
    if iso not in NE_STATUS or iso == "TWN":
        return None
    return (f"The customs data the atlas uses (CEPII BACI) have no code of their own for {name}: its trade is not shown under "
            "its name, and its lanes and partners, if any, are those of another code.")


def main():
    data = os.path.join(ROOT, "data")
    idx = load_json(os.path.join(data, "commodities", "index.json"))
    names = {c["c"]: c["name"] for c in load_json(os.path.join(data, "countries", "index.json"))}
    tables, hist = {}, {}
    for c in idx:
        p = os.path.join(data, "commodities", f"{c['id']}.json")
        if os.path.exists(p):
            tables[c["id"]] = load_json(p)
        hp = os.path.join(data, "commodities", "history", f"{c['id']}.json")
        if os.path.exists(hp):
            hist[c["id"]] = load_json(hp)["t"]
    baci = pd.read_csv(os.path.join(CACHE, "baci_flows.csv.gz"))
    raw_baci = baci
    baci = baci.assign(o=baci["o"].replace(CODE_FIX), d=baci["d"].replace(CODE_FIX))
    latest = int(baci["year"].max())
    b = baci[baci["year"] == latest]
    exp_usd = b.groupby(["o", "group"])["usd"].sum()
    imp_usd = b.groupby(["d", "group"])["usd"].sum()

    def usd(series, iso, k):
        groups = VALUE_GROUPS.get(k, [k])
        return float(sum(series.get((iso, g), 0.0) for g in groups)) * 1000  # thousand USD -> USD

    profiles = {}

    def prof(iso):
        return profiles.setdefault(iso, {"c": iso, **{sec: [] for sec in LINE_SECTIONS}})

    years_of = {}  # history key -> {"y": years, "l": labels, "w": world per year}

    # ---- lines: every row of every table
    lines = []  # (iso, section, entry, table key)
    for k, d in tables.items():
        sections = [(sec, d.get(sec), None, None, sec) for sec in SECTIONS]
        for ex in d.get("extra") or []:
            side = extra_section(ex["key"])
            if side is None:
                print(f"WARNING: {k} extra table {ex['key']}: its key names no section, left out")
                continue
            if ex["key"] in EXTRA_SIDE:
                listed, grp, label = EXTRA_SIDE[ex["key"]]
                assert listed == side, (k, ex["key"])
            else:
                # a customs table carries the value of its own rows; another source's table has none
                grp, label = ("row" if ex["table"].get("s") == "baci" else ""), extra_label(ex.get("title"), side)
            sections.append((side, ex["table"], grp, label, ex["key"]))
        for section, t, grp, label, tkey in sections:
            if not t or not t.get("rows"):
                continue
            world = t.get("worldAll") or t.get("world") or sum(r["v"] for r in t["rows"])
            h = (hist.get(k) or {}).get(tkey)
            hk = f"{k}/{tkey}"
            for i, r in enumerate(t["rows"]):
                share = r["v"] / world if world else None
                e = {"k": k, "v": r["v"], "u": t["u"], "share": round(share, 4) if share else None, "rank": i + 1,
                     "y": r.get("y", t["y"]), "s": r.get("s", t["s"])}
                if r.get("est") or t["s"] == "atlas":
                    # most of the row's tonnage is an Atlas estimate, or the table is the atlas's own: the row is credited
                    # to the atlas. A table that only converts a published figure to another unit ("Atlas conversion") is
                    # not an estimate and carries no estimate mark.
                    e["s"] = "atlas"
                    if r.get("est") or not str(t.get("n") or "").startswith("Atlas conversion"):
                        e["est"] = True
                lab = label or (REFINERY_LABEL.get(k) if section == "refinery" else PRODUCTION_LABEL.get(k) if section == "production" else
                                TRADE_LABEL.get(k) if section in ("exports", "imports") else None)
                if lab:
                    e["label"] = lab
                if t.get("basis"):
                    e["basis"] = t["basis"]
                if t.get("scopeLabel"):
                    e["scope"] = t["scopeLabel"]  # a table of part of the world (the EU member states): the line says so
                if section in ("exports", "imports") and grp == "row":
                    val = float(r.get("usd") or 0)
                elif section in ("exports", "imports") and grp != "":
                    series = exp_usd if section == "exports" else imp_usd
                    val = float(series.get((r["c"], grp), 0.0)) * 1000 if grp else usd(series, r["c"], k)
                else:
                    val = 0
                if val:
                    # the value has its own source and year, whatever the tonnage comes from
                    e["usd"], e["usdS"], e["usdY"] = round(val / 1e9, 3), "baci", int(t["y"]) if grp == "row" else latest
                if r.get("n"):
                    e["n"] = r["n"]
                if r.get("conv"):
                    e["conv"] = True  # the row is the atlas's conversion of the source's figure (EIA LPG, United States): the line says so
                if t.get("caveat") and caveat_concerns(t, r["c"], names):
                    e["warn"] = t.get("caveatShort") or t["caveat"]  # warning of the whole table (trade hubs, gross weight...), short form for a profile row
                if t.get("norank"):
                    e["_norank"] = True  # the order of the table is not a world ranking (LNG customs tonnage): no rank is printed
                e["t"] = tkey
                if h:
                    sa = series_at(h, r["c"], i + 1)
                    if sa:
                        ser, worlds = sa
                        e.update(ser)
                        e["hk"] = hk
                        if hk not in years_of:
                            years_of[hk] = {"y": h["years"], "w": worlds, **({"l": h["labels"]} if h.get("labels") else {})}
                lines.append((r["c"], "production" if section == "refinery" else section, e, tkey))

    top10 = {}
    for iso, section, e, _ in lines:
        # the same lines as the KPI's sources line on the page: production (with refinery output), exports and imports
        if section in TOP10_SECTIONS and e["rank"] <= TOP_RANK and not e.get("_norank"):
            top10.setdefault(iso, set()).add(e["k"])
        if e.get("_norank"):
            e.pop("rank", None)
            e.pop("hr", None)
        e.pop("_norank", None)
        prof(iso)[section].append(e)

    def by_value(rows):
        # thermal and metallurgical coal carry no value of their own: they follow the all-coal row
        coal = next((e["usd"] for e in rows if e.get("label") == ALL_COAL and e.get("usd")), None)

        def key(e):
            v = e.get("usd") or 0
            if not v and coal and e["k"] in COAL:
                return (-coal, 1, -(e["share"] or 0))
            return (-v, 0, -(e["share"] or 0))
        return sorted(rows, key=key)

    for iso, p in profiles.items():
        p["exports"] = by_value(p["exports"])
        p["imports"] = by_value(p["imports"])
        for sec in ("production", "consumption", "reserves", "stocks", "capacity"):
            p[sec] = sorted(p[sec], key=lambda e: -(e["share"] or 0))
        if top10.get(iso):
            p["top10"] = len(top10[iso])

    # ---- reserves over production, where both are USGS lines of the same unit (years at the latest production rate)
    for iso, p in profiles.items():
        prod = {e["k"]: e for e in p["production"] if e.get("t") == "production"}
        for e in p["reserves"]:
            q = prod.get(e["k"])
            if q and q["u"] == e["u"] and q["s"] == e["s"] and q["v"]:
                e["rp"] = round(e["v"] / q["v"], 1)
                e["rpY"] = q["y"]

    # ---- basket: largest exports and imports at HS4 (every chapter) and raw materials outside the catalogue
    hs4_year = None
    hs4p, hs4i, hs4t = (os.path.join(CACHE, f) for f in ("hs4_exports.csv.gz", "hs4_imports.csv.gz", "hs4_totals.csv"))
    if all(os.path.exists(f) for f in (hs4p, hs4i, hs4t)):
        he = pd.read_csv(hs4p, dtype={"hs4": str})
        hi = pd.read_csv(hs4i, dtype={"hs4": str})
        tot = pd.read_csv(hs4t)
        hs4_year = hs4_year_of((he, hi, tot), latest)
        if hs4_year is None:
            print(f"WARNING: HS4 extract years {sorted({int(y) for f in (he, hi, tot) for y in f['t'].unique()})} against customs "
                  f"frame of {latest}: basket and other headings left out")
    if hs4_year is not None:
        desc = pd.read_csv(os.path.join(CACHE, "hs4_exports_desc.csv"), dtype=str).groupby("hs4")["description"].apply(list).to_dict()
        codes = catalogue_hs()
        head_k = defaultdict(set)  # HS4 heading -> atlas commodities whose codes sit under it
        group_k = dict(GROUP_K)
        for f in glob.glob(os.path.join(data, "freight", "pairs", "*.json")):
            pf = load_json(f)
            group_k[pf["group"]] = pf["k"]
        for g, lst in HS.items():
            k = group_k.get(g, g if g in tables else None)
            for c in lst:
                c = c.rstrip("*")
                heads = {c[:4]} if len(c) >= 4 else {h for h in desc if h.startswith(c)}
                for hd in heads:
                    head_k[hd].add(k)

        def label_of(hs4):
            name, detail = heading_name(desc.get(hs4, []))
            return name or f"HS {hs4}", detail

        for frame, who, side in ((he, "o", "exports"), (hi, "d", "imports")):
            frame = frame[frame[who].notna()].assign(**{who: frame[who].replace(CODE_FIX)})
            totals = tot.assign(c=tot["c"].replace(CODE_FIX)).set_index("c")[side]
            for iso, g in frame.groupby(who):
                total = float(totals.get(iso, 0) or 0)
                if not total:
                    continue
                top = g.sort_values("usd", ascending=False).head(BASKET_ROWS)
                rows = []
                for r in top.itertuples():
                    lab, detail = label_of(r.hs4)
                    ks = head_k.get(r.hs4) or set()
                    row = {"hs4": r.hs4, "label": lab, "usd": round(r.usd / 1e6, 3), "share": round(r.usd / total, 4)}
                    # one atlas commodity under the heading; not coal, which customs codes do not split into thermal and metallurgical
                    if len(ks) == 1 and None not in ks and not ks & set(COAL):
                        row["k"] = next(iter(ks))
                    if detail:
                        row["d"] = detail[:200]  # the first parts of its subheadings, when the name lists several
                    rows.append(row)
                prof(iso).setdefault("basket", {"y": hs4_year, "s": "baci"})[side] = {"total": round(total / 1e6, 3), "rows": rows}
        # raw materials outside the catalogue (the "country check": diamonds for Botswana, logs for Gabon)
        raw = he[he["o"].notna() & he["hs4"].str[:2].isin(RAW_CHAPTERS)]
        raw = raw.assign(o=raw["o"].replace(CODE_FIX))
        world_hs4 = raw.groupby("hs4")["usd"].sum()
        rank_hs4 = raw.assign(r=raw.groupby("hs4")["usd"].rank(ascending=False, method="min")).set_index(["o", "hs4"])["r"]
        for iso, g in raw.groupby("o"):
            total = g["usd"].sum()
            if total < OTHER_MIN_TOTAL:  # < USD 200 million of exports from these chapters: skip
                continue
            out = []
            for r in g.sort_values("usd", ascending=False).itertuples():
                if len(out) >= OTHER_ROWS or r.usd / total < OTHER_MIN_SHARE:
                    break
                if covered(r.hs4, codes):
                    continue
                lab, _ = label_of(r.hs4)
                out.append({"k": f"hs{r.hs4}", "label": lab, "v": round(r.usd / 1e6, 2), "u": "bn USD exports",
                            "share": round(r.usd / world_hs4[r.hs4], 4), "rank": int(rank_hs4.get((iso, r.hs4), 0)) or None,
                            "y": hs4_year, "s": "baci", "n": f"{r.usd / total:.0%} of the country's exports from these chapters (HS {r.hs4})"})
            if out:
                prof(iso)["other"] = out

    # ---- partners and balance
    pairs_dir = os.path.join(data, "freight", "pairs")
    pair_frames, pair_meta = {}, {}
    for f in sorted(glob.glob(os.path.join(pairs_dir, "*.json"))):
        pf = load_json(f)
        cols = pf["cols"]
        rows = [dict(zip(cols, r)) for r in pf["rows"]]
        df = pd.DataFrame(rows)
        df["t"] = df["kt"] * 1000.0
        df["est"] = (df["f"].astype(int) & 1).astype(bool)
        pair_frames[pf["group"]] = df
        pair_meta[pf["group"]] = pf
    other_groups = sorted(set(GROUP_K) - set(pair_frames))
    cf = clean(raw_baci[raw_baci["group"].isin(other_groups)])
    cf = cf[cf["year"] == latest].assign(est=lambda x: x["imputed"].astype(bool))
    clean_frames = {g: x for g, x in cf.groupby("group")}

    def group_frame(g):
        return pair_frames.get(g) if g in pair_frames else clean_frames.get(g)

    def products():
        out = []
        for k in tables:
            g = MAIN_GROUP.get(k, k)
            out.append((k, "exports", "imports", g, "production"))
        return out + PRODUCTS

    for k, ek, ik, g, prod_key in products():
        d = tables.get(k) or {}
        etab = d.get(ek) or next((x["table"] for x in d.get("extra") or [] if x["key"] == ek), None)
        itab = (d.get(ik) or next((x["table"] for x in d.get("extra") or [] if x["key"] == ik), None)) if ik else None
        prod_tab = d.get(prod_key) if prod_key else None
        frame = group_frame(g) if g else None
        if frame is not None:
            value = g in VALUE_SHARE_GROUPS
            ptab = {side: partner_table(frame, side, value) for side in ("o", "d")}
        isos = set()
        for t in (etab, itab):
            isos |= {r["c"] for r in (t or {}).get("rows", [])}
        for iso in isos:
            if iso not in profiles:
                continue
            p = profiles[iso]
            el = next((e for e in p["exports"] if e["k"] == k and e["t"] == ek), None)
            il = next((e for e in p["imports"] if e["k"] == k and e["t"] == ik), None) if ik else None
            line = el or il
            row = {"k": k, "t": ek}
            if line.get("label"):
                row["label"] = line["label"]
            if etab and itab and etab["u"] == itab["u"] and str(etab["y"]) == str(itab["y"]):
                ev, iv = (el or {}).get("v", 0.0), (il or {}).get("v", 0.0)
                est = bool((el or {}).get("est") or (il or {}).get("est"))
                # an estimated line holds three significant digits: the difference does not hold more (115 t less 0.0415 t is 115 t)
                net = float(f"{ev - iv:.3g}") if est else round(ev - iv, 4)
                row["net"] = {"v": net, "exp": ev if el else None, "imp": iv if il else None, "u": etab["u"],
                              "y": etab["y"], "s": (el or il)["s"], **({"est": True} if est else {}),
                              "n": net_note(est, bool(el), bool(il))}
            cons = next((e for e in p["consumption"] if e["k"] == k and e["t"] == "consumption"), None) if ek == "exports" else None
            # only against a consumption figure a source publishes: the atlas's apparent consumption (production + imports -
            # exports, steel) holds the imports already, and the ratio would measure nothing
            if cons and (cons["s"] == "atlas" or cons.get("est")):
                cons = None
            if il and cons and il["u"] == cons["u"] and str(il["y"]) == str(cons["y"]) and cons["v"] and round(il["v"] / cons["v"], 4) > 0:
                row["dep"] = {"v": round(il["v"] / cons["v"], 4), "y": il["y"], "s": il["s"], "u": il["u"], "imp": il["v"], "cons": cons["v"]}
            if frame is not None:
                for side, key in (("o", "customers"), ("d", "suppliers")):
                    pr = partner_rows(ptab[side].get(iso, []))
                    if pr:
                        row[key] = {**pr, "g": g, "y": latest, "s": "baci", **({"basis": "declared value"} if value else {})}
            # trading or refining hub: a derived label, where the atlas's own data show it
            full = prod_tab is not None and prod_tab.get("s") in FULL_PRODUCTION_SOURCES and not prod_tab.get("other")
            if full and el and il and (el.get("share") or 0) >= HUB_MIN_SHARE and (il.get("share") or 0) >= HUB_MIN_SHARE:
                if not any(r["c"] == iso for r in prod_tab.get("rows", [])):
                    row["hub"] = {"exp": el["share"], "imp": il["share"], "prodS": prod_tab["s"], "prodY": prod_tab["y"]}
            if len(row) > 3 or (len(row) == 3 and "label" not in row):
                p.setdefault("balance", []).append(row)

    # ---- freight: mode split, typical ports and passages, from the pairs tables of the engine
    # The "up to" of a passage and a group, as its chokepoint page prints it (data/freight/chokepoints.json `estimates`,
    # `mt`): where the engine caps it at IMF PortWatch's count of all ships through the passage (or prints no entry), the
    # tonnes a country's routes may add are not all there, and its "up to" for that passage and group is not printed.
    published = {}
    for c in load_json(os.path.join(data, "freight", "chokepoints.json")):
        for est in c.get("estimates") or []:
            published[(c["id"], est["p"])] = est["mt"][1]
    upto_ok = {}  # (gate, group) -> the country's "up to" may be printed
    for g, df in pair_frames.items():
        sea_rows = df[df["m"].isin([0, 1])]
        vm, am, kt = (sea_rows[c].to_numpy() for c in ("via", "alt", "kt"))
        for gi, gate in enumerate(pair_meta[g]["gates"]):
            must = (vm.astype("int64") >> gi) & 1 == 1
            may = ((am.astype("int64") >> gi) & 1 == 1) & ~must
            high = float(kt[must].sum() + kt[may].sum()) / 1000  # Mt, uncapped, every origin
            pub = published.get((gate, g))
            upto_ok[(gate, g)] = pub is not None and pub >= high - (0.06 + 0.001 * high)

    def passage(gate, low, high, ok, sea):
        """One passage of a country's seaborne tonnes (kt): "at least" and, where the passage page allows it, "up to";
        listed under the engine's floor on the printed figure (2% of these tonnes, or 1 Mt)."""
        shown = high if ok else low
        if not (shown / sea >= PASSAGE_MIN_SHARE or shown >= PASSAGE_MIN_KT):
            return None
        v = {"id": gate, "low": round(low / sea, 4), "high": round(shown / sea, 4)}
        if not ok and high - low >= 0.5:
            v["capped"] = True  # no "up to": the passage page caps its own at IMF PortWatch
        return v

    for g, df in pair_frames.items():
        pf = pair_meta[g]
        ports, bases = pf["ports"], pf.get("bases") or []
        gates = pf["gates"]
        for side, port_col in (("o", "load"), ("d", "dis")):
            for iso, mine in df.groupby(side):
                if iso not in profiles and iso not in names:
                    continue
                total = float(mine["kt"].sum())
                if total <= 0:
                    continue
                modes = {m: float(mine.loc[mine["m"] == i, "kt"].sum()) for i, m in enumerate(("sea", "transit", "mixed", "land"))}
                sea_rows = mine[mine["m"].isin([0, 1])]
                sea = float(sea_rows["kt"].sum())
                # a group that is an Atlas estimate as a whole (spodumene, read from HS 253090) is an estimate on every row and is
                # credited to the atlas, like its lines; the block's own source stays customs data for the other groups
                whole = pf.get("s") == "atlas"
                x = {"g": g, "k": pf["k"], "kt": round(total, 1), "modes": {m: round(v / total, 4) for m, v in modes.items() if v},
                     **({"est": True} if whole or bool(mine["est"].any()) else {}), **({"s": "atlas"} if whole else {})}
                if not whole and bool(mine["est"].any()):  # a total with an estimated part prints in full and says how much (GR4S.12)
                    x["estKt"] = round(float(mine.loc[mine["est"], "kt"].sum()), 1)
                if sea > 0:
                    routed = sea_rows[sea_rows[port_col] >= 0]
                    unrouted = sea - float(routed["kt"].sum())
                    if unrouted >= 0.5:
                        x["unrouted"] = round(unrouted / sea, 4)
                    by_port = routed.groupby(port_col)["kt"].sum().sort_values(ascending=False)
                    pl = []
                    for pi, v in by_port.head(PORTS).items():
                        pr = ports[int(pi)]
                        bi = pr[5] if port_col == "dis" and len(pr) > 5 else pr[4]
                        pl.append({"name": pr[1], "c": pr[2], "share": round(float(v) / sea, 4),
                                   **({"basis": bases[bi]} if bi is not None and bi < len(bases) else {})})
                    x["ports"] = pl
                    via, every = [], {}
                    vm, am, kt = (sea_rows[c].to_numpy() for c in ("via", "alt", "kt"))
                    for gi, gate in enumerate(gates):
                        must = (vm.astype("int64") >> gi) & 1 == 1
                        may = ((am.astype("int64") >> gi) & 1 == 1) & ~must
                        low, high = float(kt[must].sum()), float(kt[must].sum() + kt[may].sum())
                        if high:
                            every[gate] = (low, high, upto_ok.get((gate, g), False))
                            v = passage(gate, low, high, every[gate][2], sea)
                            if v:
                                via.append(v)
                    x["via"] = sorted(via, key=lambda v: (-v["low"], -v["high"]))
                    x["_every"] = every
                    x["seaKt"] = round(sea, 1)
                fr = prof(iso).setdefault("freight", {"y": int(pf["y"]), "s": "baci", "exports": [], "imports": []})
                fr["exports" if side == "o" else "imports"].append(x)
    for p in profiles.values():
        fr = p.get("freight")
        if not fr:
            continue
        for side in ("exports", "imports"):
            rows = sorted(fr[side], key=lambda x: -x["kt"])
            fr[side] = rows
            sea = sum(x.get("seaKt", 0) for x in rows)
            allkt = sum(x["kt"] for x in rows)
            if not allkt:
                continue
            tot = {"kt": round(allkt, 1), "sea": round(sum(x["kt"] * (x["modes"].get("sea", 0) + x["modes"].get("transit", 0)) for x in rows) / allkt, 4),
                   "mixed": round(sum(x["kt"] * x["modes"].get("mixed", 0) for x in rows) / allkt, 4)}
            if sea:
                low, high, ok = defaultdict(float), defaultdict(float), defaultdict(lambda: True)
                for x in rows:
                    for gid, (lo, hi, up) in x.get("_every", {}).items():
                        low[gid] += lo
                        high[gid] += hi
                        if hi - lo >= 0.5 and not up:
                            ok[gid] = False  # one group without its "up to": the sum has none either
                tot["seaKt"] = round(sea, 1)
                tot["via"] = sorted(filter(None, (passage(gid, low[gid], high[gid], ok[gid], sea) for gid in high)),
                                    key=lambda v: (-v["low"], -v["high"]))
            fr[side + "Total"] = tot
        for side in ("exports", "imports"):
            for x in fr[side]:
                x.pop("_every", None)

    # ---- gaps: what customs data miss for this origin (caveats of the engine)
    cav_path = os.path.join(data, "freight", "caveats.json")
    if os.path.exists(cav_path):
        gk = {g: m["k"] for g, m in pair_meta.items()}
        for cid, cv in load_json(cav_path).items():
            if cv.get("d") is None and cv.get("o"):
                p = prof(cv["o"])
                p.setdefault("gaps", []).append({"id": cid, "k": gk.get(cv["group"], GROUP_K.get(cv["group"], cv["group"])), "g": cv["group"],
                                                 "kind": cv["kind"], "text": cv["text"]})

    # ---- infrastructure, operators and companies
    by_country, operators = {}, defaultdict(lambda: defaultdict(set))
    for f in sorted(glob.glob(os.path.join(data, "infrastructure", "*.geojson"))):
        for ft in load_json(f)["features"]:
            pr = ft["properties"]
            for iso in {pr.get("c")} | set(pr.get("cs") or []):
                if iso:
                    by_country.setdefault(iso, {}).setdefault(pr["type"], []).append(f"{pr['type']}:{pr['id']}")
                    if pr.get("operator"):
                        operators[iso][pr["operator"]].add(f"{pr['type']}:{pr['id']}")
    TYPE_ORDER = ["field", "refinery", "lng-export", "mine", "pipeline", "port", "smelter", "lng-import"]
    for iso, types in by_country.items():
        # No ranking here: capacities come in different units (kb/d, Mt/y, kt/y...) and a raw number says nothing across
        # them. The page ranks the assets among comparable figures (web/src/components/views/InfraList.tsx).
        queues = [sorted(types[t]) for t in TYPE_ORDER if t in types] + [sorted(types[t]) for t in sorted(types) if t not in TYPE_ORDER]
        ordered = []
        while any(queues):  # one asset per type in turn: every type is represented
            for q in queues:
                if q:
                    ordered.append(q.pop(0))
        p = prof(iso)
        p["infra"] = ordered
        if operators.get(iso):
            p["operators"] = sorted(({"name": n, "assets": sorted(a)} for n, a in operators[iso].items()), key=lambda o: (-len(o["assets"]), o["name"]))
    cp = os.path.join(data, "commodities", "companies.json")
    if os.path.exists(cp):
        found = {}
        role_rank = {"producers": 0, "processors": 1, "traders": 2}
        order = 0
        for k, groups in load_json(cp).items():
            for role in ("producers", "processors", "traders"):
                for co in groups.get(role) or []:
                    iso = co.get("hq")
                    if not iso:
                        continue
                    key = (iso, co["name"])
                    if key not in found:
                        found[key] = ({k2: co[k2] for k2 in ("name", "hq", "role", "detail", "s", "y", "url") if k2 in co} | {"k": []},
                                      role_rank[role], order)
                        order += 1
                    if k not in found[key][0]["k"]:
                        found[key][0]["k"].append(k)
        for (iso, _), (co, rr, o) in sorted(found.items(), key=lambda x: (-len(x[1][0]["k"]), x[1][1], x[1][2])):
            prof(iso).setdefault("companies", []).append(co)

    # ---- the EU: member states and the EU27 aggregate of USDA PSD link to each other
    if "EU27" in profiles:
        profiles["EU27"]["members"] = EU27
        for iso in EU27:
            prof(iso)["eu"] = "EU27"

    # ---- write: one file per country of the index, and the years of the series (one file for every country)
    has_code = set(pd.read_csv(os.path.join(CACHE, "baci_country_codes.csv"), dtype=str)["country_iso3"].dropna()) | {"TWN"}
    os.makedirs(OUT_DIR, exist_ok=True)
    written, size, used = set(), 0, set()
    for iso in sorted(set(names) | {c for c in profiles if c == "EU27"}):
        p = profiles.get(iso)
        if p is None:
            p = {"c": iso, "none": ne_text(iso, names.get(iso, iso), iso in has_code)}
        else:
            note = no_code_note(iso, names.get(iso, iso))
            if note:
                p["noCode"] = note
            for sec in LINE_SECTIONS:
                for e in p[sec]:
                    e.pop("t", None)
                    if e.get("hk"):
                        used.add(e["hk"])
                if not p[sec] and sec in ("stocks", "capacity"):
                    del p[sec]
        path = os.path.join(OUT_DIR, f"{iso}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(p, fh, separators=(",", ":"), ensure_ascii=False)
        written.add(iso)
        size += os.path.getsize(path)
    for f in glob.glob(os.path.join(OUT_DIR, "*.json")):  # a code that left the index keeps no file
        if os.path.basename(f)[:-5] not in written:
            os.remove(f)
    stray = sorted(set(profiles) - written)
    if stray:
        print("WARNING: profiles for codes outside the index, not written:", stray)
    # the years and world totals of a series are the same on every country's page: written once, not in each file
    out = os.path.join(data, "countries", "years.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({hk: years_of[hk] for hk in sorted(used)}, fh, separators=(",", ":"), ensure_ascii=False)
    old_index = os.path.join(data, "countries", "profiles.json")  # the light index of the first version: the site never read it
    if os.path.exists(old_index):
        os.remove(old_index)
    with_data = sum(1 for iso in written if iso in profiles)
    print(f"profiles {with_data} with data, {len(written) - with_data} without; files {size / 1024:.0f} KB in all, "
          f"largest {max(os.path.getsize(f) for f in glob.glob(os.path.join(OUT_DIR, '*.json'))) / 1024:.0f} KB; "
          f"years {os.path.getsize(out) / 1024:.0f} KB")

if __name__ == "__main__":
    main()
