"""
Physical and conventional constants used by the builders, each with what it is and the page that gives it.

    from common import constants as CN        # with pipeline/ on sys.path
    CN.KG_PER_LB, CN.US_GALLONS_PER_BARREL, CN.ATOMIC_WEIGHT["U"], ...

One entry of CONSTANTS per constant: `value`, `unit`, `what` it is, `url` of the page read to get it (and `also`, other pages that give
the same), `quote` (what the page says, in its words) and `read` (the date the page was read). A builder never types one of these
values: it imports it from here. pipeline/tests/test_constants.py checks that every entry has a page and a date, that every value
printed here is the value of its entry, and that no builder types one of the values.

Derived values (a pound in tonnes, a troy ounce in grams, a short ton in tonnes, the weight of a bale in tonnes...) are computed
here from the entries above them, not typed, and rounded to the digits their inputs give.

Two ratios are not constants of nature: they are read in EIA's own data (EIA_RATIOS below: the series, the years and the value read),
by the builders that need them (pipeline/trade/checks.py barrels_per_tonne for crude oil, pipeline/commodities/build_commodities.py
Eia._fill_lpg_us for LPG), and a test recomputes them from raw/eia/INTL.txt.

Not here, and why: the length of a degree of latitude (111.2 km) typed in pipeline/freight/ports.py: no page that gives that digit was
read (it follows from the Earth radius below, 111.19 km, but changing it would move the lanes), see the report of package FE1.
"""

READ = "2026-11-23"  # the day the pages below were read (package FE1, audit of November 2026)

_EIA_UNITS = "https://www.eia.gov/energyexplained/units-and-calculators/"
_NIST_B8 = "https://www.nist.gov/pml/special-publication-811/nist-guide-si-appendix-b-conversion-factors/nist-guide-si-appendix-b8"
_NIST_B9 = "https://www.nist.gov/pml/special-publication-811/nist-guide-si-appendix-b-conversion-factors/nist-guide-si-appendix-b9"
_WP_POUND = "https://en.wikipedia.org/wiki/International_yard_and_pound"
_CIAAW = "https://www.ciaaw.org/abridged-atomic-weights.htm"
_ERS_AH697 = "https://ers.usda.gov/sites/default/files/_laserfiche/publications/41880/33132_ah697_002.pdf"
_NRCAN = "https://natural-resources.canada.ca/climate-change/conversion-factors-common-units-used-north-american-cooperation-energy-information"


def _c(value, unit, what, url, quote, also=()):
    return {"value": value, "unit": unit, "what": what, "url": url, "also": list(also), "quote": quote, "read": READ}


CONSTANTS = {
    "US_GALLONS_PER_BARREL": _c(
        42, "US gallons per barrel", "the barrel of crude oil and of petroleum products", _EIA_UNITS,
        'EIA, Units and calculators explained, table of barrel equivalents: "Crude oil or petroleum products: 42 U.S. gallons"',
        also=[_NIST_B8]),
    "KG_PER_LB": _c(
        0.45359237, "kg per pound", "the international (avoirdupois) pound, exact by the agreement of 1 July 1959", _WP_POUND,
        'Wikipedia, International yard and pound: "the international pound equals 0.45359237 kilograms", agreement "signed on 1 July 1959"; '
        'NIST SP 811 appendix B.8 lists the pound as 4.535 924 E-01 kg (seven digits)',
        also=[_NIST_B8]),
    "LB_PER_SHORT_TON": _c(
        2000, "pounds per short ton", "the short (US) ton", "https://en.wikipedia.org/wiki/Short_ton",
        'Wikipedia, Short ton: "a measurement unit equal to 2,000 pounds"; NIST SP 811 appendix B.8: "ton, short (2000 lb)" = 9.071 847 E+02 kg',
        also=[_NIST_B8]),
    "GRAIN_G": _c(
        0.06479891, "g per grain", "the grain, exact by definition; the troy ounce is 480 grains", _NIST_B9,
        'NIST SP 811 appendix B.9, mass: "grain (gr)" = 6.479 891 E-05 kg, printed in boldface ("Factors in boldface are exact")',
        also=["https://en.wikipedia.org/wiki/Troy_ounce"]),
    "GRAINS_PER_TROY_OZ": _c(
        480, "grains per troy ounce", "the troy ounce", "https://en.wikipedia.org/wiki/Troy_ounce",
        'Wikipedia, Troy ounce: "based on a grain of 0.06479891 gram (exact, by definition)", "480 grains to a troy ounce"'),
    "FOOT_M": _c(
        0.3048, "m per foot", "the international foot, exact", _NIST_B8,
        'NIST SP 811 appendix B.8: "foot (ft)" = 3.048 E-01 m, printed in boldface (exact)', also=[_NIST_B9]),
    "KM_PER_NAUTICAL_MILE": _c(
        1.852, "km per nautical mile", "the international nautical mile (1852 m), exact", _NIST_B8,
        'NIST SP 811 appendix B.8: "mile, nautical" = 1.852 E+03 m, printed in boldface (exact)', also=[_NIST_B9]),
    "EARTH_RADIUS_KM": _c(
        6371, "km", "the mean radius of the Earth, for great-circle distances to a few km", "https://en.wikipedia.org/wiki/Earth_radius",
        'Wikipedia, Earth radius: "The globally averaged value is 6371 kilometres"; the IUGG arithmetic mean radius R1 is 6,371.0087714 km'),
    "BCF_PER_MT_LNG": _c(
        48.0279467, "billion cubic feet of natural gas per million tonnes of LNG", "the conversion of LNG tonnes to gas volume", _NRCAN,
        'Natural Resources Canada, Conversion factors and common units to be used for North American cooperation on energy information '
        '(page dated 2025-01-16): 1 million tonnes LNG = 48.0279467 billion cubic feet natural gas'),
    "COFFEE_BAG_KG": _c(
        60, "kg per bag", "the bag of green coffee that USDA PSD counts in (unit '1000 60 KG BAGS')", _ERS_AH697,
        'USDA ERS, Agricultural Handbook 697 (June 1992), table 52, note: "A standard 60-kilogram bag of green coffee equals 132.276 pounds."'),
    "COTTON_BALE_LB": _c(
        480, "pounds per bale", "the 480-pound net weight bale that USDA PSD counts in (unit '1000 480 lb. Bales')", _ERS_AH697,
        'USDA ERS, Agricultural Handbook 697 (June 1992), glossary: "480-pound net weight bale: an average bale weight used to maintain statistical comparability"'),
}

