"""
Gateways of the multi-coast countries and of the dry-bulk and metal cargoes, the coast rules and the freight zones
(package E4b of the trade-engine repair; plan section 2.4).

Plain data, no import of the other pipeline modules, so that ports.py can load it without a circular import.

G = {iso3: [(code, zone, families, role, src, url, note), ...]}
  families  segments of ports.SEGMENT (coal, ore, grain, fert, box, ...) or group ids ("iron-ore", "copper-ore",
            "alumina"): a row that names the group beats a row that names its segment
  role      "load", "discharge" or "both"
  src, url  a source id of data/sources.json and the page read; rows adapted from Wikipedia are CC BY-SA 4.0
  The first row of a family and role of a country is its principal gateway; the others are its coast options.
ZONES       freight zones (id -> name); written to data/freight/zones.json by build_lanes.py
ZONE_OCEAN  zone -> "atlantic" | "pacific" where a zone lies on one side only. "pacific" is the Indo-Pacific side
            (the test of routing.indo_pacific: east of 20 E except the Mediterranean, Black Sea and Baltic, and the
            Pacific coast of the Americas). Zones that straddle (s-africa, e-africa, red-sea) are left out and the
            ports.ocean_of() test reads the port's own coordinates.
COAST_RULES the geographic rules that choose a gateway from the other end of the pair (ports.assign()). Every rule is
            an Atlas assumption: it carries its reason and, where a page was read, the page.

How a row was admitted. Each page was read on 22 November 2026 (English Wikipedia). A family is on a row only when
the page names that cargo, with these readings, each marked "read as" in the note: "bulk cargoes" or "dry bulk" is
read as coal and ore for a port that the page ties to coal or ore, and a "container terminal" as general cargo
(`box`). A row whose page does not say what the port ships is not committed: the candidates are in UNSOURCED, with
the reason. Nothing here comes from memory.
"""

W = "https://en.wikipedia.org/wiki/"

ZONES = {
    "us-gulf": "US Gulf",
    "us-atlantic": "US Atlantic coast",
    "us-pnw": "US Pacific Northwest (Columbia River, Puget Sound)",
    "us-west": "US Pacific coast south of Puget Sound",
    "canada-east": "Canada east (St Lawrence, Maritimes)",
    "canada-west": "Canada west (British Columbia)",
    "mexico-gulf": "Mexico, Gulf coast",
    "mexico-pacific": "Mexico, Pacific coast",
    "cam-caribbean": "Central America, Caribbean coast",
    "cam-pacific": "Central America, Pacific coast",
    "caribbean": "Caribbean and north coast of South America",
    "ecsa": "East coast South America",
    "wcsa": "West coast South America",
    "nw-europe": "North-West Europe (Skaw to Brest)",
    "baltic": "Baltic",
    "med": "Mediterranean",
    "black-sea": "Black Sea",
    "meg": "Middle East Gulf (inside Hormuz)",
    "red-sea": "Red Sea",
    "wc-india": "India and Pakistan, west coast",
    "ec-india": "India and Bangladesh, east coast",
    "sea": "South-East Asia",
    "s-china": "South China",
    "n-china": "North China",
    "e-china": "East China (Shanghai, Ningbo)",
    "japan-korea": "Japan and Korea",
    "w-australia": "Western Australia",
    "e-australia": "Eastern Australia",
    "waf": "West Africa",
    "s-africa": "Southern Africa",
    "e-africa": "East Africa",
}

ZONE_OCEAN = {
    "us-gulf": "atlantic", "us-atlantic": "atlantic", "us-pnw": "pacific", "us-west": "pacific",
    "canada-east": "atlantic", "canada-west": "pacific", "mexico-gulf": "atlantic", "mexico-pacific": "pacific",
    "cam-caribbean": "atlantic", "cam-pacific": "pacific", "caribbean": "atlantic", "ecsa": "atlantic",
    "wcsa": "pacific", "nw-europe": "atlantic", "baltic": "atlantic", "med": "atlantic", "black-sea": "atlantic",
    "meg": "pacific", "wc-india": "pacific", "ec-india": "pacific", "sea": "pacific", "s-china": "pacific",
    "n-china": "pacific", "e-china": "pacific", "japan-korea": "pacific", "w-australia": "pacific",
    "e-australia": "pacific", "waf": "atlantic",
    # zones added by the energy module (gateways/energy.py)
    "n-australia": "pacific", "gulf-of-oman": "pacific", "taiwan": "pacific", "arctic-russia": "atlantic",
    "russia-far-east": "pacific",
}

