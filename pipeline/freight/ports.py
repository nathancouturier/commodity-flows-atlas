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
    "cocoa": "box", "cotton": "box", "nickel-int": "nickel", "nickel-fe": "nickel", "spodumene": "ore",
    # minor metals and chemicals that sail in bags, drums or containers (M-015): general cargo, as refined copper
    "lead-metal": "box", "zinc-metal": "box", "tin-metal": "box", "tin-ore": "box", "cobalt": "box", "lithium": "box",
    "rare-earths": "box",
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


# Groups that a row of their segment does not cover: raw sugar is not shipped from a wheat terminal, so a "grain"
# row (a page that names grain) is no sugar gateway; only a row that names "sugar" is.
OWN_FAMILY = {"sugar"}

# Basis of a gateway, published next to the port by the lane builder. The loader tries them in this order.
BASIS_PAGE = "page names the cargo"
BASIS_OTHER = "page names the cargo in the other direction"
BASIS_GENERAL = "general port of the country"
BASIS_LEGACY = "port used before, no page read"
BASIS_NEAREST = "nearest seaport"
BASES = (BASIS_PAGE, BASIS_OTHER, BASIS_GENERAL, BASIS_LEGACY, BASIS_NEAREST)  # strongest first

# Segments that may fall back on the country's general-cargo ("box") row: food, fertiliser, metals, general cargo.
GENERAL_SEGMENTS = {"grain", "vegoil", "fert", "box"}

# Oil, gas and ore terminals that the audit found carrying other cargo (plan 2.4, test G01; C-020 for Tubarao and
# Saldanha Bay): the legacy table and the nearest-port search may give them only for the cargo they serve.
_OIL_GAS = {"crude", "products", "lpg", "lng"}
TERMINALS = {
    "SARTA": _OIL_GAS, "IQBOT": _OIL_GAS, "NGBON": _OIL_GAS, "DZAZW": _OIL_GAS, "TRCEY": _OIL_GAS,
    "IDBPN": _OIL_GAS, "USCRP": _OIL_GAS, "AUPHE": {"iron-ore"}, "BRTUB": {"iron-ore"}, "ZASDB": {"iron-ore"},
}


def _serves(code, group):
    allowed = TERMINALS.get(code)
    return allowed is None or group in allowed or segment(group) in allowed


def _fams(group):
    return (group,) if group in OWN_FAMILY else (group, segment(group))


def _rows(iso3, group, role=None):
    """Rows of the country for the group, in the order of the tables. A row that names the group itself
    ("copper-ore") comes before a row that only names its segment ("ore"), so it is the principal one."""
    rows = [r for r in G.get(iso3, ()) if _known(r.code) and (role is None or r.role in (role, "both"))]
    out = []
    for fam in _fams(group):
        out += [r for r in rows if fam in r.families and r not in out]
    return out


def _box_rows(iso3, role=None):
    return [r for r in G.get(iso3, ()) if _known(r.code) and "box" in r.families and (role is None or r.role in (role, "both"))]


def candidates(iso3, group, role=None):
    """Candidate gateways of one end, principal first, as [(code, zone, basis)].

    A cargo family is on a row only when the cited page names the cargo, and when no row matches the loader never
    invents a port. In order: (1) the rows of the family in the role, then in the other role (a page that names
    the cargo names a port for it, whatever the direction, with its own basis; not for oil and gas terminals); (2) the legacy table's
    own entry for the family, then for food, fertiliser, metals and general cargo the country's general-cargo row;
    (3) the rest of the legacy chain (its "any" entry); (4) the nearest real seaport of the country. The legacy
    table never answers with an oil, gas or ore terminal of another cargo (TERMINALS). Each candidate carries its
    basis (BASES)."""
    key = ("cand", iso3, group, role)
    if key in _caches:
        return _caches[key]
    out, seen = [], set()

    def add(rows, basis):
        for r in rows:
            if r.code not in seen:
                out.append((r.code, r.zone, basis))
                seen.add(r.code)

    add(_rows(iso3, group, role), BASIS_PAGE)
    if not out and role and segment(group) not in ENERGY_SEGMENTS:
        # Not for oil and gas: an import terminal (a refinery's crude jetty, an LNG regasification plant) is no
        # export terminal, and the reverse.
        add(_rows(iso3, group), BASIS_OTHER)
    if not out and group not in OWN_FAMILY:
        # The legacy entry of the family itself (Dumai for Indonesian palm oil, Jubail for Saudi fertiliser,
        # Rosario for Argentine soy oil) is the port used before for that cargo: it comes before a general port.
        code = (LEGACY_P.get(iso3) or {}).get(segment(group))
        if code and _known(code) and _serves(code, group):
            out.append((code, zone_of(code), BASIS_LEGACY))
    if not out and segment(group) in GENERAL_SEGMENTS:
        add(_box_rows(iso3, role) or _box_rows(iso3), BASIS_GENERAL)
    if not out:
        code = _legacy_port(iso3, group)
        if code:
            out.append((code, zone_of(code), BASIS_LEGACY))
    if not out:
        code = nearest_port(iso3)
        if code:
            out.append((code, zone_of(code), BASIS_NEAREST))
    _caches[key] = out
    return out


