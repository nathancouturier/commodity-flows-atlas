"""Energy gateways: the ports of crude oil, refined products, LPG and LNG, the UAE, and the transit ports of
landlocked countries (package E4c of the trade-engine repair; plan section 2.4).

Plain data, no import of the other pipeline modules, so that ports.py can load it without a circular import.

G = {iso3: [row, ...]}, a row being the tuple
    (port code, freight zone, {cargo families}, role, source id, page read, note)
  role is "load", "discharge" or "both". The FIRST row of a family and role of a country is its principal
  gateway; the other rows are the other coasts or terminals (coast options).
  Families here: crude, products, lpg, lng (the families of pipeline/freight/modes.py).
  source id is an id of data/sources.json: "giignl-2026" for terminals read in the atlas's own LNG layer
  (data/infrastructure/lng.geojson, same page of the GIIGNL report as the feature), "wikipedia" for the article
  named in the url (CC BY-SA 4.0, read in November 2026; the note says what the page supports).

Sourcing pass FE4a: the rows after "FE4a" in G give the port a page names for the cargo (crude, products, LPG) to the
  largest ends of the worklist; a row replaces the port used before as the principal gateway. UNSOURCED_PORTS lists,
  as "country/family/role", the ends for which no page read names the cargo at a port, and what is missing: the
  loader's fallback applies there. A few rows sit at a landlocked end (Austria, Czechia, Hungary, Serbia) or at a
  coast with no port (Bosnia and Herzegovina), or at a pipeline terminal of another country (Kazakhstan, Azerbaijan):
  ports.candidates() does not read TRANSIT, so a pair of two landlocked countries had no port at one end. OFFSHORE
  lists the terminals in open water, which the seaport test of ports.py cannot accept.

Package FE4c (23 November 2026, after the second review GE4): Trieste is no longer the Italian crude gateway (its crude is
  the Transalpine pipeline's, and no page names crude at an Italian refinery port); Batumi is no products transit port of
  Kazakhstan and Azerbaijan; Kuwait and Ecuador crude (a history and a pipeline terminus) and the Fujairah products row
  (a bunkering hub) are gone, with their reasons in UNSOURCED_PORTS or in a comment; the Ras Lanuf page does name crude and
  products. Two free public-domain sources of the EIA were read by hand: the file of company-level imports (Form EIA-814,
  2024, ports of entry: source id eia-company-imports) gives the US crude and product import ports, and the country brief
  of Taiwan gives its crude import ports (source id eia-cab). The LNG export plants of the layer that had no row have one.
  Where no page was found for a large end (Korea, Japan, the Netherlands, Spain, Malaysia, Thailand, India products,
  Indonesia), UNSOURCED_PORTS says which pages were read and what would settle it.

TRANSIT = {iso3: {family or "default": (port code, source id, page read, note)}}: the foreign port through which
  a landlocked country's trade is assumed to reach the sea. A cargo family wins over "default". transit(iso3,
  family) returns the tuple or None. Every row is an Atlas assumption (a corridor the page documents, not a
  measured share of the trade); countries with no page read are in UNSOURCED with the reason, and their pairs
  stay "sea via a foreign port (not specified)".

MANUAL_EXTRA / MANUAL_SRC: ports missing from the searoute list, in the layout of ports.MANUAL
  ({code: (name, iso3, lon, lat)}), with the source of the coordinates.

EXTRA_ZONES / ZONES: freight zones used here that the plan's list of zones does not have; the loader of ports.py
  merges ZONES of every data module into the zone table that writes data/freight/zones.json.
"""

WP = "https://en.wikipedia.org/wiki/"
GIIGNL = "https://www.worldlngsummit.com/media/5stjrkng/2026-giignl-annual-report.pdf#page="
LIST = WP + "List_of_LNG_terminals"
EIAI = "https://www.eia.gov/petroleum/imports/companylevel/"
EIACAB = "https://www.eia.gov/international/analysis/country/"

EXTRA_ZONES = {
    "n-australia": "Northern Australia (Darwin)",
    "gulf-of-oman": "Gulf of Oman and Arabian Sea coast of Arabia (outside the Strait of Hormuz)",
    "taiwan": "Taiwan",
    "arctic-russia": "Russian Arctic coast",
    "russia-far-east": "Russian Far East",
}

# Ports missing from the searoute list. Coordinates are those of the terminal in the atlas's LNG layer.
MANUAL_EXTRA = {
    "USCVP": ("Cove Point LNG", "USA", -76.408, 38.389),
    "MZCSL": ("Coral Sul FLNG (Rovuma basin)", "MOZ", 41.0, -11.5),
    "CNRDG": ("Rudong LNG terminal", "CHN", 121.2, 32.55),
    # Qingdao LNG stands at Dongjiakou, 68 km from the searoute point Qingdao: the layer's point is the port's (OpenStreetMap)
    "CNDJK": ("Dongjiakou (Qingdao LNG terminal)", "CHN", 119.792, 35.685),
    "YEBAL": ("Balhaf (Yemen LNG)", "YEM", 48.1802, 13.9854),
    # Bonaire (BES): the searoute list has no port of the Caribbean Netherlands. Coordinates of Kralendijk, "the capital
    # and the main port of the island" (Wikipedia). Not in a gateway row: the page names no oil terminal.
    "BQKRA": ("Kralendijk (Bonaire)", "BES", -68.2656, 12.1444),
    # Offshore terminal (Halul Island lies 90 km northeast of Doha): coordinates of the page's infobox. It is further than
    # ports.SEAPORT_KM from the generalised coastline by nature (OFFSHORE).
    "QAHAL": ("Halul Island oil terminal", "QAT", 52.411, 25.675),
}
# Terminals in open water: the test of ports.is_seaport does not apply, a distance of 40 km does.
OFFSHORE = {"QAHAL"}
ZONES = EXTRA_ZONES

# {code: {zone, s, url}}, the layout of ports.MANUAL_SRC
MANUAL_SRC = {
    "USCVP": {"zone": "us-atlantic", "s": "giignl-2026", "url": GIIGNL + "17"},
    "MZCSL": {"zone": "e-africa", "s": "giignl-2026", "url": GIIGNL + "19"},
    "CNRDG": {"zone": "n-china", "s": "giignl-2026", "url": GIIGNL + "29"},
    "CNDJK": {"zone": "n-china", "s": "giignl-2026", "url": GIIGNL + "29"},
    "YEBAL": {"zone": "red-sea", "s": "giignl-2026", "url": GIIGNL + "18"},
    "BQKRA": {"zone": "caribbean", "s": "wikipedia", "url": WP + "Kralendijk"},
    "QAHAL": {"zone": "meg", "s": "wikipedia", "url": WP + "Halul_Island"},
}

