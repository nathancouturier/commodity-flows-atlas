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
    # Bonaire (BES): the searoute list has no port of the Caribbean Netherlands. Coordinates of Kralendijk, "the capital
    # and the main port of the island" (Wikipedia). Not in a gateway row: the page names no oil terminal.
    "BQKRA": ("Kralendijk (Bonaire)", "BES", -68.2656, 12.1444),
}
ZONES = EXTRA_ZONES

# {code: {zone, s, url}}, the layout of ports.MANUAL_SRC
MANUAL_SRC = {
    "USCVP": {"zone": "us-atlantic", "s": "giignl-2026", "url": GIIGNL + "17"},
    "MZCSL": {"zone": "e-africa", "s": "giignl-2026", "url": GIIGNL + "19"},
    "CNRDG": {"zone": "n-china", "s": "giignl-2026", "url": GIIGNL + "29"},
    "BQKRA": {"zone": "caribbean", "s": "wikipedia", "url": WP + "Kralendijk"},
}

G = {
    "ARE": [
        ("AEFJR", "gulf-of-oman", {"crude"}, "load", "wikipedia", WP + "Port_of_Fujairah", "Fujairah terminal on the Gulf of Oman, outside the Strait of Hormuz; end of the Habshan-Fujairah pipeline (1.5 million barrels a day, Wikipedia: Abu Dhabi Crude Oil Pipeline)"),
        ("AEDAS", "meg", {"crude"}, "load", "wikipedia", WP + "Das_Island", "Das Island exports crude oil from inside the Gulf, so a cargo loaded here has to pass the Strait of Hormuz"),
        ("AERUW", "meg", {"products"}, "load", "wikipedia", WP + "Ruwais", "Ruwais refinery and marine terminal"),
        ("AEFJR", "gulf-of-oman", {"products"}, "load", "wikipedia", WP + "Port_of_Fujairah", "Fujairah is a bunkering hub on the Gulf of Oman"),
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
    ],
    "QAT": [
        ("QARLF", "meg", {"lng"}, "load", "giignl-2026", GIIGNL + "18", None),
    ],
    "USA": [
        ("USSAB", "us-gulf", {"lng"}, "load", "giignl-2026", GIIGNL + "18", "Gulf Coast liquefaction (Sabine Pass is the largest in the layer)"),
        ("USCVP", "us-atlantic", {"lng"}, "load", "giignl-2026", GIIGNL + "17", "Atlantic coast liquefaction, Maryland"),
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
    ],
    "NOR": [
        ("NOHFT", "nw-europe", {"lng"}, "load", "giignl-2026", GIIGNL + "17", None),
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
    ],
    "MOZ": [
        ("MZCSL", "e-africa", {"lng"}, "load", "giignl-2026", GIIGNL + "19", "Floating plant offshore Cabo Delgado; no port of the searoute list within 150 km"),
    ],
    "JPN": [
        ("JPCHB", "japan-korea", {"lng"}, "discharge", "giignl-2026", GIIGNL + "30", "Tokyo Bay (Sodegaura, Futtsu and Negishi terminals)"),
    ],
    "KOR": [
        ("KRINC", "japan-korea", {"lng"}, "discharge", "giignl-2026", GIIGNL + "30", "Incheon; Pyeong-Taek is 70 km south on the same coast"),
        ("KROKP", "japan-korea", {"lng"}, "discharge", "giignl-2026", GIIGNL + "30", "Tong-Yeong, south coast (nearest port: Okpo)"),
    ],
    "CHN": [
        ("CNTAO", "n-china", {"lng"}, "discharge", "giignl-2026", GIIGNL + "29", "Qingdao terminal (the largest of the layer); 50 km from the port point"),
        ("CNYTN", "s-china", {"lng"}, "discharge", "giignl-2026", GIIGNL + "28", "Dapeng, Shenzhen (nearest port: Yantian)"),
        ("CNTSN", "n-china", {"lng"}, "discharge", "giignl-2026", GIIGNL + "29", "Tianjin terminal"),
        ("CNRDG", "n-china", {"lng"}, "discharge", "giignl-2026", GIIGNL + "29", "Rudong, Jiangsu (Yangtze delta)"),
    ],
    "TWN": [
        ("TWKHH", "taiwan", {"lng"}, "discharge", "giignl-2026", GIIGNL + "30", "Yung-An, Kaohsiung"),
        ("TWTXG", "taiwan", {"lng"}, "discharge", "giignl-2026", GIIGNL + "30", None),
    ],
    "IND": [
        ("INDAH", "wc-india", {"lng"}, "discharge", "giignl-2026", GIIGNL + "29", None),
        ("INHZA", "wc-india", {"lng"}, "discharge", "giignl-2026", GIIGNL + "29", None),
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
    ],
    "ESP": [
        ("ESBCN", "med", {"lng"}, "discharge", "giignl-2026", GIIGNL + "31", None),
    ],
    "PRT": [
        ("PTSIE", "nw-europe", {"lng"}, "discharge", "giignl-2026", GIIGNL + "31", "Atlantic coast"),
    ],
    "POL": [
        ("PLSWI", "baltic", {"lng"}, "discharge", "giignl-2026", GIIGNL + "31", None),
    ],
    "LTU": [
        ("LTKLJ", "baltic", {"lng"}, "discharge", "giignl-2026", GIIGNL + "31", None),
    ],
    "DEU": [
        ("DEWVN", "nw-europe", {"lng"}, "discharge", "giignl-2026", GIIGNL + "31", None),
        ("DEBRB", "nw-europe", {"lng"}, "discharge", "giignl-2026", GIIGNL + "31", None),
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
    ],
    "BRN": [
        ("BNLUM", "sea", {"lng"}, "load", "wikipedia", LIST, "Brunei LNG, Lumut"),
    ],
    "GNQ": [
        ("GQSSG", "waf", {"lng"}, "load", "wikipedia", LIST, "EG LNG, Bioko island (nearest port: Malabo)"),
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
    "CZE": {"crude": ("ITTRS", "wikipedia", _TAL, "The Transalpine pipeline connects Trieste with the Czech Republic")},
    "HUN": {"crude": ("HROMI", "wikipedia", _ADRIA, "The Adria pipeline runs from Omisalj to Serbia and Hungary")},
    "SRB": {"crude": ("HROMI", "wikipedia", _ADRIA, "The Adria pipeline runs from Omisalj to Serbia and Hungary")},
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
}

# Landlocked countries of the plan's candidate table for which no page stating the port was read.
UNSOURCED = {
    "BLR": "potash by rail to Baltic ports: no page read (ports.py keeps its present Ust-Luga row)",
    "BOL": "Wikipedia (Transport in Bolivia) gives free port privileges in Chile, Argentina and Brazil and the Paraguay river ports, not Arica",
    "PRY": "the Paraguay river is documented (Wikipedia: Paraguay River), the transfer port is not; ports.py keeps Up-River Parana",
    "SRB": "other cargo than crude: the Danube is documented, a seaport is not (Constanta not confirmed)",
    "MDA": "no page read",
    "AFG": "Port of Karachi page mentions Afghanistan only as a historical gateway",
    "ARM": "Poti page does not mention Armenia",
    "LAO": "Transport in Laos names no seaport",
    "MNG": "Transport in Mongolia names no seaport",
    "BWA": "no page read",
    "SWZ": "no page read",
    "LSO": "no page read",
    "SSD": "no page read",
    "KGZ": "no page read",
    "UZB": "Poti Sea Port page read: TRACECA links Constanta and Varna with the Caspian region and Central Asia; it names neither Uzbekistan nor Poti as its outlet",
    "TKM": "Poti Sea Port page read: TRACECA links Constanta and Varna with the Caspian region and Central Asia; it names neither Turkmenistan nor Poti as its outlet",
    "SVK": "Adria oil pipeline page read: the 1968 route to Bratislava was decided, but the page does not say that Slovak crude now comes through Omisalj",
    "TJK": "no page read",
}


def transit(iso3, family):
    """Transit row of a landlocked country for a cargo family, or None."""
    d = TRANSIT.get(iso3)
    if not d:
        return None
    return d.get(family) or d.get("default")
