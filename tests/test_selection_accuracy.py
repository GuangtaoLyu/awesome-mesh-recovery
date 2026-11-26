# -*- coding: utf-8 -*-
"""Admission precision/recall regression fixture; no network calls."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import evaluate_selection


class SelectionQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = json.loads(evaluate_selection.CONFIG.read_text(encoding="utf-8"))
        cases = json.loads(evaluate_selection.FIXTURES.read_text(encoding="utf-8"))["cases"]
        cls.report = evaluate_selection.evaluate(cases, cfg)

    def test_sample_set_is_diverse(self):
        self.assertGreaterEqual(self.report["count"], 50)
        self.assertGreaterEqual(self.report["expected_positive"], 30)

    def test_precision(self):
        self.assertGreaterEqual(
            self.report["precision"], evaluate_selection.THRESHOLDS["precision"],
            self.report["errors"],
        )

    def test_recall(self):
        self.assertGreaterEqual(
            self.report["recall"], evaluate_selection.THRESHOLDS["recall"],
            self.report["errors"],
        )

    def test_core_category_accuracy(self):
        self.assertGreaterEqual(
            self.report["category_accuracy"],
            evaluate_selection.THRESHOLDS["category_accuracy"],
            self.report["errors"],
        )

    def test_unknown_evidence_stays_unpublished(self):
        pending = [p for p in self.report["predictions"]
                   if p["expected"] == "defer"]
        self.assertEqual(len(pending), 2)
        self.assertTrue(all(p["predicted"] == "defer" for p in pending), pending)


if __name__ == "__main__":
    unittest.main()
