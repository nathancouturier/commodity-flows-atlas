"""
Mapping from atlas commodity ids to HS 1992 six-digit codes, as used by CEPII BACI (HS92 version).

A code ending in "*" is a prefix (e.g. "72*" = all of chapter 72). Codes were chosen so that
each group is a physical raw material whose tonnage is meaningful for freight.
Notes on limits of the HS nomenclature are kept next to each entry.
"""

HS = {
    # ---------------------------------------------------------------- energy
    "crude-oil": ["270900"],
    "refined-products": ["271000"],  # HS92 has a single code for all refined petroleum products
    "lng": ["271111"],
    "natural-gas": ["271121"],  # pipeline gas (gaseous state)
    "lpg": ["271112", "271113"],  # propane, butanes
    "coal": ["270111", "270112", "270119", "270210", "270220"],  # anthracite, bituminous, other (sub-bituminous), lignite (China declares much Indonesian coal as lignite); HS6 does not separate coking from thermal coal
    "uranium": ["261210", "284410"],
    # ---------------------------------------------------------------- metals & minerals
    "iron-ore": ["260111", "260112"],
    "steel": ["72*"],  # filtered below to exclude pig iron, ferro-alloys, scrap (7201-7205)
    "copper-ore": ["260300"],
    "copper-refined": ["740311", "740312", "740313", "740319", "740200"],
    "aluminium": ["760110", "760120"],
    "bauxite": ["260600"],
    "alumina": ["281820"],
    "nickel-ore": ["260400"],
    "nickel-int": ["750110", "750120", "750210", "750220"],
    "nickel-fe": ["720260"],  # ferro-nickel; nickel pig iron has no code of its own and is declared under it
    "zinc-ore": ["260800"],
    "zinc-metal": ["790111", "790112", "790120"],
    "lead-ore": ["260700"],
    "lead-metal": ["780110", "780191", "780199"],
    "tin-ore": ["260900"],
    "tin-metal": ["800110", "800120"],
    "lithium": ["283691", "282520"],  # lithium carbonate, lithium oxide & hydroxide
    "spodumene": ["253090"],  # spodumene concentrate has no HS6 code: a subset of "mineral substances n.e.s.", see SPLIT
    "cobalt": ["260500", "810510"],
    "rare-earths": ["280530", "284610", "284690"],
    "manganese": ["260200"],
    "gold": ["710811", "710812", "710813"],
    "silver": ["710610", "710691", "710692"],
    "pgm": ["711011", "711019", "711021", "711029", "711031", "711039", "711041", "711049"],
    # ---------------------------------------------------------------- softs & fertilisers
    "wheat": ["100110", "100190"],
    "corn": ["100590"],
    "soybeans": ["120100"],
    "soymeal": ["230400"],
    "soyoil": ["150710", "150790"],
    "rice": ["100610", "100620", "100630", "100640"],
    "sugar": ["170111", "170112", "170191", "170199"],
    "coffee": ["090111", "090112"],
    "cocoa": ["180100"],
    "cotton": ["520100"],
    "palm-oil": ["151110", "151190"],
    "rapeseed": ["120500"],
    "potash": ["310420"],
    "phosphate-rock": ["251010", "251020"],
    "dap": ["310530"],
    "urea": ["310210"],
    # ---------------------------------------------------------------- minor (country check only)
    "diamonds": ["710210", "710231"],
    "wood": ["4403*"],
}

STEEL_EXCLUDE = ("7201", "7202", "7203", "7204", "7205")

# A code that mixes products, split by trading partners: hs6 -> (group of the listed pairs, exporters, importers,
# group of the other rows). HS 253090 ("mineral substances n.e.s.") holds spodumene concentrate with other minerals;
# its rows from the countries that ship spodumene to China are read as spodumene (an Atlas estimate, said so on the
# lithium page); the rest of the code is kept as "minerals-nes" only to measure the share the subset is of it.
SPLIT = {"253090": ("spodumene", ("AUS", "ZWE", "BRA", "NGA", "MLI", "CAN"), ("CHN",), "minerals-nes")}


def build_lookup():
    """Return (exact: dict hs6 -> group, prefixes: list[(prefix, group)])."""
    exact, prefixes = {}, []
    for group, codes in HS.items():
        for c in codes:
            if c.endswith("*"):
                prefixes.append((c[:-1], group))
            else:
                exact[c] = group
    return exact, prefixes


def split_group(hs6, o, d):
    """Group of a row of a code in SPLIT, from its exporter and importer (ISO3)."""
    g, exporters, importers, rest = SPLIT[hs6]
    return g if o in exporters and d in importers else rest


def group_of(hs6: str, exact, prefixes):
    g = exact.get(hs6)
    if g:
        return g
    for p, grp in prefixes:
        if hs6.startswith(p):
            if grp == "steel" and hs6.startswith(STEEL_EXCLUDE):
                return None
            return grp
    return None
