"""
Update-status bookkeeping for the scheduled data jobs.

    from common.status import record_success, record_failure, get

Writes ``data/_status/updates.json`` (one entry per source) and appends one line per run to
``data/_status/log.jsonl`` (the last 500 lines are kept). Per source:

    last_attempt, last_success (UTC ISO times), consecutive_failures, last_error (short),
    records (rows / observations), data_to (latest date or period covered), state (free-form dict
    for the scripts, e.g. a file hash or the BACI version).

The site may show "data as of" from this file. Files are written atomically.

A script calls ``begin(source)`` when it starts working on a source: the mark goes to a journal outside the data
(``STATUS_JOURNAL``, default in the temporary folder), so that a step stopped before it recorded anything (timed out,
killed, crashed at import) can still be recorded as failed by the workflow (``interrupted``).

CLI (used by the workflows and by .github/actions/finish-data-update):
    python pipeline/common/status.py fail <source> "<message>"
    python pipeline/common/status.py interrupted <since ISO> "<message>" <source>...
        records a failure for each source with no record since <since> that the step had begun and not ended; when the
        step had begun none (it crashed before it started), for each source not marked "?" (a step that runs only when
        it is needed, e.g. "?build-freight")
    python pipeline/common/status.py report          # prints the sources at or above their alert threshold as JSON
    python pipeline/common/status.py merge-driver %O %A %B %P
        git merge driver for updates.json and log.jsonl (see .gitattributes): two jobs that wrote the status files at
        the same time keep every entry and every log line (per source, the entry with the later last attempt wins)
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DIR = os.path.join(ROOT, "data", "_status")
UPDATES = os.path.join(DIR, "updates.json")
LOG = os.path.join(DIR, "log.jsonl")
LOG_KEEP = 500
JOURNAL = os.environ.get("STATUS_JOURNAL") or os.path.join(tempfile.gettempdir(), "data-update-begun.jsonl")
# weekly sources: three runs in a row (three weeks)
ALERT_AFTER = 3
# Sources checked once a month alert after two failed months: one refused page is not a problem (the CEPII site refused
# a cloud runner once), two in a row are. A build step alerts at its first failure: its inputs did not change between
# two runs, so a second run would fail the same way, a month later.
MONTHLY_SOURCES = ("usda-psd", "usgs-mcs", "eia-intl", "baci", "faostat-wna")
BUILD_STEPS = ("build-freight", "build-alerts", "build-commodities", "build-monthly", "build-coverage", "build-profiles",
               "build-prices", "build-changes", "build-market-now")
# The freight market digest is a build step that runs every week on files that change every week: a refusal because a PortWatch
# week was short heals itself with the next week's files, so it alerts after three failed runs, as a weekly source does, not at its
# first (the argument above is for steps whose inputs do not change from one run to the next).
WEEKLY_BUILD_STEPS = ("build-market-now",)
ALERT_AFTER_SOURCE = {**{s: 2 for s in MONTHLY_SOURCES}, **{s: 1 for s in BUILD_STEPS if s not in WEEKLY_BUILD_STEPS}}


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load():
    try:
        with open(UPDATES, encoding="utf-8") as fh:
            doc = json.load(fh)
        if isinstance(doc.get("sources"), dict):
            return doc
    except (OSError, ValueError):
        pass
    return {"sources": {}}


def get(source):
    """Return the stored entry of ``source`` (empty dict when unknown)."""
    return load()["sources"].get(source, {})


def _atomic_write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _log(entry):
    try:
        with open(LOG, encoding="utf-8") as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    except OSError:
        lines = []
    lines.append(json.dumps(entry, separators=(",", ":"), ensure_ascii=False))
    _atomic_write(LOG, "\n".join(lines[-LOG_KEEP:]) + "\n")


def _save(source, entry, outcome, note):
    doc = load()
    doc["sources"][source] = entry
    doc["updated"] = entry["last_attempt"]
    _atomic_write(UPDATES, json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    _log({"t": entry["last_attempt"], "source": source, "outcome": outcome, "note": note,
          "records": entry.get("records"), "data_to": entry.get("data_to"),
          "consecutive_failures": entry["consecutive_failures"]})


def record_success(source, records=None, data_to=None, note="updated", state=None):
    """Record a successful run (``note`` e.g. "updated" or "unchanged"). ``state`` is merged into the entry state."""
    old = get(source)
    now = _now()
    st = dict(old.get("state") or {})
    st.update(state or {})
    entry = {
        "last_attempt": now, "last_success": now, "consecutive_failures": 0, "last_error": None,
        "records": records if records is not None else old.get("records"),
        "data_to": data_to if data_to is not None else old.get("data_to"),
        "state": st,
    }
    _save(source, entry, "ok", note)
    return entry


def record_failure(source, error, previous=None):
    """Record a failed run: increments consecutive_failures, keeps the previous good counts. ``previous`` is an entry
    of ``get()`` taken before a run whose new data had to be taken back: its state and counts are the ones kept."""
    cur = get(source)
    old = cur if previous is None else previous
    msg = " ".join(str(error).split())[:200]
    entry = dict(old)
    entry.update({
        "last_attempt": _now(), "consecutive_failures": int(cur.get("consecutive_failures") or 0) + 1,
        "last_error": msg, "alert_after": ALERT_AFTER_SOURCE.get(source, ALERT_AFTER),
    })
    entry.setdefault("last_success", None)
    entry.setdefault("records", None)
    entry.setdefault("data_to", None)
    entry.setdefault("state", {})
    _save(source, entry, "fail", msg)
    return entry


def _mark(source, done):
    try:
        with open(JOURNAL, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"t": _now(), "source": source, "done": done}) + "\n")
    except OSError:
        pass


def begin(source):
    """Note in the journal that a script started to work on ``source`` (see ``interrupted``). Never raises."""
    _mark(source, False)


def end(source):
    """Note in the journal that a script left ``source`` without recording it (skipped on purpose). Never raises."""
    _mark(source, True)


def begun(since):
    """{source: still open} of the sources marked by ``begin`` at or after ``since`` (ISO time)."""
    out = {}
    try:
        with open(JOURNAL, encoding="utf-8") as fh:
            for ln in fh:
                try:
                    e = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(e, dict) and str(e.get("t", "")) >= since and e.get("source"):
                    out[e["source"]] = not e.get("done")
    except OSError:
        pass
    return out


def interrupted(since, sources, message):
    """Record ``message`` as a failure for the sources of a step that did not finish (timed out, killed, crashed).
    A source recorded since ``since`` keeps its record. Of the others: when the step had begun some source, those it
    had begun and not ended (the ones it was working on); when it had begun none (a crash at import or before the first
    source), every source not marked "?" (a "?source" runs only when needed, so its absence is not a failure).
    Returns the sources recorded as failed."""
    started = begun(since)
    doc = load()["sources"]
    out = []
    for name in sources:
        s = name.lstrip("?")
        if str(doc.get(s, {}).get("last_attempt") or "") >= since:
            continue
        if started:
            if not started.get(s):
                continue  # not reached, or left on purpose: the next run does it
        elif name.startswith("?"):
            continue
        record_failure(s, message)
        out.append(s)
    return out


def merge_updates(a, b):
    """Union of two updates.json documents: per source, the entry with the later last attempt (``b`` on a tie)."""
    out = {"sources": {}}
    for doc in (a, b):
        for k, v in (doc.get("sources") or {}).items():
            cur = out["sources"].get(k)
            if not isinstance(v, dict):
                continue
            if cur is None or str(v.get("last_attempt") or "") >= str(cur.get("last_attempt") or ""):
                out["sources"][k] = v
    ups = [str(d.get("updated")) for d in (a, b) if d.get("updated")]
    if ups:
        out["updated"] = max(ups)
    return out


def merge_log(a, b):
    """Union of two log.jsonl texts: every line once, in time order, the last LOG_KEEP kept."""
    seen, lines = set(), []
    for text in (a, b):
        for ln in text.splitlines():
            if ln.strip() and ln not in seen:
                seen.add(ln)
                lines.append(ln)

    def t(ln):
        try:
            return str(json.loads(ln).get("t") or "")
        except (ValueError, AttributeError):
            return ""
    lines.sort(key=t)  # stable: lines of the same second keep their order
    return "\n".join(lines[-LOG_KEEP:]) + "\n" if lines else ""


def merge_driver(base, ours, theirs, name=""):
    """git merge driver: writes the union of ``ours`` and ``theirs`` into ``ours``; returns 0 (merged) or 1."""
    def read(p):
        try:
            with open(p, encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return ""
    a, b = read(ours), read(theirs)
    try:
        if (name or ours).endswith(".jsonl"):
            text = merge_log(a, b)
        else:
            text = json.dumps(merge_updates(json.loads(a or "{}"), json.loads(b or "{}")), indent=1, sort_keys=True,
                              ensure_ascii=False) + "\n"
    except ValueError:
        return 1
    with open(ours, "w", encoding="utf-8") as fh:
        fh.write(text)
    return 0


def failing(threshold=None):
    """Sources at or above their alert threshold (per-source, default ALERT_AFTER)."""
    out = {}
    for k, v in load()["sources"].items():
        limit = threshold or int(v.get("alert_after") or ALERT_AFTER_SOURCE.get(k, ALERT_AFTER))
        if int(v.get("consecutive_failures") or 0) >= limit:
            out[k] = v
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "fail" and len(sys.argv) >= 4:
        record_failure(sys.argv[2], sys.argv[3])
    elif cmd == "interrupted" and len(sys.argv) >= 5:
        for src in interrupted(sys.argv[2], sys.argv[4:], sys.argv[3]):
            print(f"{src}: recorded as failed ({sys.argv[3]})")
    elif cmd == "merge-driver" and len(sys.argv) >= 5:
        sys.exit(merge_driver(*sys.argv[2:6]))
    elif cmd == "report":
        print(json.dumps({"failing": failing(), "all": sorted(load()["sources"])}))
    else:
        print(__doc__)
