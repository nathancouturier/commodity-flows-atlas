"""
Checks of the downloaded inputs before they replace the previous files in raw/ (used by pipeline/annual/update_annual.py).

A download can have the right type and size and still miss what the builders read: a renamed column, a header that
gained a trailing space or a footnote asterisk, a USDA commodity or an EIA series that is no longer in the file. The
builders would then drop a country or a commodity without a word. Each check raises ``ValueError`` with the names of
what is missing, so that the previous good file is kept and the failure is recorded in the status file.

Headers are compared without the spaces and asterisks a publisher decorates them with; when the file's own header
differs from the normalised one only by that decoration, the header line is rewritten, so the builders, which read
the columns by name, find them.
"""
import ast
import csv
import io
import os
import re
import shutil
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# USDA PSD (psd_alldata.csv): the columns the builders read (build_commodities.py, trade/checks.py), the commodities
# and the attributes of the commodity pages. A commodity or attribute missing from a new file fails the download.
PSD_COLUMNS = ["Commodity_Code", "Commodity_Description", "Country_Name", "Market_Year", "Calendar_Year", "Month",
               "Attribute_Description", "Unit_Description", "Value"]
PSD_COMMODITIES = ["Wheat", "Corn", "Rice, Milled", "Oilseed, Soybean", "Meal, Soybean", "Oil, Soybean", "Oilseed, Rapeseed",
                   "Oil, Palm", "Sugar, Centrifugal", "Coffee, Green", "Cotton"]
PSD_ATTRIBUTES = ["Production", "Exports", "Imports", "Domestic Consumption", "Beginning Stocks", "Ending Stocks"]

# USGS Mineral Commodity Summaries data release (MCS<year>_Commodities_Data.csv): the columns build_commodities.py,
# metals.py and trade/checks.py read
USGS_COLUMNS = ["Section", "Commodity", "Country", "Statistics", "Statistics_detail", "Unit", "Year", "Value"]

# EIA International (INTL.txt): the annual series families build_commodities.py reads, taken from its own list (the
# ``NEED`` set of its EIA reader), so that the check never drifts from the builder
BUILDER = os.path.join(ROOT, "pipeline", "commodities", "build_commodities.py")
EIA_SERIES = re.compile(r'"series_id":"INTL\.(\d+-\d+)-[A-Z0-9]+-([A-Z0-9]+)\.A"')


def norm_header(h):
    """A column name without the spaces and asterisks around or inside it ("Urea **  " -> "Urea")."""
    return re.sub(r"\s+", " ", str(h).replace("*", " ")).strip()


def missing(found, required):
    """The names of ``required`` that are not in ``found``, both compared normalised."""
    have = {norm_header(x) for x in found}
    return [r for r in required if norm_header(r) not in have]


def csv_header(path, required, encoding="utf-8"):
    """Check that the CSV at ``path`` has every column of ``required`` (normalised); rewrite its header line when the
    file decorates a name with spaces or asterisks. Returns the normalised header; raises ValueError."""
    with open(path, encoding=encoding, newline="") as fh:
        first = fh.readline()
    head = next(csv.reader([first]), [])
    lost = missing(head, required)
    if lost:
        raise ValueError(f"column{'s' if len(lost) > 1 else ''} missing: {', '.join(lost)}")
    clean = [norm_header(h) for h in head]
    if clean != head:
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\r\n" if first.endswith("\r\n") else "\n").writerow(clean)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
        with open(path, encoding=encoding, newline="") as src, os.fdopen(fd, "w", encoding=encoding, newline="") as dst:
            src.readline()
            dst.write(buf.getvalue())
            shutil.copyfileobj(src, dst, 1 << 20)
        os.replace(tmp, path)
    return clean


def psd_content(df):
    """Raise ValueError when a commodity or an attribute the pages read is not in the PSD table ``df``."""
    lost = [c for c in PSD_COMMODITIES if c not in set(df["Commodity_Description"].astype(str).str.strip())]
    lost += [a for a in PSD_ATTRIBUTES if a not in set(df["Attribute_Description"].astype(str).str.strip())]
    if lost:
        raise ValueError(f"expected PSD commodities or attributes missing: {', '.join(lost)}")


def eia_expected(builder=BUILDER):
    """{(family, unit)} of the annual EIA series the builder reads, read from the ``NEED`` set of its source."""
    with open(builder, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "NEED" for t in node.targets):
            return set(ast.literal_eval(node.value))
    raise ValueError("the EIA series list (NEED) was not found in build_commodities.py")


def eia_found(lines):
    """{(family, unit)} of the annual series present in the lines of INTL.txt."""
    out = set()
    for line in lines:
        m = EIA_SERIES.search(line[:80])
        if m:
            out.add((m.group(1), m.group(2)))
    return out


def eia_content(found, expected=None):
    """Raise ValueError when an expected EIA series family has no annual series in the file."""
    lost = sorted((expected if expected is not None else eia_expected()) - found)
    if lost:
        raise ValueError("expected EIA series missing: " + ", ".join(f"INTL.{f}-*-{u}.A" for f, u in lost[:8])
                         + (f" and {len(lost) - 8} more" if len(lost) > 8 else ""))
