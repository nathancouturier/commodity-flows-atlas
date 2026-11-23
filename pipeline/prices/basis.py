"""
What a World Bank Pink Sheet price measures, and when that changed, read from the workbook's own
"Description" sheet (nothing is typed by hand here except which description row belongs to which column).

    descs, notes = read_description(rows_of_the_Description_sheet)
    text = find(descs, "Soybeans,")                # the one row that starts with this text
    clauses = parse_clauses(text)                   # [{"text", "from", "to", "before"}]
    basis, breaks = basis_and_breaks(clauses, first_month="1960-01")

A description row lists the basis of a series from the newest period to the oldest, separated by ";" or by a new
sentence ("from January 2025, U.S. Soybeans, FOB U.S. Gulf; January 2021-December 2024, ... CIF Rotterdam;
previously ..."). Each clause that opens with a date starts a period; the date is a basis change unless it is the
first month of the data. "prior to <date>" clauses name the basis that ended on that date, "<month> <year>
backwards" a basis that ended in that month. Dates are months ("YYYY-MM"); a bare year means January.
"""
import re

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
MON = "|".join(MONTHS)
YEAR = r"(?:19|20)\d{2}"
# "2008 (December)" -> "December 2008"; "February 13, 2017" -> "February 2017"
_YM_PAREN = re.compile(rf"\b({YEAR}) \(({MON})\)")
_MDY = re.compile(rf"\b({MON}) \d{{1,2}}, ({YEAR})")
# a new sentence starts after a word of at least four letters ("price. From 2015"), never after "f.o.b."
_SPLIT = re.compile(r";|(?<=[a-z]{4})\. (?=[A-Z0-9])")

_RANGE_MM = re.compile(rf"\b(?P<m1>{MON})\s*[-–]\s*(?P<m2>{MON}) (?P<y>{YEAR})\b")
_RANGE = re.compile(
    rf"\b(?:(?P<m1>{MON}) )?(?P<y1>{YEAR})\s*(?:to|[-–])\s*(?:(?P<m2>{MON}) )?(?P<y2>{YEAR}|\d{{2}}\b|present)")
_FROM = re.compile(rf"\b(?:[Ff]rom|beginning|since)\s+(?:(?P<m>{MON}) )?(?P<y>{YEAR})\b(?: onwards)?")
_PRIOR = re.compile(rf"\bprior to (?:(?P<m>{MON}) )?(?P<y>{YEAR})\b")
_BACK = re.compile(rf"\b(?P<m>{MON}) (?P<y>{YEAR}) backwards\b")
_TO_AFTER_FROM = re.compile(rf"\s*to (?:(?P<m>{MON}) )?(?P<y>{YEAR})\b")


def clean(text):
    return re.sub(r"\s+", " ", str(text).replace(" ", " ")).strip()


def ym(year, month=None):
    return f"{int(year):04d}-{(MONTHS.index(month) + 1 if month else 1):02d}"


def ym_end(year, month=None):
    return f"{int(year):04d}-{(MONTHS.index(month) + 1 if month else 12):02d}"


def add_month(s, n=1):
    y, m = int(s[:4]), int(s[5:7])
    k = y * 12 + m - 1 + n
    return f"{k // 12:04d}-{k % 12 + 1:02d}"


def read_description(rows):
    """(descriptions, notes) of the Description sheet. A description row is (marker, text, sources); a note is a
    long text alone in the first column; one-cell rows such as "Energy" are headings."""
    descs, notes = [], []
    for r in rows:
        r = list(r) + [None] * 3
        a, b = r[0], r[1]
        has_sources = any(isinstance(c, str) and c.strip() for c in r[2:])
        if isinstance(b, str) and has_sources and len(clean(b)) > 12:
            descs.append(clean(b))
        elif isinstance(b, str) and len(clean(b)) > 40:
            notes.append(clean(b))
        elif isinstance(a, str) and b is None and len(clean(a)) > 40:
            notes.append(clean(a))
    return descs, notes


def find(descs, prefix):
    """The description row that starts with `prefix`; fails when there is none or more than one."""
    hit = [d for d in descs if d.startswith(prefix)]
    if len(hit) != 1:
        raise LookupError(f"{len(hit)} description rows start with {prefix!r}")
    return hit[0]


def _year(y1, y2):
    return int(y1[:2] + y2) if len(y2) == 2 else int(y2)


def _period(clause):
    """(start, end, kind, span) of the first period a clause names, or None. kind: 'from' (the basis in the clause
    starts at `start`), 'prior' (it ended just before `start`), 'back' (it ended in `start`)."""
    found = []
    for rx, kind in ((_RANGE_MM, "range-mm"), (_RANGE, "range"), (_FROM, "from"), (_PRIOR, "prior"), (_BACK, "back")):
        m = rx.search(clause)
        if m:
            found.append((m.start(), -(m.end() - m.start()), kind, m))
    if not found:
        return None
    _, _, kind, m = min(found, key=lambda f: (f[0], f[1]))
    g = m.groupdict()
    if kind == "range-mm":
        return ym(g["y"], g["m1"]), ym_end(g["y"], g["m2"]), "from", m.span()
    if kind == "range":
        end = None if g["y2"] == "present" else ym_end(_year(g["y1"], g["y2"]) if len(g["y2"]) == 2 else g["y2"], g["m2"])
        return ym(g["y1"], g["m1"]), end, "from", m.span()
    if kind == "from":
        end, stop = None, m.end()
        t = _TO_AFTER_FROM.match(clause, m.end())
        if t:
            end, stop = ym_end(t.group("y"), t.group("m")), t.end()
        return ym(g["y"], g["m"]), end, "from", (m.start(), stop)
    if kind == "prior":
        return ym(g["y"], g["m"]), None, "prior", m.span()
    return ym(g["y"], g["m"]), None, "back", m.span()


