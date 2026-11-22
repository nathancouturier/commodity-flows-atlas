"""
The mode of a trade flow: sea, transit (sea through a foreign port), mixed (sea and overland, split not known) or land.

    modes.mode_of(o, d, group, year=None) -> Mode(kind, basis, note, url)   None when the group has no cargo family
                                                                          (gold, silver, PGM)

The rules apply in this order and the first that matches wins (PLAN.md 2.1):
  1. FLOW_OVERRIDES   single flows, keyed by (group, origin, destination)
  2. pseudo-places    an end such as "Asia, not specified" is seaborne by assumption and is never routed
  3. LNG              product rule: sea between coastal countries, but pipeline gas declared as LNG stays land
  4. MIXED            ordered country pairs whose cargo family moves both by sea and overland
  5. land neighbours  mainland border: land, unless the pair is in SEA_NEIGHBOURS for the cargo family
  6. sea outlet       a landlocked exporter in SEA_OUTLET for the group: transit, to a coastal or a landlocked buyer
                      (Kazakh crude to Austria leaves by the CPC pipeline and sails), unless the buyer is landlocked and
                      in one of its overland blocs (land)
  7. two landlocked   land
  8. one landlocked   transit when the two countries share no overland bloc (BLOCS), else land
  9. default          sea

Every list entry (SEA_NEIGHBOURS, LAND_NOTES, MIXED, SEA_OUTLET, BLOCS, FLOW_OVERRIDES) is an Atlas assumption: it
carries a reason and, where a page was read, its URL (Wikipedia, read on 22 November 2026), returned as Mode.url. An
entry without a URL is an unsourced Atlas assumption. No entry rests on a figure typed from memory.
LNG: with `year`, a liquefaction terminal of the layer counts only from its `opened` year (Coral Sul, Mozambique, 2022).
Without it every terminal of the layer counts, opened or not; the layer is hand-built and may miss real plants (K11
lists the LNG exporters it lacks, Brunei among them).
This module reads pipeline/cache/adjacency.json and data/infrastructure/lng.geojson itself. It imports neither
build_lanes nor ports, so that any builder can use it. It does not return a port: the transit port of a landlocked
country is gateway data.
"""
import json
import os
from collections import namedtuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

Mode = namedtuple("Mode", "kind basis note url", defaults=(None, None))
Entry = namedtuple("Entry", "families reason url", defaults=(None,))

ALL = "*"

# ------------------------------------------------------------------ geography (built by pipeline/geo/adjacency.py)
_ADJ = json.load(open(os.path.join(ROOT, "pipeline", "cache", "adjacency.json")))
COASTAL = frozenset(_ADJ["coastal"])
NEIGHBOURS = {k: frozenset(v) for k, v in _ADJ["neighbours"].items()}
PSEUDO = frozenset(p["c"] for p in _ADJ.get("extra", []) if p.get("pseudo"))
OVERSEAS_BORDERS = {
    frozenset(p): Entry(None, _ADJ.get("overseasWhy", {}).get("-".join(p), "")) for p in _ADJ.get("overseas", [])
}

# countries with a liquefaction terminal in the atlas's own layer (GIIGNL, data/infrastructure/lng.geojson)
with open(os.path.join(ROOT, "data", "infrastructure", "lng.geojson"), encoding="utf-8") as _f:
    _LNG = [f["properties"] for f in json.load(_f)["features"] if f["properties"]["type"] == "lng-export"]
LNG_EXPORTERS = frozenset(p["c"] for p in _LNG)
# country -> year of its first liquefaction terminal (None: a terminal of the layer without an opening year)
LNG_OPENED = {}
for _p in _LNG:
    _y = _p.get("opened")
    _y = int(_y) if isinstance(_y, (int, float)) or (isinstance(_y, str) and _y.isdigit()) else None
    if _p["c"] not in LNG_OPENED:
        LNG_OPENED[_p["c"]] = _y
    elif _y is None or LNG_OPENED[_p["c"]] is None:
        LNG_OPENED[_p["c"]] = None
    else:
        LNG_OPENED[_p["c"]] = min(_y, LNG_OPENED[_p["c"]])


def lng_exporter(c, year=None):
    """Whether country c has a liquefaction terminal in the layer (in year, when given)."""
    if c not in LNG_OPENED:
        return False
    return year is None or LNG_OPENED[c] is None or LNG_OPENED[c] <= year

