"""
Build data/freight/market-now.json: the digest of the freight market page, from the weekly chokepoint series.

    python pipeline/freight/build_market_now.py

For tankers and for dry bulk carriers, the five passages with the most estimated cargo of that ship type, with the vessels
that crossed each of them and PortWatch's estimated cargo over the last four complete weeks (28 days) and over the same
four weeks a year earlier (364 days back, the window of the alert banners), METHODOLOGY.md. Everything is arithmetic on
data/freight/portwatch/<passage>.json (IMF PortWatch, written by build_portwatch.py): no download, no daily table, no
raw/ folder, and nothing is read from chokepoints.json (the page takes the atlas's names from it).

  * Weeks are taken by date. A weekly file gives its first week (``start``, a Monday) and one value a week; the date of
    each week is rebuilt from it, and a file whose length does not match its dates (a week that went missing shifts every
    later value by one week) is refused.
  * ``to`` is the Sunday that ends the last complete week common to all the files (the last week of a file whose last day
    is not a Sunday is not complete and is left out). The window is the four weeks that end on ``to``; the year-earlier
    window ends 364 days before it.
  * Vessels over the window: the weekly means (vessels a day) times 7, summed, rounded to whole vessels; cargo: the same
    on PortWatch's estimate in Mt a day, three significant figures. Decimal arithmetic, half up: a rebuild never differs
    by a binary rounding.
  * The change in per cent (``pct`` of the transits, ``mt.pct`` of the cargo) is computed here, on those sums before any
    rounding: (now - year earlier) / year earlier, one decimal, a half rounded away from zero; ``null`` when the year-earlier
    sum is zero; -99.9 for a fall that one decimal would round to -100.0 while something is left. The page prints it and
    computes none.
  * The five passages: the largest estimated cargo of the ship type over the 52 weeks that end with the year-earlier
    window. They are ranked on that sum before rounding (only an exact tie of the sums goes by id); ``rankMt`` is the sum
    to three significant figures, so two passages can show the same figure. Ranked a year back so that a collapse this
    year does not remove the passage that explains the market. The rule is the atlas's, not PortWatch's.
  * A file that starts after the first of the 52 ranking weeks (a passage mapped lately) cannot be ranked: it is left out of
    the ranking, with a line in the output, and the digest is built from the others.

It never fails the job: a series that does not hold together (wherever it would rank), fewer than five series that can be
ranked, a date earlier than the stored one, a value that is not a finite number or is negative: the previous file is kept,
the failure is recorded in data/_status/updates.json (source ``build-market-now``) and the exit code is 0. A series that
ends later than ``to`` holds the date back without stopping anything: the output and the note of the status record say how
many, and the date they end on. The file is not rewritten when its content is the same, so that a week without new data
makes no commit.
"""
import glob
import json
import os
import sys
import traceback
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Context, Decimal
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

from common import status  # noqa: E402

SOURCE = "build-market-now"
FREIGHT = os.path.join(ROOT, "data", "freight")
SERIES = os.path.join(FREIGHT, "portwatch")
OUT = os.path.join(FREIGHT, "market-now.json")

TYPES = ("tanker", "dry")   # the ship types of the weekly files (``tanker``, ``dry``; ``vol`` holds the estimated cargo)
PASSAGES = 5                # rows per type
WEEKS = 4                   # the window: four complete weeks, 28 days
YEAR_BACK = 52              # weeks between the window and the same window a year earlier (364 days)
RANK_WEEKS = 52             # the weeks that decide which passages are shown, ending with the year-earlier window
# the words of the status board and of the alert banners for their own 28-day figures (BoardView.tsx, ui.tsx)
UNIT = "vessel transits in 28 days"
MT_UNIT = "Mt of estimated cargo in 28 days"

SIG3 = Context(prec=3, rounding=ROUND_HALF_UP)