G = {
    "ARE": [
        ("AEFJR", "gulf-of-oman", {"crude"}, "load", "wikipedia", WP + "Port_of_Fujairah", "Fujairah terminal on the Gulf of Oman, outside the Strait of Hormuz; end of the Habshan-Fujairah pipeline (1.5 million barrels a day, Wikipedia: Abu Dhabi Crude Oil Pipeline)"),
        ("AEDAS", "meg", {"crude"}, "load", "wikipedia", WP + "Das_Island", "Das Island exports crude oil from inside the Gulf, so a cargo loaded here has to pass the Strait of Hormuz"),
        # Fujairah is no products row (review GE6, finding 6): the Port of Fujairah page calls it 'the world second largest
        # bunkering hub' and names crude storage and the Habshan pipeline terminal, the EIA country brief a 62,000 barrel a
        # day refinery project and crude storage; no page says that UAE refined products are loaded for export there.
        ("AERUW", "meg", {"products"}, "load", "wikipedia", WP + "Ruwais", "Ruwais refinery and marine terminal"),
        ("AERUW", "meg", {"lpg"}, "load", "wikipedia", WP + "Ruwais", "Natural gas liquids fractionation plant at Ruwais"),
        ("AEDAS", "meg", {"lng"}, "load", "giignl-2026", GIIGNL + "18", None),
    ],
    "COL": [
        ("COCOV", "caribbean", {"crude"}, "load", "wikipedia", WP + "Cove%C3%B1as", "Covenas became an oil port in the twentieth century, on the Caribbean coast (the page does not name the pipeline)"),
        ("COCTG", "caribbean", {"lng"}, "discharge", "wikipedia", LIST, "SPEC terminal, Cartagena"),
    ],
    "OMN": [
        ("OMMFH", "gulf-of-oman", {"crude"}, "load", "wikipedia", WP + "Mina_Al_Fahal", "Crude export terminal near Muscat (single buoy moorings)"),
        ("OMQAL", "gulf-of-oman", {"lng"}, "load", "giignl-2026", GIIGNL + "18", None),
    ],
    "CAN": [
        ("CASJB", "canada-east", {"crude"}, "discharge", "wikipedia", WP + "Irving_Oil_Refinery", "Irving Oil refinery, the largest in Canada, receives crude by supertanker at the Canaport terminal"),
        ("CAKTM", "canada-west", {"lng"}, "load", "giignl-2026", GIIGNL + "19", None),
    ],
    "PAN": [
        ("PACHG", "cam-caribbean", {"crude"}, "discharge", "wikipedia", WP + "Trans-Panama_Pipeline", "Caribbean end of the Trans-Panama pipeline, which since 2008-2009 carries crude from the Atlantic side towards the Pacific"),
        ("PACHA", "cam-pacific", {"crude"}, "discharge", "wikipedia", WP + "Trans-Panama_Pipeline", "Pacific end of the Trans-Panama pipeline (Charco Azul)"),
    ],
    "GBR": [
        ("GBFAW", "nw-europe", {"crude"}, "discharge", "wikipedia", WP + "Fawley_Refinery", "Fawley refinery receives crude by tanker at its marine terminal on Southampton Water"),
        ("GBGRG", "nw-europe", {"crude"}, "discharge", "wikipedia", WP + "Grangemouth_Refinery", "Grangemouth docks imported Middle East crude for the refinery on the Firth of Forth"),
        ("GBPEM", "nw-europe", {"lng"}, "discharge", "giignl-2026", GIIGNL + "32", "South Hook, Milford Haven (nearest port: Pembroke)"),
        ("GBIOG", "nw-europe", {"lng"}, "discharge", "giignl-2026", GIIGNL + "32", None),
        ("GBSCU", "nw-europe", {"crude"}, "load", "wikipedia", WP + "Sullom_Voe_Terminal", "Oil and gas terminal in Shetland that stores the oil of the northern North Sea 'before it is transported by tanker'"),
        ("GBFAW", "nw-europe", {"products"}, "both", "wikipedia", WP + "Fawley_Refinery", "Fawley's marine terminal handles 22 million tonnes of crude oil and other products a year; the refinery makes petrol, jet fuel, diesel and LPG (the page does not split loading and discharge)"),
    ],
    "AUS": [
        ("AUBTB", "e-australia", {"products"}, "discharge", "wikipedia", WP + "Kurnell_Refinery", "Kurnell, Botany Bay: refinery converted in 2014 into an import terminal for refined fuel"),
        ("AUMEL", "e-australia", {"products"}, "discharge", "wikipedia", WP + "Port_of_Melbourne", "Holden Dock handles refined petroleum products"),
        ("AUDAM", "w-australia", {"lng"}, "load", "giignl-2026", GIIGNL + "18", "Karratha / Dampier: North West Shelf and Pluto"),
        ("AUGLT", "e-australia", {"lng"}, "load", "giignl-2026", GIIGNL + "19", "Curtis Island, Gladstone: three plants"),
        ("AUDRW", "n-australia", {"lng"}, "load", "giignl-2026", GIIGNL + "18", "Ichthys, Darwin"),
    ],
    "IDN": [
        ("IDTPP", "sea", {"products"}, "discharge", "wikipedia", WP + "Port_of_Tanjung_Priok", "The port has an oil terminal and a liquid bulk terminal"),
        ("IDBXT", "sea", {"lng"}, "load", "giignl-2026", GIIGNL + "19", None),
        ("IDNTI", "sea", {"lng"}, "load", "giignl-2026", GIIGNL + "19", "Tangguh, Bintuni Bay (the layer gives its capacity; Bontang's is not given, so Bontang stays first)"),
    ],
    "TUR": [
        ("TRMER", "med", {"products"}, "discharge", "wikipedia", WP + "Port_of_Mersin", "Mersin has a petroleum quay (ATAS refinery) and oil terminals"),
        ("TRALI", "med", {"lng"}, "discharge", "giignl-2026", GIIGNL + "31", None),
        ("TRTEK", "med", {"lng"}, "discharge", "giignl-2026", GIIGNL + "32", "Marmara Ereglisi (nearest port: Tekirdag)"),
    ],
    "NGA": [
        ("NGAPP", "waf", {"products"}, "discharge", "wikipedia", WP + "Apapa", "Apapa district, Lagos: refineries and petroleum tank farms (the page does not say what the ports unload)"),
        ("NGBON", "waf", {"lng"}, "load", "giignl-2026", GIIGNL + "17", None),
        ("NGBON", "waf", {"crude"}, "load", "wikipedia", WP + "Petroleum_industry_in_Nigeria", "Bonny Terminal is one of the country's six petroleum export terminals (with Forcados it stores 13 million barrels of crude oil); Bonny light is named after it"),
    ],
    "QAT": [
        ("QARLF", "meg", {"lng"}, "load", "giignl-2026", GIIGNL + "18", None),
        ("QAHAL", "meg", {"crude"}, "load", "wikipedia", WP + "Halul_Island", "Island 90 km offshore, a storage area and loading terminal for oil from the offshore fields, with 5 million barrels of crude oil storage"),
    ],
    "USA": [
        ("USSAB", "us-gulf", {"lng"}, "load", "giignl-2026", GIIGNL + "18", "Gulf Coast liquefaction (Sabine Pass is the largest in the layer)"),
        ("USCVP", "us-atlantic", {"lng"}, "load", "giignl-2026", GIIGNL + "17", "Atlantic coast liquefaction, Maryland"),
        ("USCRP", "us-gulf", {"crude"}, "load", "wikipedia", WP + "Port_of_Corpus_Christi", "The page calls the port the United States' largest gateway for crude oil exports"),
        # Ports of entry of the EIA file of company-level imports (Form EIA-814), 2024, thousand barrels of crude oil and of
        # every other petroleum product, read from impa24d.xlsx. Pipeline and rail crossings (Chicago, Peoria, Port Huron...)
        # are not seaports and are left out. Houston is the largest seaport of entry and the Gulf the largest coast (about
        # 490 million barrels of the 1,150 entered at seaports); the Pacific coast comes second and the Atlantic third, so
        # each is an option of the pairs on its own ocean.
        ("USHOU", "us-gulf", {"crude"}, "discharge", "eia-company-imports", EIAI, "EIA company-level imports 2024: Houston, TX entered 105.5 million barrels of crude oil, the largest seaport of entry (Port Arthur 97.4, Beaumont 58.4, Corpus Christi 53.2); the offshore terminal LOOP is not a port of entry of the file"),
        ("USLGB", "us-west", {"crude"}, "discharge", "eia-company-imports", EIAI, "EIA company-level imports 2024: Pacific coast, Richmond 70.2, Long Beach 69.6, Los Angeles 69.2 and El Segundo 62.8 million barrels of crude oil (Long Beach and Los Angeles are one port complex)"),
        ("USEWR", "us-atlantic", {"crude"}, "discharge", "eia-company-imports", EIAI, "EIA company-level imports 2024: Atlantic coast, Newark, NJ entered 85.2 million barrels of crude oil (Philadelphia 44.5, Wilmington, DE 50.3)"),
        ("USEWR", "us-atlantic", {"products"}, "discharge", "eia-company-imports", EIAI, "EIA company-level imports 2024: Newark, NJ entered 95.9 and Perth Amboy, NJ 33.7 million barrels of petroleum products other than crude oil (New York Harbor), the largest of the seaports of entry; the Atlantic coast is the largest coast of product imports"),
        ("USHOU", "us-gulf", {"products"}, "discharge", "eia-company-imports", EIAI, "EIA company-level imports 2024: Houston, TX entered 77.6 million barrels of petroleum products other than crude oil, the second seaport of entry (Gramercy, LA 25.6)"),
        ("USLAX", "us-west", {"products"}, "discharge", "eia-company-imports", EIAI, "EIA company-level imports 2024: Los Angeles, CA entered 23.6 million barrels of petroleum products other than crude oil, the largest Pacific seaport of entry (San Francisco 11.8, Richmond 10.5)"),
        ("USHOU", "us-gulf", {"lpg"}, "load", "wikipedia", WP + "Enterprise_Products", "Enterprise Products' marine terminals on the Houston Ship Channel load natural gas liquids for export (the page says NGL, not LPG alone)"),
    ],
    "PNG": [
        ("PGPOM", "sea", {"lng"}, "load", "giignl-2026", GIIGNL + "19", None),
    ],
    "MYS": [
        ("MYBTU", "sea", {"lng"}, "load", "giignl-2026", GIIGNL + "19", None),
    ],
    "RUS": [
        ("RUSAB", "arctic-russia", {"lng"}, "load", "giignl-2026", GIIGNL + "17", "Yamal LNG, Sabetta"),
        ("RUPRG", "russia-far-east", {"lng"}, "load", "giignl-2026", GIIGNL + "19", "Sakhalin-2, Prigorodnoye"),
        ("RUPRI", "baltic", {"products"}, "load", "wikipedia", WP + "Port_of_Primorsk", "Primorsk, the largest Russian oil-loading port of the Baltic: 'a terminal for transferring light petroleum products was opened', and the page gives the port's throughput of petroleum products, 1.56 million tonnes in 2008 and 13.5 in 2019"),
        ("RUNJK", "russia-far-east", {"products"}, "load", "wikipedia", WP + "Port_of_Nakhodka", "The Nakhodka port complex includes maritime and oil terminals and its 'key commodities handled include coal, petroleum products, containers' (the page gives no tonnage; the oil loading port was commissioned in 1973)"),
    ],
    "NOR": [
        ("NOHFT", "nw-europe", {"lng"}, "load", "giignl-2026", GIIGNL + "17", None),
        ("NOMON", "nw-europe", {"crude"}, "load", "wikipedia", WP + "Mongstad", "Equinor's crude oil terminal at Mongstad stores 9.5 million barrels (the page does not say that tankers load there)"),
    ],
    "DZA": [
        ("DZAZW", "med", {"lng"}, "load", "giignl-2026", GIIGNL + "17", None),
    ],
    "EGY": [
        ("EGAKI", "med", {"lng"}, "load", "giignl-2026", GIIGNL + "17", "Idku; Abu Qir is the nearest port of the searoute list"),
        ("EGSOK", "red-sea", {"lng"}, "discharge", "giignl-2026", GIIGNL + "32", None),
    ],
    "TTO": [
        ("TTPTF", "caribbean", {"lng"}, "load", "giignl-2026", GIIGNL + "17", None),
    ],
    "AGO": [
        ("AOSZA", "waf", {"lng"}, "load", "giignl-2026", GIIGNL + "17", None),
        ("AOCAB", "waf", {"crude"}, "load", "wikipedia", WP + "Cabinda_(city)", "The page says Cabinda 'serves as one of Angola's main oil ports', near rich offshore oil reserves"),
    ],
    "MOZ": [
        ("MZCSL", "e-africa", {"lng"}, "load", "giignl-2026", GIIGNL + "19", "Floating plant offshore Cabo Delgado; no port of the searoute list within 150 km"),
    ],
    "JPN": [
        ("JPCHB", "japan-korea", {"lng"}, "discharge", "giignl-2026", GIIGNL + "30", "Tokyo Bay (Sodegaura, Futtsu and Negishi terminals)"),
        ("JPCHB", "japan-korea", {"crude", "products"}, "discharge", "wikipedia", WP + "Port_of_Chiba", "The port 'imports crude petroleum, Liquefied Natural Gas, and other oil products'"),
    ],
    "KOR": [
        ("KRINC", "japan-korea", {"lng"}, "discharge", "giignl-2026", GIIGNL + "30", "Incheon; Pyeong-Taek is 70 km south on the same coast"),
        ("KROKP", "japan-korea", {"lng"}, "discharge", "giignl-2026", GIIGNL + "30", "Tong-Yeong, south coast (nearest port: Okpo)"),
    ],
    "CHN": [
        ("CNDJK", "n-china", {"lng"}, "discharge", "giignl-2026", GIIGNL + "29", "Qingdao terminal (the largest of the layer), at Dongjiakou: the layer's point, 68 km from the searoute point Qingdao"),
        ("CNYTN", "s-china", {"lng"}, "discharge", "giignl-2026", GIIGNL + "28", "Dapeng, Shenzhen (nearest port: Yantian)"),
        ("CNTSN", "n-china", {"lng"}, "discharge", "giignl-2026", GIIGNL + "29", "Tianjin terminal"),
        ("CNRDG", "n-china", {"lng"}, "discharge", "giignl-2026", GIIGNL + "29", "Rudong, Jiangsu (Yangtze delta)"),
        ("CNNGB", "e-china", {"crude"}, "discharge", "wikipedia", WP + "Port_of_Ningbo-Zhoushan", "The page names a 250,000-tonnage crude oil terminal among the port's larger berths (it does not say imports)"),
    ],
    "TWN": [
        ("TWKHH", "taiwan", {"lng"}, "discharge", "giignl-2026", GIIGNL + "30", "Yung-An, Kaohsiung"),
        ("TWTXG", "taiwan", {"lng"}, "discharge", "giignl-2026", GIIGNL + "30", None),
        ("TWMAL", "taiwan", {"crude"}, "discharge", "eia-cab", EIACAB + "TWN", "EIA country brief: 'Taiwan's crude oil imports come in through three ports: Mai Liao (55% in 2025), Kaohsiung (30% in 2025), and Shalung (15% in 2025)'; Mai Liao is the Mailiao of the searoute list (the third port is not in it)"),
        ("TWKHH", "taiwan", {"crude"}, "discharge", "eia-cab", EIACAB + "TWN", "Same EIA sentence: Kaohsiung 30% of Taiwan's crude oil imports in 2025"),
    ],
    "IND": [
        ("INDAH", "wc-india", {"lng"}, "discharge", "giignl-2026", GIIGNL + "29", None),
        ("INHZA", "wc-india", {"lng"}, "discharge", "giignl-2026", GIIGNL + "29", None),
        ("INVAD", "wc-india", {"crude"}, "discharge", "wikipedia", WP + "Vadinar", "Vadinar has the offshore oil terminal of Deendayal Port (single-buoy moorings of Indian Oil, one of the Essar refinery) and a crude oil terminal of Indian Oil; the Reliance refinery is close by (the page does not say imports)"),
        ("INPRT", "ec-india", {"crude"}, "discharge", "wikipedia", WP + "Paradip_Port", "East coast: the port 'mainly transports bulk cargoes and crude oil' and has single point mooring terminals handling captive crude oil for Indian Oil"),
    ],
    "NLD": [
        ("NLEUR", "nw-europe", {"lng"}, "discharge", "giignl-2026", GIIGNL + "31", "Gate terminal, Maasvlakte (nearest port: Europoort)"),
    ],
    "BEL": [
        ("BEZEE", "nw-europe", {"lng"}, "discharge", "giignl-2026", GIIGNL + "30", None),
    ],
    "FRA": [
        ("FRDKK", "nw-europe", {"lng"}, "discharge", "giignl-2026", GIIGNL + "30", None),
        ("FRMTX", "nw-europe", {"lng"}, "discharge", "giignl-2026", GIIGNL + "31", "Atlantic coast"),
        ("FRFOS", "med", {"lng"}, "discharge", "giignl-2026", GIIGNL + "31", "Mediterranean coast"),
        ("FRLEH", "nw-europe", {"products"}, "both", "wikipedia", WP + "Port_of_Le_Havre", "Two firms at the port 'manage the flows of gasoil and fuel' (the page does not split loading and discharge)"),
    ],
    "ESP": [
        ("ESBCN", "med", {"lng"}, "discharge", "giignl-2026", GIIGNL + "31", None),
    ],
    "PRT": [
        ("PTSIE", "nw-europe", {"lng"}, "discharge", "giignl-2026", GIIGNL + "31", "Atlantic coast"),
    ],
    "POL": [
        ("PLSWI", "baltic", {"lng"}, "discharge", "giignl-2026", GIIGNL + "31", None),
        ("PLGDN", "baltic", {"crude"}, "discharge", "wikipedia", WP + "Naftoport", "Naftoport runs the crude oil reloading terminal in the Port of Gdansk, built in the 1990s to diversify Poland's oil imports"),
    ],
    "LTU": [
        ("LTKLJ", "baltic", {"lng"}, "discharge", "giignl-2026", GIIGNL + "31", None),
    ],
    "DEU": [
        ("DEWVN", "nw-europe", {"lng"}, "discharge", "giignl-2026", GIIGNL + "31", None),
        ("DEBRB", "nw-europe", {"lng"}, "discharge", "giignl-2026", GIIGNL + "31", None),
        ("DEWVN", "nw-europe", {"crude"}, "discharge", "wikipedia", WP + "Wilhelmshaven", "The page calls Wilhelmshaven 'the most important German import terminal for crude oil'; pipelines supply refineries inland"),
        ("DEWVN", "nw-europe", {"products"}, "both", "wikipedia", WP + "Wilhelmshaven", "The port built jetties 'for crude oil and oil products, coal, and chemical products' (the page does not split loading and discharge)"),
    ],
    "KWT": [
        ("KWKWM", "meg", {"lng"}, "discharge", "giignl-2026", GIIGNL + "32", "Al-Zour (nearest port: Khor al Muffatta)"),
    ],
    "THA": [
        ("THMTP", "sea", {"lng"}, "discharge", "wikipedia", LIST, "Map Ta Phut LNG terminal (phase 1, 2011)"),
    ],
    "ITA": [
        ("ITCHI", "med", {"lng"}, "discharge", "wikipedia", LIST, "Adriatic LNG, offshore Porto Levante near Rovigo (nearest port: Chioggia)"),
        ("ITLIV", "med", {"lng"}, "discharge", "wikipedia", LIST, "OLT Toscana terminal, offshore Livorno"),
        ("ITSPE", "med", {"lng"}, "discharge", "wikipedia", LIST, "Panigaglia terminal, La Spezia"),
        # No crude row: Trieste's crude is the Transalpine pipeline's (Austria, Germany, Czechia), see UNSOURCED_PORTS.
    ],
    "PAK": [
        ("PKBQM", "wc-india", {"lng"}, "discharge", "wikipedia", LIST, "Engro Elengy terminal and GasPort, Port Qasim, Karachi"),
    ],
    "GRC": [
        ("GRPIR", "med", {"lng"}, "discharge", "wikipedia", LIST, "Revithoussa island terminal; Piraeus is the nearest port of the searoute list, 20 km east"),
    ],
    "HRV": [
        ("HROMI", "med", {"lng"}, "discharge", "wikipedia", LIST, "Krk floating terminal, Omisalj"),
    ],
    "CHL": [
        ("CLQTV", "wcsa", {"lng"}, "discharge", "wikipedia", LIST, "GNL Quintero"),
    ],
    "BRA": [
        ("BRPEC", "ecsa", {"lng"}, "discharge", "wikipedia", LIST, "Pecem terminal"),
        ("BRADR", "ecsa", {"crude"}, "load", "wikipedia", WP + "Angra_dos_Reis", "The TEBIG terminal of Petrobras 'transports large quantities of crude oil' and the port has an oil terminal (the page does not say tankers load there)"),
    ],
    "BRN": [
        ("BNLUM", "sea", {"lng"}, "load", "giignl-2026", GIIGNL + "19", "Brunei LNG, Lumut (five trains in the report's table)"),
    ],
    "GNQ": [
        ("GQSSG", "waf", {"lng"}, "load", "giignl-2026", GIIGNL + "17", "EG LNG, Bioko island (nearest port: Malabo)"),
    ],
    # LNG export plants of the atlas's layer (data/infrastructure/lng.geojson) that had no load row (package FE4c): the page
    # of the report is that of the feature.
    "CMR": [
        ("CMKBI", "waf", {"lng"}, "load", "giignl-2026", GIIGNL + "17", "Kribi (FLNG) in the report's table, moored off Kribi (the layer's point is the town)"),
    ],
    "PER": [
        ("PECAZ", "wcsa", {"lng"}, "load", "giignl-2026", GIIGNL + "19", "Peru LNG in the report's table, Pampa Melchorita (nearest port of the searoute list: Cerro Azul, 26 km up the coast)"),
    ],
    "YEM": [
        ("YEBAL", "red-sea", {"lng"}, "load", "giignl-2026", GIIGNL + "18", "Yemen LNG, Balhaf, on the Gulf of Aden: the report's table marks both trains 'stopped' (shut down since 2015 according to the layer); no port of the searoute list within 120 km"),
    ],
    # ------------------------------------------------------------------ FE4a: crude, products and LPG, one page per row
    "SAU": [
        ("SARTA", "meg", {"crude"}, "load", "wikipedia", WP + "Ras_Tanura", "The page calls Ras Tanura Port the world's largest crude oil export terminal"),
        ("SAYNB", "red-sea", {"crude"}, "load", "wikipedia", WP + "Yanbu", "Red Sea coast: three oil pipelines from the eastern oilfields end at Yanbu, 'a major hub for oil export'; the page calls it a petroleum shipping terminal"),
    ],
    "IRQ": [
        ("IQBOT", "meg", {"crude"}, "load", "wikipedia", WP + "Al_Ba%C5%9Frah_Oil_Terminal", "Offshore deep sea crude oil marine loading terminal: the crude produced for export from the southern oilfields is piped to it"),
    ],
    "MEX": [
        ("MXDBT", "mexico-gulf", {"crude"}, "load", "wikipedia", WP + "Dos_Bocas,_Tabasco", "Dos Bocas has a major single buoy mooring crude oil export facility and is one of Mexico's main crude oil ports"),
        ("MXATM", "mexico-gulf", {"lng"}, "load", "giignl-2026", GIIGNL + "17", "Altamira Fast LNG in the report's table, at the Altamira terminal"),
    ],
    "LBY": [
        ("LYRLA", "med", {"crude", "products"}, "load", "wikipedia", WP + "Ras_Lanuf", "'The Port of Ra's Lanuf consists of a small harbor ... Its primary activities include loading crude oil and oil products'; the town is the terminus of two oil pipelines from the fields (the page does not cover Es Sider or the other Libyan terminals)"),
    ],
    "VEN": [
        ("VEPJO", "caribbean", {"crude", "products"}, "load", "wikipedia", WP + "Puerto_Jos%C3%A9", "Oil tanker loading complex: the port exports refined petroleum products, crude oil and containers"),
    ],
    "SGP": [
        ("SGSIN", "sea", {"crude"}, "discharge", "wikipedia", WP + "Port_of_Singapore", "The port tranships half of the world's annual crude oil supplies and imports raw materials for refining; Singapore has no crude oil of its own (Jurong Island page)"),
        ("SGSIN", "sea", {"products"}, "load", "eia-cab", EIACAB + "SGP", "EIA country brief: Singapore is 'the fifth-largest refinery and export hub in the world' and 'most of Singapore's refined petroleum product and petrochemical exports are destined for neighboring Asian countries' (a city-state with one port system: the page names the exports of the country, not a berth; no tonnage by port)"),
    ],
    "KAZ": [
        ("KZCPC", "black-sea", {"crude"}, "load", "wikipedia", WP + "Caspian_Pipeline_Consortium", "The CPC pipeline handles almost all of Kazakhstan's oil exports, to the Novorossiysk-2 marine terminal in Russia (pipeline terminal, not a Kazakh port)"),
    ],
    "AZE": [
        ("TRCEY", "med", {"crude"}, "load", "wikipedia", WP + "Ceyhan", "The BTC pipeline brings Caspian crude oil to Ceyhan's marine terminal, whose jetty loads tankers (pipeline terminal, not an Azerbaijani port)"),
    ],
    # Landlocked ends: candidates() does not read TRANSIT, so a pair between two landlocked countries (Kazakh crude to
    # Austria) had no port at the buyer's end. The port is the one of the TRANSIT row, same page.
    "AUT": [
        ("ITTRS", "med", {"crude"}, "discharge", "wikipedia", WP + "Transalpine_Pipeline", "The Transalpine crude oil pipeline starts at the marine terminal in Trieste and connects Italy, Austria, Germany and the Czech Republic"),
    ],
    "CZE": [
        ("ITTRS", "med", {"crude"}, "discharge", "wikipedia", WP + "Transalpine_Pipeline", "The Transalpine crude oil pipeline starts at the marine terminal in Trieste and connects Italy, Austria, Germany and the Czech Republic"),
    ],
    "HUN": [
        ("HROMI", "med", {"crude"}, "discharge", "wikipedia", WP + "Adria_oil_pipeline", "The Adria crude oil pipeline starts at the Omisalj oil terminal; its northern branch crosses the Croatian-Hungarian border at Gola and runs to the Duna refinery in Szazhalombatta"),
    ],
    "SRB": [
        ("HROMI", "med", {"crude"}, "discharge", "wikipedia", WP + "Adria_oil_pipeline", "The Adria crude oil pipeline starts at the Omisalj oil terminal; its eastern branch runs from Sisak to Sotin on the Croatian-Serbian border, then to Novi Sad and Pancevo"),
    ],
    "BIH": [
        ("HRPLE", "med", {"products"}, "discharge", "wikipedia", WP + "Port_of_Plo%C4%8De", "Ploce is the natural outlet of Bosnia and Herzegovina (Ploce Agreement of 1996); its liquid cargo terminal handles fuel"),
    ],
}

