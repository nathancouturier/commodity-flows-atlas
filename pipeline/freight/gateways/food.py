"""
Gateways for grain, vegetable oil, fertiliser and general cargo (package E4a of the trade-engine repair).

Data only, no import. `ports.py` merges it with the other two gateway modules (coasts.py, energy.py).

    G = {iso3: [(code, zone, families, role, src, url, note), ...]}

code      UN/LOCODE of a port of the searoute list, of `ports.MANUAL`, or of `MANUAL_EXTRA` below
zone      freight zone (list of section 2.4 of the plan; the table itself lives in gateways/coasts.py)
families  subset of grain (wheat, corn, soybeans, soymeal, rice, sugar, rapeseed), vegoil (palm oil, soyoil),
          fert (potash, phosphate rock, DAP, urea) and box (steel, refined copper, aluminium, coffee, cocoa, cotton:
          general cargo and containers, the "box" segment of ports.SEGMENT)
role      load (exports), discharge (imports) or both
src, url  source id of data/sources.json and the page read. Rows adapted from Wikipedia are CC BY-SA 4.0
note      what the page says, in a few words

The first row of a country that carries a family in a role is its principal gateway for that family and role.
Where a country has no row for a family, the loader keeps the present table (`LEGACY_P`) for it.

How a row was admitted. Each page was read on 22 November 2026 (Wikipedia, English). A family is on a row only
when the page names that cargo (grain or cereals or agricultural products; fertiliser or phosphate; edible or palm
oil; general cargo, containers, break-bulk). When the page only says "bulk" or "dry bulk" without naming the cargo,
the row lists grain and fertiliser (and vegoil only for "liquid bulk") and its note says so: that is a reading of
the page, not a statement of it. A port whose page says nothing about its cargo is not committed: the country is
listed in UNSOURCED with the ports that a source should be found for. Nothing here comes from memory.
"""

W = "https://en.wikipedia.org/wiki/"

# Terminals missing from the searoute list: code -> (name, iso3, lon, lat), same shape as ports.MANUAL.
# Coordinates are those printed on the page of the row that uses the code.
MANUAL_EXTRA = {
    "SADMM": ("Dammam (King Abdulaziz Port)", "SAU", 50.20, 26.49),   # King_Abdulaziz_Port: 26.48861 N 50.20111 E
    "INKDL": ("Kandla (Deendayal Port)", "IND", 70.22, 23.00),        # Deendayal_Port: 23.000271 N 70.220884 E
    "IRBIK": ("Bandar Imam Khomeini", "IRN", 49.07, 30.51),           # Bandar_Imam_Khomeini: 30.50583 N 49.07417 E, given for the town
}

