"""
Port reference table for lane geometry.

Coordinates come from the port list bundled with the `searoute` package (UN/LOCODE codes),
except entries marked "manual", which are well-known terminals missing from that list
(coordinates to ~0.05 degree, sufficient for routing on a world map).
"""
import json
import os

_SR = os.path.join(os.path.dirname(__import__("searoute").__file__), "data", "ports.geojson")
_sr = {f["properties"]["port"]: (f["properties"]["name"].strip(), f["geometry"]["coordinates"]) for f in json.load(open(_SR, encoding="utf-8-sig"))["features"]}

# code -> (name, iso3, lon, lat) for terminals missing from the searoute list
MANUAL = {
    "RUKOZ": ("Kozmino", "RUS", 133.07, 42.72),
    "ZASDB": ("Saldanha Bay", "ZAF", 17.95, -33.03),
    "SAYNB": ("Yanbu", "SAU", 38.06, 24.08),
    "IQBOT": ("Basrah Oil Terminal", "IRQ", 48.82, 29.68),
    "IRKHK": ("Kharg Island", "IRN", 50.32, 29.24),
    "CNZHA": ("Zhanjiang", "CHN", 110.42, 21.18),
    "TRCEY": ("Ceyhan", "TUR", 35.88, 36.88),
    "AERUW": ("Ruwais", "ARE", 52.73, 24.12),
    "RUTAM": ("Taman", "RUS", 36.72, 45.12),
    "VEPJO": ("Puerto José", "VEN", -64.82, 10.1),
    "ARNEC": ("Necochea / Quequén", "ARG", -58.7, -38.58),
    "AUGET": ("Geraldton", "AUS", 114.6, -28.78),
    "IDMOR": ("Morowali (IMIP)", "IDN", 122.13, -2.83),
    "IDWED": ("Weda Bay", "IDN", 127.97, 0.45),
    "OMDQM": ("Duqm", "OMN", 57.7, 19.66),
    "GYGEO": ("Liza FPSOs (Stabroek)", "GUY", -57.0, 8.0),
    "SAJIZ": ("Jizan", "SAU", 42.56, 16.89),
    "GNMOR": ("Morebaya (Simandou)", "GIN", -13.4, 9.2),
    "USLCH": ("Lake Charles / Cameron", "USA", -93.33, 29.78),
    "ARUPR": ("Up-River (Rosario hub)", "ARG", -60.63, -32.96),
    "MZMAP": ("Maputo", "MOZ", 32.56, -25.97),
    "UAPIV": ("Pivdennyi", "UKR", 31.02, 46.62),
    "CNYSN": ("Yangshan / Shanghai", "CHN", 122.07, 30.63),
    "BRPMA": ("Ponta da Madeira", "BRA", -44.37, -2.57),
    "GNKMS": ("Kamsar", "GIN", -14.62, 10.65),
    "CLCOQ": ("Coquimbo", "CHL", -71.34, -29.95),
    "INVTZ": ("Visakhapatnam", "IND", 83.29, 17.69),
    "INKRI": ("Krishnapatnam", "IND", 80.12, 14.25),
    "PHNIC": ("Surigao (nickel ore loading)", "PHL", 125.5, 9.8),
    "QAMES": ("Mesaieed", "QAT", 51.57, 24.99),
    "NOMON": ("Mongstad", "NOR", 5.03, 60.81),
    "GBSCU": ("Sullom Voe", "GBR", -1.28, 60.45),
    "KZCPC": ("CPC terminal, Novorossiysk", "RUS", 37.73, 44.66),
    "MYPGU": ("Pengerang", "MYS", 104.13, 1.37),
    "RUPRG": ("Prigorodnoye (Sakhalin-2 LNG)", "RUS", 142.93, 46.62),
    "RUSAB": ("Sabetta (Yamal LNG)", "RUS", 72.06, 71.27),
    "OMMFH": ("Mina al Fahal", "OMN", 58.52, 23.63),
}

# Extra searoute ports whose ISO3 is needed (searoute only stores the country name)
_SR_ISO = {}


def port(code):
    """Return {id, name, c, at} for a port code."""
    if code in MANUAL:
        n, c, x, y = MANUAL[code]
        return {"id": code, "name": n, "c": c, "at": [x, y]}
    n, (x, y) = _sr[code]
    return {"id": code, "name": n, "c": code[:2], "at": [round(x, 3), round(y, 3)]}


