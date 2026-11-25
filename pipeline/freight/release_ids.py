"""
Writes pipeline/freight/released_ids.json: the ids of what the last release published, for the two selections that a change of the data
must not shake: the generated routes (ids that start with "gen-" in data/freight/routes.json) and the main lanes (the lanes of the "main" set in
data/freight/lanes/*.json, by group as "<origin>-<destination>").

    .venv/bin/python -I pipeline/freight/release_ids.py                 # from the files of the working tree, as published
    .venv/bin/python -I pipeline/freight/release_ids.py --ref <commit>  # from the files of a commit (git show <commit>:data/...)

Run it at each release, on the files that are published, and commit the result with the release: the builders read it (generated_routes.py,
build_lanes.py) and keep a released route or lane as long as its corridor or pair still exists in the data, whatever the caps.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(ROOT, "pipeline", "freight", "released_ids.json")


def reader(ref):
    """read(path relative to the repository) -> parsed JSON, from the working tree or from a commit."""
    if ref:
        return lambda rel: json.loads(subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=ROOT, check=True, capture_output=True, text=True).stdout)
    return lambda rel: json.load(open(os.path.join(ROOT, rel), encoding="utf-8"))


def lane_files(ref):
    if ref:
        out = subprocess.run(["git", "ls-tree", "--name-only", f"{ref}:data/freight/lanes/"], cwd=ROOT, check=True, capture_output=True, text=True).stdout
        return sorted(f for f in out.split() if f.endswith(".json"))
    return sorted(f for f in os.listdir(os.path.join(ROOT, "data", "freight", "lanes")) if f.endswith(".json"))


def collect(ref=None):
    read = reader(ref)
    routes = read("data/freight/routes.json")
    gen = sorted(r["id"] for r in routes if r["id"].startswith("gen-"))
    lanes = {}
    for f in lane_files(ref):
        j = read(f"data/freight/lanes/{f}")
        lanes[j["group"]] = sorted(ln["id"].split(":", 1)[1] for ln in j["lanes"] if ln["set"] == "main")  # "o-d": the id is "<group>:<o>-<d>"
    return {"released": ref or "the files of the working tree when the script ran", "generated_routes": gen, "main_lanes": lanes}


def dump(doc):
    """One line per list (a group's lanes, the routes), so that a release changes the lines of the groups it moved."""
    lines = [f' "released": {json.dumps(doc["released"])},', ' "generated_routes": [']
    lines += [f'  {json.dumps(i)}{"," if k < len(doc["generated_routes"]) - 1 else ""}' for k, i in enumerate(doc["generated_routes"])]
    lines += [" ],", ' "main_lanes": {']
    items = sorted(doc["main_lanes"].items())
    lines += [f'  {json.dumps(g)}: {json.dumps(v)}{"," if k < len(items) - 1 else ""}' for k, (g, v) in enumerate(items)]
    return "{\n" + "\n".join(lines) + "\n }\n}\n"


def main(argv):
    ref = argv[argv.index("--ref") + 1] if "--ref" in argv else None
    doc = collect(ref)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(dump(doc))
    print(f"release_ids: {len(doc['generated_routes'])} generated routes, {sum(len(v) for v in doc['main_lanes'].values())} main lanes "
          f"of {len(doc['main_lanes'])} groups written to {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
