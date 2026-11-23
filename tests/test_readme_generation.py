# -*- coding: utf-8 -*-
"""Regression tests for source-of-truth and order in generated README."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import generate_readme  # noqa: E402

CURATED = (ROOT / "data" / "embodied.md").read_text(encoding="utf-8").strip()
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
PAPERS = json.loads((ROOT / "data" / "papers.json").read_text(encoding="utf-8"))["papers"]
HEADING = "## Embodied Motion Recovery & Robot Tracking"
TOC = "- [Embodied Motion Recovery & Robot Tracking](#embodied-motion-recovery--robot-tracking)"


def render(papers):
    with tempfile.TemporaryDirectory() as work:
        path = Path(work) / "README.md"
        generate_readme.generate(papers, CONFIG, str(path))
        return path.read_text(encoding="utf-8")


class TestReadmeGeneration(unittest.TestCase):
    def test_embodied_first_in_contents_and_body(self):
        rendered = render(PAPERS)
        contents = rendered.split("## Contents\n", 1)[1]
        self.assertTrue(contents.startswith(TOC + "\n"))
        self.assertEqual(rendered.count(HEADING), 1)
        headings = re.findall(r"^## (?!Contents)(.+)$", rendered, flags=re.MULTILINE)
        self.assertEqual(headings[0], "Embodied Motion Recovery & Robot Tracking")

    def test_curated_survives_new_harvested_paper(self):
        fixture = {
            "title": "A Regression Test for Human Mesh Recovery",
            "authors": ["Unit Test"],
            "year": 2026,
            "venue": "arXiv",
            "url": "https://example.org/test-paper",
            "category": "Full-Body Human Mesh Recovery",
        }
        rendered = render(PAPERS + [fixture])
        start = rendered.index(HEADING)
        end = rendered.index("## Full-Body Human Mesh Recovery", start)
        self.assertEqual(rendered[start:end].strip(), CURATED)
        self.assertIn(fixture["title"], rendered)
        self.assertIn(f"Auto-indexed papers: {len(PAPERS)+1}", rendered)

    def test_generated_readme_checked_in(self):
        # Weekly automation runs pipeline generation before these tests.
        self.assertEqual((ROOT / "README.md").read_text(encoding="utf-8"), render(PAPERS))


if __name__ == "__main__":
    unittest.main()
