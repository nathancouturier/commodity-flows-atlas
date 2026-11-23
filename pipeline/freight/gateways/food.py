"""
Gateways for grain, vegetable oil, fertiliser and general cargo (package E4a of the trade-engine repair).

Data only, no import. `ports.py` merges it with the other two gateway modules (coasts.py, energy.py).

    G = {iso3: [(code, zone, families, role, src, url, note), ...]}

code      UN/LOCODE of a port of the searoute list, of `ports.MANUAL`, or of `MANUAL_EXTRA` below
zone      freight zone (list of section 2.4 of the plan; the table itself lives in gateways/coasts.py)
families  subset of grain (wheat, corn, soybeans, soymeal, rice, rapeseed), sugar (its own family: a grain row is
          no sugar gateway), vegoil (palm oil, soyoil), fert (potash, phosphate rock, DAP, urea) and box (steel,
          refined copper, aluminium, coffee, cocoa, cotton: general cargo and containers, the "box" segment of
          ports.SEGMENT), or a group id ("urea", "potash", "phosphate-rock") when the page names that cargo only
role      load (exports), discharge (imports) or both
src, url  source id of data/sources.json and the page read. Rows adapted from Wikipedia are CC BY-SA 4.0
note      what the page says, in a few words

The first row of a country that carries a family in a role is its principal gateway for that family and role.
Where a country has no row for a family and role, the loader (ports.candidates) tries a row of the family in the
other role, then the country's general-cargo row, then the legacy table (never an oil, gas or ore terminal), then
the nearest seaport, and publishes which one it used.

How a row was admitted. Each page was read on 22 November 2026 (Wikipedia, English). A family is on a row only
when the page names that cargo or a cargo of that family (grain, cereals, wheat, soybean; sugar; fertiliser,
phosphate, urea, potash; edible or palm oil; general cargo, containers, break-bulk). "Bulk", "dry bulk",
"agricultural products" or "foodstuffs" alone name no cargo of these families. A port whose page says nothing
about its cargo is not committed: the country or the family is listed in UNSOURCED with the ports that a source
should be found for. Nothing here comes from memory.
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
        ("MYPKG", "sea", ("box",), "both", "wikipedia", W + "Port_Klang",
         "wharves for containers and for conventional cargo"),
    ],
    "MMR": [
        ("MMRGN", "sea", ("box",), "both", "wikipedia", W + "Port_of_Yangon",
         "Yangon: the country's largest port, Thilawa, and the other Yangon ports; the page says 90% of trade was handled in the Yangon ports in 2019 "
         "and names a container service; no grain, fertiliser or edible oil (the page does not name the cargo of Sittwe)"),
    ],
    "CHN": [
        ("CNTSN", "n-china", ("box",), "discharge", "wikipedia", W + "Port_of_Tianjin",
         "general cargo and containers, 13 million TEU in 2013 (the page names no grain, fertiliser or edible oil)"),
    ],
    "IND": [
        ("INMUN", "wc-india", ("grain", "sugar", "vegoil", "fert", "box"), "discharge", "wikipedia", W + "Mundra_Port",
         "warehouses to store wheat, sugar, rice and fertilizer; edible oil among liquid cargo; Fertilizer Cargo Complex; containers, dry bulk, break bulk"),
        ("INKDL", "wc-india", ("vegoil", "box"), "discharge", "wikipedia", W + "Deendayal_Port",
         "oil jetty 7 mainly handles edible oil; cargo berths mainly handle bulk cargoes and containers (no grain or fertiliser named)"),
    ],
    "BGD": [
        ("BDCGP", "ec-india", ("grain", "fert", "vegoil", "box"), "discharge", "wikipedia", W + "Port_of_Chittagong",
         "grain silo jetty, urea fertiliser jetty, edible oil in bulk at river mooring, general cargo and container berths"),
    ],
    "PAK": [
        ("PKKHI", "wc-india", ("box",), "discharge", "wikipedia", W + "Port_of_Karachi",
         "bulk and general cargo terminal at East Wharf berths 11 to 17; container terminals (the page names wheat only as an export of 1899)"),
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
        ("SAJED", "red-sea", ("box",), "discharge", "wikipedia", W + "Port_of_Jeddah",
         "handles 65% of the country's sea imports; container port for the largest ships (Red Sea side, outside Hormuz; no bulk cargo named)"),
        ("SADMM", "meg", ("box",), "discharge", "wikipedia", W + "King_Abdulaziz_Port",
         "Dammam: main imports food and foodstuffs, construction materials, consumer goods; two container terminals (no grain named)"),
    ],
    "ISR": [
        ("ILHFA", "med", ("grain", "box"), "discharge", "wikipedia", W + "Port_of_Haifa",
         "large grain silos; mostly bulk and general cargo; container terminal"),
    ],
    # ------------------------------------------------------------------ Mediterranean, Black Sea, Europe
    "ESP": [
        ("ESSAG", "med", ("fert",), "discharge", "wikipedia", W + "Port_of_Valencia",
         "Port of Sagunt, run by the Valencia port authority: around 70% iron and steel products, the rest fertilizers, construction materials, timber"),
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
        ("NGAPP", "waf", ("box",), "discharge", "wikipedia", W + "Apapa",
         "ports and terminals for containers and bulk cargo; a major container terminal (no grain or fertiliser named)"),
    ],
    # ------------------------------------------------------------------ Oceania
    "AUS": [
        ("AUTSV", "e-australia", ("sugar",), "load", "wikipedia", W + "Port_of_Townsville",
         "'the number one port in Australia for exports in copper, zinc, lead and sugar'; bulk sugar terminal since 1959"),
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
        # The report names urea only: potash, phosphate rock and DAP imports are not on this row.
        ("USMSY", "us-gulf", ("urea",), "discharge", "company-reports",
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
        ("CAVAN", "canada-west", ("potash",), "load", "wikipedia", W + "Canpotex",
         "Canpotex: the majority of its potash is shipped overseas to Asian, Latin American and Oceanic markets through Neptune Terminals, North Vancouver; the code is the Vancouver port"),
        ("CAVAN", "canada-west", ("grain", "box"), "load", "wikipedia", W + "Port_of_Vancouver",
         "bulk terminals include Alliance Grain Terminal and Fraser Grain Terminal; break-bulk, bulk and container sectors (no fertiliser named); the code is the Vancouver port"),
        ("CAMTR", "canada-east", ("grain", "sugar", "fert", "box"), "both", "wikipedia", W + "Port_of_Montreal",
         "grain terminal leased to Viterra; fertilizers and raw sugar among the major dry bulk commodities; five container terminals"),
    ],
    "MEX": [
        ("MXZLO", "mexico-pacific", ("box",), "both", "wikipedia", W + "Port_of_Manzanillo",
         "main entrance of container shipping on the west coast; imports of consumer goods and steel products; Manzanillo, Colima (searoute code MXZLO)"),
        ("MXZLO", "mexico-pacific", ("sugar",), "load", "wikipedia", W + "Port_of_Manzanillo",
         "the principal exports are beer, cars, cement, sugar, copper, steel tubes"),
        ("MXVER", "mexico-gulf", ("box",), "both", "wikipedia", W + "Port_of_Veracruz",
         "handles all kinds of cargo; container terminal; vehicles"),
    ],
    "BRA": [
        # The pages do not rank the three ports for exports: the order keeps Santos, the port with sugar, soy, coffee
        # and general cargo on its page, as principal. Paranagua and Rio Grande are the other load options.
        ("BRSSZ", "ecsa", ("grain", "sugar"), "load", "wikipedia", W + "Port_of_Santos",
         "main exports include coffee, sugar and soy; solid and liquid bulk, containers and general cargo"),
        ("BRPNG", "ecsa", ("grain", "sugar"), "load", "wikipedia", W + "Port_of_Paranagu%C3%A1",
         "main port for the export of soybeans and soybean meal, also corn; second in Brazil for the export of sugar; largest bulk port in Latin America"),
        ("BRRIG", "ecsa", ("grain",), "load", "wikipedia", W + "Port_of_Rio_Grande",
         "exports soybeans, soybean meal, corn, wheat and rice (2003 list on the page)"),
        ("BRITQ", "ecsa", ("grain",), "load", "wikipedia", W + "Port_of_Itaqui",
         "Port of Itaqui, Sao Luis (Maranhao): the main cargoes include aluminium ingots, pig iron, dry and liquid bulk, soybean and copper"),
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
    # ------------------------------------------------------------------ sourcing pass FE4b (22-23 November 2026):
    # general-cargo rows ("box": a container port or a general-cargo terminal on the page) and the few grain and
    # fertiliser rows that a page names. A box row is also the country's "general port" for food and fertiliser.
    "JPN": [
        ("JPYOK", "japan-korea", ("box",), "both", "wikipedia", W + "Port_of_Yokohama",
         "Yokohama: Honmoku Pier, 'the port's core facility with 24 berths including 14 container berths'; Daikoku Pier with 'seven container berths'"),
    ],
    "TWN": [
        ("TWKHH", "taiwan", ("box",), "both", "wikipedia", W + "Port_of_Kaohsiung",
         "Kaohsiung: the port plan distinguishes 'Container Docks' and 'Bulk and Sundry Goods Docks'; the 2017 expansion added container capacity"),
    ],
    "VNM": [
        ("VNCMT", "sea", ("box",), "both", "wikipedia", W + "Cai_Mep",
         "Cai Mep - Thi Vai: 'the main port for container transport' of the southern port complex; Phu My and My Xuan are 'a general port, a container port'. Replaces Ho Chi Minh City, a river port 44 km from the sea, as the general-cargo port"),
    ],
    "THA": [
        ("THLCH", "sea", ("box",), "both", "wikipedia", W + "Laem_Chabang_Port",
         "Laem Chabang: seven container terminals, a multipurpose terminal and one general cargo terminal"),
    ],
    "PHL": [
        ("PHSFS", "sea", ("grain", "fert"), "discharge", "wikipedia", W + "Port_of_Subic_Bay",
         "Subic Bay: 'a fertilizer terminal at the Boton Wharf, a grain bulk terminal at the Leyte Wharf' (direction not given; the Philippines imports grain and fertiliser)"),
        ("PHMNL", "sea", ("box",), "both", "wikipedia", W + "Port_of_Manila",
         "Manila: North Harbor, South Harbor and the Manila International Container Terminal (the page names no bulk cargo)"),
    ],
    "SGP": [
        ("SGSIN", "sea", ("box",), "both", "wikipedia", W + "Port_of_Singapore",
         "Singapore: three container terminals at Keppel Harbour, others at Pasir Panjang and Jurong"),
    ],
    "HKG": [
        ("HKHKG", "s-china", ("box",), "both", "wikipedia", W + "Port_of_Hong_Kong",
         "Hong Kong: 'a deepwater seaport dominated by trade in containerised manufactured products'; container terminals at Kwai Chung"),
    ],
    "ARE": [
        ("AEJEA", "meg", ("box",), "both", "wikipedia", W + "Jebel_Ali",
         "Jebel Ali: 'the busiest port in the Middle East by container volume'; the page names no bulk cargo"),
    ],
    "OMN": [
        ("OMSOH", "gulf-of-oman", ("grain",), "discharge", "wikipedia", W + "Port_of_Sohar",
         "Sohar: the Food Cluster 'includes a flourmill, a sugar refinery, a grain silo complex'; 'able to load and unload 600 tonnes of grain per hour'"),
        ("OMSOH", "gulf-of-oman", ("box",), "both", "wikipedia", W + "Port_of_Sohar",
         "Sohar: a concession 'for all dry bulk, break-bulk, roll-on/roll-off and container stuffing and stripping related operations'"),
    ],
    "JOR": [
        ("JOAQB", "red-sea", ("phosphate-rock",), "load", "wikipedia", W + "Aqaba",
         "Aqaba page: 'the Aqaba railway which transported phosphate to the old port ceased operations in 2018' and a successor line 'to transport phosphate from Al Shidiya and Ghor es-Safi to the new terminal in Port of Aqaba is planned'; the Port of Aqaba is 'the only port in Jordan' (phosphate rock only: no DAP and no potash named; the page gives no tonnage and the railway is history)"),
    ],
    "NLD": [
        ("NLRTM", "nw-europe", ("box",), "both", "wikipedia", W + "Port_of_Rotterdam",
         "Rotterdam: Europe Container Terminals 'operates two major container terminals at the port' (the page names no grain)"),
    ],
    "SWE": [
        ("SEGOT", "nw-europe", ("box",), "both", "wikipedia", W + "Port_of_Gothenburg",
         "Gothenburg: 'specialised terminals for containers, ro-ro, cars'; the primary exports include steel"),
    ],
    "FRA": [
        ("FRFOS", "med", ("box",), "both", "wikipedia", W + "Fos-sur-Mer",
         "Fos: 'the facilities include container handling terminals and a gas (methane) terminal' at the port of Marseille"),
    ],
}

# Countries among the 40 largest traders of these families (2024 customs data) for which no page that names
# their import or export gateway for these cargoes could be read on 22 November 2026, so that no row is
# committed, and the families still missing for countries that have rows. The ports are candidates only; each
# needs a page before it becomes a row.
UNSOURCED = {
    "DZA": "Oran (page read: no cargo statement), Algiers, Annaba, Skikda, Djen Djen (pages not found), Bejaia (page read: historical trade only); Arzew is an energy terminal, so food goes to the nearest seaport until a page is read",
    "IRQ": "Umm Qasr (Umm Qasr Port page read: food unloaded in 2003 only, no cargo statement), Khor al-Zubair; Basrah Oil Terminal is an oil terminal, so food goes to the nearest seaport until a page is read",
    "CHN": "grain, soybeans, fertiliser and vegetable oil imports: Dalian, Rizhao, Qingdao and the Yangtze ports (Tianjin, Dalian and Qingdao pages read: no grain or fertiliser named); the Tianjin general-cargo row answers meanwhile",
    "IDN": "grain, fertiliser and vegetable oil imports: Tanjung Priok page read, 'dry bulk' and 'liquid bulk' only",
    "MMR": "grain, fertiliser and vegetable oil: the Port of Yangon page names no such cargo (Thilawa page: a multi-purpose container port); the Yangon general-cargo row answers meanwhile, as the country's general port",
    "MYS": "grain and fertiliser imports: Port Klang page read, 'bulk cargo' only",
    "IND": "grain and fertiliser at Kandla (Deendayal Port page read: 'bulk cargoes' only)",
    "PAK": "grain and fertiliser imports: Karachi page read (wheat named only as an export of 1899), Port Qasim (page not read)",
    "SAU": "grain, fertiliser and vegetable oil: Jeddah page read (containers only), King Abdulaziz Port, Dammam ('food and foodstuffs' only)",
    "ESP": "grain imports: Tarragona page read ('agricultural products', no grain named)",
    "ITA": "grain and fertiliser: Ravenna page read (bulk terminals, no cargo named)",
    "NGA": "grain and fertiliser: Apapa page read (containers and bulk cargo, no cargo named)",
    "MEX": "grain and fertiliser imports: Manzanillo (page names wheat, sorghum, oat and fertilizer, but a Pacific-only row would send every Gulf cargo through Panama) and a Gulf port, Veracruz or Altamira (Veracruz page read: no grain named); the general-cargo rows answer on each coast meanwhile",
    "USA": "potash, phosphate rock and DAP imports (the Agrium report names urea only)",
    "CAN": "fertiliser other than potash at Vancouver (Port of Vancouver page read: no fertiliser named)",
    "FRA": "wheat and grain: the Fos-sur-Mer page names container terminals and a methane terminal only (a general-cargo row, so Fos answers as the general port); Rouen, Dunkirk, Le Havre (pages not found under the titles tried), La Pallice (La Rochelle page read: no cargo statement)",
    "JPN": "grain, sugar, fertiliser and vegetable oil: Kashima (page read: no cargo statement), Chiba (page read: crude oil, LNG, steel exports; grain only as a 19th-century trade), Nagoya, Kobe, Tokyo (pages read: containers, no grain); the Yokohama general-cargo row answers meanwhile, as the country's general port",
    "THA": "grain, fertiliser and vegetable oil: Laem Chabang page read (container terminals and one general cargo terminal, no bulk cargo), Map Ta Phut page read (no cargo), Bangkok (page not found); the Laem Chabang general-cargo row answers meanwhile",
    "VNM": "grain, fertiliser: Haiphong (the Haiphong city page names containers only), Cai Mep (page read: containers, 'a general port'); no page ranks the northern and southern ports; the Cai Mep general-cargo row answers meanwhile for the south",
    "PHL": "Manila (page read: containers only), Davao; Subic is a row for grain and fertiliser imports (its page names a grain terminal and a fertilizer terminal); Batangas page read: no bulk cargo; no page gives the shares of Manila, Subic and Batangas",
    "NLD": "grain: Rotterdam (page read: container terminals; Europoort names iron ore and coal, no grain), Amsterdam (page read: coal transhipment); the Rotterdam general-cargo row answers meanwhile",
    "BEL": "Antwerp-Bruges (page read: no cargo statement), Ghent",
    "COL": "Cartagena (page not found), Barranquilla (page not found), Santa Marta (page not found), Buenaventura (page not found)",
    "ARE": "grain, sugar, fertiliser: Jebel Ali (page read: containers; no bulk cargo), Khalifa, Fujairah; the Jebel Ali general-cargo row answers meanwhile",
    "KAZ": "landlocked: its transit port belongs to the TRANSIT table of package E4c",
    "ZAF": "Durban (page read: containers only, no grain), Cape Town, Richards Bay",
    "CZE": "landlocked: transit port belongs to package E4c",
    "AUT": "landlocked: transit port belongs to package E4c",
    "PRY": "landlocked: transit port belongs to package E4c (up-river Parana)",
    "CHL": "San Antonio and Valparaiso (pages read: no bulk or grain statement), Coronel",
    "ECU": "Guayaquil (page not found), Esmeraldas is an oil terminal",
    "TWN": "grain: Kaohsiung (page read: container docks and 'bulk and sundry goods docks', no grain), Taichung (page read: no cargo statement); the Kaohsiung general-cargo row answers meanwhile",
    "KEN": "Mombasa (page read: containers, no grain statement)",
    "GHA": "Tema (page not found)",
    "URY": "Montevideo (page read: containers, no grain statement)",
    "GRC": "Piraeus (page read: general cargo and containers, no grain), Thessaloniki",
    "JOR": "Aqaba (page read: phosphate company and container port, no grain or fertiliser statement)",
    "PRT": "Sines (page read: solid bulk, general cargo, containers; already the default port of the legacy table)",
    "SGP": "grain and fertiliser: Singapore is not a gateway of bulk cargo on the page read; the container row answers meanwhile",
    "HKG": "grain and fertiliser: the Hong Kong page names containerised manufactured products; the container row answers meanwhile",
}
