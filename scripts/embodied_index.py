# -*- coding: utf-8 -*-
"""Structured embodied-paper index: classification, rendering and safe link updates.

All new research is discovered/accepted by the scheduled pipeline, not by
manual editing. A GitHub repository link proves only that the repository
exists; it never proves that the entire paper pipeline is released.
"""
import datetime
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

GROUPS = (
    "Whole-Body Recovery → Humanoid Robots",
    "Hand-Object Recovery → Dexterous Robots",
)
CODE_LABELS = {
    "repository": "Code (repository)",
    "partial": "Code (partial release)",
    "demo": "Code (demo only)",
    "unverified": "Code not verified",
}


def load(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("papers"), list):
        raise ValueError("Invalid structured embodied paper index")
    if not data["papers"]:
        raise ValueError("Embodied index is empty; refusing destructive update")
    for item in data["papers"]:
        if not item.get("title") or item.get("group") not in GROUPS:
            raise ValueError(f"Malformed embodied entry: {item.get('title')!r}")
    return data


def _strip(value):
    return " ".join(str(value or "").split()).strip()


def _publication(item):
    venue = _strip(item.get("publication"))
    year = item.get("year")
    status = item.get("publication_status", "preprint")
    if status == "venue-listed" and venue:
        return venue
    if item.get("arxiv_id"):
        return f"arXiv {year}" if year else "arXiv"
    return f"Preprint {year}" if year else "Venue unverified"


def _link(label, url):
    return f"[{label}]({url})" if url and str(url).startswith("https://") else ""


def format_paper(item):
    """One-line awesome-list style; never repeat per-paper task descriptions."""
    title = _strip(item["title"])
    links = [
        _link("Paper", item.get("paper_url")),
        _link("Code" if item.get("code_status") == "repository" else
              CODE_LABELS.get(item.get("code_status"), "Code"),
              item.get("code_url")),
        _link("Project", item.get("project_url")),
        _link("Models", item.get("models_url")),
    ]
    links = [link for link in links if link]
    return f"- **{title}** ({_publication(item)}) — " + " · ".join(links)


def render(data):
    lines = [
        "## Embodied Motion Recovery & Robot Tracking",
        "",
        "From human/hand recovery to robot retargeting, teleoperation and tracking. "
        "**arXiv preprints are included**; links to code are shown only when "
        "found, and a code link does not imply a complete release.",
        "",
    ]
    for group in GROUPS:
        lines += ["### " + group, ""]
        group_papers = [p for p in data.get("papers", []) if p.get("group") == group]
        group_papers.sort(key=lambda p: (-(p.get("year") or 0), p["title"].lower()))
        lines.extend(format_paper(p) for p in group_papers)
        lines.append("")
    if data.get("toolkits"):
        lines += ["### Reusable Retargeting Toolkit", ""]
        for t in data["toolkits"]:
            url = _link("Code", t.get("code_url"))
            lines.append(f"- **{t['name']}** — {url}" if url else f"- **{t['name']}**")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


