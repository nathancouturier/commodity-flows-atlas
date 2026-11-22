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
    # Pengerang keeps its own private code: MYPGU is the UN/LOCODE of Pasir Gudang, which searoute lists with the
    # right name and coordinates, and the old entry hid it behind Pengerang's coordinates (audit C-010, FR-16).
    "MYPRG": ("Pengerang", "MYS", 104.13, 1.37),
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
        return {"id": code, "name": RENAME.get(code, n), "c": c, "at": [x, y]}
    n, (x, y) = _sr[code]
    return {"id": code, "name": RENAME.get(code, n), "c": code[:2], "at": [round(x, 3), round(y, 3)]}


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

# The table above is the legacy table: one port per country and segment. It still answers for the countries and
# families that have no row in the new tables (pipeline/freight/gateways/).
LEGACY_P = P


def _legacy(iso3, group):
    """The old rule: segment key, then the fall-backs, ending on "any"."""
    seg = SEGMENT.get(group, "any")
    table = LEGACY_P.get(iso3)
    if not table:
        return None
    for key in [seg] + _FALLBACK.get(seg, []) + ["ore" if seg in ("bauxite", "alumina", "manganese", "nickel") else "any", "any"]:
        code = table.get(key)
        if code and (code in MANUAL or code in _sr):
            return code
    return None


def _legacy_strict(iso3, group):
    """For a country that has rows in the new tables: only the legacy entry of the family itself, never "any"
    (that fall-back put wheat on the crude jetty of Ras Tanura and Canadian potash on a container terminal)."""
    seg = SEGMENT.get(group, "any")
    table = LEGACY_P.get(iso3) or {}
    keys = [seg] + (["ore"] if seg in ("bauxite", "alumina", "manganese", "nickel") else [])
    if seg in ENERGY_SEGMENTS:
        # The "any" entry of the legacy table is the country's oil and gas port (Mongstad for Norway, Ulsan for
        # Korea). A country whose new rows cover one energy family (LNG terminals from the atlas's layer) keeps its
        # present port for the others until a page is read for them (plan 2.4: "the country keeps its present port").
        keys.append("any")
    for key in keys:
        code = table.get(key)
        if code and (code in MANUAL or code in _sr):
            return code
    return None


ENERGY_SEGMENTS = ("crude", "products", "lpg", "lng")


# ------------------------------------------------------------------ the new tables
# pipeline/freight/gateways/{food,coasts,energy}.py each expose G = {iso3: [row, ...]} with plain tuples
#   (code, zone, families, role, src, url, note)
# plus, optionally, MANUAL_EXTRA (ports missing from searoute, same shape as MANUAL), RENAME (display names),
# ZONES / ZONE_OCEAN (coasts only), COAST_RULES (coasts only) and TRANSIT (energy only).
# A module that does not exist yet is skipped; a module that exists is loaded strictly.
import importlib  # noqa: E402
import sys  # noqa: E402
from collections import namedtuple  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

Gw = namedtuple("Gw", "code zone families role src url note")
Option = namedtuple("Option", "load discharge w")
Assignment = namedtuple("Assignment", "main options basis rule", defaults=(None,))
ROLES = ("load", "discharge", "both")
MODULES = ("food", "coasts", "energy")  # merge order: for one country, rows of food come first, then coasts, then energy

G = {}          # iso3 -> [Gw]
ZONES = {}      # zone id -> name
ZONE_OCEAN = {}  # zone id -> "atlantic" | "pacific" (pacific = Indo-Pacific side, see ocean_of)
COAST_RULES = []
TRANSIT = {}
RENAME = {}


def _gw(row):
    if isinstance(row, Gw):
        return row
    if isinstance(row, dict):
        row = (row["code"], row.get("zone"), row["families"], row["role"], row.get("src"), row.get("url"), row.get("note"))
    code, zone, fams, role, src, url, note = row
    fams = frozenset([fams] if isinstance(fams, str) else fams)
    return Gw(code, zone, fams, role, src, url, note)


