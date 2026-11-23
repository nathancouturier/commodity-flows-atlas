"""
Release watcher of the pages the atlas reads by hand once a year (pipeline/common/release_watch.json): a new edition
of these pages is otherwise noticed by nobody.

For each page, one request through common/fetch.py: rule "header" compares the page's Last-Modified (or ETag) header
with the value recorded in ``known``; rule "text" compares the first match of ``pattern`` in the page (its "Last
updated" date) with ``known``. The value is recorded by hand when the figures are updated, so the job writes nothing.

    python pipeline/common/watch_releases.py      prints {"changed": {id: {...}}, "same": [ids], "errors": {id: msg}}

Run monthly by .github/workflows/watch-releases.yml, which opens one "New release available: <id>" issue per changed
page, with its tasks, and closes it once ``known`` is updated. Exits 0.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from common import fetch  # noqa: E402

WATCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "release_watch.json")


def current(entry, get_text=None, head=None):
    """The value of the page now (a date or a header), or raise fetch.FetchError / ValueError."""
    if entry["rule"] == "header":
        h = (head or fetch.head)(entry["url"])
        value = h.get("Last-Modified") or h.get("ETag")
        if not value:
            raise ValueError("the page sends neither Last-Modified nor ETag")
        return value
    text = (get_text or fetch.get_text)(entry["url"])
    m = re.search(entry["pattern"], text)
    if not m:
        raise ValueError("the update date was not found on the page (its layout changed?)")
    return m.group(1)


def check(entries=None, get_text=None, head=None):
    if entries is None:
        with open(WATCH, encoding="utf-8") as fh:
            entries = json.load(fh)
    out = {"changed": {}, "same": [], "errors": {}}
    for e in entries:
        try:
            now = current(e, get_text, head)
        except (fetch.FetchError, ValueError) as err:
            out["errors"][e["id"]] = str(err)[:200]
            continue
        if now != e["known"]:
            out["changed"][e["id"]] = {"name": e["name"], "url": e["url"], "known": e["known"], "now": now,
                                       "todo": e.get("todo", []), "note": e.get("note", "")}
        else:
            out["same"].append(e["id"])
    return out


if __name__ == "__main__":
    print(json.dumps(check(), indent=1))