# ------------------------------------------------------------------ cargo families
FAMILY = {
    "crude-oil": "crude", "refined-products": "products", "lpg": "lpg", "lng": "lng",
    "iron-ore": "drybulk", "coal": "drybulk", "bauxite": "drybulk", "alumina": "drybulk", "manganese": "drybulk",
    "copper-ore": "drybulk", "nickel-ore": "drybulk", "zinc-ore": "drybulk",
    "wheat": "grain", "corn": "grain", "soybeans": "grain", "soymeal": "grain", "rice": "grain", "sugar": "grain",
    "rapeseed": "grain",
    "soyoil": "vegoil", "palm-oil": "vegoil",
    "potash": "fert", "phosphate-rock": "fert", "dap": "fert", "urea": "fert",
    "steel": "metal", "copper-refined": "metal", "aluminium": "metal", "nickel-int": "metal",
    "coffee": "soft", "cocoa": "soft", "cotton": "soft",
    # groups outside the lane model (M-100): the same geographic rule as the metals
    "uranium": "metal", "lithium": "metal", "cobalt": "metal", "rare-earths": "metal",
    "tin-ore": "metal", "tin-metal": "metal", "lead-ore": "metal", "lead-metal": "metal", "zinc-metal": "metal",
}
# Deliberately without a family, so without a mode: gold, silver and platinum-group metals. The audit suggests air
# freight but no source was read; a badge would be a published claim.
NO_MODE = frozenset({"gold", "silver", "pgm"})


def family_of(group):
    return FAMILY.get(group)


def _pair(a, b):
    return frozenset((a, b))


# ------------------------------------------------------------------ 1. single flows
FlowOverride = namedtuple("FlowOverride", "kind reason url", defaults=(None,))
FLOW_OVERRIDES = {
    ("iron-ore", "BRA", "ARG"): FlowOverride(
        "land",
        "Corumba ore goes down the Paraguay-Parana waterway on barges to Argentina; the atlas draws no ocean lane for it",
        "https://en.wikipedia.org/wiki/Paran%C3%A1%E2%80%93Paraguay_Waterway",
    ),
    # LNG Mozambique to South Africa (0.70 Mt in 2024, tonnage estimated from value) is probably the Pande-Temane gas
    # pipeline. Left out: no page was read that confirms it (PLAN.md 2.1).
}