def load_modules(names=MODULES):
    """Merge the data modules into the module-level tables. Returns the names that were loaded."""
    g, zones, zocean, rules, transit, rename, loaded = {}, {}, {}, [], {}, {}, []
    for name in names:
        try:
            mod = importlib.import_module("gateways." + name)
        except ModuleNotFoundError as e:
            if e.name in ("gateways", "gateways." + name):
                continue
            raise
        loaded.append(name)
        for iso3, rows in getattr(mod, "G", {}).items():
            have = g.setdefault(iso3, [])
            seen = {(r.code, r.role, r.families) for r in have}
            for row in rows:
                r = _gw(row)
                if (r.code, r.role, r.families) not in seen:
                    have.append(r)
                    seen.add((r.code, r.role, r.families))
        for code, v in getattr(mod, "MANUAL_EXTRA", {}).items():
            MANUAL.setdefault(code, tuple(v))
        for code, v in getattr(mod, "MANUAL_SRC", {}).items():
            MANUAL_SRC.setdefault(code, dict(v))
        zones.update(getattr(mod, "ZONES", {}))
        zocean.update(getattr(mod, "ZONE_OCEAN", {}))
        rules.extend(getattr(mod, "COAST_RULES", []))
        transit.update(getattr(mod, "TRANSIT", {}))
        rename.update(getattr(mod, "RENAME", {}))
    G.clear()
    G.update(g)
    ZONES.clear()
    ZONES.update(zones)
    ZONE_OCEAN.clear()
    ZONE_OCEAN.update(zocean)
    COAST_RULES[:] = rules
    TRANSIT.clear()
    TRANSIT.update(transit)
    RENAME.clear()
    RENAME.update(rename)
    _caches.clear()
    return loaded


_caches = {}


def _known(code):
    return code in MANUAL or code in _sr


def segment(group):
    return SEGMENT.get(group, "any")


def _rows(iso3, group, role=None):
    """Rows of the country for the group, in the order of the tables. A row that names the group itself
    ("copper-ore") beats a row that only names its segment ("ore")."""
    rows = [r for r in G.get(iso3, ()) if _known(r.code) and (role is None or r.role in (role, "both"))]
    for fam in (group, segment(group)):
        hit = [r for r in rows if fam in r.families]
        if hit:
            return hit
    return []


def gateway(iso3, group, role=None):
    """Principal port code of a country for a commodity group, or None.

    Same signature as before, plus an optional `role` ("load" or "discharge"). A country that has rows in the new
    tables never gets a port of another family: no row of the family means its own legacy entry, else None.
    A country without any new row is answered by the legacy table, as before."""
    if iso3 in G:
        rows = _rows(iso3, group, role)
        if rows:
            return rows[0].code
        return _legacy_strict(iso3, group)
    return _legacy(iso3, group)


def zone_of(code):
    """Freight zone of a port code, from the first row that names it, or None."""
    z = _caches.get("zone")
    if z is None:
        z = {}
        for rows in G.values():
            for r in rows:
                if r.zone and r.code not in z:
                    z[r.code] = r.zone
        _caches["zone"] = z
    return z.get(code)


def port_meta(code):
    """{zone, s, url} of a port from the first row that names it (what the lane file's `ports` table publishes)."""
    for rows in G.values():
        for r in rows:
            if r.code == code:
                return {"zone": r.zone, "s": r.src, "url": r.url}
    mn = MANUAL_SRC.get(code)
    return dict(mn) if mn else {"zone": None, "s": None, "url": None}


MANUAL_SRC = {}  # code -> {zone, s, url} of a manual port that is in no gateway row (set by the data modules)


def zones():
    """[{id, name, ports}] for data/freight/zones.json."""
    out = []
    for zid, name in ZONES.items():
        codes = []
        for rows in G.values():
            for r in rows:
                if r.zone == zid and r.code not in codes:
                    codes.append(r.code)
        out.append({"id": zid, "name": name, "ports": codes})
    return out


