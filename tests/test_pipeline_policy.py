# -*- coding: utf-8 -*-
"""Offline tests: automatic preprints, scope, dedup and safe publishing."""
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
import embodied_index

CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
TODAY = datetime.date(2026, 11, 23)


class AdmissionTests(unittest.TestCase):
    def test_preprint_without_acceptance_auto_indexed(self):
        p = {"title": "Fast Hand Mesh Recovery", "year": 2026, "venue": "arXiv"}
        self.assertEqual(selection.decide(p, CONFIG, "core")[0], "auto")
        no_year = {"title": "Fast Human Mesh Reconstruction", "venue": "arXiv"}
        self.assertEqual(selection.decide(no_year, CONFIG, "core")[0], "auto")

    def test_unrelated_robotics_not_core(self):
        p = {"title": "Language Guided Humanoid Navigation", "year": 2026}
        self.assertEqual(selection.decide(p, CONFIG, "core")[0], "ignore")

    def test_embodied_auto_admission_with_video_robot_connection(self):
        p = {"title": "Video to Humanoid Motion Tracking",
             "abstract": "Recover human motion from monocular video for robot tracking.",
             "year": 2026, "venue": "arXiv"}
        self.assertEqual(selection.decide(p, CONFIG, "embodied")[0], "auto")

    def test_biomedical_mesh_is_not_human_mesh_recovery(self):
        candidate = {
            "title": "Mesh-guided self-assembly of centimeter-scale, cell-derived human dermis",
            "year": 2027,
        }
        self.assertEqual(selection.decide(candidate, CONFIG, "core")[0], "ignore")

    def test_downstream_anonymization_is_not_a_new_hmr_method(self):
        candidate = {
            "title": "Training-Free Anonymization of Driving Data with "
                     "Promptable Segmentation and 3D Human Mesh Recovery",
            "year": 2026,
        }
        self.assertEqual(selection.decide(candidate, CONFIG, "core")[0], "ignore")

    def test_robot_only_topics_do_not_enter_embodied(self):
        examples = [
            {"title": "Proprioceptive-visual correspondence enables "
                      "self-other distinction in humanoid robots",
             "abstract": "Supports human-to-robot motion retargeting."},
            {"title": "DexForce: Extracting Force-informed Actions "
                      "from Kinesthetic Demonstrations for Dexterous Manipulation",
             "abstract": "Compared with human-to-robot motion retargeting."},
            {"title": "Morphology-Consistent Humanoid Interaction "
                      "through Robot-Centric Video Synthesis",
             "abstract": "Avoids human-to-robot motion retargeting."},
        ]
        for paper in examples:
            with self.subTest(paper=paper["title"]):
                self.assertEqual(
                    selection.decide(paper, CONFIG, "embodied")[0], "ignore"
                )

    def test_pure_hand_object_reconstruction_routes_to_core(self):
        p = {"title": "HOSt3R: Keypoint-free Hand-Object 3D Reconstruction "
                      "from RGB images",
             "abstract": "Potential downstream applications in human-robot interaction."}
        self.assertEqual(selection.decide(p, CONFIG, "core")[0], "auto")
        self.assertEqual(selection.decide(p, CONFIG, "embodied")[0], "ignore")

    def test_real_transfer_related_preprint_still_auto_accepted(self):
        p = {
            "title": "From Festival Video to the Stage: A Sim-to-Real Ladder "
                     "for Whole-Body Dance on a Commercial Humanoid",
            "abstract": "Recover human motion from video and retarget "
                        "it onto the humanoid robot.",
        }
        self.assertEqual(selection.decide(p, CONFIG, "embodied")[0], "auto")
        retarget = {
            "title": "ObjRetarget: An Object-Aware Motion Retargeting Framework "
                     "with Anthropomorphic Arm Constraints and Hand Modeling",
            "abstract": "Human demonstrations to robot retargeting.",
        }
        self.assertEqual(selection.decide(retarget, CONFIG, "embodied")[0], "auto")

    def test_no_generic_vision_to_robotics_false_positive(self):
        p = {"title": "Humanoid Robot Navigation with Language",
             "abstract": "Vision language planning in indoor environments"}
        self.assertEqual(selection.decide(p, CONFIG, "embodied")[0], "ignore")

    def test_legacy_pose_only_and_camera_application_titles_stay_out(self):
        titles = [
            "KASportsFormer: Kinematic Anatomy Enhanced Transformer for "
            "3D Human Pose Estimation on Short Sports Scene Video",
            "Posegu: 3d Human Pose Estimation with Novel Human Pose Generator",
            "EgoRayFormer: Ray-Space Stereo Refinement for "
            "Egocentric 3D Human Pose Estimation",
            "Unsupervised camera pose estimation through human mesh recovery",
            "Unsupervised continuous camera network pose estimation through "
            "human mesh recovery",
            "Interaction with Virtual Objects using Human Pose and Shape Estimation",
            "Generating Multi-View Action Data from a Monocular Camera Video "
            "by Fusing Human Mesh Recovery and 3D Scene Reconstruction",
            "Dual Mesh Convolutional Networks for Human Shape Correspondence",
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertEqual(selection.decide({"title": title}, CONFIG, "core")[0],
                                 "ignore")
        # Body/hand/shape recovery itself still needs automatic admission.
        self.assertEqual(selection.decide(
            {"title": "Video-based Human Mesh Recovery for Occluded People"},
            CONFIG, "core"
        )[0], "auto")

    def test_title_only_classification(self):
        self.assertEqual(classify.classify(
            {"title": "Occluded Hand Mesh Recovery", "venue": "Dynamic Robotics"}),
            "Hand, Face & Expressive Mesh")


class IdentityTests(unittest.TestCase):
    def test_transitive_duplicates(self):
        records = [
            {"title": "Alpha Human Mesh Recovery", "arxiv_id": "2601.12345",
             "category": "Full-Body Human Mesh Recovery", "source": "seed"},
            {"title": "Alpha Human Mesh Recovery", "doi": "10.1109/ABCDE",
             "venue": "CVPR", "source": "crossref"},
            {"title": "Another Title", "doi": "10.1109/abcde",
             "authors": ["Alice"], "source": "s2"},
        ]
        result = pipeline.dedup_records(records)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["category"], "Full-Body Human Mesh Recovery")
        self.assertEqual(result[0]["venue"], "CVPR")

    def test_year_conflict_not_labeled_as_conference(self):
        a = {"title": "Mesh Recovery Paper", "venue": "arXiv", "year": 2025}
        b = {"title": "Mesh Recovery Paper", "venue": "CVPR", "year": 2026}
        self.assertEqual(pipeline.enrich(a, b)["venue"], "arXiv")

    def test_two_sources_same_arxiv_id(self):
        a = {"title": "Video to Robot Imitation",
             "paper_url": "https://arxiv.org/abs/2611.22222",
             "arxiv_id": "2611.22222"}
        b = {"title": "Revised Video Robot Imitation",
             "url": "https://arxiv.org/abs/2611.22222"}
        self.assertTrue(pipeline.keys(a) & pipeline.keys(b))


