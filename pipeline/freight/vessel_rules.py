"""
Typical vessel classes per lane, and typical laden speeds.

These are Atlas assumptions based on standard industry practice (cargo size economics, port
draft limits, canal limits). They are documented in METHODOLOGY.md and shown in the UI as
"typical" classes, never as measured shares. The first class listed is the primary one.
"""
MEG = {"SAU", "IRQ", "ARE", "KWT", "IRN", "OMN", "QAT", "BHR"}
WAF = {"NGA", "AGO", "COG", "GAB", "GNQ", "CMR", "GHA", "CIV"}
ASIA_FAR = {"CHN", "JPN", "KOR", "TWN", "SGP", "MYS", "THA", "VNM", "PHL", "IDN", "IND", "PAK", "BGD", "LKA"}
EUROPE = {"NLD", "BEL", "DEU", "FRA", "GBR", "ITA", "ESP", "PRT", "POL", "GRC", "TUR", "SWE", "FIN", "DNK", "NOR", "IRL", "ROU", "BGR", "HRV", "SVN", "LTU", "LVA", "EST"}
BIG_ORE = {"AUS", "BRA", "ZAF", "CAN", "GIN", "SWE", "MRT", "LBR", "SLE"}

# typical laden service speed, knots (eco-speed era)
SPEED = {
    "vloc": 11.0, "capesize": 11.0, "newcastlemax": 11.0, "panamax": 12.0, "kamsarmax": 12.0, "supramax": 12.0,
    "ultramax": 12.0, "handysize": 11.5, "vlcc": 12.5, "suezmax": 13.0, "aframax": 13.0, "lr2": 13.0, "lr1": 13.0,
    "mr": 12.5, "handy-tanker": 12.5, "lng": 17.0, "vlgc": 15.5, "container": 17.0,
}


# LPG carriers. Thresholds of the LPG rule of classes(); LPG_SHORT_HAUL_NM and LPG_MID_HAUL_NM are Atlas assumptions,
# as the other distance thresholds of classes(). A VLGC parcel is 44 kt (Baltic BLPG reference, 84,000 cbm vessel, see
# vessel_classes.json); a lane that loads fewer than one such parcel a week (44 kt x 52) does not keep a VLGC busy
# and is served by mid-size carriers (25,000 to 50,000 cbm, class "mgc").
LPG_SHORT_HAUL_NM = 1000
LPG_MID_HAUL_NM = 3000
VLGC_PARCEL_KT = 44
VLGC_WEEKLY_MT = VLGC_PARCEL_KT * 52 / 1000


def speed(vclass):
    return SPEED.get(vclass, 12.0)


def classes(group, o, d, tonnes, nm):
    """Return typical vessel classes for a lane, primary first."""
    mt = tonnes / 1e6
    if group == "iron-ore":
        if o == "BRA" and d in ASIA_FAR:
            return ["vloc", "capesize"]
        if o in BIG_ORE and mt > 3:
            return ["capesize", "newcastlemax"] if o == "AUS" else ["capesize"]
        return ["supramax", "panamax"]
    if group in ("bauxite",):
        return ["capesize", "panamax"] if (o in ("GIN", "AUS") and mt > 3) else ["supramax", "panamax"]
    if group == "coal":
        if o == "IDN":
            return ["supramax", "panamax"]
        if o in ("AUS", "COL", "ZAF", "USA", "CAN") and mt > 5:
            return ["capesize", "panamax"] if nm > 3000 else ["panamax", "capesize"]
        if o == "RUS":
            return ["panamax", "capesize"]
        return ["panamax", "supramax"]
    if group in ("manganese", "phosphate-rock", "alumina"):
        return ["supramax", "panamax"]
    if group in ("copper-ore", "zinc-ore", "nickel-ore", "lead-ore", "nickel-int"):
        return ["supramax", "handysize"]
    if group in ("wheat", "corn", "soybeans", "soymeal", "rapeseed", "sugar"):
        if o in ("UKR", "RUS", "ROU", "BGR") and d not in ASIA_FAR:
            return ["supramax", "handysize"]
        if o in ("USA", "BRA", "ARG", "CAN", "AUS") and mt > 1:
            return ["kamsarmax", "supramax"]
        return ["supramax", "handysize"]
    if group == "rice":
        return ["handysize", "supramax"]
    if group in ("potash", "urea", "dap"):
        return ["supramax", "handysize"] if not (group == "potash" and o == "CAN" and mt > 2) else ["panamax", "supramax"]
    if group in ("soyoil", "palm-oil"):
        return ["mr", "handy-tanker"]
    if group in ("steel",):
        return ["supramax", "handysize"]
    if group in ("copper-refined", "aluminium", "coffee", "cocoa", "cotton", "lead-metal", "zinc-metal", "tin-metal",
                 "tin-ore", "cobalt", "lithium", "rare-earths"):
        return ["container", "handysize"]
    if group == "lng":
        return ["lng"]
    if group == "lpg":
        # Regional trades (short haul) and small lanes (under a VLGC parcel a week) on a medium haul are served by
        # mid-size gas carriers, with the VLGC second where the volume or the haul allows it; long hauls and large
        # lanes keep the VLGC (the Gulf to India trade, 1,000 to 1,300 nm, is a VLGC benchmark route).
        big = mt >= VLGC_WEEKLY_MT
        if 0 < nm < LPG_SHORT_HAUL_NM:
            return ["mgc", "vlgc"] if big else ["mgc"]
        if 0 < nm < LPG_MID_HAUL_NM and not big:
            return ["mgc", "vlgc"]
        return ["vlgc"]
    if group == "crude-oil":
        if o in MEG and (d in ASIA_FAR or nm > 6000):
            return ["vlcc", "suezmax"]
        if o in ("BRA", "USA", "GUY") and d in ASIA_FAR:
            return ["vlcc"]
        if o in WAF:
            return ["vlcc", "suezmax"] if d in ASIA_FAR else ["suezmax", "aframax"]
        if o in ("RUS", "KAZ", "NOR", "GBR", "LBY", "DZA", "AZE", "MEX", "COL", "VEN", "CAN", "ECU"):
            return ["aframax", "suezmax"] if nm < 6000 else ["suezmax", "aframax"]
        if o == "USA" and d in EUROPE:
            return ["aframax", "suezmax"]
        return ["suezmax", "aframax"] if mt > 3 else ["aframax"]
    if group == "refined-products":
        if nm > 5000 and mt > 3:
            return ["lr2", "lr1", "mr"]
        return ["mr", "lr1"]
    return ["supramax"]