# ------------------------------------------------------------------ 5. neighbours whose trade sails
# unordered pair -> families ("*" = every family). Pairs that share a land border but trade by sea.
_SEA_PAIRS = [
    # kept from the previous list, for every family
    (("IDN", "MYS"), ALL, "Land border on Borneo only; the trade crosses the Malacca and Singapore straits from Sumatra and Java"),
    (("MYS", "SGP"), ALL, "Johor to Singapore cargo sails from Johor ports (Pasir Gudang, Pengerang); the land link is two causeways"),
    (("ARG", "BRA"), ALL, "The border follows rivers and a forest region; the bulk trade runs between Atlantic ports"),
    (("ARG", "URY"), ALL, "The border is the River Plate and the Uruguay river; trade runs between river and Atlantic ports"),
    (("BRA", "URY"), ALL, "Bulk trade runs between Atlantic and River Plate ports"),
    (("CHN", "VNM"), ALL, "Mountain and jungle border; the bulk trade sails between south China and Vietnamese ports"),
    (("SAU", "ARE"), ALL, "Desert border with few crossings; trade sails across the Gulf and from Red Sea ports"),
    (("SAU", "KWT"), ALL, "Gulf ports carry the bulk trade"),
    (("NOR", "SWE"), ALL, "Bulk trade runs between coastal terminals"),
    (("CHL", "PER"), ALL, "Desert border; bulk trade runs between Pacific ports"),
    (("COL", "VEN"), ALL, "Bulk trade runs between Caribbean ports"),
    (("EGY", "LBY"), ALL, "Desert border; bulk trade runs between Mediterranean ports"),
    (("TUR", "GRC"), ALL, "Bulk trade runs between Aegean and Mediterranean ports"),
    (("THA", "MYS"), ALL, "Bulk trade runs between ports on the Gulf of Thailand and the Malacca Strait"),
    (("PNG", "IDN"), ALL, "Land border on New Guinea in jungle; the trade runs between ports"),
    (("RUS", "FIN"), ALL, "Bulk trade runs between Baltic ports (Ust-Luga, Primorsk) and Finnish ports"),
    # added: the border is a mountain range, a jungle, a desert, an estuary or the far north (PLAN.md 2.1)
    (("IND", "CHN"), ALL, "The border runs along the Himalaya with three border trade points; Indian iron ore sails from east-coast ports to China",
     "https://en.wikipedia.org/wiki/China%E2%80%93India_border"),
    (("CHN", "PAK"), ALL, "Karakoram border with a single pass; trade sails from Chinese ports to Karachi"),
    (("COL", "PAN"), ALL, "No road crosses the Darien gap; Colombian crude sails to Panama"),
    (("NOR", "FIN"), ALL, "Far-north border with few crossings; crude and LNG sail from Norwegian terminals"),
    (("SWE", "FIN"), ALL, "Iron ore and products sail across the Gulf of Bothnia from Lulea and Swedish ports"),
    (("BRA", "COL"), ALL, "Amazon border with no road trade; coal sails from the Colombian Caribbean coast"),
    (("BRA", "PER"), ALL, "Amazon border with no road trade; Peruvian cargo sails from Pacific ports"),
    (("BRA", "VEN"), ALL, "Jungle border; Venezuelan cargo sails from Caribbean ports"),
    (("BRA", "GUY"), ALL, "Jungle border; Guyanese crude is loaded offshore and sails"),
    (("BRA", "SUR"), ALL, "Jungle border; trade runs between ports"),
    (("MYS", "BRN"), ALL, "Brunei crude and products sail from its coast terminals"),
    (("ECU", "PER"), {"crude"}, "Ecuadorian crude sails from Esmeraldas to Peruvian Pacific ports; other cargo is overland"),
    (("GBR", "IRL"), ALL, "The only land border is in Northern Ireland; trade crosses the Irish Sea"),
    (("MRT", "DZA"), ALL, "Desert border; Mauritanian iron ore sails from Nouadhibou"),
    (("CHN", "HKG"), ALL, "Hong Kong is a port; trade with mainland China moves by sea and river"),
    # narrowed to the cargo that sails
    (("USA", "MEX"), {"crude"}, "Mexican crude sails to US Gulf refineries; other cargo is mixed or overland (see MIXED)"),
    (("ESP", "FRA"), {"crude", "products", "lpg"}, "Liquid cargo sails between ports of the two coasts; grain is mixed (see MIXED)"),
    (("ESP", "PRT"), {"crude", "products", "lpg"}, "Liquid cargo sails between ports; other cargo is overland"),
]
SEA_NEIGHBOURS = {
    _pair(*e[0]): Entry(ALL if e[1] == ALL else frozenset(e[1]), e[2], e[3] if len(e) > 3 else None) for e in _SEA_PAIRS
}

# Land neighbours whose overland route has a note (returned as the Mode note): pairs that were "sea" in the previous
# list (audit entries C-004, SOFT-05, MET-02), and pairs whose trade is partly or newly overland.
LAND_NOTES = {
    _pair("NLD", "BEL"): Entry(ALL, "Rotterdam-Antwerp pipeline (RAPL) and Scheldt barges"),
    _pair("NLD", "DEU"): Entry(ALL, "Rhine barges and the RRP and RMR pipelines"),
    _pair("FRA", "BEL"): Entry(ALL, "Barge, rail and road across a short land border"),
    _pair("DEU", "POL"): Entry(ALL, "Rail, road and Oder barges"),
    _pair("CAN", "USA"): Entry(
        frozenset({"crude", "products"}),
        "Pipelines and rail across the border; the Trans Mountain pipeline also feeds tankers at its Westridge terminal "
        "(atlas pipeline layer), so part of the trade may sail, in a share not known",
        "https://en.wikipedia.org/wiki/Trans_Mountain_pipeline",
    ),
    _pair("IND", "BGD"): Entry(
        frozenset({"products"}),
        "Diesel from the Numaligarh refinery crosses by the India-Bangladesh Friendship Pipeline to the Parbatipur depot "
        "(inaugurated in March 2023)",
        "https://en.wikipedia.org/wiki/India%E2%80%93Bangladesh_Friendship_Pipeline",
    ),
}