# Ports that the searoute list lacks are added by the other modules (MANUAL_EXTRA); this module needs none.

# Display names: the searoute list names this point after one terminal.
RENAME = {
    "CAVAN": "Vancouver",   # searoute: "Vancouver Centerm Terminal", a container terminal; the point is the port's
}

G = {
    # ------------------------------------------------------------------ North America
    "USA": [
        ("USKAM", "us-pnw", ("grain",), "load", "wikipedia", W + "Kalama,_Washington",
         "Port of Kalama: TEMCO loads over 125 oceangoing vessels a year with soybeans, corn and wheat for export (China, South-East Asia, Central America, Middle East). Columbia River grain terminals; searoute names the port Kalama"),
        ("USHNV", "us-atlantic", ("coal",), "load", "wikipedia", W + "Hampton_Roads",
         "Hampton Roads: 'the U.S. leader in coal exports', coal piers at Lambert's Point (Norfolk) and Newport News; searoute port Hampton Roads"),
        ("USBAL", "us-atlantic", ("coal",), "load", "wikipedia", W + "Port_of_Baltimore",
         "Port of Baltimore 'handles one-fourth of the country's coal exports'"),
        ("USMOB", "us-gulf", ("coal",), "load", "wikipedia", W + "Port_of_Mobile",
         "Port of Mobile: McDuffie Terminal is one of the largest coal terminals; fourth largest US coal exporter in 2012"),
    ],
    "CAN": [
        ("CAVAN", "canada-west", ("coal",), "load", "wikipedia", W + "Roberts_Bank_Superport",
         "Roberts Bank (Westshore Terminals), part of the Port of Vancouver: 'the busiest single coal export terminal in North America'; the searoute point Vancouver stands for the port"),
    ],
    # ------------------------------------------------------------------ South America
    "BRA": [
        ("BRTUB", "ecsa", ("iron-ore",), "load", "wikipedia", W + "Port_of_Tubar%C3%A3o",
         "Port of Tubarao: created by Vale 'to export iron ore from the Iron Quadrangle'; the world's largest iron-ore port in 2007"),
        ("BRVLC", "ecsa", ("alumina", "bauxite"), "load", "wikipedia", W + "Barcarena,_Par%C3%A1",
         "Barcarena (Para) has a port and an economy based on bauxite; the Alunorte alumina refinery is at Barcarena (Wikipedia, Barcarena water contamination); searoute names the port Vila do Conde. That the cargo leaves from the Vila do Conde terminals is read from the two pages together"),
        ("BRITQ", "ecsa", ("alumina", "bauxite"), "load", "wikipedia", W + "Port_of_Itaqui",
         "Port of Itaqui, Sao Luis (Maranhao): main cargoes include aluminium ingots and bars; the Alumar alumina refinery is at Sao Luis (Wikipedia, List of alumina refineries). The page does not name alumina: read as the port of that refinery"),
    ],
    "COL": [
        ("COPBO", "caribbean", ("coal",), "load", "wikipedia", W + "Cerrej%C3%B3n",
         "Puerto Bolivar, the Cerrejon coal port: 'the largest coal-export port in Latin America'"),
    ],
    # ------------------------------------------------------------------ Oceania
    "AUS": [
        ("AUNTL", "e-australia", ("coal",), "load", "wikipedia", W + "Port_of_Newcastle",
         "Port of Newcastle: 'the world's busiest coal export port'"),
        ("AUHPT", "e-australia", ("coal",), "load", "wikipedia", W + "Hay_Point,_Queensland",
         "Hay Point has two bulk coal terminals (Dalrymple Bay and Hay Point Coal Terminal), Queensland"),
        ("AUGLT", "e-australia", ("coal", "alumina"), "load", "wikipedia", W + "Port_of_Gladstone",
         "Port of Gladstone: fourth largest coal exporting terminal; major exports include coal and alumina"),
        ("AUPHE", "w-australia", ("iron-ore",), "load", "wikipedia", W + "Port_Hedland",
         "Port Hedland: exported 519 Mt of iron ore in 2017-18; one of three major Pilbara iron-ore ports"),
        ("AUWEI", "e-australia", ("bauxite",), "load", "wikipedia", W + "Weipa",
         "Weipa: 'the Port of Weipa is mainly involved in exports of bauxite'"),
        ("AUTSV", "e-australia", ("copper-ore", "zinc-ore", "lead-ore"), "load", "wikipedia", W + "Port_of_Townsville",
         "Port of Townsville: 'the number one port in Australia for exports in copper, zinc, lead and sugar' (concentrates)"),
    ],
    # ------------------------------------------------------------------ Asia
    "IND": [
        ("INPRT", "ec-india", ("coal",), "discharge", "wikipedia", W + "Paradip_Port",
         "Paradip Port: 'mainly transports bulk cargoes and crude oil', dry and break-bulk terminals, handles Capesize; coal is read from 'bulk cargoes'"),
        ("INKRI", "ec-india", ("coal",), "discharge", "wikipedia", W + "Krishnapatnam_Port",
         "Krishnapatnam Port: a mechanised coal berth in phase 1; a further six coal berths planned"),
        ("INMUN", "wc-india", ("coal",), "discharge", "wikipedia", W + "Mundra_Port",
         "Mundra Port: service agreement with Tata Power 'to produce power for handling coal cargo imports'; open storage for coal"),
    ],
    "CHN": [
        ("CNCFD", "n-china", ("coal",), "discharge", "wikipedia", W + "Caofeidian",
         "Caofeidian: 'a large coal and ore discharging port, one of the prime ports of Northern China'"),
    ],
    "IDN": [
        ("IDAMA", "sea", ("copper-ore",), "load", "wikipedia", W + "Grasberg_mine",
         "Grasberg: the copper-gold concentrate slurry goes by pipeline to the seaport of Amamapare, is dried and shipped. Batu Hijau (Benete, Sumbawa) is the second concentrate port and is not committed: no coordinates were read (UNSOURCED)"),
    ],
    # ------------------------------------------------------------------ Africa
    "ZAF": [
        ("ZARCB", "s-africa", ("coal",), "load", "wikipedia", W + "Port_of_Richards_Bay",
         "Port of Richards Bay: the Richards Bay Coal Terminal, the largest coal export facility in Africa"),
        ("ZARCB", "s-africa", ("alumina",), "discharge", "wikipedia", W + "Richards_Bay",
         "Richards Bay: two aluminium smelters (Hillside, Bayside) operated by South32 stand at the port. The page does not name alumina imports: read as the port of those smelters"),
    ],
    # ------------------------------------------------------------------ Russia (moved from build_lanes.RUS_PORTS)
    "RUS": [
        ("RUVYP", "russia-far-east", ("coal",), "load", "wikipedia", W + "Vostochny_Port",
         "Vostochny Port: the largest stevedoring firm 'specializes in coal handling with conveyor equipment'"),
        ("RUTAM", "black-sea", ("coal",), "load", "wikipedia", W + "Port_of_Taman",
         "Port of Taman: terminals for oil products, LPG, ammonia, grain, coal, fertilisers, iron ore and containers"),
        ("RUULU", "baltic", ("coal",), "load", "wikipedia", W + "Ust-Luga",
         "Ust-Luga: 'the site of an important coal and fertiliser terminal'"),
        ("RUPRI", "baltic", ("crude",), "load", "wikipedia", W + "Primorsk,_Leningrad_Oblast",
         "Port of Primorsk: the largest Baltic Sea oil terminal, terminus of the Baltic Pipeline System; first in Russia for crude exports in 2006"),
        ("RUNVS", "black-sea", ("crude",), "load", "wikipedia", W + "Novorossiysk",
         "Novorossiysk: 'the busiest oil port in the Black Sea', terminus of the Caspian Pipeline Consortium pipeline"),
    ],
    # ------------------------------------------------------------------ two-ocean countries of Central America
    "GTM": [
        ("GTSTC", "cam-caribbean", ("box",), "both", "wikipedia", W + "Puerto_Barrios",
         "Santo Tomas de Castilla: 'most modern cargo traffic moved to its twin port in Santo Tomas de Castilla' after the 1976 earthquake; its page shows a container port"),
        ("GTPRQ", "cam-pacific", ("box",), "both", "wikipedia", W + "Puerto_Quetzal",
         "Puerto Quetzal: 'Guatemala's largest Pacific Ocean port', important for cargo traffic"),
    ],
    "HND": [
        ("HNPCR", "cam-caribbean", ("box",), "both", "wikipedia", W + "Puerto_Cort%C3%A9s",
         "Puerto Cortes: 805,000 TEU in 2025 (container port on the Caribbean coast)"),
    ],
    "NIC": [
        ("NICIO", "cam-pacific", ("grain", "fert", "box"), "both", "wikipedia", W + "Corinto,_Nicaragua",
         "Corinto: Nicaragua's largest and only Pacific port; 'a container terminal and able to manage liquid, bulk, containers, cars'; grain and fertiliser are read from 'bulk'"),
    ],
    "PAN": [
        ("PAMIT", "cam-caribbean", ("box",), "both", "wikipedia", W + "Manzanillo_International_Terminal",
         "Manzanillo International Terminal (Colon): 'one of the largest container transshipment terminals in the region', Atlantic terminus of the Panama Canal Railway"),
        ("PABLB", "cam-pacific", ("box",), "both", "wikipedia", W + "Balboa,_Panama",
         "Balboa: Pacific side of the Panama Canal, 'an important transshipment container port'"),
    ],
}