# ------------------------------------------------------------------ default ports per country
# Main seaborne gateway per country and cargo segment. Segments:
#   ore (iron ore, bauxite, manganese, concentrates), coal, grain (grains, oilseeds, meal, sugar),
#   crude, products, lng, lpg, vegoil, fert, box (container / breakbulk cargo)
# Missing segment -> "any" -> fallback.
P = {
    "AUS": {"ore": "AUPHE", "coal": "AUNTL", "metcoal": "AUHPT", "grain": "AUKWI", "lng": "AUDAM", "any": "AUPHE", "box": "AUPKL", "alumina": "AUGLT", "bauxite": "AUWEI"},
    "BRA": {"ore": "BRTUB", "grain": "BRSSZ", "crude": "BRSSZ", "any": "BRSSZ", "box": "BRSSZ", "products": "BRSSZ"},
    "CHN": {"ore": "CNTAO", "coal": "CNCFD", "grain": "CNTSN", "crude": "CNNGB", "products": "CNNGB", "lng": "CNTSN", "lpg": "CNNGB", "any": "CNTAO", "box": "CNYSN", "bauxite": "CNRZH", "vegoil": "CNTSN"},
    "JPN": {"any": "JPCHB", "ore": "JPKSM", "coal": "JPKSM", "box": "JPYOK"},
    "KOR": {"any": "KRUSN", "ore": "KRKPO", "coal": "KRKAN", "lng": "KRUSN", "box": "KRUSN"},
    "TWN": {"any": "TWKHH"},
    "IND": {"any": "INMUN", "coal": "INPRT", "metcoal": "INPRT", "crude": "INSIK", "products": "INSIK", "lng": "INDAH", "fert": "INMUN", "vegoil": "INMUN", "ore": "INPRT"},
    "IDN": {"coal": "IDSRI", "any": "IDBPN", "vegoil": "IDDUM", "lng": "IDBXT", "ore": "IDMOR", "nickel": "IDMOR", "box": "IDBLW"},
    "MYS": {"vegoil": "MYPGU", "any": "MYKUA", "lng": "MYBTU", "box": "MYKUA"},
    "SGP": {"any": "SGSIN"},
    "VNM": {"any": "VNSGN"},
    "THA": {"any": "THLCH"},
    "PHL": {"any": "PHMNL", "ore": "PHNIC"},
    "RUS": {"coal": "RUVYP", "crude": "RUPRI", "products": "RUPRI", "grain": "RUNVS", "fert": "RUULU", "lng": "RUULU", "any": "RUNVS"},
    "UKR": {"any": "UAODS", "grain": "UAPIV", "ore": "UAPIV"},
    "USA": {"coal": "USBAL", "grain": "USMSY", "crude": "USCRP", "products": "USHOU", "lng": "USSAB", "lpg": "USHOU", "any": "USHOU", "box": "USHOU"},
    "CAN": {"ore": "CASEI", "coal": "CAVAN", "metcoal": "CAVAN", "grain": "CAVAN", "fert": "CAVAN", "any": "CAVAN", "crude": "CAVAN"},
    "MEX": {"any": "MXCOA", "crude": "MXDBT"},
    "COL": {"coal": "COPBO", "any": "COCTG"},
    "ARG": {"grain": "ARUPR", "any": "ARUPR", "vegoil": "ARUPR"},
    "CHL": {"ore": "CLANF", "any": "CLANF"},
    "PER": {"ore": "PECLL", "any": "PECLL"},
    "ZAF": {"coal": "ZARCB", "ore": "ZASDB", "any": "ZADUR", "manganese": "ZAPLZ"},
    "GIN": {"bauxite": "GNKMS", "ore": "GNMOR", "any": "GNCKY"},
    "SAU": {"crude": "SARTA", "products": "SAJUB", "lpg": "SARTA", "fert": "SAJUB", "any": "SARTA"},
    "ARE": {"crude": "AEFJR", "products": "AERUW", "lng": "AERUW", "lpg": "AERUW", "any": "AEJEA"},
    "QAT": {"lng": "QARLF", "lpg": "QAMES", "fert": "QAMES", "any": "QARLF", "crude": "QAMES"},
    "KWT": {"any": "KWMEA"},
    "IRQ": {"any": "IQBOT"},
    "IRN": {"crude": "IRKHK", "any": "IRBND"},
    "OMN": {"any": "OMSOH", "lng": "OMSOH"},
    "NGA": {"any": "NGBON", "crude": "NGBON", "lng": "NGBON"},
    "AGO": {"any": "AOCAB"},
    "NOR": {"any": "NOMON", "lng": "NOHFT"},
    "GBR": {"any": "GBSOU", "crude": "GBSCU"},
    "NLD": {"any": "NLRTM"},
    "BEL": {"any": "BEANR"},
    "DEU": {"any": "DEWVN", "box": "DEHAM"},
    "FRA": {"any": "FRFOS", "products": "FRLEH"},
    "ITA": {"any": "ITAUG", "box": "ITTRS"},
    "ESP": {"any": "ESALG"},
    "TUR": {"any": "TRCEY", "coal": "TRIZM"},
    "EGY": {"any": "EGALY", "grain": "EGDAM", "lng": "EGDAM"},
    "MAR": {"any": "MAJFL"},
    "DZA": {"any": "DZAZW"},
    "LBY": {"any": "LYTIP"},
    "KAZ": {"crude": "KZCPC"},
    "AZE": {"crude": "TRCEY"},
    "ZMB": {"any": "TZDAR"},
    "COD": {"any": "TZDAR"},
    "BLR": {"fert": "RUULU"},
    "GUY": {"any": "GYGEO"},
    "ECU": {"any": "ECESM"},
    "VEN": {"any": "VEPJO"},
    "TTO": {"any": "TTPTF"},
    "BGD": {"any": "BDCGP"},
    "PAK": {"any": "PKKHI"},
    "LKA": {"any": "LKCMB"},
    "POL": {"any": "PLGDN"},
    "LTU": {"any": "LTKLJ"},
    "ROU": {"any": "ROCND"},
    "BGR": {"any": "BGVAR"},
    "GRC": {"any": "GRPIR"},
    "ISR": {"any": "ILHFA"},
    "JOR": {"any": "JOAQB"},
    "MOZ": {"any": "MZMAP"},
    "TZA": {"any": "TZDAR"},
    "KEN": {"any": "KEMBA"},
    "GAB": {"any": "GAOWE"},
    "CMR": {"any": "CMDLA"},
    "CIV": {"any": "CIABJ"},
    "GHA": {"any": "GHTEM"},
    "SEN": {"any": "SNDKR"},
    "MRT": {"any": "MRNDB"},
    "NZL": {"any": "NZTRG"},
    "PNG": {"any": "PGPOM"},
    "BRN": {"any": "BNMUA"},
    "HKG": {"any": "HKHKG"},
    "CUB": {"any": "CUHAV"},
    "DOM": {"any": "DOHAI"},
    "PRT": {"any": "PTSIE"},
    "SWE": {"any": "SEGOT", "ore": "SELLA"},
    "FIN": {"any": "FIHEL"},
    "DNK": {"any": "DKAAR"},
    "IRL": {"any": "IEDUB"},
    "URY": {"any": "UYMVD"},
    "PRY": {"any": "ARUPR"},
}