# standard atomic weights, abridged (CIAAW 2024): the value of the page, rounded as the page prints it
ATOMIC_WEIGHT = {
    "H": 1.008, "Li": 6.94, "C": 12.011, "N": 14.007, "O": 15.999, "Cl": 35.45, "K": 39.098, "U": 238.03,
}
ATOMIC_WEIGHT_PAGE = {
    "url": _CIAAW, "read": READ,
    "quote": 'CIAAW, "Abridged Standard Atomic Weights 2024": H 1.0080 ± 0.0002, Li 6.94 ± 0.06, C 12.011 ± 0.002, N 14.007 ± 0.001, '
             'O 15.999 ± 0.001, Cl 35.45 ± 0.01, K 39.098 ± 0.001, U 238.03 ± 0.01',
}
for _el, _w in ATOMIC_WEIGHT.items():
    CONSTANTS["ATOMIC_WEIGHT_" + _el.upper()] = _c(_w, "g per mol", f"the standard atomic weight of {_el}", _CIAAW, ATOMIC_WEIGHT_PAGE["quote"])

# ratios read in EIA's own data (not constants of nature): the series, the years, the value read on the page of the bulk files
EIA_RATIOS = {
    "BARRELS_PER_TONNE_CRUDE": {
        "value": 7.33, "unit": "barrels per tonne", "url": "https://www.eia.gov/opendata/bulkfiles.php", "read": READ,
        "what": "crude oil including lease condensate, United States: the series in thousand barrels per day (INTL.57-1-USA-TBPD.A) times the days of the "
                "year over the series in thousand metric tons (INTL.57-1-USA-MT.A), median of 1980 to 1999 (7.333 read in raw/eia/INTL.txt)",
        "series": ["57-1-USA-TBPD", "57-1-USA-MT"]},
    "BARRELS_PER_TONNE_LPG": {
        "value": 11.6, "unit": "barrels per tonne", "url": "https://www.eia.gov/opendata/bulkfiles.php", "read": READ,
        "what": "liquefied petroleum gases consumption, United States: INTL.67-2-USA-TBPD.A times the days of the year over INTL.67-2-USA-MT.A, "
                "11.600 in every year from 1980 to 2019 (3.385 in 2021, which the atlas does not use)",
        "series": ["67-2-USA-TBPD", "67-2-USA-MT"]},
}


# ---- the values the builders import (typed nowhere else)
US_GALLONS_PER_BARREL = CONSTANTS["US_GALLONS_PER_BARREL"]["value"]
KG_PER_LB = CONSTANTS["KG_PER_LB"]["value"]
LB_PER_SHORT_TON = CONSTANTS["LB_PER_SHORT_TON"]["value"]
TONNES_PER_SHORT_TON = round(LB_PER_SHORT_TON * KG_PER_LB / 1000, 8)  # 0.90718474: a short ton in metric tonnes
GRAIN_G = CONSTANTS["GRAIN_G"]["value"]
GRAMS_PER_TROY_OZ = round(CONSTANTS["GRAINS_PER_TROY_OZ"]["value"] * GRAIN_G, 7)  # 31.1034768
FOOT_M = CONSTANTS["FOOT_M"]["value"]
KM_PER_NAUTICAL_MILE = CONSTANTS["KM_PER_NAUTICAL_MILE"]["value"]
EARTH_RADIUS_KM = CONSTANTS["EARTH_RADIUS_KM"]["value"]
BCF_PER_MT_LNG = CONSTANTS["BCF_PER_MT_LNG"]["value"]
# USDA PSD counts coffee in 1000 bags of 60 kg and cotton in 1000 bales of 480 pounds: million tonnes per PSD unit
MT_PER_1000_COFFEE_BAGS = round(CONSTANTS["COFFEE_BAG_KG"]["value"] * 1e3 / 1e9, 12)
MT_PER_1000_COTTON_BALES = round(CONSTANTS["COTTON_BALE_LB"]["value"] * KG_PER_LB * 1e3 / 1e9, 11)
# thousand tonnes per PSD unit (pipeline/trade/checks.py)
KT_PER_1000_COFFEE_BAGS = round(CONSTANTS["COFFEE_BAG_KG"]["value"] / 1000, 6)
KT_PER_1000_COTTON_BALES = CONSTANTS["COTTON_BALE_LB"]["value"] * KG_PER_LB / 1000
