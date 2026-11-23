# -*- coding: utf-8 -*-
"""Source-of-truth literature pipeline.

Recovery: data/papers.json          (automatic, preprints included)
Embodied: data/embodied.json        (automatic, preprints included)
Exclusions: data/ignored.json       (stable identifier blocklist)
Generated view: README.md          (always built from the two JSON sources)

Usage:
    python scripts/pipeline.py                # weekly discovery + regeneration
    python scripts/pipeline.py --render-only  # offline, no discovery or data edits

GitHub Actions publishes only after all tests pass.
"""
import argparse
import copy
import datetime
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from lib_common import load_json, norm_title  # noqa: E402
import classify  # noqa: E402
import generate_readme  # noqa: E402
import embodied_index  # noqa: E402
import harvest  # noqa: E402
import selection  # noqa: E402

CONFIG = ROOT / "config.json"
PAPERS = ROOT / "data" / "papers.json"
EMBODIED = ROOT / "data" / "embodied.json"
IGNORED = ROOT / "data" / "ignored.json"
README = ROOT / "README.md"


def keys(paper):
    """Identifiers that independently establish the same publication."""
    title = norm_title(paper.get("title", ""))
    result = {"title:" + title} if title else set()
    raw_id = paper.get("arxiv_id") or ""
    url = str(paper.get("url") or paper.get("paper_url") or "")
    match = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", url, re.I)
    if not raw_id and match:
        raw_id = match.group(1)
    if raw_id:
        result.add("arxiv:" + re.sub(r"v\d+$", "", str(raw_id)).lower())
    doi = str(paper.get("doi") or "")
    if not doi:
        match = re.search(r"doi\.org/(10\.\d{4,9}/[^?#\s]+)", url, re.I)
        doi = match.group(1) if match else ""
    if doi:
        result.add("doi:" + doi.lower().rstrip(".,;/"))
    return result


def curated_keys(text):
    """Extract curated paper titles and arXiv IDs from numbered Markdown rows."""
    found = set()
    for line in text.splitlines():
        match = re.match(r"^\d+\.\s+\*\*(.*?)\*\*", line)
        if not match:
            continue
        found |= keys({"title": match.group(1)})
        for identifier in re.findall(r"arxiv\.org/abs/(\d{4}\.\d{4,5})", line, re.I):
            found.add("arxiv:" + identifier.lower())
    return found


def enrich(old, new):
    """Backfill metadata without replacing published title/category or curation."""
    merged = dict(old)
    for field in ("arxiv_id", "doi", "year", "authors", "abstract"):
        if not merged.get(field) and new.get(field):
            merged[field] = new[field]
    if not merged.get("url") and new.get("url"):
        merged["url"] = new["url"]
    old_venue = str(merged.get("venue") or "").lower()
    incoming_venue = str(new.get("venue") or "")
    incoming_real = incoming_venue.lower() not in ("", "arxiv", "arxiv.org", "print")
    old_year, new_year = merged.get("year"), new.get("year")
    same_publication_year = not (old_year and new_year) or str(old_year) == str(new_year)
    # Avoid rendering "CVPR 2025" from a 2025 arXiv preprint and 2026
    # proceedings record. Conflicting publication years need manual review.
    if old_venue in ("", "arxiv", "arxiv.org", "print") and incoming_real and same_publication_year:
        merged["venue"] = incoming_venue
    return merged


