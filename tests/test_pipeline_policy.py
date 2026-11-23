# -*- coding: utf-8 -*-
"""Fast offline invariants for the future weekly update pipeline."""
import datetime
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import pipeline
import selection
import classify
import harvest

CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


class SelectionTests(unittest.TestCase):
    def test_strict_hmr_admission(self):
        p = {"title": "Robust Human Mesh Recovery in the Wild", "year": 2026}
        self.assertEqual(selection.decide(p, CONFIG, "core")[0], "auto")

    def test_ordinary_pose_not_auto_published(self):
        p = {"title": "3D Human Pose Estimation for Sports", "year": 2026}
        self.assertEqual(selection.decide(p, CONFIG, "core")[0], "review")

    def test_unrelated_robotics_ignored_by_core(self):
        p = {"title": "Language Guided Humanoid Navigation", "year": 2026}
        self.assertEqual(selection.decide(p, CONFIG, "core")[0], "ignore")

    def test_embodied_always_requires_editor(self):
        p = {"title": "Video to Robot Dexterous Hand Imitation", "year": 2026}
        self.assertEqual(selection.decide(p, CONFIG, "embodied")[0], "review")

    def test_title_based_classification_does_not_use_venue(self):
        paper = {"title": "Human Mesh Recovery", "venue": "Journal of Dynamic Vision"}
        self.assertEqual(classify.classify(paper), "Full-Body Human Mesh Recovery")
        self.assertEqual(classify.classify({"title": "Video-based Human Mesh Recovery"}),
                         "Motion & Temporal Recovery")
        self.assertEqual(classify.classify({"title": "Occluded Hand Mesh Recovery"}),
                         "Hand, Face & Expressive Mesh")


class DedupTests(unittest.TestCase):
    def test_transitive_dedup_preserves_first_category(self):
        records = [
            {"title": "Alpha Human Mesh Recovery", "arxiv_id": "2601.12345",
             "category": "Full-Body Human Mesh Recovery", "source": "seed"},
            {"title": "Alpha Human Mesh Recovery", "doi": "10.1109/ABCDE",
             "venue": "CVPR", "source": "crossref"},
            {"title": "Different Publication Title", "doi": "10.1109/abcde",
             "authors": ["Alice"], "source": "s2"},
        ]
        result = pipeline.dedup_records(records)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["category"], "Full-Body Human Mesh Recovery")
        self.assertEqual(result[0]["title"], "Alpha Human Mesh Recovery")
        self.assertEqual(result[0]["venue"], "CVPR")
        self.assertEqual(result[0]["authors"], ["Alice"])

    def test_curated_identifiers_from_markdown(self):
        c = ("1. **VideoManip: Human Reconstruction for Robotics** — 2026. "
             "[Paper](https://arxiv.org/abs/2602.09013)\n")
        keys = pipeline.curated_keys(c)
        self.assertIn("arxiv:2602.09013", keys)
        self.assertIn("title:videomanip human reconstruction for robotics", keys)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.old = [{"title": "Classic Human Mesh Recovery",
                     "year": 2024, "category": "Full-Body Human Mesh Recovery",
                     "url": "https://example.org/classic"}]
        self.today = datetime.date(2026, 11, 23)
        self.core_auto = {"title": "Fast Hand Mesh Recovery",
                          "arxiv_id": "2611.00001", "year": 2026,
                          "url": "https://arxiv.org/abs/2611.00001", "source": "arxiv"}
        self.core_review = {"title": "3D Human Pose Estimation for Sports",
                            "arxiv_id": "2611.00002", "year": 2026, "source": "arxiv"}
        self.robot = {"title": "Video to Robot Dexterous Manipulation",
                      "arxiv_id": "2611.00003", "year": 2026, "source": "arxiv"}

    def test_auto_review_and_curated_isolation(self):
        papers, queue, stats = pipeline.process_candidates(
            self.old, [], set(), set(),
            {"core": [self.core_auto, self.core_review],
             "embodied": [self.robot]}, CONFIG, self.today)
        self.assertEqual(stats["auto_added"], 1)
        self.assertEqual(stats["review_added"], 2)
        self.assertEqual(len(papers), 2)
        self.assertEqual(set(p["track"] for p in queue), {"core", "embodied"})
        self.assertEqual(papers[-1]["category"], "Hand, Face & Expressive Mesh")
        self.assertEqual(self.old[0]["category"], papers[0]["category"])

    def test_repeat_discovery_is_idempotent(self):
        batch = {"core": [self.core_auto, self.core_review],
                 "embodied": [self.robot]}
        ps, qs, _ = pipeline.process_candidates(
            self.old, [], set(), set(), batch, CONFIG, self.today)
        ps2, qs2, second = pipeline.process_candidates(
            ps, qs, set(), set(), batch, CONFIG, self.today)
        self.assertEqual((ps2, qs2), (ps, qs))
        self.assertEqual(second["auto_added"], 0)
        self.assertEqual(second["review_added"], 0)

    def test_curated_and_rejected_never_queued(self):
        ps, qs, stats = pipeline.process_candidates(
            self.old, [], pipeline.keys(self.core_review),
            pipeline.keys(self.robot),
            {"core": [self.core_review], "embodied": [self.robot]},
            CONFIG, self.today)
        self.assertEqual(ps, self.old)
        self.assertEqual(qs, [])
        self.assertEqual(stats["review_added"], 0)

    def test_per_track_queue_cap(self):
        candidates = [
            {"title": f"3D Human Pose Estimation Series {i}", "year": 2026}
            for i in range(20)
        ]
        ps, qs, _ = pipeline.process_candidates(
            self.old, [], set(), set(), {"core": candidates}, CONFIG, self.today)
        self.assertEqual(len(ps), 1)
        self.assertEqual(len(qs), CONFIG["discovery"]["new_review_per_run_per_track"])

    def test_all_source_failures_are_visible(self):
        with mock.patch.object(harvest, "SOURCES", {
            "arxiv": lambda *args: (_ for _ in ()).throw(RuntimeError("offline"))
        }):
            with self.assertRaisesRegex(RuntimeError, "All core discovery"):
                harvest.harvest(
                    {**CONFIG, "queries": {"arxiv": ["human mesh recovery"]}},
                    track="core", today=self.today
                )


if __name__ == "__main__":
    unittest.main()