# Candidate rows for which no page was read that supports them: not committed (audit entries C-007, C-010, C-020).
UNSOURCED = {
    "USA": "copper and zinc concentrate (USA-JPN loads at Houston via Panama in the lane files): Red Dog zinc ships from the DeLong Mountain Port on the Chukchi Sea (Wikipedia, Red Dog mine, read) but the page gives no coordinates of the port; no page was read for US copper concentrate",
    "CAN": "potash by port: Canpotex ships the majority through Neptune Terminals, North Vancouver, and since 1997 also through Portland, Oregon (Wikipedia, Canpotex, read); no page names an Atlantic potash terminal except Saint John's Barrack Point Potash Terminal (Wikipedia, Port of Saint John), and it was not added because the Pacific side would then lose its potash row; Canadian grain by port needs the Canadian Grain Commission statistics (follow-up F3); iron ore at Sept-Iles and Port-Cartier: pages not read, the legacy entry stays",
    "MEX": "copper and zinc concentrate at Manzanillo, Guaymas or Lazaro Cardenas (audit MET-20): no page read names a port for these cargoes (Port of Guaymas: 'dry bulk cargoes'; Port of Manzanillo: copper among exports and zinc concentrate among imports, which contradicts rather than supports the audit); the legacy table keeps Coatzacoalcos for ore. Gulf and Pacific rows for grain, fertiliser and general cargo are in food.py (Manzanillo, Veracruz)",
    "BRA": "Ponta da Madeira (Carajas iron ore, searoute code BRPMA): the page names a large iron-ore loading port at Sao Luis but the zone and the share against Tubarao are not documented; not added as a second iron-ore gateway",
    "PER": "San Nicolas (Marcona iron ore) and Callao: no page read names the loading terminals of Peruvian iron ore (Wikipedia, Shougang Hierro Peru and Marcona, not found under the titles tried; Port of Callao: 'containers, bulk and multipurpose'). BIG_ORE is therefore not extended to PER",
    "CHL": "Huasco and Caldera / Punta Totoralillo (CAP iron ore): Wikipedia, Huasco, read but names no iron-ore terminal; BIG_ORE is therefore not extended to CHL",
    "IDN": "Benete (Batu Hijau copper concentrate, Sumbawa): the page names the port, not its coordinates; Morowali stays the legacy ore entry for the other ores",
    "ZAF": "Saldanha Bay (Sishen-Saldanha iron ore): page not found under the titles tried; the legacy 'ore' entry (ZASDB) stays",
    "FRA": "Rouen, La Pallice, Fos for wheat: pages not found under the titles tried (the same gap is in UNSOURCED of food.py)",
    "CRI": "Limon-Moin (Caribbean) and Caldera (Pacific): the Port of Limon and Port of Moin pages name a seaport and a container terminal operated by APM Terminals, no cargo; Caldera: page not found",
    "COL": "Cartagena, Barranquilla, Santa Marta, Buenaventura: pages not found under the titles tried (also in food.py); the Pacific gateway of Colombia is therefore missing and the rule by ocean falls back on the principal gateway",
    "CHN-south": "Zhanjiang (CNZHA): the page names a harbour city only; the rule 'South-East Asian coal into South China' keeps the legacy port without a row",
}