def basis_of(iso3, group, role, code):
    """Basis of a gateway code at one end of a pair (one of BASES), for the lane builder to publish next to the port.
    A port chosen by a coast rule that is not among the candidates is a legacy choice of the rule (RUS_PORTS)."""
    for c, _, basis in candidates(iso3, group, role):
        if c == code:
            return basis
    if any(r.code == code for r in _rows(iso3, group, role)):
        return BASIS_PAGE
    if any(r.code == code for r in _rows(iso3, group)):
        return BASIS_OTHER
    if any(r.code == code for r in _box_rows(iso3)):
        return BASIS_GENERAL
    return BASIS_LEGACY


def source_of(iso3, group, role, code):
    """(source id, url) of the gateway row behind basis_of() for this end, or (None, None) when the basis is the
    port used before or the nearest seaport (no page read for that cargo)."""
    basis = basis_of(iso3, group, role, code)
    if basis == BASIS_PAGE:
        rows = _rows(iso3, group, role)
    elif basis == BASIS_OTHER:
        rows = _rows(iso3, group)
    elif basis == BASIS_GENERAL:
        rows = _box_rows(iso3, role) + _box_rows(iso3)
    else:
        return None, None
    for r in rows:
        if r.code == code:
            return r.src, r.url
    return None, None


def gateway(iso3, group, role=None):
    """Principal port code of a country for a commodity group, or None (landlocked, or no seaport).

    Same signature as before, plus an optional `role` ("load" or "discharge"). The order of candidates() applies:
    a sourced row of the family, the legacy entry of the family or the general-cargo row, the rest of the legacy
    table (never an oil, gas or ore terminal of another cargo), the nearest seaport. basis_of() says which."""
    cands = candidates(iso3, group, role)
    return cands[0][0] if cands else None


def _legacy_port(iso3, group):
    """The legacy chain of _legacy() (segment, fall-backs, "any"), skipping the terminals of another cargo."""
    seg = SEGMENT.get(group, "any")
    table = LEGACY_P.get(iso3)
    if not table:
        return None
    for key in [seg] + _FALLBACK.get(seg, []) + ["ore" if seg in ("bauxite", "alumina", "manganese", "nickel") else "any", "any"]:
        code = table.get(key)
        if code and _known(code) and _serves(code, group):
            return code
    return None


def _fallback(iso3, group, role=None):
    """The principal gateway of candidates() when it is not the nearest seaport (step 4), else None."""
    cands = [c for c in candidates(iso3, group, role) if c[2] != BASIS_NEAREST]
    return cands[0][0] if cands else None


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
    """[{id, name, ports}] for data/freight/zones.json. A zone with no gateway row is left out."""
    out = []
    for zid, name in ZONES.items():
        codes = []
        for rows in G.values():
            for r in rows:
                if r.zone == zid and r.code not in codes:
                    codes.append(r.code)
        if codes:
            out.append({"id": zid, "name": name, "ports": codes})
    return out


# ------------------------------------------------------------------ geography used by the rules
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))


def _load_json(*parts):
    with open(os.path.join(_ROOT, *parts), encoding="utf-8") as f:
        return json.load(f)


def _load_countries():
    c = _caches.get("countries")
    if c is None:
        idx = {x["c"]: x for x in _load_json("data", "countries", "index.json")}
        coastal, extra = set(), {}
        if os.path.exists(os.path.join(_ROOT, "pipeline", "cache", "adjacency.json")):
            coastal = set(_load_json("pipeline", "cache", "adjacency.json").get("coastal", []))
        if os.path.exists(os.path.join(_ROOT, "pipeline", "geo", "places_extra.json")):
            extra = {x["c"]: x for x in _load_json("pipeline", "geo", "places_extra.json")}
        c = _caches["countries"] = (idx, coastal, extra)
    return c