_CODE_CONTEXT = re.compile(
    r"\b(?:source code|official code|code(?:s)?(?: and (?:data|models|"
    r"weights|checkpoints))?|implementation|codebase)\b"
    r".{0,70}\b(?:available|released|published|at|on|here|:)\b"
    r"|\b(?:code(?: and (?:data|models|weights|checkpoints))?|implementation|repository)\s*:\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _github_candidates(candidate):
    """Author-declared code only: never mistake cited dependencies for our code."""
    found = []

    # Explicitly structured author-supplied code metadata is direct evidence.
    sources = [(str(candidate.get("code_url") or ""), True)]
    # Generic URLs in an abstract/comment are *not* proof of official code.
    sources += [(str(candidate.get(field) or ""), False)
                for field in ("comment", "abstract")]
    for text, explicit in sources:
        for match in re.finditer(
            r"https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)",
            text, flags=re.I,
        ):
            owner, name = match.groups()
            name = name.rstrip(".,:;])}")
            if owner.lower() in ("features", "topics", "orgs", "users", "search"):
                continue
            prefix = text[max(0, match.start() - 150):match.start()]
            # Require an explicit release statement in the same sentence,
            # e.g. "Our code is available at https://github.com/...".
            # A bare GitHub URL or a citation to another model is not enough.
            phrase = re.split(r"[.!?;\n]", prefix)[-1]
            if not explicit and not _CODE_CONTEXT.search(phrase):
                continue
            url = f"https://github.com/{owner}/{name}"
            suffix = re.match(
                r"/tree/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*",
                text[match.end():],
            )
            if suffix:
                url += suffix.group(0).rstrip(".,:;])}")
            if url not in found:
                found.append(url)
    return found


def _http_get(url, timeout=8):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "awesome-mesh-recovery/3.0",
                 "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def _official_repository(url):
    match = re.match(
        r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:/|$)",
        url or "",
    )
    if not match:
        return False
    owner, repo = match.groups()
    try:
        data = json.loads(_http_get(
            f"https://api.github.com/repos/{owner}/{repo}"
        ))
        return bool(data.get("full_name", "").lower() == f"{owner}/{repo}".lower())
    except (ValueError, OSError, urllib.error.HTTPError):
        return False


def discover_code(item, candidate, *, verify=True):
    """Discover a repo only from author-supplied metadata, not a fuzzy search."""
    if item.get("code_url"):
        return item
    for url in _github_candidates(candidate):
        if verify and not _official_repository(url):
            continue
        item = dict(item)
        item["code_url"] = url
        item["code_status"] = "repository"
        item["code_checked"] = datetime.date.today().isoformat()
        return item
    return item


def classify(candidate):
    """Use the subject of the paper title for the two broad robot tracks."""
    title = str(candidate.get("title") or "").lower()
    abstract = str(candidate.get("abstract") or "").lower()
    if re.search(r"\b(hand|dexterous|grasp|bimanual|hand.object)\b", title):
        return GROUPS[1]
    if re.search(r"\b(humanoid|whole.body|full.body|locomotion)\b", title):
        return GROUPS[0]
    if re.search(r"\b(hand|dexterous|bimanual)\b", abstract):
        return GROUPS[1]
    return GROUPS[0]


def new_paper(candidate, *, today):
    """Minimal metadata; no invented publication year or unused summaries."""
    group = classify(candidate)
    arxiv_id = candidate.get("arxiv_id")
    year = candidate.get("year")
    if not year and arxiv_id and re.match(r"^\d{4}\.\d{4,5}$", str(arxiv_id)):
        year = 2000 + int(str(arxiv_id)[:2])
    venue = _strip(candidate.get("venue"))
    real_venue = venue and venue.lower() not in ("arxiv", "arxiv.org", "print")
    publication = " ".join(str(x) for x in (venue, year) if x) if real_venue else ""
    paper_url = (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id
                 else candidate.get("url"))
    return {
        "title": _strip(candidate.get("title")),
        "group": group,
        "year": year,
        "publication": publication,
        "publication_status": "venue-listed" if real_venue else "preprint",
        "arxiv_id": arxiv_id,
        "paper_url": paper_url,
        "code_url": None,
        "code_status": "unverified",
        "origin": "auto",
        "added": today.isoformat(),
    }


def enrich(item, candidate, *, verify_code=True):
    """Safe metadata refresh of existing work, preserving authored summaries."""
    out = dict(item)
    for key in ("arxiv_id", "paper_url"):
        if not out.get(key) and candidate.get("arxiv_id"):
            out["arxiv_id"] = candidate["arxiv_id"]
            out["paper_url"] = "https://arxiv.org/abs/" + candidate["arxiv_id"]
    venue = _strip(candidate.get("venue"))
    year = candidate.get("year")
    if (out.get("publication_status") != "venue-listed" and year and
            str(year) == str(out.get("year")) and venue.lower()
            not in ("", "arxiv", "arxiv.org", "print")):
        out["publication_status"] = "venue-listed"
        out["publication"] = f"{venue} {year}"
    out = discover_code(out, candidate, verify=verify_code)
    return out