SEGMENT = {
    "iron-ore": "ore", "bauxite": "bauxite", "alumina": "alumina", "manganese": "manganese", "copper-ore": "ore",
    "nickel-ore": "ore", "zinc-ore": "ore", "lead-ore": "ore", "coal": "coal", "crude-oil": "crude",
    "refined-products": "products", "lng": "lng", "lpg": "lpg", "wheat": "grain", "corn": "grain",
    "soybeans": "grain", "soymeal": "grain", "rice": "grain", "sugar": "grain", "rapeseed": "grain",
    "soyoil": "vegoil", "palm-oil": "vegoil", "potash": "fert", "phosphate-rock": "fert", "dap": "fert",
    "urea": "fert", "steel": "box", "copper-refined": "box", "aluminium": "box", "coffee": "box",
    "cocoa": "box", "cotton": "box", "nickel-int": "nickel",
}

_FALLBACK = {"ore": ["ore", "any"], "coal": ["coal", "any"], "metcoal": ["metcoal", "coal", "any"]}


def gateway(iso3, group):
    """Port code used for a country's trade in a given commodity group, or None."""
    seg = SEGMENT.get(group, "any")
    table = P.get(iso3)
    if not table:
        return None
    for key in [seg] + _FALLBACK.get(seg, []) + ["ore" if seg in ("bauxite", "alumina", "manganese", "nickel") else "any", "any"]:
        code = table.get(key)
        if code and (code in MANUAL or code in _sr):
            return code
    return None
