# -*- coding: utf-8 -*-
"""Discovery pagination/fairness, automatic evidence repair, and safety caps."""
import datetime
import json
import sys
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import harvest
import pipeline
import selection

CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
TODAY = datetime.date(2026, 11, 26)


class DiscoveryTests(unittest.TestCase):
    def test_arxiv_incremental_vs_backfill_sort(self):
        xml = b'''<feed xmlns="http://www.w3.org/2005/Atom">
          <entry><id>https://arxiv.org/abs/2611.12345v2</id>
          <title>Robust Human Mesh Recovery from Videos</title>
          <published>2026-11-20T10:00:00Z</published>
          <updated>2026-11-25T10:00:00Z</updated>
          <summary>We reconstruct SMPL body meshes from video.</summary></entry>
          </feed>'''
        urls = []

        def fetch(url):
            urls.append(url)
            return xml

        with mock.patch.object(harvest, "_arxiv_fetch", side_effect=fetch):
            config = {**CONFIG, "queries": {"arxiv": ["human mesh recovery"]}}
            recent, status = harvest.harvest(config, track="core", today=TODAY)
            old, status_old = harvest.harvest(
                config, track="core", today=TODAY, mode="backfill")
        self.assertEqual(len(recent), 1)
        self.assertEqual(len(old), 1)
        self.assertEqual(recent[0]["updated_at"], "2026-11-25")
        self.assertIn("sortBy=lastUpdatedDate", urls[0])
        self.assertIn("sortBy=submittedDate", urls[1])
        self.assertIn("max_results=75", urls[0])
        self.assertIn("max_results=75", urls[1])

    def test_arxiv_pages_beyond_first_75_results(self):
        def atom(start, count):
            entries = [
                '<entry><id>https://arxiv.org/abs/2611.%05d</id>'
                '<title>Human Mesh Recovery Method %d</title>'
                '<published>2026-11-20T00:00:00Z</published>'
                '<updated>2026-11-25T00:00:00Z</updated></entry>' %
                (start + i + 10000, start + i) for i in range(count)
            ]
            return ('<feed xmlns="http://www.w3.org/2005/Atom">' +
                    ''.join(entries) + '</feed>').encode("utf-8")

        urls = []

        def fake(url):
            urls.append(url)
            return atom(0, 75) if "start=0" in url else atom(75, 1)

        with mock.patch.object(harvest, "_arxiv_fetch", side_effect=fake):
            data = harvest.arxiv("human mesh recovery", 2024, 100)
        self.assertEqual(len(data), 76)
        self.assertEqual(len(urls), 2)
        self.assertIn("start=75", urls[1])

    def test_queries_rotate_across_weeks(self):
        seen = []

        def fake(query, since_year, limit):
            seen.append(query)
            return [{"title": "Human Mesh Recovery", "year": 2026}]
        with mock.patch.object(harvest, "SOURCES", {"dblp": fake}):
            cfg = {**CONFIG, "queries": {"dblp": ["a", "b", "c"]}}
            harvest.harvest(cfg, track="core", today=datetime.date(2026, 11, 23))
            first = list(seen)
            seen.clear()
            harvest.harvest(cfg, track="core", today=datetime.date(2026, 11, 30))
        self.assertNotEqual(first, seen)
        self.assertEqual(set(first), set(seen))

    def test_total_empty_core_queries_fail_safe(self):
        with mock.patch.object(harvest, "SOURCES", {"dblp": lambda *args: []}):
            with self.assertRaisesRegex(RuntimeError, "returned no papers"):
                harvest.harvest(
                    {**CONFIG, "queries": {"dblp": ["mesh"]}},
                    track="core", today=TODAY)