# ------------------------------------------------------------------ 4. mixed pairs
# ordered (exporter, importer) -> cargo families that move both by sea and overland; the atlas has no source for the split
_MIXED = [
    (("RUS", "CHN"), {"crude", "products", "lpg", "drybulk", "fert", "metal", "grain", "vegoil"},
     "Long land border with rail and pipelines, and Far East and Arctic ports; no free source gives the sea share (Russian customs detail is suspended since 2022)",
     "https://en.wikipedia.org/wiki/Eastern_Siberia%E2%80%93Pacific_Ocean_oil_pipeline"),
    (("CHN", "RUS"), {"drybulk", "metal"}, "Rail and road across the border, and sea from Chinese ports to Russian Far East ports; the split is not known", None),
    (("USA", "MEX"), {"products", "lpg", "grain", "vegoil", "fert"},
     "Rail, truck and pipeline across the border, and Gulf ports; the split is not known", None),
    (("MEX", "USA"), {"products", "lpg"}, "Pipeline, rail and truck across the border, and Gulf and Pacific ports; the split is not known", None),
    (("ESP", "FRA"), {"grain"}, "Road and rail through the Pyrenees, and sea from Spanish to French ports; the split is not known", None),
    (("FRA", "ESP"), {"grain"}, "Road and rail through the Pyrenees, and sea from French to Spanish ports; the split is not known", None),
]
MIXED = {e[0]: Entry(frozenset(e[1]), e[2], e[3]) for e in _MIXED}

# ------------------------------------------------------------------ 7. landlocked ends
# landlocked exporter -> groups that it ships by sea through a foreign port, also to a coastal buyer of its own bloc and to
# a landlocked buyer outside its blocs; neighbours (rule 5) and landlocked buyers of its blocs stay land (rule 6)
SEA_OUTLET = {
    "KAZ": Entry(frozenset({"crude-oil"}), "Kazakh crude leaves by the CPC pipeline to the Novorossiysk marine terminal, where tankers load",
                 "https://en.wikipedia.org/wiki/Caspian_Pipeline_Consortium"),
    "AZE": Entry(frozenset({"crude-oil"}), "Azerbaijani crude leaves by the BTC pipeline to the Ceyhan marine terminal, where tankers load",
                 "https://en.wikipedia.org/wiki/Baku%E2%80%93Tbilisi%E2%80%93Ceyhan_pipeline"),
    "ZMB": Entry(frozenset({"copper-ore", "copper-refined"}), "The TAZARA railway carries Zambian copper for export to the port of Dar es Salaam",
                 "https://en.wikipedia.org/wiki/TAZARA_Railway"),
    "BLR": Entry(frozenset({"potash"}),
                 "Belarusian potash for buyers beyond its neighbours is shipped from foreign seaports; which ones has changed "
                 "with the sanctions on Belaruskali since 2021", "https://en.wikipedia.org/wiki/Belaruskali"),
    "PRY": Entry(frozenset({"soybeans", "soymeal", "soyoil", "corn"}),
                 "Soy and its products are the main cargo of the Parana-Paraguay waterway, which ends at Nueva Palmira in "
                 "Uruguay (corn: assumed to take the same waterway)",
                 "https://en.wikipedia.org/wiki/Paran%C3%A1%E2%80%93Paraguay_Waterway"),
}

