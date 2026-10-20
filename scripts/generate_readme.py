# -*- coding: utf-8 -*-
"""Render README.md from papers.json + config taxonomy.

Groups papers by category (in the taxonomy's order), numbers them within each
category (so adding a paper never forces a global renumber), and sorts by year
desc then title. This is the auto-reorganized view the user asked for.
"""
import re
import datetime

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
    return cat.lower().replace(" & ", " and ").replace(" ", "-").replace("&", "and")


def format_entry(idx, p):
    title = p.get("title", "")
    authors = p.get("authors") or []
    if authors:
        first = authors[0].split()[-1]
        auth = f"{first} et al." if len(authors) > 1 else authors[0]
    else:
        auth = ""
    raw_venue = p.get("venue") or ""
    venue = _short_venue(raw_venue)
    year = p.get("year")
    link = ""
    if p.get("arxiv_id"):
        link = f"[arXiv](https://arxiv.org/abs/{p['arxiv_id']})"
    elif p.get("url"):
        label = venue or "Paper"
        link = f"[{label}]({p['url']})"
    parts = [f"{idx}. **{title}**"]
    if auth:
        parts.append(f", {auth}")
    # Venue + year. arXiv preprints have no real venue, so show the year only.
    # _short_venue() strips a year embedded in the container-title, so it is
    # never printed twice.
    if "arxiv" in raw_venue.lower():
        # "arXiv" / "arXiv.org" / "arXiv preprint" -> no real venue, year only.
        meta = str(year) if year else ""
    else:
        meta = " ".join(str(x) for x in [venue, year] if x)
    if meta:
        parts.append(f", {meta}")
    if link:
        parts.append(f", {link}")
    return "".join(parts)


def generate(papers, config, readme_path):
    taxonomy = config.get("taxonomy", [])
    cats = {c: [] for c in taxonomy}
    for p in papers:
        c = p.get("category") or config.get("default_category")
        if c not in cats:
            c = config.get("default_category")
        cats.setdefault(c, []).append(p)

    lines = []
    lines.append(f"# {config.get('display_name', 'Awesome List')}")
    lines.append("")
    if config.get("description"):
        lines.append(config["description"])
        lines.append("")
    lines.append(
        f"*Last updated: {datetime.date.today().isoformat()} | "
        f"Total papers: {len(papers)}*"
    )
    lines.append("")
    lines.append(
        "> \U0001F916 Auto-updated weekly by GitHub Actions "
        "(multi-source: arXiv + DBLP + Semantic Scholar + Crossref). "
        "Entries are auto-categorized by topic."
    )
    lines.append("")

    # Contents TOC (only non-empty categories)
    lines.append("## Contents")
    for c in taxonomy:
        if cats.get(c):
            lines.append(f"- [{c}](#{_anchor(c)})")
    lines.append("")

    for c in taxonomy:
        items = cats.get(c, [])
        if not items:
            continue
        items.sort(key=lambda p: (-(p.get("year") or 0), p["title"].lower()))
        lines.append(f"## {c}")
        lines.append("")
        for i, p in enumerate(items, 1):
            lines.append(format_entry(i, p))
        lines.append("")

    lines.append("## Contributing")
    lines.append("")
    lines.append(
        "Found a missing or mis-categorized paper? Open an issue or pull "
        "request — the list is regenerated automatically, so manual README "
        "edits will be overwritten on the next run."
    )
    lines.append("")

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