_KILINDINI = WP + "Kilindini_Harbour"
_DAR = WP + "Port_of_Dar_es_Salaam"
_TAL = WP + "Transalpine_Pipeline"
_ADRIA = WP + "Adria_oil_pipeline"

TRANSIT = {
    "KAZ": {"crude": ("KZCPC", "wikipedia", WP + "Caspian_Pipeline_Consortium",
                      "The CPC pipeline carries almost all of Kazakhstan's crude to the Novorossiysk terminal, in Russia")},
    "AZE": {"crude": ("TRCEY", "wikipedia", WP + "Baku%E2%80%93Tbilisi%E2%80%93Ceyhan_pipeline",
                      "The BTC pipeline runs from the Caspian to Ceyhan on the Mediterranean")},
    "TCD": {"crude": ("CMKBI", "wikipedia", WP + "Chad%E2%80%93Cameroon_Petroleum_Development_and_Pipeline_Project",
                      "The pipeline carries Chadian crude to the offshore export terminal near Kribi")},
    "AUT": {"crude": ("ITTRS", "wikipedia", _TAL, "The Transalpine pipeline runs from Trieste to Austria and Germany")},
    "CZE": {"crude": ("ITTRS", "wikipedia", _TAL, "The Transalpine pipeline connects Trieste with the Czech Republic"),
            "default": ("DEHAM", "wikipedia", WP + "Port_of_Hamburg",
                        "Assumption: the page says the Moldauhafen, a harbour area of the Port of Hamburg, is reserved for the Czech Republic exclusively; it does not say how much Czech trade uses Hamburg")},
    "SSD": {"crude": ("SDPZU", "wikipedia", WP + "Greater_Nile_Oil_Pipeline",
                      "The Greater Nile Oil Pipeline begins in the Unity oil field and ends at the Port Sudan refinery on the Red Sea (the page does not name South Sudan or a loading terminal)")},
    "HUN": {"crude": ("HROMI", "wikipedia", _ADRIA, "The Adria pipeline runs from the Omisalj terminal, over the Croatian-Hungarian border at Gola, to the Duna refinery in Hungary")},
    "SRB": {"crude": ("HROMI", "wikipedia", _ADRIA, "The Adria pipeline runs from the Omisalj terminal to Sisak, then its eastern branch crosses into Serbia at Sotin and runs to Novi Sad and Pancevo")},
    "UGA": {"default": ("KEMBA", "wikipedia", _KILINDINI, "Mombasa's hinterland extends to Uganda; transit cargo for landlocked neighbours")},
    "RWA": {"default": ("KEMBA", "wikipedia", _KILINDINI, "Rail links planned from Mombasa to Uganda and Rwanda")},
    "ZMB": {"default": ("TZDAR", "wikipedia", _DAR, "Gateway for Zambian copper exports and fuel imports")},
    "COD": {"default": ("TZDAR", "wikipedia", _DAR, "Listed among the countries the port serves")},
    "BDI": {"default": ("TZDAR", "wikipedia", _DAR, "Listed among the countries the port serves")},
    "MWI": {"default": ("TZDAR", "wikipedia", _DAR, "Gateway for Malawian tobacco exports and fuel imports")},
    "ETH": {"default": ("DJJIB", "wikipedia", WP + "Port_of_Djibouti", "Principal maritime outlet for Ethiopia's trade")},
    "ZWE": {"default": ("MZBEW", "wikipedia", WP + "Port_of_Beira", "The port's railways carry products from Malawi and Zimbabwe")},
    "CHE": {"default": ("NLRTM", "wikipedia", WP + "Rotterdam", "Assumption: the page says the Maas and the Rhine give Rotterdam access to the hinterland, reaching to Basel, Switzerland; it does not say how much Swiss trade uses it")},
    "BFA": {"default": ("CIABJ", "wikipedia", WP + "Transport_in_Burkina_Faso", "The Ouagadougou-Abidjan railway is the freight corridor (rerouted to Togo, Benin and Ghana in the 2003 crisis)")},
    "MLI": {"default": ("CIABJ", "wikipedia", WP + "Transport_in_Mali", "Abidjan has been Mali's main seaport; Dakar is the other")},
    "NER": {"default": ("BJCOO", "wikipedia", WP + "Transport_in_Niger", "Niger relies on the port of Cotonou, and less on Lome")},
    "NPL": {"default": ("INCCU", "wikipedia", WP + "Port_of_Kolkata", "Kolkata serves the landlocked neighbours Nepal and Bhutan")},
    "BTN": {"default": ("INCCU", "wikipedia", WP + "Port_of_Kolkata", "Kolkata serves the landlocked neighbours Nepal and Bhutan")},
    # a coast with no port of its own: build_lanes.py treats it like a landlocked end
    "BIH": {"default": ("HRPLE", "wikipedia", WP + "Port_of_Plo%C4%8De",
                        "The page calls the site 'the natural outlet for the economy of Bosnia and Herzegovina', says the port is 'mostly serving Bosnia and Herzegovina' and names the Ploce Agreement on the passage of goods; it names coal, cereals, bauxite, timber and fuel terminals")},
}