class AutomaticPipelineTests(unittest.TestCase):
    def setUp(self):
        self.old = [{"title": "Classic Human Mesh Recovery",
                     "year": 2024, "venue": "CVPR",
                     "category": "Full-Body Human Mesh Recovery",
                     "url": "https://example.org/classic"}]
        self.embodied = {
            "schema_version": 1,
            "papers": [{
                "title": "Existing Human-to-Robot Paper",
                "year": 2025, "group": embodied_index.GROUPS[0],
                "publication": "arXiv 2025", "publication_status": "preprint",
                "paper_url": "https://arxiv.org/abs/2505.00001",
                "arxiv_id": "2505.00001",
            }],
            "toolkits": []
        }
        self.core = {"title": "Fast Hand Mesh Recovery",
                     "arxiv_id": "2611.00001", "year": 2026, "venue": "arXiv",
                     "url": "https://arxiv.org/abs/2611.00001", "source": "arxiv"}
        self.robot = {"title": "Video to Humanoid Motion Tracking",
                      "abstract": "We recover human motion from video and track it on a robot.",
                      "arxiv_id": "2611.00003", "year": 2026,
                      "venue": "arXiv", "source": "arxiv"}

    def test_both_tracks_auto_publish(self):
        ps, data, stats = pipeline.process_candidates(
            self.old, self.embodied, set(),
            {"core": [self.core], "embodied": [self.robot]},
            CONFIG, TODAY, verify_code=False)
        self.assertEqual(stats["core_added"], 1)
        self.assertEqual(stats["embodied_added"], 1)
        self.assertEqual(len(ps), 2)
        self.assertEqual(len(data["papers"]), 2)
        self.assertEqual(ps[-1]["category"], "Hand, Face & Expressive Mesh")

    def test_repeated_discovery_idempotent(self):
        batch = {"core": [self.core], "embodied": [self.robot]}
        ps, data, _ = pipeline.process_candidates(
            self.old, self.embodied, set(), batch, CONFIG, TODAY, verify_code=False)
        ps2, data2, stats = pipeline.process_candidates(
            ps, data, set(), batch, CONFIG, TODAY, verify_code=False)
        self.assertEqual((ps2, data2), (ps, data))
        self.assertEqual(stats["core_added"], 0)
        self.assertEqual(stats["embodied_added"], 0)

    def test_no_duplicate_in_existing_embodied(self):
        robot = {**self.robot, "arxiv_id": "2505.00001",
                 "url": "https://arxiv.org/abs/2505.00001"}
        ps, data, stats = pipeline.process_candidates(
            self.old, self.embodied, set(),
            {"core": [], "embodied": [robot]}, CONFIG, TODAY, verify_code=False)
        self.assertEqual(len(data["papers"]), 1)
        self.assertEqual(stats["embodied_added"], 0)

    def test_blocklist_keeps_bad_paper_out(self):
        ps, data, stats = pipeline.process_candidates(
            self.old, self.embodied, pipeline.keys(self.core),
            {"core": [self.core]}, CONFIG, TODAY, verify_code=False)
        self.assertEqual(len(ps), 1)
        self.assertEqual(stats["core_added"], 0)

    def test_malformed_or_missing_data_never_silent(self):
        with self.assertRaisesRegex(ValueError, "Missing/invalid"):
            with mock.patch.object(pipeline, "PAPERS", ROOT / "data" / "not-found.json"):
                pipeline.run(render_only=True)

    def test_all_core_source_failures_visible(self):
        with mock.patch.object(harvest, "SOURCES", {
            "arxiv": lambda *args: (_ for _ in ()).throw(RuntimeError("offline"))
        }):
            with self.assertRaisesRegex(RuntimeError, "All core discovery"):
                harvest.harvest(
                    {**CONFIG, "queries": {"arxiv": ["human mesh recovery"]}},
                    track="core", today=TODAY)


