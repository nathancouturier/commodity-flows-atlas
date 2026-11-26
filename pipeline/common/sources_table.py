"""
Regenerates the sources table of DATA_SOURCES.md from data/sources.json, so the two cannot drift apart.

    python pipeline/common/sources_table.py            # rewrite the table in DATA_SOURCES.md
    python pipeline/common/sources_table.py --check    # exit 1 if DATA_SOURCES.md is out of date

The table sits between the markers <!-- sources:start --> and <!-- sources:end -->; the rest of the file is
written by hand. Fields read from each registry entry: id, name, publisher, url, licence, update, access
(how it is fetched), use (what it feeds) and, when an account or key is needed, key. An entry whose use says "no value is stored or shown"
is one the atlas only links to: the introduction names those entries and does not call their pages free to read.
"""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SOURCES = os.path.join(ROOT, "data", "sources.json")
DOC = os.path.join(ROOT, "DATA_SOURCES.md")
START, END = "<!-- sources:start -->", "<!-- sources:end -->"


# a registry entry whose use says this is a publisher the atlas only links to: nothing of it is fetched, no figure of it is shown
LINK_ONLY_MARK = "no value is stored or shown"


def link_only(sources):
    return [s["id"] for s in sources if LINK_ONLY_MARK in str(s.get("use") or "")]


def cell(text):
    return str(text or "").replace("|", "\\|").replace("\n", " ").strip()


def render(sources):
    keyed = [s for s in sources if s.get("key")]
    linked = link_only(sources)
    # a link-only entry shows no value, so the sentence on what is free to read is about the figures shown, not about every entry
    intro = f"{len(sources)} sources are registered. Every figure shown comes from a source that is free to read."
    if linked:
        ids = ", ".join(f"`{i}`" for i in linked)
        intro += f" The entries that are only linked ({ids}) show no value."
    lines = [
        START,
        "<!-- Generated from data/sources.json by pipeline/common/sources_table.py. Do not edit by hand. -->",
        "",
        intro,
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
        pub = cell(s.get("publisher"))
        # a name that already starts with its publisher does not name it twice in a row
        src = name if pub and cell(s["name"]).startswith(pub) else f"{name}, {pub}"
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