# Landlocked countries of the plan's candidate table for which no page stating the port was read.
UNSOURCED = {
    "BLR": "potash by rail to Baltic ports: Belaruskali page read, 'most of its production is exported to China', no port or route named; the Klaipeda page names no Belarusian cargo (ports.py keeps its present Ust-Luga row)",
    "BOL": "Wikipedia (Transport in Bolivia) gives free port privileges in Chile, Argentina and Brazil and the Paraguay river ports, not Arica; the Port of Arica page names Arica a common port of Peru and Bolivia in 1836 (history, no cargo today), so soy products have no transit row",
    "PRY": "Parana-Paraguay Waterway page read: it runs to Nueva Palmira (Uruguay), carrying soy first, then iron and fuels, but Nueva Palmira is not in the searoute list and its page (Nueva Palmira: 'the second most important commercial port in Uruguay') names no cargo and gives no Paraguayan trade; ports.py keeps Up-River Parana",
    "SRB": "other cargo than crude: the Danube is documented, a seaport is not (Constanta not confirmed)",
    "MDA": "no page read",
    "AFG": "Port of Karachi page mentions Afghanistan only as a historical gateway",
    "ARM": "Poti page does not mention Armenia",
    "LAO": "Transport in Laos names no seaport",
    "MNG": "Transport in Mongolia names no seaport",
    "BWA": "no page read",
    "SWZ": "no page read",
    "LSO": "no page read",
    "SSD": "other cargo than crude (fuel imports): no page read",
    "KAZ": "refined products, coal, steel, grain, copper and aluminium (crude: CPC): Transport in Kazakhstan and Trans-Caspian Route pages read, they name no sea outlet for these cargoes; the Port of Lianyungang page calls the port 'a logistics cooperation base with Kazakhstan' and an ocean access point for the SCO states, naming no cargo, so it is no row either; the Batumi Seaport page calls Batumi 'a major transit port for oil refining in Kazakhstan and Azerbaijan' (crude going to refining there, the opposite direction of products leaving a landlocked refiner) and names no product, so it is no row",
    "AZE": "refined products, urea, sugar, soymeal (crude: BTC): Transport in Azerbaijan page read, it names no port; the Batumi Seaport page names oil going from Baku to Batumi by rail (the history of the port) and a transit role for oil refining, no product, so Batumi is no row",
    "AUT": "other cargo than crude (coal, steel): Transport in Austria and Port of Koper pages read, neither names Austrian cargo",
    "HUN": "other cargo than crude: no page read",
    "KGZ": "no page read",
    "UZB": "Poti Sea Port page read: TRACECA links Constanta and Varna with the Caspian region and Central Asia; it names neither Uzbekistan nor Poti as its outlet",
    "TKM": "Poti Sea Port page read: TRACECA links Constanta and Varna with the Caspian region and Central Asia; it names neither Turkmenistan nor Poti as its outlet",
    "SVK": "Adria oil pipeline page read: the 1968 route to Bratislava was decided, but the page does not say that Slovak crude now comes through Omisalj",
    "TJK": "no page read",
}


