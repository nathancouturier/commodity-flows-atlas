"""
Regenerates the sources table of DATA_SOURCES.md from data/sources.json, so the two cannot drift apart.

    python pipeline/common/sources_table.py            # rewrite the table in DATA_SOURCES.md
    python pipeline/common/sources_table.py --check    # exit 1 if DATA_SOURCES.md is out of date

The table sits between the markers <!-- sources:start --> and <!-- sources:end -->; the rest of the file is
written by hand. Fields read from each registry entry: id, name, publisher, url, licence, update, access
(how it is fetched), use (what it feeds) and, when an account or key is needed, key.
"""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SOURCES = os.path.join(ROOT, "data", "sources.json")
DOC = os.path.join(ROOT, "DATA_SOURCES.md")
START, END = "<!-- sources:start -->", "<!-- sources:end -->"


def cell(text):
    return str(text or "").replace("|", "\\|").replace("\n", " ").strip()


def render(sources):
    keyed = [s for s in sources if s.get("key")]
    lines = [
        START,
        "<!-- Generated from data/sources.json by pipeline/common/sources_table.py. Do not edit by hand. -->",
        "",
        f"{len(sources)} sources are registered. Every one is free to read.",
    ]
    if keyed:
        lines.append("")
        lines.append("Accounts and keys:")
        lines += [f"- `{s['id']}`: {s['key']}." for s in keyed]
    else:
        lines += ["", "None needs an account or an API key."]
    lines += ["", "| Id | Source | Licence | Cadence | How it is fetched | Used for |", "|---|---|---|---|---|---|"]
    for s in sources:
        name = f"[{cell(s['name'])}]({s['url']})" if s.get("url") else cell(s["name"])
        src = f"{name}, {cell(s.get('publisher'))}"
        lines.append(
            f"| `{s['id']}` | {src} | {cell(s.get('licence'))} | {cell(s.get('update'))} | "
            f"{cell(s.get('access'))} | {cell(s.get('use'))} |"
        )
    lines.append(END)
    return "\n".join(lines)


def main():
    with open(SOURCES, encoding="utf-8") as fh:
        sources = json.load(fh)
    with open(DOC, encoding="utf-8") as fh:
        doc = fh.read()
    i, j = doc.find(START), doc.find(END)
    if i < 0 or j < i:
        sys.exit(f"markers {START} / {END} not found in DATA_SOURCES.md")
    new = doc[:i] + render(sources) + doc[j + len(END):]
    if "--check" in sys.argv:
        if new != doc:
            sys.exit("DATA_SOURCES.md is out of date: run python pipeline/common/sources_table.py")
        print("DATA_SOURCES.md is up to date")
        return
    if new != doc:
        with open(DOC, "w", encoding="utf-8") as fh:
            fh.write(new)
    print(f"DATA_SOURCES.md: {len(sources)} sources")


if __name__ == "__main__":
    main()
