"""
Builds the companies files the site reads from the hand-curated source files of this folder.

    python pipeline/companies/build_companies.py            # write the published files
    python pipeline/companies/build_companies.py --check    # exit 1 if a published file is out of date

Sources (one JSON object per file, keyed by commodity id, or by shipping segment for shipping.json):
  energy.json, metals.json, agri.json  ->  data/commodities/companies.json
  shipping.json                        ->  data/freight/shipping-companies.json (written once it holds an entry)

Nobody edits the published files by hand. The schema of an entry is in README.md of this folder.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FAMILIES = ("energy", "metals", "agri")
OUT = os.path.join(ROOT, "data", "commodities", "companies.json")
OUT_SHIPPING = os.path.join(ROOT, "data", "freight", "shipping-companies.json")
# the order of the commodities in the published file (new ids follow, in the order of the source files)
ORDER = ["crude-oil", "refined-products", "lng", "natural-gas", "thermal-coal", "met-coal", "iron-ore", "copper", "aluminium",
         "bauxite", "nickel", "cobalt", "lithium", "zinc", "gold", "pgm", "uranium", "rare-earths", "steel", "potash",
         "phosphate", "urea", "wheat", "corn", "soybeans", "soymeal", "soyoil", "rapeseed", "rice", "sugar", "coffee",
         "cocoa", "cotton", "palm-oil", "lpg", "tin", "lead", "silver", "manganese"]


def load(name):
    with open(os.path.join(HERE, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def merged():
    out, seen = {}, {}
    for fam in FAMILIES:
        for k, v in load(fam).items():
            if k in seen:
                sys.exit(f"{k} is in {seen[k]}.json and in {fam}.json")
            seen[k] = fam
            out[k] = v
    return {k: out[k] for k in ORDER if k in out} | {k: v for k, v in out.items() if k not in ORDER}


def dump(obj):
    return json.dumps(obj, indent=1, ensure_ascii=False) + "\n"


def main():
    targets = [(OUT, dump(merged()))]
    shipping = load("shipping")
    if shipping:
        targets.append((OUT_SHIPPING, dump(shipping)))
    stale = []
    for path, text in targets:
        old = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if old != text:
            stale.append(os.path.relpath(path, ROOT))
            if "--check" not in sys.argv:
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
    if "--check" in sys.argv:
        if stale:
            print("out of date: " + ", ".join(stale) + " (run pipeline/companies/build_companies.py)")
            sys.exit(1)
        print("companies files are up to date")
        return
    print("companies files " + ("written: " + ", ".join(stale) if stale else "unchanged"))


if __name__ == "__main__":
    main()