# ------------------------------------------------------------------ coast rules
# kind "sides": one port per group and side of the other end (Russia)
# kind "origin": a named port when the other end is in a set
# kind "basin": a zone chosen from the basin of the other end (sets of countries)
# kind "ocean": a zone chosen from the ocean of the other end's principal gateway (see ports.ocean_of)
# `two_ocean`: the country has a gateway on each ocean; two such countries trading together both take their
# Atlantic (Gulf and Caribbean) gateway.

EAST_ASIA = {"CHN", "JPN", "KOR", "TWN", "PRK", "VNM", "PHL", "THA", "MYS", "IDN", "SGP", "HKG"}
MED_BLACK = {"TUR", "EGY", "ISR", "MAR", "GRC", "ITA", "ESP", "CYP", "LBN", "TUN", "DZA", "LBY", "BGR", "ROU", "HRV", "SVN", "SYR", "MLT", "GEO"}

# Russia exports from three coasts; the load port depends on where the cargo goes (rule moved from
# build_lanes.RUS_PORTS / gateway_pair). Ports of groups with no row of their own above are the legacy choices.
RUS_PORTS = {
    "coal": {"east": "RUVYP", "south": "RUTAM", "west": "RUULU"},
    "crude-oil": {"east": "RUKOZ", "south": "RUNVS", "west": "RUPRI"},
    "refined-products": {"east": "RUNJK", "south": "RUTUA", "west": "RUPRI"},
    "lng": {"east": "RUPRG", "south": "RUSAB", "west": "RUSAB"},
    "wheat": {"east": "RUVYP", "south": "RUNVS", "west": "RUNVS"},
}