class PresentationTests(unittest.TestCase):
    def test_embodied_one_line_no_per_paper_bullets(self):
        record = {
            "title": "VideoManip", "year": 2026, "publication": "2026",
            "publication_status": "preprint", "arxiv_id": "2602.09013",
            "paper_url": "https://arxiv.org/abs/2602.09013",
            "code_url": "https://github.com/hychen-naza/VideoManip",
            "code_status": "partial",
        }
        line = embodied_index.format_paper(record)
        self.assertEqual(len(line.splitlines()), 1)
        self.assertIn("(arXiv 2026)", line)
        self.assertIn("[Code (partial release)]", line)
        self.assertNotIn("summary", line)

    def test_monorepo_code_links_keep_official_subdirectories(self):
        paper = {"comment": "Code and models: "
                 "https://github.com/huawei-noah/noah-research/tree/master/CLIFF"}
        urls = embodied_index._github_candidates(paper)
        self.assertEqual(
            urls,
            ["https://github.com/huawei-noah/noah-research/tree/master/CLIFF"],
        )

    def test_unverified_code_not_claimed_closed(self):
        record = {"title": "Preprint", "year": 2026,
                  "publication_status": "preprint", "arxiv_id": "2611.10000",
                  "paper_url": "https://arxiv.org/abs/2611.10000"}
        line = embodied_index.format_paper(record)
        self.assertNotIn("Code", line)

    def test_author_link_required_for_code(self):
        third_party = {
            "abstract": "We compare with methods using "
                        "https://github.com/facebookresearch/sam2."
        }
        self.assertEqual(embodied_index._github_candidates(third_party), [])
        official = {
            "comment": "Our code is available at "
                       "https://github.com/example-lab/paper/tree/main/method."
        }
        self.assertEqual(
            embodied_index._github_candidates(official),
            ["https://github.com/example-lab/paper/tree/main/method"],
        )

    def test_new_preprint_never_invents_unknown_year_or_summary(self):
        item = embodied_index.new_paper(
            {"title": "Human-to-Robot Motion Retargeting",
             "url": "https://doi.org/10.1234/example", "venue": ""},
            today=TODAY,
        )
        self.assertIsNone(item["year"])
        self.assertNotIn("role", item)
        self.assertNotIn("summary", item)
        self.assertIn("Preprint", embodied_index.format_paper(item))
        paper = embodied_index.new_paper(
            {"title": "Dexterous Hand Tracking from Human Video",
             "arxiv_id": "2611.12345", "venue": "arXiv"},
            today=TODAY,
        )
        self.assertEqual(paper["year"], 2026)
        self.assertEqual(paper["group"], embodied_index.GROUPS[1])

    def test_seeded_embodied_collection_preserved(self):
        data = embodied_index.load(ROOT / "data" / "embodied.json")
        self.assertGreaterEqual(len(data["papers"]), 21)
        self.assertTrue(any("VideoManip" in x["title"] for x in data["papers"]))


if __name__ == "__main__":
    unittest.main()