def _km(lon1, lat1, lon2, lat2):
    import math
    p = math.pi / 180
    return 6371 * math.hypot((lon2 - lon1) * p * math.cos((lat1 + lat2) * p / 2), (lat2 - lat1) * p)


# A searoute "port" is a real seaport when it lies within this distance of the base map's coastline or of the sea
# network (estuary ports such as Hamburg or Kalama are far from the generalised coastline but on the network).
# The searoute list also holds inland towns (Shelton, Nebraska; Bhusawal; Kiev; Giessen; Riyadh), 300 to 1,200 km
# from both, and a few river ports (Sapele, Modena) about 60 to 100 km away.
SEAPORT_KM = 20


def _sea_points():
    pts = _caches.get("seapts")
    if pts is None:
        import numpy as np
        topo = _load_json("data", "geo", "countries.topo.json")
        tr = topo["transform"]
        users = {}
        for g in topo["objects"]["countries"]["geometries"]:
            a = g.get("arcs", [])
            flat = [x for ring in a for x in ring] if g["type"] == "Polygon" else [x for poly in a for ring in poly for x in ring]
            for x in flat:
                users.setdefault(x if x >= 0 else ~x, set()).add(g["properties"]["c"])
        xy = []
        for i, arc in enumerate(topo["arcs"]):
            if len(users.get(i, ())) != 1:  # an arc shared by two countries is a land border, not a coast
                continue
            x = y = 0
            line = []
            for dx, dy in arc:
                x, y = x + dx, y + dy
                line.append((x * tr["scale"][0] + tr["translate"][0], y * tr["scale"][1] + tr["translate"][1]))
            for (x1, y1), (x2, y2) in zip(line, line[1:]):
                n = max(1, int(max(abs(x2 - x1), abs(y2 - y1)) / 0.05))
                xy += [(x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n) for k in range(n)]
        with open(os.path.join(os.path.dirname(_SR), "marnet_searoute.geojson"), encoding="utf-8") as f:
            for feat in json.load(f)["features"]:
                g = feat["geometry"]
                for line in (g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]):
                    xy += [tuple(p[:2]) for p in line]
        pts = _caches["seapts"] = np.array(xy)
    return pts


def sea_km(code):
    """Distance in km from a port to the nearest point of the coastline or of the sea network."""
    import math
    pts = _sea_points()
    x, y = port(code)["at"]
    dx = (pts[:, 0] - x) * math.cos(math.radians(y)) * 111.2
    dy = (pts[:, 1] - y) * 111.2
    return float((dx * dx + dy * dy).min() ** 0.5)


def is_seaport(code):
    key = ("sea", code)
    if key not in _caches:
        _caches[key] = _known(code) and sea_km(code) <= SEAPORT_KM
    return _caches[key]


def nearest_port(iso3):
    """Last-resort gateway: the real seaport of the country closest to its label point, never an inland place of
    the searoute list nor an oil, gas or ore terminal of TERMINALS (None for a landlocked country)."""
    idx, coastal, extra = _load_countries()
    if iso3 in extra and extra[iso3].get("port") and _known(extra[iso3]["port"]):
        return extra[iso3]["port"]
    meta = idx.get(iso3)
    if not meta or iso3 not in coastal or not meta.get("a2"):
        return None
    near = sorted((_km(meta["at"][0], meta["at"][1], x, y), code) for code, (_, (x, y)) in _sr.items()
                  if code[:2] == meta["a2"] and code not in TERMINALS)
    return next((code for _, code in near if is_seaport(code)), None)


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
    """Candidate gateways of one end, principal first, as [(code, zone)]: candidates() without the basis."""
    return [(c, z) for c, z, _ in candidates(iso3, group, role)]


def _zone_fallback(iso3, group, role, zones):
    """A port in the zones a coast rule asks for when no candidate of the family is there: the country's
    general-cargo row in those zones (food, fertiliser, metals, general cargo), else its legacy port when that port
    lies on the same ocean. None when there is neither."""
    if segment(group) in GENERAL_SEGMENTS:
        for r in _box_rows(iso3, role) + _box_rows(iso3):
            if r.zone in zones:
                return (r.code, r.zone)
    code = _legacy_port(iso3, group)
    if code and (zone_of(code) in zones or (zone_of(code) is None and ocean_of(code) in {ZONE_OCEAN.get(z) for z in zones})):
        return (code, zone_of(code))
    return None