# Basins of the other end, for the Canadian rule
PACIFIC_ASIA = {"CHN", "JPN", "KOR", "PRK", "TWN", "HKG", "MAC", "VNM", "PHL", "THA", "MYS", "SGP", "IDN", "BRN", "KHM",
                "MNG", "AUS", "NZL", "PNG", "FJI"}
PACIFIC_AMERICAS = {"PER", "CHL", "ECU", "SLV"}
ATLANTIC_SIDE = {
    # Europe, the Mediterranean and the Black Sea
    "GBR", "IRL", "FRA", "ESP", "PRT", "BEL", "NLD", "DEU", "DNK", "NOR", "SWE", "FIN", "POL", "LTU", "LVA", "EST", "ISL",
    "ITA", "GRC", "MLT", "HRV", "SVN", "ALB", "MNE", "ROU", "BGR", "UKR", "GEO", "TUR", "CYP", "ISR", "LBN", "SYR",
    # Africa
    "MAR", "DZA", "TUN", "LBY", "EGY", "MRT", "SEN", "GMB", "GNB", "GIN", "SLE", "LBR", "CIV", "GHA", "TGO", "BEN",
    "NGA", "CMR", "GNQ", "GAB", "COG", "COD", "AGO", "NAM", "ZAF", "MOZ", "TZA", "KEN", "DJI", "SDN",
    # Atlantic coast of the Americas and the Caribbean
    "BRA", "ARG", "URY", "VEN", "GUY", "SUR", "TTO", "CUB", "DOM", "JAM", "HTI", "BHS", "BRB",
}

