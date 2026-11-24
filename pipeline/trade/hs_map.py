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
    # the metal bulks that were missing (audit A-010). One code, one group; the words are those of the product code list of CEPII BACI
    # (HS 1992). 7204 is the whole heading of ferrous waste and scrap: cast iron (720410), stainless (720421), other alloy steel
    # (720429), tinned (720430), turnings, shavings and the like (720441), the rest of the scrap (720449: three quarters of the
    # heading) and remelting scrap ingots (720450). 261000 chromium ores and concentrates (chromite). 270400 coke and semi-coke of
    # coal, lignite or peat, retort carbon: the coal pages hold the coal codes, not this one. 7201 non-alloy pig iron (720110 and
    # 720120 by phosphorus content), alloy pig iron and spiegeleisen (720130, 720140). 7203 ferrous products obtained by direct
    # reduction of iron ore (720310) and spongy ferrous products and iron of 99.94% purity or more (720390). Left out: 7205 granules
    # and powders of pig iron and steel (they stay out of the steel group too, see STEEL_EXCLUDE) and the scrap of the other
    # metals.
    "ferrous-scrap": ["720410", "720421", "720429", "720430", "720441", "720449", "720450"],
    "chromium-ore": ["261000"],
    "pig-iron": ["720110", "720120", "720130", "720140"],
    "dri": ["720310", "720390"],
    "coke": ["270400"],
    # The ferro-alloys of heading 7202 by alloy, with ferro-nickel (720260, group nickel-fe above) left on the nickel page: ferro-chromium
    # (720241 more than 4% of carbon, 720249 4% or less), ferro-manganese (720211 more than 2% of carbon, 720219 2% or less),
    # ferro-silico-manganese (720230), ferro-silicon (720221 more than 55% of silicon, 720229 55% or less), and the other ferro-alloys
    # together: ferro-silico-chromium (720250), ferro-molybdenum (720270), ferro-tungsten and ferro-silico-tungsten (720280),
    # ferro-titanium and ferro-silico-titanium (720291), ferro-vanadium (720292), ferro-niobium (720293) and the ferro-alloys n.e.s. (720299)
    "ferro-chromium": ["720241", "720249"],
    "ferro-manganese": ["720211", "720219"],
    "silico-manganese": ["720230"],
    "ferro-silicon": ["720221", "720229"],
    "ferro-alloys-other": ["720250", "720270", "720280", "720291", "720292", "720293", "720299"],
    # molybdenum ores and concentrates, roasted (261310) and other (261390), and natural graphite, in powder or flakes (250410) and in other
    # forms (250490): trade tables of their own pages, no lanes. Left out: molybdenum oxides and hydroxides (2825), ferro-molybdenum
    # (720270, in the ferro-alloys group above), artificial graphite (3801) and graphite articles (6815)
    "molybdenum-ore": ["261310", "261390"],
    "graphite": ["250410", "250490"],
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
    # processed cocoa and coffee (codes from the follow-ups of the agriculture package A1): inputs of the trade tables of the
    # cocoa and coffee pages only; boxed goods that the atlas does not route, so no lanes (pipeline/freight/build_lanes.py GROUPS)
    "cocoa-paste": ["180310", "180320"],
    "cocoa-butter": ["180400"],
    "cocoa-powder": ["180500"],
    "chocolate": ["180610", "180620", "180631", "180632", "180690"],
    "coffee-roasted": ["090121", "090122"],
    "coffee-soluble": ["210110"],  # HS92: extracts, essences and concentrates of coffee and preparations based on them
    "cotton": ["520100"],
    "palm-oil": ["151110", "151190"],
    "rapeseed": ["120500"],
    # the grains, oilseeds and their products that were missing (audit M-023). One code, one group. HS 1992 words, from the
    # product code list of CEPII BACI: 100300 barley (malting and feed barley are not told apart), 100700 grain sorghum,
    # 120600 sunflower seeds (oil seed and seed for sowing and eating are not told apart), 151211 and 151219 sunflower-seed OR
    # safflower oil (crude and other: safflower oil is in the same codes), 151410 and 151490 rape, colza OR mustard oil (the
    # same), 230630 and 230640 the oil-cake and other solid residues of sunflower and of rape or colza seed oil extraction
    # (meals and pellets), 110100 wheat or meslin flour, 230330 brewing or distilling dregs and waste (distillers' dried grains
    # are in it, with brewers' grains and other waste: one code for all of them), 0713 dried leguminous vegetables.
    # Left out: malt (1107), oats (1004), rye (1002), the other flours and groats (1102-1104), starches (1108), safflower and
    # other oilseeds (1207), cotton, groundnut, palm kernel and coconut oils and meals (the next packages), 0708 fresh pulses.
    "barley": ["100300"],
    "sorghum": ["100700"],
    "sunflower-seed": ["120600"],
    "sunflower-oil": ["151211", "151219"],
    "sunflower-meal": ["230630"],
    "rapeseed-oil": ["151410", "151490"],
    "rapeseed-meal": ["230640"],
    "wheat-flour": ["110100"],
    "brewing-distilling-dregs": ["230330"],
    # dried leguminous vegetables, shelled: peas 071310, chickpeas 071320, beans 071331 (mung and urd), 071332 (adzuki),
    # 071333 (kidney), 071339 (other beans), 071350 (broad and horse beans), lentils 071340, other 071390 (pigeon
    # peas and every pulse the code does not name). The kinds are read from the six-digit rows (pipeline/commodities/metals.py SPLITS)
    "pulses": ["071310", "071320", "071331", "071332", "071333", "071339", "071340", "071350", "071390"],
    "potash": ["310420"],
    "potassium-sulphate": ["310430"],  # sulphate of potash (SOP): second group of the potash page
    "phosphate-rock": ["251010", "251020"],
    "dap": ["310530"],
    # more fertilisers (audit M-022). One code, one group: 310260 (calcium nitrate double salts), 310229 and 310290 (other nitrogen),
    # 310390 (other phosphatic), 310510 (tablets and small packages) and 310590 (the rest of heading 3105) are not loaded. 310240
    # (ammonium nitrate with limestone) and 310551, 310559, 310560 (the two-nutrient compounds) are loaded since package FNCB
    # (review GNC1.4: together about as heavy as the products added with M-022)
    "monoammonium-phosphate": ["310540"],  # HS92: MAP and its mixtures with DAP
    "superphosphates": ["310310"],  # HS92: one code for single and triple superphosphate
    "phosphoric-acid": ["280920"],  # HS92: phosphoric acid and polyphosphoric acids; moves as a liquid
    "npk": ["310520"],  # HS92: fertilisers with the three nutrients nitrogen, phosphorus and potassium
    # the compound fertilisers with two of the three nutrients: nitrates and phosphates (310551), nitrogen and phosphorus other than
    # nitrates and phosphates (310559, the ammonium phosphate nitrates), phosphorus and potassium (310560). The NPK page's second group
    "npk-two-nutrient": ["310551", "310559", "310560"],
    "urea": ["310210"],
    "ammonia": ["281410"],  # anhydrous ammonia (refrigerated or pressurised liquid); 281420, ammonia in solution, is not loaded
    "ammonium-nitrate": ["310230"],  # HS92: ammonium nitrate, whether or not in aqueous solution
    # ammonium nitrate mixed with calcium carbonate or other inorganic substances that carry no fertilising element: calcium ammonium
    # nitrate (CAN) and the like. The nitrogen page's group next to ammonium nitrate (310230); the two are never the same code
    "ammonium-nitrate-limestone": ["310240"],
    "uan": ["310280"],  # HS92: urea and ammonium nitrate mixtures in aqueous or ammoniacal solution; moves as a liquid
    "ammonium-sulphate": ["310221"],
    # sulphur: crude and unrefined (250310) with sublimed, precipitated and colloidal sulphur (280200); 250390 has no flow in BACI
    "sulphur": ["250310", "250390", "280200"],
    # ---------------------------------------------------------------- minor (country check only)
    "diamonds": ["710210", "710231"],
    "wood": ["4403*"],
}

STEEL_EXCLUDE = ("7201", "7202", "7203", "7204", "7205")

# A code that mixes products, split by trading partners: hs6 -> (group of the listed pairs, exporters, importers,
# group of the other rows). HS 253090 ("mineral substances n.e.s.") holds spodumene concentrate with other minerals;
# its rows from the exporters for which a page read by the atlas says they ship lithium concentrate to China are read
# as spodumene (an Atlas estimate, said so on the lithium page, with the pages): Australia (ABS national subheading
# 25309011), Zimbabwe (Reuters) and Brazil (Diario do Comercio, SMM). The rest of the code is kept as "minerals-nes"
# only to measure the share the subset is of it. SPLIT_NOT_READ: exporters read as spodumene in an earlier version of
# this list, for which no page was found; the lithium page names their tonnage in a note.
SPLIT = {"253090": ("spodumene", ("AUS", "ZWE", "BRA"), ("CHN",), "minerals-nes")}
SPLIT_NOT_READ = {"253090": ("NGA", "MLI", "CAN")}


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
