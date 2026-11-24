# -*- coding: utf-8 -*-
"""Generate a compact, deterministic Awesome List from two JSON indexes."""
import os
import re
import embodied_index

# Specific forms first: workshops and findings must not inherit main-track labels.
_VENUE_ACR = [
    ("computer vision and pattern recognition", "CVPR"),
    ("international conference on computer vision", "ICCV"),
    ("european conference on computer vision", "ECCV"),
    ("aaai conference on artificial intelligence", "AAAI"),
    ("association for the advancement of artificial intelligence", "AAAI"),
    ("neural information processing systems", "NeurIPS"),
    ("international conference on learning representations", "ICLR"),
    ("international conference on machine learning", "ICML"),
    ("international conference on image processing", "ICIP"),
    ("winter conference on applications of computer vision", "WACV"),
    ("applications of computer vision", "WACV"),
    ("international conference on multimedia and expo", "ICME"),
    ("3d vision", "3DV"),
    ("british machine vision", "BMVC"),
    ("robotics and automation", "ICRA"),
    ("intelligent robots and systems", "IROS"),
    ("siggraph asia", "SIGGRAPH Asia"),
    ("siggraph", "SIGGRAPH"),
    ("acm multimedia", "ACM MM"),
    ("international journal of computer vision", "IJCV"),
    ("pattern analysis and machine intelligence", "TPAMI"),
    ("ieee transactions on image processing", "TIP"),
    ("transactions on image processing", "TIP"),
    ("ieee transactions on multimedia", "TMM"),
    ("transactions on circuits and systems for video technology", "TCSVT"),
    ("visual communication and image representation", "JVCIR"),
    ("signal image and video processing", "SIVP"),
    ("signal, image and video processing", "SIVP"),
    ("audio, speech", "ICASSP"),
]


def _short_venue(v):
    """Prefer accurate common acronyms; never publish ellipsized venue names."""
    if not v:
        return ""
    s = " ".join(str(v).split())
    s = re.sub(r"^(19|20)\d{2}\s+", "", s)
    s = re.sub(r"\s+(19|20)\d{2}$", "", s)
    found = re.search(r"\(([A-Z][A-Za-z0-9\-]{1,14})\)\s*$", s)
    if found:
        return found.group(1)
    low = s.lower()
    for phrase, acronym in _VENUE_ACR:
        if phrase in low:
            if acronym in ("CVPR", "ICCV") and "workshop" in low:
                return acronym + "W"
            if acronym == "CVPR" and ("findings" in low or "finding track" in low):
                return "CVPR Findings"
            return acronym
    if low in ("arxiv", "arxiv.org", "arxiv preprint", "print"):
        return "arXiv"
    # An unknown long Crossref journal name is better represented by its
    # year than by a fabricated abbreviation or a truncated "...".
    return s if len(s) <= 38 else ""


def _anchor(cat):
    """Match GitHub heading slugs: strip punctuation, preserve spaces as dashes."""
    return re.sub(r"[^a-z0-9 _-]", "", cat.lower()).replace(" ", "-")


def format_entry(p):
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

    # Each collection is independently updated; JSON is the source of truth.
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
            for p in items:
                lines.append(format_entry(p))
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
