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
    if group in ("copper-refined", "aluminium", "coffee", "cocoa", "cotton"):
        return ["container", "handysize"]
    if group == "lng":
        return ["lng"]
    if group == "lpg":
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
# A class avoids a passage only when its sourced laden draught exceeds the passage's sourced limit. A class
# without a sourced draught is not restricted. Figures read on Wikipedia in November 2026 (CC BY-SA 4.0); the
# Malacca figure is the one quoted in pipeline/freight/chokepoints.json and the two must stay in step.
PASSAGE_LIMIT_M = {
    "malacca": 20.5,     # Malaccamax design draught; the limit is set by the Singapore Strait
    "singapore": 20.5,   # same limit: the shallowest point of the Malacca route is in the Singapore Strait
    "sunda": 20.0,       # minimum depth in parts of the north-eastern end (a depth, not a draught limit)
    "torres": 12.2,      # ships of 12.2 m static draught or less are permitted to transit
}
PASSAGE_LIMIT_SRC = {
    "malacca": "https://en.wikipedia.org/wiki/Malaccamax (read 2026)",
    "singapore": "https://en.wikipedia.org/wiki/Malaccamax (read 2026); https://en.wikipedia.org/wiki/Singapore_Strait (read 2026)",
    "sunda": "https://en.wikipedia.org/wiki/Sunda_Strait (read 2026)",
    "torres": "https://en.wikipedia.org/wiki/Torres_Strait (read 2026)",
}
DRAUGHT_M = {
    "vloc": 22.0,        # Valemax: maximum draught of 22 to 23 m loaded (lower figure)
    "capesize": 18.0,    # typical Capesize: 18 m draught
    "panamax": 12.04,    # Panamax: maximum allowable draft in the old Panama locks
    "handysize": 10.0,   # Handysize: summer draft of about 10 m
    "lng": 12.0,         # Q-Max, the largest LNG carriers: draft of about 12 m (upper bound for the class)
}
DRAUGHT_SRC = {
    "vloc": "https://en.wikipedia.org/wiki/Valemax (read 2026)",
    "capesize": "https://en.wikipedia.org/wiki/Capesize (read 2026)",
    "panamax": "https://en.wikipedia.org/wiki/Panamax (read 2026)",
    "handysize": "https://en.wikipedia.org/wiki/Handysize (read 2026)",
    "lng": "https://en.wikipedia.org/wiki/Q-Max (read 2026)",
}


def avoids(vclass):
    """Passages that a laden ship of this class cannot use under the draught rule."""
    return {p for p, lim in PASSAGE_LIMIT_M.items() if DRAUGHT_M.get(vclass, 0) > lim}
