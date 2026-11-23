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
the page names that cargo or a cargo of that family ("bulk cargoes" or "dry bulk" alone names none; a "container
terminal" or "container port" is general cargo, `box`). A row whose page does not say what the port ships is not
committed: the candidates are in UNSOURCED, with the reason. Nothing here comes from memory.
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
    "russia-far-east": "Russian Far East",  # also declared by gateways/energy.py
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

# Ports that the searoute list lacks or misplaces: code -> (name, iso3, lon, lat), same shape as ports.MANUAL.
MANUAL_EXTRA = {
    # searoute puts PAMIT at -79.602, 9.612, 41 km from the terminal; these are the coordinates of the page of the row
    "PAMIT": ("Manzanillo International Terminal (Colon)", "PAN", -79.882, 9.362),
}

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
        ("BRPMA", "ecsa", ("iron-ore",), "load", "wikipedia", W + "Ponta_da_Madeira",
         "Ponta da Madeira, Sao Luis (Maranhao): a private Vale port, 'a large iron ore loading port', one of the few terminals suited to the ultra large Valemax ships. Second iron-ore gateway after Tubarao (the shares are not documented, so the options are open)"),
        ("BRVLC", "ecsa", ("alumina",), "load", "wikipedia", W + "Barcarena,_Par%C3%A1",
         "Barcarena (Para) has a port, and the page shows Norsk Hydro's Alunorte facility (the alumina refinery, Wikipedia: Barcarena water contamination); searoute names the port Vila do Conde. That the cargo leaves from the Vila do Conde terminals is read from the two pages together"),
    ],
    "CHL": [
        # The page does not rank the two ports, so both are options of Chilean iron ore.
        ("CLGYC", "wcsa", ("iron-ore",), "load", "wikipedia", W + "Compa%C3%B1%C3%ADa_Minera_del_Pac%C3%ADfico",
         "CMP, 99% of Chilean iron exports in 2022: its El Romeral mine 'uses the port of Guayacan in Coquimbo'"),
        ("CLHSO", "wcsa", ("iron-ore",), "load", "wikipedia", W + "Compa%C3%B1%C3%ADa_Minera_del_Pac%C3%ADfico",
         "CMP, 99% of Chilean iron exports in 2022: 'at the port of Huasco it operates the Planta de Pellets', supplied from the Los Colorados mine"),
    ],
    "COL": [
        ("COPBO", "caribbean", ("coal",), "load", "wikipedia", W + "Cerrej%C3%B3n",
         "Puerto Bolivar, the Cerrejon coal port: 'the largest coal-export port in Latin America'"),
    ],
    "MEX": [
        ("MXZLO", "mexico-pacific", ("copper-ore",), "load", "wikipedia", W + "Port_of_Manzanillo",
         "Port of Manzanillo: 'the principal exports are beer, cars, cement, sugar, copper, steel tubes' (the page does not say in what form the copper leaves)"),
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
        ("INKRI", "ec-india", ("coal",), "discharge", "wikipedia", W + "Krishnapatnam_Port",
         "Krishnapatnam Port: a mechanised coal berth in phase 1; 'coal is now the primary commodity handled by the port'"),
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
        ("GTSTC", "cam-caribbean", ("box",), "both", "wikipedia", W + "Santo_Tom%C3%A1s_de_Castilla",
         "Santo Tomas de Castilla: the page's picture is captioned 'View of the city's container port'; the Puerto Barrios page says most modern cargo traffic moved there after the 1976 earthquake"),
        ("GTPRQ", "cam-pacific", ("box",), "both", "wikipedia", W + "Puerto_Quetzal",
         "Puerto Quetzal: 'Guatemala's largest Pacific Ocean port', important for cargo traffic"),
    ],
    "HND": [
        ("HNPCR", "cam-caribbean", ("box",), "both", "wikipedia", W + "Puerto_Cort%C3%A9s",
         "Puerto Cortes: 805,000 TEU in 2025 (container port on the Caribbean coast)"),
    ],
    "NIC": [
        ("NICIO", "cam-pacific", ("box",), "both", "wikipedia", W + "Corinto,_Nicaragua",
         "Corinto: Nicaragua's largest and only Pacific port; 'a container terminal and able to manage liquid, bulk, containers, cars' (no grain or fertiliser named)"),
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
    "MEX": "zinc and lead concentrate exports (audit MET-20): no page read names a port (Port of Guaymas: 'dry bulk cargoes'; Port of Manzanillo: zinc concentrate among imports); the Manzanillo row covers copper only, because the page names copper among the principal exports. The legacy table keeps Coatzacoalcos for the other ores. Gulf and Pacific rows for general cargo are in food.py (Manzanillo, Veracruz)",
    "BRA": "bauxite: Porto Trombetas (MRN, searoute code BRTMT) and Juruti: no page read names them (Wikipedia: Mineracao Rio do Norte, Porto Trombetas not found; Oriximina read: an airport only); the Barcarena page names bauxite only as the town's economy and the Itaqui page names aluminium ingots, so neither is a bauxite row. Alumina at Itaqui (Alumar): the page does not name alumina",
    "PER": "San Nicolas (Marcona iron ore) and Callao: no page read names the loading terminals of Peruvian iron ore (Wikipedia, Shougang Hierro Peru and Marcona, not found under the titles tried; Port of Callao: 'containers, bulk and multipurpose'). BIG_ORE is therefore not extended to PER",
    "CHL": "Caldera / Punta Totoralillo (CAP iron ore): no page read. Guayacan and Huasco are rows (Compania Minera del Pacifico page), but no page read gives the ship size at those terminals, so BIG_ORE is not extended to CHL",
    "IDN": "Benete (Batu Hijau copper concentrate, Sumbawa): the page names the port, not its coordinates; Morowali stays the legacy ore entry for the other ores",
    "ZAF": "Saldanha Bay (Sishen-Saldanha iron ore): page not found under the titles tried; the legacy 'ore' entry (ZASDB) stays for iron ore only. Alumina imports at Richards Bay: the page names the two aluminium smelters, not alumina",
    "IND": "coal imports at Paradip: the Paradip Port page names bulk cargoes and crude oil, not coal (the legacy entry is not used: Krishnapatnam and Mundra have coal rows)",
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
# build_lanes.RUS_PORTS / gateway_pair). RUKOZ (Kozmino), RUNJK (Nakhodka) and RUTUA (Tuapse) have no row and no
# page: they are legacy choices of the rule, published as such (ports.basis_of). Wheat has no Far East port: the
# Vostochny page names coal only, so wheat follows the Novorossiysk grain row for every destination.
RUS_PORTS = {
    "coal": {"east": "RUVYP", "south": "RUTAM", "west": "RUULU"},
    "crude-oil": {"east": "RUKOZ", "south": "RUNVS", "west": "RUPRI"},
    "refined-products": {"east": "RUNJK", "south": "RUTUA", "west": "RUPRI"},
    "lng": {"east": "RUPRG", "south": "RUSAB", "west": "RUSAB"},
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
        "groups": {"coal", "crude-oil", "refined-products", "lng"},
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
        "id": "sau-dry-cargo", "kind": "ocean", "country": "SAU", "role": "discharge",
        "segments": {"grain", "fert", "vegoil", "box"},
        "zones": {"atlantic": ["red-sea"], "pacific": ["meg"]},
        "reason": "Saudi Arabia has a Red Sea and a Gulf seaboard. Dry cargo from west of Suez (Europe, the Mediterranean, the Americas) uses the Red Sea gateway, the rest the Gulf gateway. Imports only: the rows are import gateways, and the rule would otherwise move fertiliser exports from the Gulf to the Red Sea general-cargo port",
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