G = {
    # ------------------------------------------------------------------ Asia
    "IDN": [
        ("IDTPP", "sea", ("grain", "fert", "vegoil"), "discharge", "wikipedia", W + "Port_of_Tanjung_Priok",
         "20 terminals for general cargo, liquid bulk, dry bulk and containers; cargo not named (dry bulk read as grain and fertiliser, liquid bulk as oil)"),
        ("IDTPP", "sea", ("box",), "both", "wikipedia", W + "Port_of_Tanjung_Priok",
         "general cargo and containers; 20 terminals"),
        ("IDSUB", "sea", ("box",), "both", "wikipedia", W + "Port_of_Tanjung_Perak",
         "Tanjung Perak: container terminal and multi-purpose terminals for conventional cargo"),
    ],
    "MYS": [
        ("MYPGU", "sea", ("vegoil",), "load", "wikipedia", W + "Pasir_Gudang",
         "oil palm storage and distribution at Johor Port (Pasir Gudang) and Tanjung Langsat; searoute code MYPGU is Pasir Gudang"),
        ("MYPKG", "sea", ("vegoil",), "load", "wikipedia", W + "Port_Klang",
         "permanent installations for palm oil and latex, two increasingly important exports"),
        ("MYPKG", "sea", ("grain", "fert"), "discharge", "wikipedia", W + "Port_Klang",
         "berths for bulk cargo and wharves for conventional cargo; cargo not named (bulk read as grain and fertiliser)"),
        ("MYPKG", "sea", ("box",), "both", "wikipedia", W + "Port_Klang",
         "wharves for containers and for conventional cargo"),
    ],
    "CHN": [
        ("CNTSN", "n-china", ("grain", "fert", "vegoil", "box"), "discharge", "wikipedia", W + "Port_of_Tianjin",
         "dry and liquid bulk, general cargo and containers; bulk logistics centre; cargo not named (bulk read as grain and fertiliser, liquid bulk as oil)"),
    ],
    "IND": [
        ("INMUN", "wc-india", ("grain", "vegoil", "fert", "box"), "discharge", "wikipedia", W + "Mundra_Port",
         "wheat among agri commodities; edible oil among liquid cargo; Fertilizer Cargo Complex; containers, dry bulk, break bulk"),
        ("INKDL", "wc-india", ("vegoil", "grain", "fert", "box"), "discharge", "wikipedia", W + "Deendayal_Port",
         "oil jetty 7 mainly handles edible oil; cargo berths mainly handle bulk cargoes and containers (bulk read as grain and fertiliser)"),
    ],
    "BGD": [
        ("BDCGP", "ec-india", ("grain", "fert", "vegoil", "box"), "discharge", "wikipedia", W + "Port_of_Chittagong",
         "grain silo jetty, urea fertiliser jetty, edible oil in bulk at river mooring, general cargo and container berths"),
    ],
    "PAK": [
        ("PKKHI", "wc-india", ("grain", "fert", "box"), "discharge", "wikipedia", W + "Port_of_Karachi",
         "bulk and general cargo terminal at East Wharf berths 11 to 17; container terminal; cargo not named (bulk read as grain and fertiliser)"),
    ],
    "KOR": [
        ("KRPUS", "japan-korea", ("box",), "both", "wikipedia", W + "Port_of_Busan",
         "largest container and general cargo port of the country"),
    ],
    "IRN": [
        ("IRBIK", "meg", ("grain", "box"), "discharge", "wikipedia", W + "Bandar_Imam_Khomeini",
         "most feed grain (mainly corn from Brazil) is imported to this harbour; bulk, general cargo and container berths; coordinates are the town's"),
    ],
    "YEM": [
        ("YEADE", "red-sea", ("grain", "box"), "discharge", "wikipedia", W + "Port_of_Aden",
         "Aden Gulf Terminal built for bulk carriers of grain, particularly wheat; Ma'alla grain silos, general cargo and containers"),
    ],
    # ------------------------------------------------------------------ Middle East
    "SAU": [
        ("SAJED", "red-sea", ("grain", "vegoil", "fert", "box"), "discharge", "wikipedia", W + "Port_of_Jeddah",
         "handles 65% of the country's sea imports; container and general cargo port; cargo types not named (Red Sea side, outside Hormuz)"),
        ("SADMM", "meg", ("grain", "box"), "discharge", "wikipedia", W + "King_Abdulaziz_Port",
         "Dammam: main imports food and foodstuffs, construction materials, consumer goods; general cargo berths and two container terminals"),
    ],
    "ISR": [
        ("ILHFA", "med", ("grain", "box"), "discharge", "wikipedia", W + "Port_of_Haifa",
         "large grain silos; mostly bulk and general cargo; container terminal"),
    ],
    # ------------------------------------------------------------------ Mediterranean, Black Sea, Europe
    "ESP": [
        ("ESTAR", "med", ("grain",), "discharge", "wikipedia", W + "Port_of_Tarragona",
         "ranked as the most relevant port in Spain in terms of agricultural products"),
        ("ESVLC", "med", ("fert",), "discharge", "wikipedia", W + "Port_of_Valencia",
         "Port of Sagunt, run by the Valencia port authority: iron and steel, the rest fertilizers, construction materials, timber"),
        ("ESVLC", "med", ("box",), "both", "wikipedia", W + "Port_of_Valencia",
         "traffic split into solid bulk, conventional general cargo and containerised general cargo; 4.8 million TEU in 2023"),
    ],
    "TUR": [
        ("TRMER", "med", ("grain", "box"), "discharge", "wikipedia", W + "Port_of_Mersin",
         "cereal quay with a 100,000 t silo; bulk quay; merchandise quay; container terminal"),
        ("TRIZM", "med", ("box",), "both", "wikipedia", W + "Port_of_%C4%B0zmir",
         "container port; 9 million tonnes of cargo in 2018"),
    ],
    "ITA": [
        ("ITRAN", "med", ("grain", "fert"), "discharge", "wikipedia", W + "Port_of_Ravenna",
         "multipurpose and bulk cargo terminals and a container terminal; cargo not named (bulk read as grain and fertiliser)"),
        ("ITGOA", "med", ("box",), "both", "wikipedia", W + "Port_of_Genoa",
         "handles containers, dry and liquid bulk"),
    ],
    "DEU": [
        ("DEHAM", "nw-europe", ("grain",), "both", "wikipedia", W + "Port_of_Hamburg",
         "terminal list includes G.T.H. Getreide Terminal Hamburg (bulk cargo)"),
        ("DEHAM", "nw-europe", ("box",), "both", "wikipedia", W + "Port_of_Hamburg",
         "container and multi-purpose terminals; 7.8 million TEU in 2024"),
        ("DEBRE", "nw-europe", ("grain",), "both", "wikipedia", W + "Port_of_Bremerhaven",
         "Bremen: Getreidehafen (cereal harbour) in the Ueberseestadt area"),
    ],
    "GBR": [
        ("GBLIV", "nw-europe", ("grain", "box"), "discharge", "wikipedia", W + "Port_of_Liverpool",
         "Seaforth Dock deals with grain and containers; container, bulk and cruise traffic"),
    ],
    "EGY": [
        ("EGALY", "med", ("grain",), "discharge", "wikipedia", W + "Port_of_Alexandria",
         "Zone 5 handles grains and flour"),
        ("EGALY", "med", ("fert", "box"), "both", "wikipedia", W + "Port_of_Alexandria",
         "Zone 4: containers, cement, coal, fertilizers and general cargo; Zone 1: general cargo"),
    ],
    "MAR": [
        ("MAJFL", "waf", ("fert",), "load", "wikipedia", W + "Jorf_Lasfar",
         "harbour equipped for the export of phosphate rock; fertilizer and petrochemical factories in the industrial zone"),
        ("MACAS", "waf", ("box",), "both", "wikipedia", W + "Port_of_Casablanca",
         "container port; facilities for phosphate shipping"),
    ],
    "ROU": [
        ("ROCND", "black-sea", ("grain", "fert", "box"), "both", "wikipedia", W + "Port_of_Constan%C8%9Ba",
         "two cereal terminals (Constanta North and South); a terminal storing phosphorus and urea; general cargo and the main Black Sea container hub"),
    ],
    "BGR": [
        ("BGVAR", "black-sea", ("grain", "fert", "box"), "both", "wikipedia", W + "Port_of_Varna",
         "practically all kinds of solid bulk; exports include urea, fertilisers, grain and containers; imports include phosphates and containers"),
    ],
    "UKR": [
        ("UAODS", "black-sea", ("grain",), "load", "wikipedia", W + "Port_of_Odesa",
         "grain and main oil terminals in the northern part; Chornomorsk and Pivdennyi are satellite ports (not described on the page)"),
    ],
    "POL": [
        ("PLGDN", "baltic", ("grain", "fert", "box"), "both", "wikipedia", W + "Port_of_Gda%C5%84sk",
         "equipment for the handling of grain, fertilizers, lumber, ore, steel and containers"),
    ],
    "RUS": [
        ("RUULU", "baltic", ("fert",), "load", "wikipedia", W + "Port_of_Ust-Luga",
         "important coal and fertiliser terminal"),
        ("RUNVS", "black-sea", ("grain", "fert", "box"), "load", "wikipedia", W + "Port_of_Novorossiysk",
         "mainly handles grain, coal, mineral fertilizers, timber, oil, containerized, food and general cargo"),
    ],
    # ------------------------------------------------------------------ Africa
    "NGA": [
        ("NGAPP", "waf", ("grain", "fert", "box"), "discharge", "wikipedia", W + "Apapa",
         "ports and terminals for containers and bulk cargo; cargo not named (bulk read as grain and fertiliser)"),
    ],
    # ------------------------------------------------------------------ Oceania
    "AUS": [
        ("AUKWI", "w-australia", ("fert", "grain"), "both", "wikipedia", W + "Fremantle_Harbour",
         "Outer Harbour bulk facilities (Kwinana) handle grain, fertilisers, sulphur, alumina and other bulk commodities"),
        ("AUFRE", "w-australia", ("box",), "both", "wikipedia", W + "Fremantle_Harbour",
         "Western Australia's largest and busiest general cargo port; sea containers"),
        ("AUBNE", "e-australia", ("box",), "both", "wikipedia", W + "Port_of_Brisbane",
         "nine deep-water container berths and 17 bulk and general cargo berths"),
    ],
    # ------------------------------------------------------------------ Americas
    "USA": [
        ("USMSY", "us-gulf", ("grain",), "load", "wikipedia", W + "Port_of_South_Louisiana",
         "Mississippi River grain ports handle some 60% of raw grain exports; the page is the Port of South Louisiana, the code is New Orleans"),
        # Imports come first: US fertiliser imports are many times its exports, and a lookup without a role takes the first row.
        ("USMSY", "us-gulf", ("fert",), "discharge", "company-reports",
         "https://www.sec.gov/Archives/edgar/data/0000943003/000113031905000211/o16065exv1.htm",
         "Agrium Inc. annual report 2004: the U.S. Gulf port at New Orleans is the primary port of entry for urea imported into North America (urea only; a 2004 statement)"),
        ("USTPA", "us-gulf", ("fert",), "load", "wikipedia", W + "Port_of_Tampa",
         "main exports phosphate and fertilizer; bulk and tanker ships"),
        ("USMSY", "us-gulf", ("box",), "both", "wikipedia", W + "Port_of_New_Orleans",
         "general cargo port; break-bulk steel, metals, rubber; only deep-water container port in Louisiana"),
        ("USHOU", "us-gulf", ("box",), "both", "wikipedia", W + "Port_of_Houston",
         "general cargo terminals (Turning Basin, Jacintoport, Woodhouse, Care) and two container terminals"),
    ],
    "CAN": [
        ("CAVAN", "canada-west", ("grain", "fert", "box"), "load", "wikipedia", W + "Port_of_Vancouver",
         "bulk terminals include Alliance Grain Terminal and Fraser Grain Terminal; break-bulk, bulk and container sectors; fertiliser not named (bulk read as fertiliser); the code is the Vancouver port"),
        ("CAMTR", "canada-east", ("grain", "fert", "box"), "both", "wikipedia", W + "Port_of_Montreal",
         "grain terminal leased to Viterra; fertilizers and raw sugar among the major dry bulk commodities; five container terminals"),
    ],
    "MEX": [
        ("MXZLO", "mexico-pacific", ("grain", "fert", "box"), "discharge", "wikipedia", W + "Port_of_Manzanillo",
         "agricultural products include wheat, sorghum, oat and fertilizer; container gateway; Manzanillo, Colima (searoute code MXZLO)"),
        ("MXVER", "mexico-gulf", ("box",), "both", "wikipedia", W + "Port_of_Veracruz",
         "handles all kinds of cargo; container terminal; vehicles"),
    ],
    "BRA": [
        # The pages do not rank the three ports for exports: the order keeps Santos, the port with sugar, soy, coffee
        # and general cargo on its page, as principal. Paranagua and Rio Grande are the other load options.
        ("BRSSZ", "ecsa", ("grain",), "load", "wikipedia", W + "Port_of_Santos",
         "main exports include coffee, sugar and soy; solid and liquid bulk, containers and general cargo"),
        ("BRPNG", "ecsa", ("grain",), "load", "wikipedia", W + "Port_of_Paranagu%C3%A1",
         "main port for the export of soybeans and soybean meal, also corn and sugar; largest bulk port in Latin America"),
        ("BRRIG", "ecsa", ("grain",), "load", "wikipedia", W + "Port_of_Rio_Grande",
         "exports soybeans, soybean meal, corn, wheat and rice (2003 list on the page)"),
        ("BRPNG", "ecsa", ("fert",), "discharge", "wikipedia", W + "Port_of_Paranagu%C3%A1",
         "represents 34% of all fertilizer imports in the country"),
        ("BRRIG", "ecsa", ("fert",), "discharge", "wikipedia", W + "Port_of_Rio_Grande",
         "imports urea, phosphates, fertilizers and potassium chloride (2003 list on the page)"),
        ("BRSSZ", "ecsa", ("box",), "both", "wikipedia", W + "Port_of_Santos",
         "general cargo is 53% of the volume; leading container port of the country; coffee exports"),
    ],
    "ARG": [
        ("ARUPR", "ecsa", ("grain",), "load", "wikipedia", W + "Port_of_Rosario",
         "the nation's leading grain export hub (the Rosario hub, ports.MANUAL ARUPR)"),
        ("ARBUE", "ecsa", ("box",), "both", "wikipedia", W + "Port_of_Buenos_Aires",
         "container port, 1.1 million TEU in 2010 and about 11 million tonnes of cargo a year"),
    ],
    "PER": [
        ("PECLL", "wcsa", ("grain", "box"), "discharge", "wikipedia", W + "Port_of_Callao",
         "closed warehouse specialised in grains; docks for containers, bulk and multipurpose; imports of corn, wheat and rice"),
    ],
}