COAST_RULES = [
    {
        "id": "rus-by-destination", "kind": "sides", "country": "RUS", "role": "load",
        "groups": {"coal", "crude-oil", "refined-products", "lng", "wheat"},
        "sides": {"east": EAST_ASIA, "south": MED_BLACK}, "default_side": "west",
        "special": {("coal", "IND"): "east"},
        "open": {("crude-oil", "IND"): ["west", "south"]},
        "ports": RUS_PORTS,
        "reason": "Russia loads from three coasts. Cargo for East Asia leaves from the Far East, for the Mediterranean and the Black Sea from the Black Sea, for the rest from the Baltic; Indian coal is taken from the Far East. Russian crude for India is shipped from the Baltic and from the Black Sea and customs data do not say in what shares: both are options, the Baltic is principal",
        "src": "atlas", "url": None,
    },
    {
        "id": "chn-south-coal", "kind": "origin", "country": "CHN", "role": "discharge", "groups": {"coal"},
        "when_other_in": {"IDN", "PHL", "VNM", "MYS"}, "port": "CNZHA",
        "reason": "South-East Asian coal is discharged in South China (Guangdong and Guangxi), not in the north (rule moved from build_lanes.gateway_pair)",
        "src": "atlas", "url": None,
    },
    {
        "id": "can-coast", "kind": "basin", "country": "CAN", "role": "both", "groups": None,
        "basins": {"pacific": PACIFIC_ASIA | PACIFIC_AMERICAS, "atlantic": ATLANTIC_SIDE},
        "zones": {"pacific": ["canada-west"], "atlantic": ["canada-east"]},
        "reason": "Canada has a Pacific and an Atlantic seaboard. Cargo for Asia, Oceania and the Pacific coast of the Americas uses the British Columbia gateways, cargo for Europe, Africa and the Atlantic side of the Americas the St Lawrence and Maritime gateways; other ends (India, the Gulf) are left open",
        "src": "atlas", "url": None, "two_ocean": True,
    },
    {
        "id": "sau-dry-cargo", "kind": "ocean", "country": "SAU", "role": "both",
        "segments": {"grain", "fert", "vegoil", "box"},
        "zones": {"atlantic": ["red-sea"], "pacific": ["meg"]},
        "reason": "Saudi Arabia has a Red Sea and a Gulf seaboard. Dry cargo from west of Suez (Europe, the Mediterranean, the Americas) uses the Red Sea gateway, the rest the Gulf gateway",
        "src": "atlas", "url": None,
    },
    {
        "id": "mex-ocean", "kind": "ocean", "country": "MEX", "role": "both", "groups": None, "two_ocean": True,
        "zones": {"atlantic": ["mexico-gulf"], "pacific": ["mexico-pacific"]},
        "reason": "Mexico has a Gulf and a Pacific seaboard: the gateway is on the ocean of the other end",
        "src": "atlas", "url": None,
    },
    {
        "id": "col-ocean", "kind": "ocean", "country": "COL", "role": "both", "groups": None, "two_ocean": True,
        "zones": {"atlantic": ["caribbean"], "pacific": ["wcsa"]},
        "reason": "Colombia has a Caribbean and a Pacific seaboard: the gateway is on the ocean of the other end",
        "src": "atlas", "url": None,
    },
] + [
    {
        "id": "cam-ocean-" + iso.lower(), "kind": "ocean", "country": iso, "role": "both", "groups": None, "two_ocean": True,
        "zones": {"atlantic": ["cam-caribbean"], "pacific": ["cam-pacific"]},
        "reason": "The countries of the Central American isthmus have a Caribbean and a Pacific port: the gateway is on the ocean of the other end, so that a US Gulf cargo does not cross Panama to reach the Pacific port of the same country",
        "src": "atlas", "url": None,
    }
    for iso in ("GTM", "HND", "NIC", "CRI", "PAN")
]