def _strip(clause, span):
    """The clause without its period phrase and the connecting words around it ("during years", "for years", "from")."""
    a, b = span
    head = re.sub(r"(?:\b(?:during|for|From|from)\b\s*(?:the )?(?:years?|period)?\s*)+$", "", clause[:a])
    tail = re.sub(r"^\s*(?:onwards|backwards)\b", "", clause[b:])
    t = clean(head + " " + tail)
    t = re.sub(r",?\s*\bbeginning\b(?: (?:%s))? (?:%s)\b" % (MON, YEAR), "", t)
    t = re.sub(r"^(?:years?|refer to|Grade)\s+", "", t)
    t = re.sub(r"\s+([,;)])", r"\1", t)
    t = re.sub(r"(?:,\s*){2,}", ", ", t)
    return t.strip(" ,.")


def parse_clauses(text):
    """The clauses of a description row, newest basis first. Each: text (without its dates), from, to (months or
    None), before (True for a "prior to" or "backwards" clause: the text is the basis that ended at `from`)."""
    text = _MDY.sub(r"\1 \2", _YM_PAREN.sub(r"\2 \1", clean(text)))
    out = []
    for raw in _SPLIT.split(text):
        raw = re.sub(r"^\s*previously,?\s+", "", clean(raw))  # "previously, f.o.b. Black Sea": the clause is what it was
        if not raw:
            continue
        p = _period(raw)
        if p is None:
            out.append({"text": raw.strip(" ,."), "from": None, "to": None, "before": False})
            continue
        start, end, kind, span = p
        body = _strip(raw, span)
        if kind == "back":
            start = add_month(start)  # "June 2020 backwards": June 2020 is the last month of that basis
        out.append({"text": body, "from": start, "to": end, "before": kind in ("prior", "back")})
    return out


def basis_and_breaks(clauses, first_month, last_month=None):
    """(current basis text, list of breaks). A break is {"at": "YYYY-MM", "now": text, "before": text}: the basis
    `now` starts at `at`, replacing `before`. Dates at or before the first month of the data are not breaks."""
    if not clauses:
        return "", []
    plain = [c for c in clauses if not c["before"]]
    current = next((c for c in plain if c["to"] is None), plain[0] if plain else clauses[0])
    breaks = {}
    for i, c in enumerate(clauses):
        if c["from"] is None or c["from"] <= first_month or (last_month and c["from"] > last_month):
            continue
        if c["before"]:
            # the basis ended here: what replaced it is the main (first) clause, or the clause just before in the list
            now = plain[0]["text"] if plain else ""
            b = breaks.setdefault(c["from"], {"at": c["from"], "now": now, "before": c["text"]})
            if not b["before"]:
                b["before"] = c["text"]
            continue
        nxt = next((d for d in clauses[i + 1:] if not d["before"] and d["from"] != c["from"]), None)
        before = nxt["text"] if nxt else ""
        breaks[c["from"]] = {"at": c["from"], "now": c["text"], "before": before, **({"to": c["to"]} if c["to"] else {})}
    return current["text"], [breaks[k] for k in sorted(breaks)]


# ---------------------------------------------------------------- estimates marked by the source

def _months(token_list):
    """["June to November 2022", "March", "April", "June to September", "December 2023", "January-May 2024"]
    -> [("2022-06", "2022-11"), ("2023-03", "2023-03"), ...]: a month group without a year takes the next year named."""
    out, pending = [], []
    rx = re.compile(rf"^(?P<m1>{MON})(?:\s*(?:to|[-–])\s*(?P<m2>{MON}))?(?: (?P<y>{YEAR}))?$")
    for tok in token_list:
        m = rx.match(tok.strip())
        if not m:
            continue
        g = m.groupdict()
        pending.append((g["m1"], g["m2"] or g["m1"]))
        if g["y"]:
            out += [(ym(g["y"], a), ym(g["y"], b)) for a, b in pending]
            pending = []
    return out


def merge_ranges(ranges):
    out = []
    for a, b in sorted(ranges):
        if out and a <= add_month(out[-1][1]):
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def estimate_ranges(label, descs, notes, last_month):
    """Months the source itself marks as estimates, for the series whose description starts with `label`:
    "recent two months' averages are estimates" (the newest two months) and a note such as
    "Coal (South Africa), June to November 2022, March, April ... 2024 are estimates based on similar benchmarks"."""
    out = []
    for d in descs:
        if d.startswith(label):
            m = re.search(r"recent (two|three|four) months'? averages are estimates", d)
            if m and last_month:
                n = {"two": 2, "three": 3, "four": 4}[m.group(1)]
                out.append((add_month(last_month, 1 - n), last_month))
    for note in notes:
        if not note.startswith(label):
            continue
        m = re.search(r"^(?P<head>.*?) are estimates", note)
        if not m:
            continue
        head = m.group("head")[len(label):].lstrip(" ,)")
        tokens = [t for t in re.split(r",\s*(?:and\s+)?|\s+and\s+", head) if t.strip()]
        out += _months(tokens)
    return merge_ranges(out)
