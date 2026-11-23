# -*- coding: utf-8 -*-
"""Regression tests for stable, compact, fully automatic README output."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import generate_readme
import embodied_index

CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
PAPERS = json.loads((ROOT / "data" / "papers.json").read_text(encoding="utf-8"))["papers"]
EMBODIED = embodied_index.load(ROOT / "data" / "embodied.json")
HEADING = "## Embodied Motion Recovery & Robot Tracking"
TOC = "- [Embodied Motion Recovery & Robot Tracking](#embodied-motion-recovery--robot-tracking)"


def render(papers):
    with tempfile.TemporaryDirectory() as dirname:
        destination = Path(dirname) / "README.md"
        generate_readme.generate(papers, CONFIG, str(destination))
        return destination.read_text(encoding="utf-8")


class TestReadmeGeneration(unittest.TestCase):
    def test_embodied_first_in_toc_and_body(self):
        text = render(PAPERS)
        self.assertTrue(text.split("## Contents\n", 1)[1].startswith(TOC + "\n"))
        self.assertEqual(text.count(HEADING), 1)
        headings = re.findall(r"^## (?!Contents)(.+)$", text, flags=re.MULTILINE)
        self.assertEqual(headings[0], "Embodied Motion Recovery & Robot Tracking")

    def test_new_hmr_does_not_remove_embodied_papers(self):
        fixture = {"title": "A Test for Hand Mesh Recovery",
                   "authors": [], "year": 2026, "venue": "arXiv",
                   "url": "https://example.org/paper",
                   "category": "Hand, Face & Expressive Mesh"}
        text = render(PAPERS + [fixture])
        section = text[text.index(HEADING):text.index("## Full-Body Human Mesh Recovery")].strip()
        self.assertEqual(section, embodied_index.render(EMBODIED).strip())
        self.assertIn(fixture["title"], text)
        self.assertIn(f"Recovery papers: {len(PAPERS)+1}", text)

    def test_one_line_per_entry(self):
        text = render(PAPERS)
        self.assertNotIn("\n   - ", text)
        self.assertIn("(arXiv 2026)", text)
        self.assertIn("[Code (partial release)]", text)

    def test_readme_reproducible(self):
        self.assertEqual(
            (ROOT / "README.md").read_text(encoding="utf-8"),
            render(PAPERS),
        )


if __name__ == "__main__":
    unittest.main()