def dedup_records(records):
    """Merge connected duplicates by title, arXiv ID, or DOI (including chains).

    A matches B by title and B matches C by DOI => all three merge. The first
    record owns the published category and title; later records only enrich it.
    """
    items = list(records)
    parent = list(range(len(items)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        a, b = root(a), root(b)
        if a != b:
            parent[max(a, b)] = min(a, b)

    index = {}
    for i, item in enumerate(items):
        for key in keys(item):
            if key in index:
                union(i, index[key])
            else:
                index[key] = i
    groups = {}
    for i, item in enumerate(items):
        groups.setdefault(root(i), []).append(item)
    deduped = []
    for group in groups.values():
        master = dict(group[0])
        for extra in group[1:]:
            master = enrich(master, extra)
        deduped.append(master)
    return deduped


def _write_if_changed(path, obj):
    """Atomic JSON persistence; a no-op run does not touch tracked files."""
    new_text = json.dumps(obj, ensure_ascii=False, indent=1) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == new_text:
        return False
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    os.replace(tmp, path)
    return True


def _known_index(records):
    result = {}
    for i, item in enumerate(records):
        for k in keys(item):
            result[k] = i
    return result


def process_candidates(papers, embodied, blocked_keys, batches, config, today,
                       *, verify_code=True):
    """Pure scheduled update: automatically publish eligible preprints/papers.

    Existing titles, editorial classifications and partial-code labels survive
    refreshed metadata. No reviewer, approval queue or acceptance requirement.
    """
    papers = [dict(p) for p in papers]
    embodied = copy.deepcopy(embodied)
    embodied.setdefault("papers", [])
    core_index = _known_index(papers)
    robot_index = _known_index(embodied["papers"])
    blocked = set(blocked_keys)
    max_core = int(config.get("discovery", {}).get("new_core_per_run", 30))
    max_embodied = int(config.get("discovery", {}).get("new_embodied_per_run", 15))
    stats = {"core_added": 0, "embodied_added": 0,
             "metadata_updated": 0, "skipped": 0}

    # Process embodied first; never print an eligible embodied paper in both
    # the robotic highlight section and the broad recovery index.
    for track in ("embodied", "core"):
        candidates = dedup_records(batches.get(track, []))
        candidates.sort(key=lambda p: (-(p.get("year") or 0),
                                       (p.get("title") or "").lower()))
        for candidate in candidates:
            identity = keys(candidate)
            if not identity or identity & blocked:
                continue
            robot_id = next((robot_index[k] for k in identity if k in robot_index), None)
            core_id = next((core_index[k] for k in identity if k in core_index), None)
            if robot_id is not None:
                updated = embodied_index.enrich(
                    embodied["papers"][robot_id], candidate, verify_code=verify_code
                )
                if updated != embodied["papers"][robot_id]:
                    embodied["papers"][robot_id] = updated
                    stats["metadata_updated"] += 1
                for k in keys(updated):
                    robot_index[k] = robot_id
                continue
            if core_id is not None:
                updated = enrich(papers[core_id], candidate)
                updated = embodied_index.discover_code(
                    updated, candidate, verify=verify_code
                )
                if updated != papers[core_id]:
                    papers[core_id] = updated
                    stats["metadata_updated"] += 1
                for k in keys(updated):
                    core_index[k] = core_id
                continue

            if track == "core":
                # High-confidence robotics bridges discovered by generic HMR
                # searches are routed to the front section automatically.
                robot_decision = selection.decide(candidate, config, "embodied")[0]
                target = "embodied" if robot_decision == "auto" else "core"
            else:
                target = "embodied"
            decision, _ = selection.decide(candidate, config, target)
            if decision != "auto":
                stats["skipped"] += 1
                continue
            if not (candidate.get("arxiv_id") or
                    str(candidate.get("url") or "").startswith("https://")):
                stats["skipped"] += 1
                continue

            if target == "embodied":
                if stats["embodied_added"] >= max_embodied:
                    continue
                record = embodied_index.new_paper(candidate, today=today)
                record = embodied_index.discover_code(
                    record, candidate, verify=verify_code
                )
                embodied["papers"].append(record)
                i = len(embodied["papers"]) - 1
                for k in keys(record):
                    robot_index[k] = i
                stats["embodied_added"] += 1
            else:
                if stats["core_added"] >= max_core:
                    continue
                record = dict(candidate)
                record["category"] = classify.classify(record, config)
                record["added"] = today.isoformat()
                record = embodied_index.discover_code(
                    record, candidate, verify=verify_code
                )
                papers.append(record)
                i = len(papers) - 1
                for k in keys(record):
                    core_index[k] = i
                stats["core_added"] += 1
    return dedup_records(papers), embodied, stats


def _refresh_ids(papers, embodied, today, limit=30):
    """One small rotating batch per week checks old arXiv metadata for new code.

    Incomplete optional lookups do not stop the regular discovery workflow.
    """
    missing = []
    for p in list(papers) + list(embodied["papers"]):
        if p.get("arxiv_id") and not p.get("code_url"):
            missing.append(str(p["arxiv_id"]).split("v")[0])
    missing = list(dict.fromkeys(missing))
    if not missing:
        return []
    offset = ((today.isocalendar().week - 1) * limit) % len(missing)
    chosen = (missing + missing)[offset: offset + min(limit, len(missing))]
    return harvest.arxiv_by_ids(chosen)


def run(*, render_only=False, today=None):
    today = today or datetime.date.today()
    config = load_json(str(CONFIG), {})
    store = load_json(str(PAPERS), None)
    if not isinstance(store, dict) or not isinstance(store.get("papers"), list):
        raise ValueError("Missing/invalid data/papers.json; never regenerate from README")
    if not store["papers"]:
        raise ValueError("Empty recovery source-of-truth; refusing destructive update")
    embodied = embodied_index.load(EMBODIED)
    if not IGNORED.is_file():
        raise FileNotFoundError("Missing existing identifier blocklist")
    ignored = load_json(str(IGNORED), None)
    if not isinstance(ignored, dict) or not isinstance(ignored.get("keys"), list):
        raise ValueError("Malformed data/ignored.json")

    papers = dedup_records(store["papers"])
    if not render_only:
        batches = {}
        for track in ("core", "embodied"):
            candidates, status = harvest.harvest(config, track=track, today=today)
            batches[track] = candidates
            print(f"[discover:{track}] {status['succeeded']}/"
                  f"{status['attempted']} queries succeeded; "
                  f"{len(candidates)} raw papers")
        batches["embodied"] += _refresh_ids(papers, embodied, today)
        papers, embodied, counts = process_candidates(
            papers, embodied, ignored["keys"], batches, config, today
        )
        print("[update] " + ", ".join(f"{k}: {v}" for k, v in counts.items()))
        _write_if_changed(PAPERS, {"papers": papers})
        _write_if_changed(EMBODIED, embodied)

    # Both collections are automatic; README never acts as input.
    generate_readme.generate(papers, config, str(README))
    print(f"[render] {len(papers)} recovery + {len(embodied['papers'])} embodied papers")



def main():
    parser = argparse.ArgumentParser(description="Update the literature index safely")
    parser.add_argument("--render-only", action="store_true",
                        help="Regenerate README from committed data; no internet calls")
    args = parser.parse_args()
    run(render_only=args.render_only)


if __name__ == "__main__":
    main()
