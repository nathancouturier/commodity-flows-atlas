"""
Update-status bookkeeping for the scheduled data jobs.

    from common.status import record_success, record_failure, get

Writes ``data/_status/updates.json`` (one entry per source) and appends one line per run to
``data/_status/log.jsonl`` (the last 500 lines are kept). Per source:

    last_attempt, last_success (UTC ISO times), consecutive_failures, last_error (short),
    records (rows / observations), data_to (latest date or period covered), state (free-form dict
    for the scripts, e.g. a file hash or the BACI version).

The site may show "data as of" from this file. Files are written atomically.

CLI (used by the workflows after a discarded run):
    python pipeline/common/status.py fail <source> "<message>"
    python pipeline/common/status.py report          # prints sources failing >= 3 runs as JSON
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
ALERT_AFTER = 3
# Sources updated once a year but checked every month alert later: a blocked check page for a few
# months is not a data problem (e.g. the CEPII site sometimes refuses cloud runners).
ALERT_AFTER_SOURCE = {"baci": 6, "faostat-wna": 6}


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


def record_failure(source, error):
    """Record a failed run: increments consecutive_failures, keeps the previous good counts."""
    old = get(source)
    msg = " ".join(str(error).split())[:200]
    entry = dict(old)
    entry.update({
        "last_attempt": _now(), "consecutive_failures": int(old.get("consecutive_failures") or 0) + 1,
        "last_error": msg, "alert_after": ALERT_AFTER_SOURCE.get(source, ALERT_AFTER),
    })
    entry.setdefault("last_success", None)
    entry.setdefault("records", None)
    entry.setdefault("data_to", None)
    entry.setdefault("state", {})
    _save(source, entry, "fail", msg)
    return entry


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
    elif cmd == "report":
        print(json.dumps({"failing": failing(), "all": sorted(load()["sources"])}))
    else:
        print(__doc__)