# ------------------------------------------------------------------ geography used by the rules
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))


def _load_countries():
    c = _caches.get("countries")
    if c is None:
        idx = {x["c"]: x for x in json.load(open(os.path.join(_ROOT, "data", "countries", "index.json"), encoding="utf-8"))}
        coastal = set()
        p = os.path.join(_ROOT, "pipeline", "cache", "adjacency.json")
        if os.path.exists(p):
            coastal = set(json.load(open(p, encoding="utf-8")).get("coastal", []))
        extra = {}
        p = os.path.join(_ROOT, "pipeline", "geo", "places_extra.json")
        if os.path.exists(p):
            extra = {x["c"]: x for x in json.load(open(p, encoding="utf-8"))}
        c = _caches["countries"] = (idx, coastal, extra)
    return c


def _km(lon1, lat1, lon2, lat2):
    import math
    p = math.pi / 180
    return 6371 * math.hypot((lon2 - lon1) * p * math.cos((lat1 + lat2) * p / 2), (lat2 - lat1) * p)


def nearest_port(iso3):
    """Fallback gateway: the searoute port of the country closest to its label point (None for a landlocked one)."""
    idx, coastal, extra = _load_countries()
    if iso3 in extra and extra[iso3].get("port") and _known(extra[iso3]["port"]):
        return extra[iso3]["port"]
    meta = idx.get(iso3)
    if not meta or iso3 not in coastal or not meta.get("a2"):
        return None
    best, bd = None, 1e9
    for code, (_, (x, y)) in _sr.items():
        if code[:2] != meta["a2"]:
            continue
        d = _km(meta["at"][0], meta["at"][1], x, y)
        if d < bd:
            best, bd = code, d
    return best


# countries whose own coast decides nothing: a2 prefixes of the Pacific coast of the Americas
_PACIFIC_A2 = {"PE", "CL", "EC", "SV"}


def ocean_of(code):
    """"pacific" for the Indo-Pacific side (east of 20 E except the Mediterranean, Black Sea and Baltic, plus the
    Pacific coast of the Americas) or "atlantic" for the rest. Zone first, geometry second; same test as
    routing.indo_pacific for the east."""
    z = zone_of(code)
    if z in ZONE_OCEAN:
        return ZONE_OCEAN[z]
    if not _known(code):
        return None
    c = MANUAL[code] if code in MANUAL else None
    lon, lat = (c[2], c[3]) if c else (_sr[code][1][0], _sr[code][1][1])
    if 20 < lon <= 180 and not (lat > 30 and lon < 45):
        return "pacific"
    if code[:2] in _PACIFIC_A2 or (lon < -100 and lat > 14):
        return "pacific"
    return "atlantic"


def _cands(iso3, group, role):
    """Candidate gateways of one end, principal first, as [(code, zone)]. Falls back to the legacy table and then
    to the nearest port of the country."""
    rows = _rows(iso3, group, role) if iso3 in G else []
    out, seen = [], set()
    for r in rows:
        if r.code not in seen:
            out.append((r.code, r.zone))
            seen.add(r.code)
    if out:
        return out
    code = _legacy_strict(iso3, group) if iso3 in G else _legacy(iso3, group)
    code = code or nearest_port(iso3)
    return [(code, zone_of(code))] if code else []


def _side_sets(rule, other):
    for side, members in rule["sides"].items():
        if other in members:
            return side
    return rule.get("default_side")