# Countries among the 40 largest traders of these families (2024 customs data) for which no page that names
# their import or export gateway for these cargoes could be read on 22 November 2026, so that no row is
# committed. The ports are candidates only; each needs a page before it becomes a row.
UNSOURCED = {
    "DZA": "Oran (page read: no cargo statement), Algiers (page not found), Annaba, Bejaia, Skikda; Arzew is an energy terminal",
    "IRQ": "Umm Qasr (page read: no cargo statement), Khor al-Zubair; Basrah Oil Terminal is an oil terminal",
    "FRA": "Marseille-Fos, Rouen, La Pallice, Dunkirk, Le Havre: pages not found under the titles tried",
    "JPN": "Kashima (page read: no cargo statement), Chiba, Nagoya (page read: no cargo statement), Kobe, Yokohama",
    "THA": "Laem Chabang (page not found), Bangkok (page not found)",
    "VNM": "Haiphong (page read: general port, containers), Cai Mep, Ho Chi Minh City: no page ranks the northern and southern ports",
    "PHL": "Manila (page read: containers only), Subic, Davao",
    "NLD": "Rotterdam (page read: general cargo and containers, no grain), Amsterdam",
    "BEL": "Antwerp-Bruges (page read: no cargo statement), Ghent",
    "COL": "Cartagena (page not found), Barranquilla (page not found), Santa Marta (page not found), Buenaventura (page not found)",
    "ARE": "Jebel Ali (page read: containers and general cargo storage only), Khalifa, Fujairah",
    "KAZ": "landlocked: its transit port belongs to the TRANSIT table of package E4c",
    "ZAF": "Durban (page read: containers only, no grain), Cape Town, Richards Bay",
    "CZE": "landlocked: transit port belongs to package E4c",
    "AUT": "landlocked: transit port belongs to package E4c",
    "PRY": "landlocked: transit port belongs to package E4c (up-river Parana)",
    "CHL": "San Antonio and Valparaiso (pages read: no bulk or grain statement), Coronel",
    "ECU": "Guayaquil (page not found), Esmeraldas is an oil terminal",
    "TWN": "Kaohsiung (page read: containers, 'bulk and sundry goods docks'), Taichung",
    "KEN": "Mombasa (page read: containers, no grain statement)",
    "GHA": "Tema (page not found)",
    "URY": "Montevideo (page read: containers, no grain statement)",
    "GRC": "Piraeus (page read: general cargo and containers, no grain), Thessaloniki",
    "JOR": "Aqaba (page read: phosphate company and container port, no grain or fertiliser statement)",
    "PRT": "Sines (page read: solid bulk, general cargo, containers; already the default port of the legacy table)",
}