# Overland blocs: two countries in the same bloc trade overland by default, and a landlocked country ships to the
# countries outside its blocs through a foreign port. Every bloc is an Atlas assumption about regional land routes.
Bloc = namedtuple("Bloc", "members reason url", defaults=(None,))
BLOCS = {
    "europe": Bloc(
        "AUT CHE CZE SVK HUN LUX SRB MKD MDA BLR AND SMR DEU FRA ITA POL NLD BEL ESP PRT GBR IRL DNK SWE NOR FIN EST LVA "
        "LTU UKR ROU BGR GRC HRV SVN BIH MNE ALB XKS KOS RUS TUR LIE SCG",
        "Europe with Russia, Belarus, Ukraine, Moldova and Turkey: one continuous road, rail, river and pipeline network",
    ),
    "1520-gauge": Bloc(
        "RUS BLR UKR MDA GEO ARM AZE KAZ UZB TKM KGZ TJK EST LVA LTU FIN MNG POL",
        "The broad-gauge rail network of the former Soviet Union, Finland and Mongolia, and the Polish border crossings "
        "where it meets the standard gauge (Poland: Atlas assumption); Central Asia reaches the rest of Europe through "
        "foreign ports",
        "https://en.wikipedia.org/wiki/Russian_gauge",
    ),
    "s-africa": Bloc("ZMB ZWE BWA MWI SWZ LSO ZAF MOZ NAM AGO COD TZA",
                     "Southern Africa: road and rail corridors from the Copperbelt and Zimbabwe to South African, Mozambican, "
                     "Namibian, Angolan and Tanzanian ports"),
    "e-africa": Bloc("UGA RWA BDI SSD ETH KEN TZA DJI SDN COD ERI SOM",
                     "East Africa: road and rail corridors from the Great Lakes, South Sudan and Ethiopia to Mombasa, Dar es "
                     "Salaam and Djibouti"),
    "w-africa": Bloc("MLI BFA NER TCD CAF SEN CIV GHA TGO BEN NGA CMR GIN DZA LBY MRT",
                     "West Africa and the Sahel: road corridors from the Gulf of Guinea and Senegal to the landlocked Sahel, "
                     "and trans-Saharan roads from Algeria and Libya"),
    "s-america": Bloc("BOL PRY BRA ARG CHL PER URY",
                      "South America: roads, railways and the Parana-Paraguay waterway between Bolivia, Paraguay and their neighbours"),
    "s-asia": Bloc("AFG NPL BTN IND PAK IRN CHN", "South Asia: roads and railways from Afghanistan, Nepal and Bhutan to their neighbours"),
    "se-asia": Bloc("LAO THA VNM KHM MMR CHN", "Mainland Southeast Asia: roads and railways from Laos to its neighbours"),
    "ne-asia": Bloc("MNG CHN RUS", "Mongolia: road and rail links to China and Russia only"),
}
BLOC = {}
for _b, _e in BLOCS.items():
    for _c in _e.members.split():
        BLOC.setdefault(_c, set()).add(_b)


def coastal(c):
    return c in COASTAL


def _in(entry, family):
    return entry.families == ALL or family in entry.families


def mode_of(o, d, group, year=None):
    """year (optional): LNG terminals of the layer count only from their opening year."""
    fam = FAMILY.get(group)
    if fam is None:
        return None
    ov = FLOW_OVERRIDES.get((group, o, d))
    if ov:
        return Mode(ov.kind, "flow", ov.reason, ov.url)
    if o in PSEUDO or d in PSEUDO:
        return Mode("sea", "default", "country not specified in customs data: seaborne by assumption, not routed")
    pair = _pair(o, d)
    neighbours = d in NEIGHBOURS.get(o, ()) and pair not in OVERSEAS_BORDERS
    lo, ld = not coastal(o), not coastal(d)
    if fam == "lng":
        if lo or ld:
            return Mode("land", "landlocked")
        if neighbours and not lng_exporter(o, year):
            return Mode("land", "product", "no liquefaction terminal in the atlas layer: probably pipeline gas declared as LNG")
        return Mode("sea", "product")
    m = MIXED.get((o, d))
    if m and fam in m.families:
        return Mode("mixed", "pair", m.reason, m.url)
    if neighbours:
        if lo or ld:
            return Mode("land", "landlocked")
        sn = SEA_NEIGHBOURS.get(pair)
        if sn and _in(sn, fam):
            return Mode("sea", "pair", sn.reason, sn.url)
        ln = LAND_NOTES.get(pair)
        if ln and _in(ln, fam):
            return Mode("land", "default", ln.reason, ln.url)
        return Mode("land", "default", "shares a mainland border")
    if lo or ld:
        common = sorted(BLOC.get(o, set()) & BLOC.get(d, set()))
        so = SEA_OUTLET.get(o) if lo else None
        # a landlocked exporter with a sea outlet ships by sea, except to a landlocked buyer of its own bloc
        if so and group in so.families and not (ld and common):
            return Mode("transit", "pair", so.reason, so.url)
        if common:
            b = BLOCS[common[0]]
            return Mode("land", "landlocked" if lo and ld else "bloc", b.reason, b.url)
        if lo and ld:
            return Mode("land", "landlocked")
        return Mode("transit", "bloc", "sea through a foreign port: no overland bloc in common")
    return Mode("sea", "default")