def _apply_rule(rule, iso3, group, role, other, other_port, other_is_two_ocean):
    """The code(s) a coast rule prefers for this end, or None when the rule has nothing to say."""
    kind = rule["kind"]
    if kind == "sides":                       # one port per group and side of the other end
        open_sides = rule.get("open", {}).get((group, other))
        if open_sides:                        # the side cannot be told from the customs data: several options
            codes = [rule["ports"][group][s] for s in open_sides if rule["ports"].get(group, {}).get(s)]
            return ("ports", codes) if codes else None
        side = rule.get("special", {}).get((group, other)) or _side_sets(rule, other)
        code = rule["ports"].get(group, {}).get(side)
        return ("port", code) if code else None
    if kind == "origin":                      # a named port when the other end is in a set
        if other in rule["when_other_in"]:
            return ("port", rule["port"])
        return None
    if kind == "basin":                       # zone chosen from the basin of the other end (country sets)
        for basin, members in rule["basins"].items():
            if other in members:
                return ("zone", rule["zones"][basin])
        return None
    if kind == "ocean":                       # zone chosen from the ocean of the other end's principal port
        if other_is_two_ocean:
            return ("zone", rule["zones"]["atlantic"])
        if not other_port:
            return None
        side = ocean_of(other_port)
        return ("zone", rule["zones"][side]) if side in rule["zones"] else None
    raise ValueError("unknown coast rule kind " + kind)


def _rules_for(iso3, group, role):
    seg = segment(group)
    for rule in COAST_RULES:
        if rule["country"] != iso3 or rule.get("role", "both") not in (role, "both"):
            continue
        if rule.get("groups") and group not in rule["groups"]:
            continue
        if rule.get("segments") and seg not in rule["segments"]:
            continue
        yield rule


MAX_OPTIONS = 3  # per end


def assign(o, d, group):
    """Load and discharge gateways of an exporter-importer pair for a group.

    Returns Assignment(main, options, basis, rule):
      basis "single"   one gateway at each end
      basis "rule"     a coast rule (COAST_RULES) chose the gateway of one end or both; one option
      basis "open"     an end has several gateways and nothing decides between them: `options` lists them, the
                       main one is the principal gateway (first row of the family), never the shortest route
      basis "unrouted" an end has no gateway at all (landlocked, or no port in searoute): main has a None end
    Options vary one end at a time around the main option (at most MAX_OPTIONS gateways per end); `w` is None
    until a measured split (pipeline/freight/splits/) gives a weight."""
    cl, cd = _cands(o, group, "load"), _cands(d, group, "discharge")
    chosen, used = {}, None
    ends = (("load", o, cl, d, cd, "discharge"), ("discharge", d, cd, o, cl, "load"))
    for role, iso, cands, other, ocands, orole in ends:
        other_port = ocands[0][0] if ocands else None
        for rule in _rules_for(iso, group, role):
            two = bool(rule.get("two_ocean")) and any(r.get("two_ocean") and r["country"] == other for r in COAST_RULES)
            pick = _apply_rule(rule, iso, group, role, other, other_port, two)
            if not pick:
                continue
            if pick[0] == "port":
                chosen[role] = [(pick[1], zone_of(pick[1]))]
            elif pick[0] == "ports":
                chosen[role] = [(c, zone_of(c)) for c in pick[1]]
            else:
                inzone = [c for c in cands if c[1] in pick[1]]
                if not inzone:
                    continue
                chosen[role] = inzone[:1]
            used = rule.get("id")
            break
    cl = chosen.get("load", cl)
    cd = chosen.get("discharge", cd)
    if not cl or not cd:
        main = Option(cl[0][0] if cl else None, cd[0][0] if cd else None, None)
        return Assignment(main, [main], "unrouted", used)
    main = Option(cl[0][0], cd[0][0], None)
    opts = [main]
    for c in cl[1:MAX_OPTIONS]:
        opts.append(Option(c[0], cd[0][0], None))
    for c in cd[1:MAX_OPTIONS]:
        opts.append(Option(cl[0][0], c[0], None))
    basis = "rule" if used and len(opts) == 1 else ("open" if len(opts) > 1 else "single")
    return Assignment(main, opts, basis, used)


load_modules()