class EvidenceAndPublishingTests(unittest.TestCase):
    def setUp(self):
        self.old = [{"title": "Classic Human Mesh Recovery", "year": 2024,
                     "category": "Full-Body Human Mesh Recovery",
                     "url": "https://arxiv.org/abs/2401.00001"}]
        self.emb = {"schema_version": 1, "papers": [
            {"title": "Human to Robot Retargeting", "group":
             "Whole-Body Recovery → Humanoid Robots",
             "year": 2025, "arxiv_id": "2505.00001",
             "paper_url": "https://arxiv.org/abs/2505.00001"}],
            "toolkits": []}

    def test_first_monday_backfill_mode(self):
        self.assertEqual(
            pipeline.discovery_mode(datetime.date(2026, 11, 30)), "weekly")
        self.assertEqual(
            pipeline.discovery_mode(datetime.date(2026, 12, 7)), "backfill")
        self.assertEqual(
            pipeline.discovery_mode(datetime.date(2026, 12, 1)), "weekly")
        self.assertEqual(
            pipeline.discovery_mode(datetime.date(2026, 11, 26),
                                    force_backfill=True), "backfill")

    def test_auto_pending_lookups_rotate(self):
        config = json.loads(json.dumps(CONFIG))
        config["discovery"]["ambiguous_lookup_per_run"] = 2
        papers = [{
            "title": f"Human Reconstruction in Unknown Scenes {i}",
            "arxiv_id": f"2611.{45000+i:05d}",
            "first_seen": "2026-11-01", "year": 2026,
        } for i in range(6)]
        calls = []
        with mock.patch.object(
            pipeline.harvest, "arxiv_by_ids",
            side_effect=lambda ids: calls.append(tuple(ids)) or []
        ):
            pipeline._resolve_ambiguous(
                {"core": papers, "embodied": []}, config,
                today=datetime.date(2026, 11, 23))
            pipeline._resolve_ambiguous(
                {"core": papers, "embodied": []}, config,
                today=datetime.date(2026, 11, 30))
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(calls[0]), 2)
        self.assertNotEqual(calls[0], calls[1])

    def test_pending_first_seen_survives_new_source_enrichment(self):
        old = {"title": "Human Reconstruction in Unknown Scenes",
               "arxiv_id": "2611.67891", "first_seen": "2026-11-01",
               "source": "arxiv"}
        new = {"title": old["title"], "arxiv_id": old["arxiv_id"],
               "source": "s2", "year": 2026}
        merged = pipeline.dedup_records([new, old])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["first_seen"], "2026-11-01")

    def test_alpha_sort_never_silently_discards_papers(self):
        papers = [{"title": f"Human Mesh Recovery Method {i:03d}",
                   "year": 2026, "arxiv_id": f"2611.{i+20000:05d}",
                   "source": "arxiv"} for i in range(40)]
        core, emb, stats = pipeline.process_candidates(
            self.old, self.emb, set(), {"core": papers},
            CONFIG, TODAY, verify_code=False)
        self.assertEqual(stats["core_added"], 40)
        self.assertEqual(len(core), 41)
        self.assertEqual(len(emb["papers"]), 1)

    def test_safety_limit_raises_instead_of_dropping(self):
        cfg = json.loads(json.dumps(CONFIG))
        cfg["discovery"]["max_new_core_per_run"] = 3
        papers = [{"title": f"Human Mesh Recovery Model {i}",
                   "year": 2026, "arxiv_id": f"2611.{i+30000:05d}"}
                  for i in range(5)]
        with self.assertRaisesRegex(RuntimeError, "admission spike"):
            pipeline.process_candidates(
                self.old, self.emb, set(), {"core": papers},
                cfg, TODAY, verify_code=False)
        self.assertEqual(len(self.old), 1)
        self.assertEqual(len(self.emb["papers"]), 1)

    def test_uncertain_paper_is_deferred_then_auto_promoted(self):
        unclear = {"title": "Human Reconstruction in Unknown Scenes",
                   "arxiv_id": "2611.56789", "year": 2026,
                   "url": "https://arxiv.org/abs/2611.56789",
                   "source": "s2"}
        batches = {"core": [unclear], "embodied": []}
        core, emb, stats = pipeline.process_candidates(
            self.old, self.emb, set(), batches, CONFIG,
            TODAY, verify_code=False)
        self.assertEqual(stats["ambiguous"], 1)
        self.assertEqual(len(core), 1)
        pending = pipeline._automated_pending(
            [], batches, core, emb, set(), CONFIG, TODAY)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["track"], "core")
        # A later arXiv update gives concrete 3D recovery evidence.
        updated = dict(unclear)
        updated["abstract"] = (
            "We propose a human mesh recovery framework that reconstructs "
            "3D body shape and SMPL motion from in-the-wild video.")
        core2, emb2, stats2 = pipeline.process_candidates(
            core, emb, set(),
            {"core": [pending[0], updated], "embodied": []},
            CONFIG, TODAY, verify_code=False)
        self.assertEqual(stats2["core_added"], 1)
        self.assertEqual(len(core2), 2)
        pending2 = pipeline._automated_pending(
            pending, {"core": [pending[0], updated]}, core2, emb2,
            set(), CONFIG, TODAY)
        self.assertEqual(pending2, [])

    def test_embodied_search_can_find_pure_hand_recovery(self):
        p = {"title": "HOSt3R: Keypoint-free Hand-Object 3D Reconstruction "
                      "from RGB Images",
             "year": 2026, "arxiv_id": "2611.67890"}
        ps, emb, stats = pipeline.process_candidates(
            self.old, self.emb, set(),
            {"embodied": [p]}, CONFIG, TODAY, verify_code=False)
        self.assertEqual(stats["core_added"], 1)
        self.assertEqual(stats["embodied_added"], 0)

    def test_recency_prefers_updates_to_alphabetic_title(self):
        a = {"title": "AAA Human Mesh Recovery", "year": 2026,
             "submitted_at": "2026-01-02", "updated_at": "2026-01-02"}
        z = {"title": "ZZZ Human Mesh Recovery", "year": 2026,
             "submitted_at": "2026-11-22", "updated_at": "2026-11-25"}
        self.assertGreater(pipeline._recent_key(z), pipeline._recent_key(a))

    def test_automated_metadata_lookup_for_ambiguous_id(self):
        original = {"title": "Human Reconstruction in Unknown Scenes",
                    "arxiv_id": "2611.88990", "source": "s2"}
        batches = {"core": [original], "embodied": []}
        rich = dict(original)
        rich["abstract"] = "We reconstruct human mesh and 3D body shape using SMPL."
        with mock.patch.object(pipeline.harvest, "arxiv_by_ids", return_value=[rich]) as get:
            count = pipeline._resolve_ambiguous(batches, CONFIG)
        self.assertEqual(count, 1)
        get.assert_called_once_with(["2611.88990"])
        self.assertEqual(len(batches["core"]), 2)


if __name__ == "__main__":
    unittest.main()
