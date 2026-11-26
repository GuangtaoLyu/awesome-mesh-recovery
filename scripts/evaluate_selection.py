# -*- coding: utf-8 -*-
"""Offline admission quality check on fixed representative research tasks.

This is a regression fixture, NOT a statistically representative estimate of
live publication-search precision. It prevents future keyword edits from
reintroducing known false positives or dropping diverse true positives.

Usage:
    python scripts/evaluate_selection.py
    python scripts/evaluate_selection.py --strict
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import classify
import selection

FIXTURES = ROOT / "tests" / "fixtures" / "selection_cases.json"
CONFIG = ROOT / "config.json"

THRESHOLDS = {"precision": 0.95, "recall": 0.90, "category_accuracy": 0.80}


def predict(paper, config):
    robot = selection.assess(paper, config, "embodied")
    core = selection.assess(paper, config, "core")
    if robot["decision"] == "auto":
        return "embodied", robot
    if core["decision"] == "auto":
        return "core", core
    if robot["decision"] == "verify" or core["decision"] == "verify":
        return "defer", robot if robot["decision"] == "verify" else core
    return "ignore", core


def evaluate(cases, config):
    predictions = []
    true_positive = 0
    predicted_positive = 0
    gold_positive = 0
    category_correct = category_total = 0
    for sample in cases:
        gold = sample["label"]
        guess, assessment = predict(sample, config)
        if guess in ("core", "embodied"):
            predicted_positive += 1
        if gold in ("core", "embodied"):
            gold_positive += 1
        if guess == gold and gold in ("core", "embodied"):
            true_positive += 1
        if gold == "core" and guess == "core" and sample.get("category"):
            category_total += 1
            if classify.classify(sample, config) == sample["category"]:
                category_correct += 1
        predictions.append({
            "title": sample["title"], "expected": gold, "predicted": guess,
            "evidence": assessment["evidence"],
        })

    return {
        "count": len(cases),
        "precision": true_positive / predicted_positive if predicted_positive else 0.0,
        "recall": true_positive / gold_positive if gold_positive else 0.0,
        "category_accuracy": (
            category_correct / category_total if category_total else 0.0
        ),
        "predicted_positive": predicted_positive,
        "expected_positive": gold_positive,
        "errors": [p for p in predictions if p["expected"] != p["predicted"]],
        "predictions": predictions,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Fail when regression thresholds are missed")
    args = parser.parse_args()
    data = json.loads(FIXTURES.read_text(encoding="utf-8"))
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    report = evaluate(data["cases"], cfg)
    print(f"Selection fixture: {report['count']} representative cases "
          f"({report['expected_positive']} positives)")
    print(f"Precision: {report['precision']:.1%}, "
          f"Recall: {report['recall']:.1%}, "
          f"Category accuracy: {report['category_accuracy']:.1%}")
    for item in report["errors"]:
        print(f"  expected={item['expected']} predicted={item['predicted']}: "
              f"{item['title']}")
    if args.strict:
        failures = [k for k, minimum in THRESHOLDS.items()
                    if report[k] < minimum]
        if failures:
            raise SystemExit("Selection regression threshold failed: " + ", ".join(failures))


if __name__ == "__main__":
    main()