def number(v, where):
    """``v`` as a Decimal; refuses what is not a finite number (a string, null, NaN, infinity, a boolean) or is negative."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{where}: {v!r} is not a number")
    d = Decimal(repr(v))
    if not d.is_finite():
        raise ValueError(f"{where}: {v!r} is not a finite number")
    if d < 0:
        raise ValueError(f"{where}: {v!r} is negative")
    return d


def plain(d):
    """A Decimal as the JSON number to write: a whole number as an integer, otherwise as it reads."""
    d = d.normalize()
    return int(d) if d == d.to_integral_value() else float(d)


def sig3(d):
    return plain(SIG3.create_decimal(d))


def pct(now, ago):
    """The change from ``ago`` to ``now`` (Decimal sums, not rounded) in per cent, one decimal, a half rounded away from zero, as a float;
    None when ``ago`` is zero. A fall that would round to -100.0 while ``now`` is not zero is -99.9."""
    if ago == 0:
        return None
    tenths = (Fraction(now) - Fraction(ago)) * 1000 / Fraction(ago)
    r = int(abs(tenths) + Fraction(1, 2))          # a positive number: the integer part is the floor
    r = -r if tenths < 0 else r
    if r == -1000 and now != 0:
        r = -999
    return r / 10


class Series:
    """One weekly file, read and checked; ``weeks`` are indexed by the date their week ends (a Sunday)."""

    def __init__(self, path):
        self.id = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        at = f"{self.id}.json"
        if not isinstance(doc, dict) or doc.get("id") != self.id:
            raise ValueError(f"{at}: not the series of {self.id}")
        try:
            self.start, last_day = date.fromisoformat(doc["start"]), date.fromisoformat(doc["y"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"{at}: start and y must be dates") from None
        if self.start.weekday() != 0:
            raise ValueError(f"{at}: the first week starts on {self.start}, which is not a Monday")
        vol = doc.get("vol")
        if not isinstance(vol, dict):
            raise ValueError(f"{at}: no vol block (estimated cargo)")
        raw = {(k, False): doc.get(k) for k in TYPES} | {(k, True): vol.get(k) for k in TYPES}
        for (k, v), arr in raw.items():
            if not isinstance(arr, list):
                raise ValueError(f"{at}: no {'vol.' if v else ''}{k} list")
        n = {len(a) for a in raw.values()}
        if len(n) != 1:
            raise ValueError(f"{at}: the lists have different lengths ({sorted(n)})")
        self.n = n.pop()
        # the weeks the dates call for: the complete ones, and one more when the last day does not end a week
        days = (last_day - self.start).days + 1
        if days < 7:
            raise ValueError(f"{at}: y {last_day} is before the end of the first week")
        complete = days // 7
        if self.n != complete + (1 if days % 7 else 0):
            raise ValueError(f"{at}: {self.n} weeks from {self.start}, but the dates (to {last_day}) make {complete + (1 if days % 7 else 0)}: "
                             f"a week is missing or extra, and the values would not be those of their dates")
        self.last_week_end = self.start + timedelta(days=7 * complete - 1)
        self.cnt = {k: [number(x, f"{at} {k}[{i}]") for i, x in enumerate(raw[(k, False)])] for k in TYPES}
        self.cargo = {k: [number(x, f"{at} vol.{k}[{i}]") for i, x in enumerate(raw[(k, True)])] for k in TYPES}

    def can_rank(self, ago_to):
        """Whether the file holds the ``RANK_WEEKS`` weeks that end on ``ago_to``."""
        return self.start <= ago_to - timedelta(days=7 * RANK_WEEKS - 1)

    def index(self, week_end):
        """Position of the week that ends on ``week_end``; refuses a date outside the complete weeks of the file."""
        days = (week_end - self.start).days - 6
        if days < 0 or days % 7 or days // 7 >= (self.last_week_end - self.start).days // 7 + 1:
            raise ValueError(f"{self.id}.json: no week ends on {week_end}")
        return days // 7

    def over(self, values, end, weeks):
        """The weekly means (a day) of the ``weeks`` weeks that end with ``end``, times 7, summed: a Decimal."""
        return sum((values[self.index(end - timedelta(days=7 * k))] for k in range(weeks)), Decimal(0)) * 7


class Notes:
    """What a build says without refusing: the series left out of the ranking and the series that end later than ``to``."""

    def __init__(self):
        self.left_out = []     # (id, first week) of a file that starts after the first ranking week
        self.ahead = None      # (number of series, the latest date they end on, ids of the series that end on ``to``, ``to``)

    def lines(self):
        out = [f"left out of the ranking: {i}.json starts on {start}, after the first of the {RANK_WEEKS} ranking weeks" for i, start in self.left_out]
        if self.ahead:
            n, latest, holding, to = self.ahead
            out.append(f"{n} series end later than the digest, on {latest}; the digest ends on {to}, the last complete week of {', '.join(holding[:3])}"
                       + (f" and {len(holding) - 3} more" if len(holding) > 3 else ""))
        return out

    def note(self):
        """The same, short, for the note of the status record."""
        out = []
        if self.left_out:
            out.append(f"{len(self.left_out)} series left out of the ranking ({', '.join(i for i, _ in self.left_out[:3])})")
        if self.ahead:
            out.append(f"{self.ahead[0]} series end later than {self.ahead[3]} (on {self.ahead[1]})")
        return "".join("; " + x for x in out)


def build(series_dir=SERIES, notes=None):
    """The digest of the weekly files of ``series_dir``: (document, number of rows). Raises ValueError when a file does not hold
    together or a window is missing; ``notes`` (a Notes) is filled with what the build leaves out or holds back."""
    notes = notes if notes is not None else Notes()
    paths = sorted(glob.glob(os.path.join(series_dir, "*.json")))
    series = [Series(p) for p in paths]      # every file is read and checked, whether it can be ranked or not
    if len(series) < PASSAGES:
        raise ValueError(f"{len(series)} weekly series, at least {PASSAGES} are needed to name {PASSAGES} passages")
    to = min(s.last_week_end for s in series)
    ago_to = to - timedelta(days=7 * YEAR_BACK)
    later = [s for s in series if s.last_week_end > to]
    if later:
        notes.ahead = (len(later), str(max(s.last_week_end for s in later)), [s.id for s in series if s.last_week_end == to], str(to))
    ranking = [s for s in series if s.can_rank(ago_to)]
    notes.left_out = [(s.id, str(s.start)) for s in series if not s.can_rank(ago_to)]
    if len(ranking) < PASSAGES:
        raise ValueError(f"{len(ranking)} of {len(series)} weekly series reach back {RANK_WEEKS} weeks before {ago_to}, at least {PASSAGES} are needed to name {PASSAGES} passages")
    out = {"s": "portwatch", "to": str(to), "yearAgoTo": str(ago_to), "weeks": WEEKS, "days": 7 * WEEKS, "rankWeeks": RANK_WEEKS,
           "unit": UNIT, "mtUnit": MT_UNIT, "types": {}}
    for t in TYPES:
        ranked = sorted(((s.over(s.cargo[t], ago_to, RANK_WEEKS), s.id, s) for s in ranking), key=lambda r: (-r[0], r[1]))
        rows = []
        for rank, pid, s in ranked[:PASSAGES]:
            now, ago = s.over(s.cnt[t], to, WEEKS), s.over(s.cnt[t], ago_to, WEEKS)
            mnow, mago = s.over(s.cargo[t], to, WEEKS), s.over(s.cargo[t], ago_to, WEEKS)
            rows.append({
                "id": pid,
                "now": int(now.to_integral_value(ROUND_HALF_UP)),
                "ago": int(ago.to_integral_value(ROUND_HALF_UP)),
                "pct": pct(now, ago),
                "mt": {"now": sig3(mnow), "ago": sig3(mago), "pct": pct(mnow, mago)},
                "rankMt": sig3(rank),
            })
        out["types"][t] = rows
    return out, sum(len(r) for r in out["types"].values())


def text_of(doc):
    return json.dumps(doc, separators=(",", ":"), ensure_ascii=False) + "\n"


def stored_to(path):
    """The ``to`` of the file published now; None when there is none or it cannot be read."""
    try:
        with open(path, encoding="utf-8") as fh:
            return date.fromisoformat(json.load(fh)["to"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def write_files(series_dir=SERIES, out=OUT, notes=None):
    """Build and write the digest; returns (document, rows, changed). The file is replaced only when its content differs."""
    notes = notes if notes is not None else Notes()
    doc, rows = build(series_dir, notes)
    before = stored_to(out)
    if before is not None and date.fromisoformat(doc["to"]) < before:
        raise ValueError(f"the new digest ends on {doc['to']}, earlier than the one published ({before})"
                         + (f"; {notes.ahead[0]} series end later, on {notes.ahead[1]}: the earliest holds it back" if notes.ahead else ""))
    text = text_of(doc)
    try:
        with open(out, encoding="utf-8") as fh:
            if fh.read() == text:
                return doc, rows, False
    except OSError:
        pass
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, out)
    return doc, rows, True


def main(series_dir=SERIES, out=OUT):
    """Weekly job: record the outcome in the status file and never fail."""
    notes = Notes()
    try:
        doc, rows, changed = write_files(series_dir, out, notes)
        status.record_success(SOURCE, records=rows, data_to=doc["to"], note=("updated" if changed else "unchanged") + notes.note())
        print(f"market digest: {rows} rows, four weeks to {doc['to']}" + ("" if changed else " (unchanged)"))
    except Exception as e:  # noqa: BLE001
        if not isinstance(e, (ValueError, KeyError, OSError)):
            traceback.print_exc()
        status.record_failure(SOURCE, f"{e.__class__.__name__}: {e}")
        print("failed, previous file kept:", e)
    for line in notes.lines():
        print(line)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
