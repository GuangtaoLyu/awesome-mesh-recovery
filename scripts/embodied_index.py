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
import urllib.parse
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
        return f"arXiv preprint ({year})" if year else "arXiv preprint"
    return f"Preprint / venue unverified ({year})" if year else "Publication unverified"


def _link(label, url):
    return f"[{label}]({url})" if url and str(url).startswith("https://") else ""


def format_paper(index, item):
    title = _strip(item["title"])
    publication = _publication(item)
    role = _strip(item.get("role")) or "Recovery / robotics bridge"
    links = [
        _link("Paper", item.get("paper_url")),
        _link("Code" if item.get("code_status") == "repository" else
              CODE_LABELS.get(item.get("code_status"), "Code (scope unverified)"),
              item.get("code_url")),
        _link("Project", item.get("project_url")),
        _link("Models", item.get("models_url")),
    ]
    links = [s for s in links if s]
    if not item.get("code_url"):
        links.append("Code: unverified")
    info = f"{index}. **{title}** — *{publication}* · **{role}**"
    if links:
        info += " · " + " · ".join(links)
    summary = _strip(item.get("summary")).rstrip(".")
    if summary:
        info += "\n   - " + summary + "."
    return info


def render(data):
    lines = [
        "## Embodied Motion Recovery & Robot Tracking",
        "",
        "A focused **research-to-robot bridge**, spanning video/hand recovery, "
        "motion retargeting, teleoperation and tracking. Papers are included "
        "**regardless of conference acceptance**; arXiv-only work is labeled "
        "as a preprint. New papers and links are found by the weekly automated "
        "pipeline. A code link verifies a repository, **not** a complete release.",
        "",
    ]
    papers = data.get("papers", [])
    for group in GROUPS:
        lines += ["### " + group, ""]
        group_papers = [p for p in papers if p.get("group") == group]
        # Fresh research first, then stable original position on equal year.
        group_papers.sort(key=lambda p: -(p.get("year") or 0))
        for i, p in enumerate(group_papers, 1):
            lines.append(format_paper(i, p))
        lines.append("")
    tools = data.get("toolkits", [])
    if tools:
        lines += ["### Reusable Retargeting Toolkit", ""]
        for t in tools:
            link = _link("Code", t.get("code_url"))
            lines.append(f"- **{t['name']}** — {_strip(t.get('role'))}: "
                         f"{_strip(t.get('summary')).rstrip('.')}. {link}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _github_candidates(candidate):
    """Only explicit GitHub URLs supplied by a primary research record."""
    sources = (candidate.get("comment"), candidate.get("abstract"),
               candidate.get("code_url"))
    found = []
    for source in sources:
        text = str(source or "")
        for match in re.finditer(
            r"https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)",
            text, flags=re.I,
        ):
            owner, name = match.groups()
            name = name.rstrip(".,:;])}")
            if owner.lower() in ("features", "topics", "orgs", "users", "search"):
                continue
            url = f"https://github.com/{owner}/{name}"
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
    match = re.fullmatch(
        r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", url or ""
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
    text = (str(candidate.get("title") or "") + " " +
            str(candidate.get("abstract") or "")).lower()
    title = str(candidate.get("title") or "").lower()
    if re.search(r"\b(humanoid|whole.body|full.body|locomotion)\b", title):
        group = GROUPS[0]
    elif re.search(r"\b(hand|dexterous|grasp|manipulation|bimanual)\b", text):
        group = GROUPS[1]
    else:
        group = GROUPS[0]
    visual = bool(re.search(r"\b(video|rgb|vision|monocular|egocentric|visual)\b", text))
    execution = bool(re.search(
        r"\b(retarget|retargeting|robot control|robot policy|tracking|"
        r"imitation|teleoperation|manipulation)\b", text
    ))
    if visual and execution:
        role = "Vision → Robot"
    elif re.search(r"\b(teleoperation|teleoperated|xr|vr headset)\b", title):
        role = "Teleoperation"
    elif re.search(r"\b(retarget|retargeting)\b", title):
        role = "Retargeting"
    elif re.search(r"\b(track|tracking|policy|control)\b", title):
        role = "Tracking / control"
    else:
        role = "Recovery / retargeting"
    return group, role


def new_paper(candidate, *, today):
    group, role = classify(candidate)
    year = candidate.get("year") or today.year
    venue = _strip(candidate.get("venue"))
    real_venue = venue and venue.lower() not in ("arxiv", "arxiv.org", "print")
    publication = f"{venue} {year}" if real_venue else str(year)
    abstract = str(candidate.get("abstract") or "").lower()
    if re.search(r"\b(monocular|single.camera)\b", abstract):
        modality = "monocular video"
    elif re.search(r"\b(egocentric|first.person)\b", abstract):
        modality = "egocentric video"
    elif re.search(r"\b(video|rgb|visual)\b", abstract):
        modality = "video"
    elif re.search(r"\b(mocap|motion capture)\b", abstract):
        modality = "human motion capture"
    else:
        modality = "human motion / interaction"
    output = ("humanoid robot motion" if group == GROUPS[0]
              else "dexterous hand / robot interaction")
    summary = f"Input: {modality}; related output: {output}"
    arxiv_id = candidate.get("arxiv_id")
    paper_url = (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else
                 candidate.get("url"))
    return {
        "title": _strip(candidate.get("title")),
        "group": group,
        "year": year,
        "publication": publication,
        "publication_status": "venue-listed" if real_venue else "preprint",
        "arxiv_id": arxiv_id,
        "paper_url": paper_url,
        "role": role,
        "summary": summary,
        "code_url": None,
        "code_status": "unverified",
        "project_url": None,
        "models_url": None,
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