def _in_zone(iso3, group, role, cands, zones):
    hit = [c for c in cands if c[1] in zones]
    if hit:
        return hit[0]
    return _zone_fallback(iso3, group, role, zones)


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
    cands = {"load": _cands(o, group, "load"), "discharge": _cands(d, group, "discharge")}
    iso = {"load": o, "discharge": d}
    chosen, used, paired = {}, None, None
    # Rules that read the other end's country run first; rules that read the ocean of the other end's port run
    # second, on the port the first pass chose for it.
    for ocean_pass in (False, True):
        for role, orole in (("load", "discharge"), ("discharge", "load")):
            if role in chosen or paired:
                continue
            ocands = chosen.get(orole, cands[orole])
            for rule in _rules_for(iso[role], group, role):
                if (rule["kind"] == "ocean") != ocean_pass:
                    continue
                two = bool(rule.get("two_ocean")) and any(r.get("two_ocean") and r["country"] == iso[orole] for r in COAST_RULES)
                sides = {ocean_of(c[0]) for c in ocands[:MAX_OPTIONS]} - {None}
                if ocean_pass and not two and orole not in chosen and len(sides) > 1:
                    # The other end is open on two oceans: each of its options gets this end's gateway on its ocean,
                    # so that no option pairs a Pacific port with a gateway chosen for the Atlantic.
                    pairs = []
                    for oc in ocands[:MAX_OPTIONS]:
                        side = ocean_of(oc[0])
                        mine = _in_zone(iso[role], group, role, cands[role], rule["zones"][side]) if side in rule["zones"] else None
                        mine = mine or (cands[role][0] if cands[role] else None)
                        if mine:
                            pairs.append((mine, oc) if role == "load" else (oc, mine))
                    if pairs:
                        paired, used = pairs, rule.get("id")
                        break
                    continue
                pick = _apply_rule(rule, iso[role], group, role, iso[orole], ocands[0][0] if ocands else None, two)
                if not pick:
                    continue
                if pick[0] == "port":
                    chosen[role] = [(pick[1], zone_of(pick[1]))]
                elif pick[0] == "ports":
                    chosen[role] = [(c, zone_of(c)) for c in pick[1]]
                else:
                    hit = _in_zone(iso[role], group, role, cands[role], pick[1])
                    if not hit:
                        continue
                    chosen[role] = [hit]
                used = rule.get("id")
                break
    if paired:
        opts = []
        for ld, dd in paired:
            op = Option(ld[0], dd[0], None)
            if op not in opts:
                opts.append(op)
        return Assignment(opts[0], opts, "open" if len(opts) > 1 else "rule", used)
    cl = chosen.get("load", cands["load"])
    cd = chosen.get("discharge", cands["discharge"])
    if not cl or not cd:
        main = Option(cl[0][0] if cl else None, cd[0][0] if cd else None, None)
        return Assignment(main, [main], "unrouted", used)
    main = Option(cl[0][0], cd[0][0], None)
    opts = [main]
    for c in cl[1:MAX_OPTIONS]:
        if _same_side(c[0], main.load, main.discharge):
            opts.append(Option(c[0], cd[0][0], None))
    for c in cd[1:MAX_OPTIONS]:
        if _same_side(c[0], main.discharge, main.load):
            opts.append(Option(cl[0][0], c[0], None))
    basis = "rule" if used and len(opts) == 1 else ("open" if len(opts) > 1 else "single")
    return Assignment(main, opts, basis, used)


def _same_side(alt, own, other):
    """An option of one end on the other ocean than its main gateway is listed only when the other end of the pair
    lies on that ocean too (Kalama for Japan, not for Germany or Brazil)."""
    side = ocean_of(alt)
    if side is None or side == ocean_of(own):
        return True
    if _west_indian(other):
        # East and Southern Africa, the Red Sea and the Gulf are nearer the Atlantic side through Suez or round
        # the Cape (US Gulf to Durban 8,100 nm, Kalama to Durban 11,300 nm)
        return False
    return side == ocean_of(other)


def _west_indian(code):
    if not _known(code):
        return False
    lon, lat = port(code)["at"]
    return 20 < lon < 60 and -40 < lat < 31

load_modules()
