# -*- coding: utf-8 -*-
"""One-time bootstrap: parse the EXISTING curated README into papers.json.

Run once (locally or as the pipeline's first-run fallback) so the already
curated papers are not lost when we switch to the generated README. Best-effort
regex parse of the `N. **Title** , Author et al. , [link]` format.

Robust against the shields.io badge style used by this repo, e.g.
  `1. **Title**  ,   Yang et al.  ,   [![arXiv](https://img.shields.io/...svg)](https://arxiv.org/abs/XXXX)`
where the real paper URL is nested inside the badge and must be pulled out by
matching `arxiv.org/abs/<id>` anywhere on the line (the first `](...)` would
otherwise capture the shields.io image URL).
"""
import re
import json
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_common import save_json


def parse(readme_path):
    """Return a list of paper dicts parsed from the existing README."""
    with open(readme_path, encoding="utf-8") as f:
        text = f.read()
    year = None
    papers = []
    for line in text.splitlines():
        m = re.match(r"^#{1,2}\s+(\d{4})\b", line.strip())
        if m:
            year = int(m.group(1))
            continue
        m = re.search(r"\*\*(.+?)\*\*", line)
        if not m:
            continue
        title = " ".join(m.group(1).split())
        if len(title) < 10:  # skip short headings / badges
            continue
        # First author, captured before "et al".
        auth = ""
        am = re.search(r"\*\*\s*.+?\*\*\s*,\s*([^,]+?)\s*et al", line)
        if am:
            auth = am.group(1).strip()
        # arXiv id anywhere on the line (handles nested shields badges).
        arxiv = None
        km = re.search(r"arxiv\.org/abs/([0-9]+\.[0-9]+)", line)
        if km:
            arxiv = km.group(1)
        if arxiv:
            url = f"https://arxiv.org/abs/{arxiv}"
            venue = "arXiv"
        else:
            um = re.search(r"\]\((https?://[^)]+)\)", line)
            url = um.group(1) if um else ""
            venue = ""
            # Try to infer a venue name from a known host for the label.
            if "springer" in url:
                venue = "Springer"
            elif "cvf" in url or "thecvf" in url:
                venue = "CVPR"
            elif "ieeexplore" in url or "ieee" in url:
                venue = "IEEE"
        papers.append({
            "title": title,
            "authors": [auth] if auth else [],
            "year": year,
            "venue": venue,
            "url": url,
            "arxiv_id": arxiv,
            "source": "seed",
        })
    return papers


def run(config, readme_path, papers_path):
    import classify  # per-repo classification script
    papers = parse(readme_path)
    for p in papers:
        try:
            p["category"] = classify.classify(p, config)
        except Exception:
            p["category"] = config.get("default_category")
        p["added"] = datetime.date.today().isoformat()
    save_json(papers_path, {"papers": papers})
    return papers