# ------------------------------------------------------------------ draught rule for straits
# A class avoids a passage only when its sourced laden draught exceeds the passage's sourced limit. A limit is a
# navigable draught limit or a minimum depth read on the cited page; a draught is a laden draught of the class
# read on the cited page (a canal's maximum draft is a limit of that canal, never the draught of a class). A class
# or passage without such a figure is not restricted: panamax (its page gives only the locks' 12.04 m maximum
# draft), lng (the Q-Max page gives a 12 m draft of the largest ships, not a laden draught of the class) and the
# classes with no page figure (newcastlemax, kamsarmax, supramax, ultramax, vlcc, suezmax, aframax, lr2, lr1, mr,
# handy-tanker, vlgc, container). Figures read on Wikipedia in November 2026 (CC BY-SA 4.0); the Malacca figure is
# the one quoted in pipeline/freight/chokepoints.json and the two must stay in step. Each source string says which
# quantity the figure is.
PASSAGE_LIMIT_M = {
    "malacca": 20.5,     # draught of the largest ships that can pass the Strait of Malacca (Malaccamax)
    "singapore": 20.5,   # same limit: the Malaccamax page puts the route's minimum depth in the Singapore Strait
    "sunda": 20.0,       # a minimum depth, used as the limit with no under-keel margin
    "torres": 12.2,      # ships of 12.2 m static draught or less are permitted to transit
}
PASSAGE_LIMIT_SRC = {
    "malacca": "https://en.wikipedia.org/wiki/Malaccamax (read 2026): navigable draught limit, the 20.5 m draught "
               "of a Malaccamax tanker, the largest ship able to pass the 25 m deep strait",
    "singapore": "https://en.wikipedia.org/wiki/Malaccamax (read 2026): navigable draught limit, the same 20.5 m "
                 "Malaccamax draught; the page places the minimum depth of the Malacca route in the Singapore "
                 "Strait (https://en.wikipedia.org/wiki/Singapore_Strait gives 22 m minimum depth in the channel, "
                 "not used)",
    "sunda": "https://en.wikipedia.org/wiki/Sunda_Strait (read 2026): minimum depth, 20 m in parts of its "
             "north-eastern end (no under-keel margin is taken off)",
    "torres": "https://en.wikipedia.org/wiki/Torres_Strait (read 2026): navigable draught limit, ships of 12.2 m "
              "static draught or less are permitted to transit",
}
DRAUGHT_M = {
    "vloc": 22.0,        # Valemax: maximum draught of 22 to 23 m loaded (lower figure)
    "capesize": 18.0,    # typical Capesize: 18 m draught at about 170,000 DWT
    "handysize": 10.0,   # Handysize: summer draft of about 10 m
}
DRAUGHT_SRC = {
    "vloc": "https://en.wikipedia.org/wiki/Valemax (read 2026): laden draught, 'a maximum draught of between 22 "
            "and 23 metres while loaded' (lower figure)",
    "capesize": "https://en.wikipedia.org/wiki/Capesize (read 2026): laden draught, 18 m draught of the typical "
                "ship of about 170,000 DWT",
    "handysize": "https://en.wikipedia.org/wiki/Handysize (read 2026): laden draught, about 32,000 DWT 'on a "
                 "summer draft of about 10 metres'",
}


def avoids(vclass):
    """Passages that a laden ship of this class cannot use under the draught rule."""
    return {p for p, lim in PASSAGE_LIMIT_M.items() if DRAUGHT_M.get(vclass, 0) > lim}
