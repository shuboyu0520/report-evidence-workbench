"""Exercise the offline CLI and check the archived browser and CLI data agree."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "scripts/inspect_eval.py"


def case(cid, kind, passed, **updates):
    return {"id": cid, "question": "这一季的销售额是多少？", "kind": kind, "passed": passed,
            "answer": "120 元", "previous_answer": None, "grade": "金额与原行一致。",
            "verification": "source_earnings_cell", "citations": [], **updates}


class InspectEvalTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)
        self.file = self.work / "fixture.json"
        self.archive = {"schema_version": 1, "cohorts": {
            "repair": {"title": "同题复测", "kind": "same_set", "source": "https://example.com/report.pdf?lang=en#view=fit",
                       "cases": [case("R1", "actual", True, previous_answer="100 元",
                                     citations=[{"page": 3, "quote": "Sales 120"}])]},
            "first": {"title": "独立首测", "kind": "blind", "source": "https://example.com/first.pdf",
                      "cases": [case("F1", "guidance", False, grade="期间错配。"), case("F2", "future", True)]},
        }}

    def invoke(self, *args):
        self.file.write_text(json.dumps(self.archive), encoding="utf-8")
        return subprocess.run([sys.executable, "-I", "-S", str(CLI), "--archive", str(self.file), *args],
                              cwd=self.work, capture_output=True, encoding="utf-8")

    def test_first_run_and_repaired_set_keep_separate_denominators(self):
        response = self.invoke("--failed", "--json")
        self.assertEqual(response.returncode, 0, response.stderr)
        data = json.loads(response.stdout)
        self.assertEqual(data["mode"], "archived_replay")
        first = data["cohorts"]["first"]
        self.assertEqual(first["scores"]["lookup_guidance"], {"passed": 0, "total": 1})
        self.assertEqual(first["scores"]["disclosure_status"], {"passed": 1, "total": 1})
        self.assertEqual([c["id"] for c in first["cases"]], ["F1"])
        self.assertEqual(data["cohorts"]["repair"]["cases"], [])

    def test_detail_preserves_source_query_and_shows_prior_answer(self):
        response = self.invoke("--cohort", "repair", "--case", "R1")
        self.assertEqual(response.returncode, 0, response.stderr)
        for text in ["上版答案  100 元", "本轮答案  120 元", "Sales 120", "report.pdf?lang=en#page=3"]:
            self.assertIn(text, response.stdout)

    def test_refusal_separates_independent_grade_from_answer_citations(self):
        self.archive["cohorts"]["first"]["cases"][0].update(
            answer="证据不足", gold_pages=[4], gold_quote="Reported growth 1% to 3%"
        )
        response = self.invoke("--cohort", "first", "--case", "F1")
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertIn("独立评分参考第 4 页  https://example.com/first.pdf#page=4", response.stdout)
        self.assertIn("独立评分参考原文  Reported growth 1% to 3%", response.stdout)
        self.assertNotIn("原文第 4 页", response.stdout)

    def test_unknown_case_and_malformed_scores_fail_clearly(self):
        response = self.invoke("--cohort", "first", "--case", "R1")
        self.assertEqual(response.returncode, 2)
        self.assertNotIn("Traceback", response.stderr)
        self.archive["cohorts"]["first"]["cases"][0]["passed"] = "false"
        response = self.invoke()
        self.assertEqual(response.returncode, 2)
        self.assertNotIn("Traceback", response.stderr)


class ShippedArchiveTests(unittest.TestCase):
    def test_browser_data_matches_cli_archive_including_grades_and_sources(self):
        root = CLI.parents[1]
        browser_data = (root / "docs/evidence-review-data.js").read_text(encoding="utf-8").strip()
        prefix = "window.EVIDENCE_REVIEW = "
        self.assertTrue(browser_data.startswith(prefix) and browser_data.endswith(";"))
        browser_archive = json.loads(browser_data[len(prefix):-1])
        cli_archive = json.loads((root / "evaluation/showcase.json").read_text(encoding="utf-8"))
        self.assertEqual(browser_archive, cli_archive)
