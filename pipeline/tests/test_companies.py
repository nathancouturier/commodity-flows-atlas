"""The companies layer: the source files follow the schema of pipeline/companies/README.md, the builder refuses an
entry that breaks it, and the published files are exactly what the sources give."""
import copy
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "pipeline", "companies"))
import build_companies as B  # noqa: E402


def load(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return json.load(f)


CTX = B.context()


def problems(companies, shipping):
    return B.problems(companies, shipping, *CTX)


class SourcesFollowTheSchema(unittest.TestCase):
    def test_no_problem_in_the_source_files(self):
        self.assertEqual(problems(B.merged(), B.load("shipping")), [])

    def test_published_files_are_the_sources(self):
        self.assertEqual(load("data/commodities/companies.json"), B.merged())
        self.assertEqual(load("data/freight/shipping-companies.json"), B.load("shipping"))
        for path, obj in ((B.OUT, B.merged()), (B.OUT_SHIPPING, B.load("shipping"))):
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), B.dump(obj), path)

    def test_source_files_keep_their_formatting(self):
        for name in ("energy", "metals", "agri", "shipping"):
            path = os.path.join(ROOT, "pipeline", "companies", name + ".json")
            with open(path, encoding="utf-8") as f:
                text = f.read()
            self.assertEqual(text, B.dump(json.loads(text)), name)

    def test_company_reports_is_not_one_company(self):
        reg = {s["id"]: s for s in load("data/sources.json")}
        self.assertIn("pipeline/companies/README.md", reg["company-reports"]["url"])
        for sid in ("sec-edgar", "cochilco", "ofac", "uk-sanctions"):
            self.assertIn(sid, reg)

    def test_energy_lists_cover_the_main_names(self):
        co = B.merged()
        names = lambda k, g: {e["name"] for e in co[k].get(g, [])}
        self.assertTrue({"PetroChina", "Petrobras", "Chevron", "Lukoil", "Pemex", "Kuwait Petroleum Corporation"} <= names("crude-oil", "producers"))
        self.assertTrue({"Novatek", "Venture Global"} <= names("lng", "producers"))
        self.assertTrue({"Uranium One", "CGN", "Navoi Mining and Metallurgical Company"} <= names("uranium", "producers"))
        self.assertIn("Novatek", names("natural-gas", "producers"))
        self.assertIn("CHN Energy", names("thermal-coal", "producers"))
        self.assertTrue(names("lpg", "producers"))
        self.assertNotIn("Gunvor", {e["name"] for k in co for g in co[k].values() for e in g})  # renamed Centalion

    def test_sanctions_name_the_authority_and_date(self):
        co = B.merged()
        rosneft = next(e for e in co["crude-oil"]["producers"] if e["name"] == "Rosneft")
        self.assertEqual({(s["by"], s["since"]) for s in rosneft["sanction"]}, {("OFAC", "2025-10"), ("UK", "2025-10")})
        for k, groups in co.items():
            for g in groups.values():
                for e in g:
                    self.assertNotRegex(e.get("detail", ""), r"(?i)\bsanctioned\b", e["name"])

    def test_shipping_companies_have_fleets_and_classes(self):
        sh = B.load("shipping")
        self.assertTrue({"dry-bulk", "tankers", "gas"} <= set(sh))
        fro = next(e for e in sh["tankers"] if e["name"] == "Frontline")
        self.assertEqual((fro["fig"]["v"], fro["fig"]["u"], fro["fig"]["y"]), (80, "ships", 2025))
        self.assertIn("vlcc", fro["classes"])
        vlcc = [e["name"] for seg in sh.values() for e in seg if "vlcc" in e.get("classes", [])]
        self.assertGreaterEqual(len(vlcc), 3)
        self.assertGreaterEqual(sum(len(v) for v in sh.values()), 30)


class BuilderRefusesBrokenEntries(unittest.TestCase):
    def broken(self, change):
        co = copy.deepcopy(B.merged())
        sh = copy.deepcopy(B.load("shipping"))
        change(co, sh)
        return problems(co, sh)

    def first(self, co, k="crude-oil", g="producers"):
        return co[k][g][0]

    def test_missing_read(self):
        errs = self.broken(lambda co, sh: self.first(co).pop("read"))
        self.assertTrue(any("read is required" in e for e in errs), errs)

    def test_unknown_unit(self):
        errs = self.broken(lambda co, sh: self.first(co)["fig"].update(u="Mboe/d hydrocarbon production"))
        self.assertTrue(any("is not a unit of the schema" in e for e in errs), errs)

    def test_home_page_url(self):
        errs = self.broken(lambda co, sh: self.first(co).update(url="https://www.vitol.com/"))
        self.assertTrue(any("home page" in e for e in errs), errs)
        errs = self.broken(lambda co, sh: self.first(co).update(url="https://www.example.com/en/"))
        self.assertTrue(any("home page" in e for e in errs), errs)
        self.assertIsNone(B.url_problem("https://www.vitol.com/vitol-2025-volumes-and-review/"))

    def test_two_identities_for_one_company(self):
        def change(co, sh):
            glen = next(e for e in co["thermal-coal"]["producers"] if e["name"] == "Glencore")
            glen["hq"] = "GBR"
        errs = self.broken(change)
        self.assertTrue(any("one identity per company" in e for e in errs), errs)

    def test_superlative_without_figure(self):
        def change(co, sh):
            e = next(e for e in co["crude-oil"]["producers"] if "fig" not in e)
            e["detail"] = "World's largest independent producer"
        errs = self.broken(change)
        self.assertTrue(any("superlative" in e for e in errs), errs)

    def test_unknown_source(self):
        errs = self.broken(lambda co, sh: self.first(co).update(s="company-website"))
        self.assertTrue(any("is not in data/sources.json" in e for e in errs), errs)

    def test_year_of_reading_is_not_the_year_of_the_fact(self):
        def change(co, sh):
            e = self.first(co)
            e["y"] = e["fig"]["y"] + 1
        errs = self.broken(change)
        self.assertTrue(any("y must be the year of fig" in e for e in errs), errs)

    def test_sanction_needs_authority_and_date(self):
        def change(co, sh):
            e = next(e for e in co["crude-oil"]["producers"] if e["name"] == "Rosneft")
            for x in e["sanction"]:
                x.pop("since")
        errs = self.broken(change)
        self.assertTrue(any("sanction must be" in e for e in errs), errs)

    def test_shipping_figure_is_a_fleet_and_classes_exist(self):
        def change(co, sh):
            sh["tankers"][0]["fig"]["u"] = "Mt"
            sh["tankers"][0]["classes"] = ["supertanker"]
        errs = self.broken(change)
        self.assertTrue(any("fleet" in e for e in errs), errs)
        self.assertTrue(any("classes must be ids" in e for e in errs), errs)

    def test_check_mode_passes_on_the_published_files(self):
        import subprocess
        r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "pipeline", "companies", "build_companies.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
