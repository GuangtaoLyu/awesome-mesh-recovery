# -*- coding: utf-8 -*-
"""Render README.md from papers.json + config taxonomy.

Groups papers by category (in the taxonomy's order), numbers them within each
category (so adding a paper never forces a global renumber), and sorts by year
desc then title. This is the auto-reorganized view the user asked for.
"""
import re
import os
import json
import embodied_index

# Long container-title (as returned by Crossref) -> short acronym.
_VENUE_ACR = [
    ("computer vision and pattern recognition", "CVPR"),
    ("international conference on computer vision", "ICCV"),
    ("european conference on computer vision", "ECCV"),
    ("neural information processing systems", "NeurIPS"),
    ("international conference on learning representations", "ICLR"),
    ("international conference on machine learning", "ICML"),
    ("association for the advancement of artificial intelligence", "AAAI"),
    ("acm multimedia", "ACM MM"),
    ("international conference on image processing", "ICIP"),
    ("applications of computer vision", "WACV"),
    ("3d vision", "3DV"),
    ("virtual reality", "ICVR"),
    ("robotics and automation", "ICRA"),
    ("intelligent robots and systems", "IROS"),
    ("siggraph", "SIGGRAPH"),
    ("pattern analysis and machine intelligence", "TPAMI"),
    ("audio, speech", "ICASSP"),
    ("multimedia", "ACM MM"),
    ("graphics", "Eurographics"),
]


def _short_venue(v):
    """Turn a verbose container-title into a compact label.

    Crossref returns things like "2026 IEEE/CVF Conference on Computer Vision
    and Pattern Recognition- FINDINGS Track (CVPRF)"; we want "CVPRF".
    """
    if not v:
        return ""
    s = " ".join(str(v).split())
    # Drop a leading / trailing bare year so it is not shown twice.
    s = re.sub(r"^(19|20)\d{2}\s+", "", s)
    s = re.sub(r"\s+(19|20)\d{2}$", "", s)
    # Prefer a trailing parenthesized acronym, e.g. "... (ICRAS)" -> ICRAS.
    m = re.search(r"\(([A-Z][A-Za-z0-9\-]{1,14})\)\s*$", s)
    if m:
        return m.group(1)
    low = s.lower()
    for kw, acr in _VENUE_ACR:
        if kw in low:
            return acr
    return s if len(s) <= 30 else s[:28].rstrip() + "..."


def _anchor(cat):
    """Match GitHub heading slugs: strip punctuation, preserve spaces as dashes."""
    return re.sub(r"[^a-z0-9 _-]", "", cat.lower()).replace(" ", "-")


def format_entry(idx, p):
    """Compact one-line listing: name, year/venue, and verified links."""
    title = p.get("title") or "Untitled paper"
    venue = _short_venue(p.get("venue") or "")
    year = p.get("year")
    if venue.lower() in ("arxiv", "arxiv.org", "print"):
        venue = "arXiv"
    meta = " ".join(str(x) for x in (venue, year) if x)
    url = (f"https://arxiv.org/abs/{p['arxiv_id']}" if p.get("arxiv_id")
           else p.get("url"))
    links = []
    if url:
        links.append(f"[Paper]({url})")
    if p.get("code_url"):
        label = ("Code (partial)" if p.get("code_status") == "partial" else
                 "Code (demo)" if p.get("code_status") == "demo" else "Code")
        links.append(f"[{label}]({p['code_url']})")
    if p.get("project_url"):
        links.append(f"[Project]({p['project_url']})")
    return f"- **{title}** ({meta}) — " + " · ".join(links)


EMBODIED_TITLE = "Embodied Motion Recovery & Robot Tracking"
EMBODIED_ANCHOR = "embodied-motion-recovery--robot-tracking"


def load_embodied_section():
    """All embodied papers come from structured, auto-updated JSON."""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "embodied.json"
    )
    data = embodied_index.load(path)
    return embodied_index.render(data).strip().splitlines(), len(data["papers"])


def generate(papers, config, readme_path):
    taxonomy = config.get("taxonomy", [])
    cats = {c: [] for c in taxonomy}
    for p in papers:
        c = p.get("category") or config.get("default_category")
        if c not in cats:
            c = config.get("default_category")
        cats.setdefault(c, []).append(p)

    # Curated source is separate from the auto-harvested paper store.
    embodied_lines, embodied_count = load_embodied_section()

    lines = []
    lines.append(f"# {config.get('display_name', 'Awesome List')}")
    lines.append("")
    if config.get("description"):
        lines.append(config["description"])
        lines.append("")
    lines.append(
        f"*Recovery papers: {len(papers)} | Embodied papers: {embodied_count}*"
    )
    lines.append("")
    lines.append(
        "> \U0001F916 Auto-updated weekly by GitHub Actions "
        "(multi-source: arXiv + DBLP + Semantic Scholar + Crossref). "
        "Includes arXiv preprints; code links are shown when verified."
    )
    lines.append("")

    # Contents TOC (only non-empty categories)
    lines.append("## Contents")
    lines.append(f"- [{EMBODIED_TITLE}](#{EMBODIED_ANCHOR})")
    for c in taxonomy:
        if cats.get(c):
            lines.append(f"- [{c}](#{_anchor(c)})")
    lines.append("")

    # Embodied work is the first research section in both the TOC and body.
    lines.extend(embodied_lines)
    lines.append("")

    for c in taxonomy:
        items = cats.get(c, [])
        if items:
            items.sort(key=lambda p: (-(p.get("year") or 0), p["title"].lower()))
            lines.append(f"## {c}")
            lines.append("")
            for i, p in enumerate(items, 1):
                lines.append(format_entry(i, p))
            lines.append("")

    lines.append("## Contributing")
    lines.append("")
    lines.append(
        "Papers are collected automatically from arXiv, DBLP, Semantic Scholar "
        "and Crossref. The sources of truth are `data/papers.json` and "
        "`data/embodied.json`. To suggest corrections, open an issue or PR. "
        "See [CONTRIBUTING.md](CONTRIBUTING.md) for scope and link rules."
    )
    lines.append("")

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