# Gateways of the engine's worklist (country/family/role) for which no page read names the cargo at a port: the
# loader's fallback applies (the port used before, "no source page yet" on the site). What is missing is stated.
UNSOURCED_PORTS = {
    "NLD/crude/discharge": "Port of Rotterdam, Europoort, Botlek, Pernis and Maasvlakte pages read: refineries and tank storage, no crude oil named at a port (the EIA country brief of the Netherlands, read, gives storage in Rotterdam, 'more than 170 million barrels' at the beginning of 2014, and calls Amsterdam a gasoline hub: no tonnage by port; the Port of Rotterdam Authority's throughput statistics by cargo, a free page whose address was not found, would settle it)",
    "NLD/products/load": "same pages: no products named at a port",
    "NLD/products/discharge": "same pages: no products named at a port",
    "KOR/crude/discharge": "Ulsan, Port of Ulsan, Yeosu, SK Innovation, GS Caltex and HD Hyundai Oilbank pages read: refineries and crude imports by company, no port or terminal named (the EIA country brief of South Korea, read, lists the refineries by town: Ulsan 1,383, Daesan 809, Yeosu 744 and Incheon 349 thousand barrels a day in its 2022 table, no port; the national port statistics of the Ministry of Oceans and Fisheries by port and cargo would settle it)",
    "KOR/products/load": "same pages: no port named for exports",
    "KOR/products/discharge": "same pages: no port named",
    "KOR/lpg/discharge": "same pages: no port named",
    "IND/products/load": "Jamnagar refinery and Sikka pages read: oil products exported by the refinery whose complex has port facilities, Sikka port not named (the EIA country brief of India, read, lists the refineries by town: Jamnagar, Vadinar, Kochi, Mangalore, Visakhapatnam, Paradip, Mumbai, Manali and Haldia among others, no port)",
    "IND/products/discharge": "no page read names products imports at a port",
    "IND/lpg/discharge": "Mundra Port page names liquid cargo and a liquid terminal, not LPG",
    "USA/products/load": "Port of Houston, Houston Ship Channel, Port of Corpus Christi, Port Arthur and Texas City pages read: refineries and 'petroleum related' cargo, no refined products named at a port; the EIA file of company-level imports covers imports only, and no free statistic of exports by port was found (EIA publishes exports by PADD, not by port)",
    "SGP/products/discharge": "Port of Singapore and Jurong Island pages read: bunkering and refining, no products import named",
    "SGP/lng/discharge": "no page read; the layer of the atlas has no Singapore terminal",
    "BRA/crude/discharge": "Port of Santos page names liquid bulk only; no page names a crude oil import port",
    "BRA/products/load": "no page read",
    "BRA/products/discharge": "Port of Santos page names liquid bulk only",
    "FRA/crude/discharge": "Fos-sur-Mer and Port of Marseille pages read: oil industry, no crude oil named at a port",
    "ESP/crude/discharge": "Port of Algeciras, Huelva, Bilbao and Tarragona pages read: no crude oil named at a port (the EIA country brief of Spain, read, names LNG terminals only; Eurostat's mar_go_am_es, built like the Italian table (liquid bulk by port, no crude split), would rank the ports but name no crude)",
    "ESP/products/load": "same pages",
    "ESP/products/discharge": "same pages",
    "ITA/crude/discharge": "Trieste is no row: its crude is mostly the Transalpine pipeline's, in transit to Austria, Germany and Czechia (the Transalpine page gives 34.9 Mt in 2012, no Italian share), while Italy's own refineries stand at Augusta/Priolo, Sarroch, Milazzo and on the Tyrrhenian and Adriatic coasts. No page names crude at those ports: Augusta, Port of Augusta, Priolo Gargallo, Sarroch, Saras, Milazzo, Port of Cagliari, Livorno, Genoa and Taranto pages read (refineries, 'hydrocarbons' at Milazzo, 'oil' berths at Cagliari). Eurostat mar_go_am_it, liquid bulk goods (crude, products and chemicals together, no split by cargo), 2024, thousand tonnes inwards by port: Trieste 40,783, Augusta 13,354, Porto Foxi (Sarroch) 12,739, Genoa 11,129, Siracusa 6,822, Venice 6,527, Milazzo 3,926; this ranks the refinery ports (Augusta first) but names no crude. The port used before (Augusta) answers",
    "KWT/crude/load": "Ahmadi Governorate page: the first Kuwaiti oil export left Mina Al-Ahmadi in 1946 (history, no recent volume); Kuwait National Petroleum Company page: refineries, no port. No page names crude loading at a port today. The port used before (Mina al-Ahmadi) answers",
    "ECU/crude/load": "Esmeraldas page: terminus of the Trans-Ecuadorian pipeline and a refinery, the port exports wood and bananas, 'the port of Balao is an important oil processing facility'; no page names tankers loading crude. The port used before (Esmeraldas) answers",
    "IDN/crude/discharge": "Cilacap (Java, south coast), Balikpapan, Dumai and the Pertamina refinery table (Wikipedia Pertamina; EIA country brief, 2025: Cilacap 348 thousand barrels a day, the largest) read: they place refineries in provinces and towns and name no crude or product at a port. The Cilacap page calls the town a sea port that 'is a hub for national or international trade' and the site of Pertamina's largest processing unit, which is not a cargo at the port; the Balongan page does not exist on Wikipedia and the Pertamina pages are scripts that show no text. Balikpapan, on the Makassar Strait, stays the port used before (28 Mt of tanker cargo of the pairs cross the Makassar Strait because of it, test C06); a Java port needs a page that names crude, products or LPG at Cilacap or Balongan (Pertamina, the port authority Pelindo or the Ministry of Transport)",
    "IDN/products/load": "same pages",
    "IDN/lpg/discharge": "same pages",
    "ITA/products/load": "Augusta and Priolo Gargallo pages read: refineries (16 million tonnes of crude a year), no products or port role named",
    "ITA/products/discharge": "same pages",
    "THA/crude/discharge": "Laem Chabang, Map Ta Phut and Si Racha pages read: a Thai Oil jetty is named, with oil, not crude (the EIA country brief of Thailand, read, names the Map Ta Phut LNG terminal only)",
    "MYS/crude/load": "Kerteh page names the Terengganu Crude Oil Terminal but gives the town's coordinates (inland), and no searoute port lies within a few km; Labuan page says crude oil is exported, the searoute point for Labuan is inland (the EIA country brief of Malaysia, read, lists the refineries by town: Melaka, Pengerang, Port Dickson, Kerteh and Kemaman, no port)",
    "MYS/products/load": "Kuantan and Port Dickson pages read: no products named at a port",
    "MYS/products/discharge": "same pages",
    "MYS/crude/discharge": "same pages",
    "GUY/crude/load": "no page read (the Wikipedia article on the Stabroek block was not found)",
    "SAU/products/load": "Jubail and Yanbu pages read: refineries and 'petroleum' shipping, no refined products named at a port",
    "SAU/lpg/load": "Ras Tanura page names oil and gas exports, not LPG",
    "KWT/products/load": "Ahmadi Governorate page names the Mina Al-Ahmadi refinery, not products at the port",
    "QAT/products/load": "Ras Laffan and Mesaieed pages read: no products named",
    "QAT/lpg/load": "same pages",
    "CHN/products/load": "Port of Ningbo-Zhoushan page names a crude oil terminal and a liquid chemical berth, not products",
    "CHN/products/discharge": "same page",
    "CHN/lpg/discharge": "same page",
    "DZA/crude/load": "Arzew page names LNG; Skikda page names 'a gas and oil terminal' without crude or products",
    "DZA/products/load": "same pages",
    "TUR/products/load": "Ceyhan page names the BTC and Kirkuk crude terminal, not products",
    "SWE/crude/discharge": "Port of Gothenburg page names no refinery or crude",
    "SWE/products/load": "same page",
    "FIN/crude/discharge": "Naantali and Porvoo pages read: refineries, no crude oil named at a port",
    "LTU/crude/discharge": "no page read",
    "GRC/crude/discharge": "Aspropyrgos and Port of Piraeus pages read: refinery with a dock, no crude named",
    "GRC/products/load": "same pages",
    "PAK/crude/discharge": "no page read",
    "PAK/products/discharge": "no page read",
    "ZAF/products/discharge": "no page read",
    "ZAF/crude/discharge": "no page read",
    "AUS/crude/load": "Port Bonython (South Australia): the page says the wharf 'is used for the export of hydrocarbon products' and that the plant 'receive[s] crude oil and gas from the Cooper Basin', no crude or LPG loaded at the port; Varanus Island: 'piping oil and gas', no port; Dampier: iron ore, LNG and salt (Barrow Island: a disambiguation page). The loader's nearest seaport (Thevenard) applies",
    "AUS/lpg/load": "same pages: Port Bonython has a gas fractionation plant, LPG is not named",
    "AUS/crude/discharge": "no page read",
    "CAN/crude/load": "no page read that names an Atlantic crude port (Newfoundland): the Come By Chance Refinery page (a renewable diesel refinery today) and the Placentia Bay page name no crude loading, and there is no Whiffen Head page; Vancouver stays the port used before, so Canadian crude for Europe is drawn to the Pacific coast",
    "GTM/products/discharge": "Puerto Barrios and Santo Tomas de Castilla pages read: 'Guatemala's main Caribbean Sea port' and 'most modern cargo traffic', bananas and containers, no fuel or product named",
    "OMN/products/load": "no page read",
    "EGY/products/load": "no page read",
    "EGY/products/discharge": "no page read",
    "HKG/products/discharge": "no page read",
    "ARE/products/discharge": "no page read",
    "IRQ/products/load": "Al Basrah Oil Terminal page names crude only",
}


def transit(iso3, family):
    """Transit row of a landlocked country for a cargo family, or None."""
    d = TRANSIT.get(iso3)
    if not d:
        return None
    return d.get(family) or d.get("default")
