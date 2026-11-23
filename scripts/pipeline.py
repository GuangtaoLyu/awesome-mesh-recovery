# -*- coding: utf-8 -*-
"""Source-of-truth literature pipeline.

Accepted HMR: data/papers.json        (strict automatic admission)
Curated robotics: data/embodied.md   (human-reviewed; NEVER auto-overwritten)
Review leads: data/review_queue.json  (unpublished discovery suggestions)
Rejections: data/ignored.json        (stable identifiers, no re-suggestion)
Generated view: README.md            (always built from accepted + curated)

Usage:
    python scripts/pipeline.py                # weekly discovery + regeneration
    python scripts/pipeline.py --render-only  # offline, no discovery or data edits

Committing is done by GitHub Actions only AFTER the generated-view tests pass.
"""
import argparse
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
import harvest  # noqa: E402
import selection  # noqa: E402

CONFIG = ROOT / "config.json"
PAPERS = ROOT / "data" / "papers.json"
CURATED = ROOT / "data" / "embodied.md"
QUEUE = ROOT / "data" / "review_queue.json"
IGNORED = ROOT / "data" / "ignored.json"
README = ROOT / "README.md"


def keys(paper):
    """Identifiers that independently establish the same publication."""
    title = norm_title(paper.get("title", ""))
    result = {"title:" + title} if title else set()
    raw_id = paper.get("arxiv_id") or ""
    url = str(paper.get("url") or "")
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
    if old_venue in ("", "arxiv", "arxiv.org", "print") and incoming_venue.lower() not in (
        "", "arxiv", "arxiv.org", "print"
    ):
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


def process_candidates(papers, queue, blocked_keys, curated, batches, config, today):
    """Pure candidate processing; returns updated papers, queue and counters."""
    papers = [dict(p) for p in papers]
    queue = [dict(q) for q in queue]
    indexed = _known_index(papers)
    queued = _known_index(queue)
    blocked_keys = set(blocked_keys)
    counters = {"auto_added": 0, "enriched": 0, "review_added": 0, "ignored": 0,
                "queue_capacity_skips": 0}
    max_queue = int(config["discovery"]["review_queue_max"])
    per_track = int(config["discovery"]["new_review_per_run_per_track"])

    for track in ("core", "embodied"):
        candidates = dedup_records(batches.get(track, []))
        # The APIs each return ranked results; newer works are examined first.
        candidates.sort(key=lambda p: -(p.get("year") or 0))
        added_review_for_track = 0
        for candidate in candidates:
            identity = keys(candidate)
            if not identity:
                continue
            if identity & curated or identity & blocked_keys:
                continue
            seen = next((indexed[k] for k in identity if k in indexed), None)
            if seen is not None:
                enriched = enrich(papers[seen], candidate)
                if enriched != papers[seen]:
                    papers[seen] = enriched
                    counters["enriched"] += 1
                    for k in keys(enriched):
                        indexed[k] = seen
                continue
            if any(k in queued for k in identity):
                continue
            decision, reason = selection.decide(candidate, config, track)
            if decision == "ignore":
                counters["ignored"] += 1
                continue
            if decision == "auto" and track == "core":
                record = dict(candidate)
                record["category"] = classify.classify(record, config)
                record["added"] = today.isoformat()
                papers.append(record)
                idx = len(papers) - 1
                for k in keys(record):
                    indexed[k] = idx
                counters["auto_added"] += 1
                continue
            if len(queue) >= max_queue or added_review_for_track >= per_track:
                counters["queue_capacity_skips"] += 1
                continue
            record = dict(candidate)
            record["track"] = track
            record["reason"] = reason
            record["first_seen"] = today.isoformat()
            queue.append(record)
            idx = len(queue) - 1
            for k in keys(record):
                queued[k] = idx
            added_review_for_track += 1
            counters["review_added"] += 1

    # A new curated / accepted paper should disappear from the review queue.
    accepted = set(indexed)
    queue = [q for q in queue
             if not (keys(q) & accepted or keys(q) & curated or keys(q) & blocked_keys)]
    return papers, queue, counters


def run(*, render_only=False, today=None):
    today = today or datetime.date.today()
    config = load_json(str(CONFIG), {})
    store = load_json(str(PAPERS), None)
    if not isinstance(store, dict) or not isinstance(store.get("papers"), list):
        raise ValueError("data/papers.json is missing/invalid; refusing to bootstrap from README")
    if not store["papers"]:
        raise ValueError("Empty accepted-paper store; refusing destructive regeneration")
    if not CURATED.is_file():
        raise FileNotFoundError("Missing human-reviewed data/embodied.md")
    curated_text = CURATED.read_text(encoding="utf-8")
    curated = curated_keys(curated_text)
    if len(curated) < 2:
        raise ValueError("Curated embodied section is unexpectedly empty")

    papers = dedup_records(store["papers"])
    if not QUEUE.is_file() or not IGNORED.is_file():
        raise FileNotFoundError("Review queue or rejection data is missing; refusing to discard decisions")
    queue_data = load_json(str(QUEUE), None)
    ignored_data = load_json(str(IGNORED), None)
    if not isinstance(queue_data, dict) or not isinstance(queue_data.get("items"), list):
        raise ValueError("Invalid review_queue.json")
    if not isinstance(ignored_data, dict) or not isinstance(ignored_data.get("keys"), list):
        raise ValueError("Invalid ignored.json")
    queue = queue_data["items"]

    if not render_only:
        batches = {}
        for track in ("core", "embodied"):
            candidates, status = harvest.harvest(config, track=track, today=today)
            batches[track] = candidates
            print(f"[discover:{track}] {status['succeeded']}/{status['attempted']} "
                  f"queries succeeded, {len(candidates)} raw candidates")
        papers, queue, stats = process_candidates(
            papers, queue, ignored_data["keys"], curated, batches, config, today
        )
        print(f"[select] +{stats['auto_added']} indexed, "
              f"+{stats['review_added']} review leads, "
              f"{stats['enriched']} metadata enrichments, "
              f"{stats['ignored']} unrelated ignored, "
              f"{stats['queue_capacity_skips']} unqueued due to limits")
        # A new DOI/arXiv connection can bridge two older indexed records.
        papers = dedup_records(papers)
        _write_if_changed(PAPERS, {"papers": papers})
        _write_if_changed(QUEUE, {"items": queue})

    # README is always generated, never edited as the primary source.
    generate_readme.generate(papers, config, str(README))
    print(f"[render] {len(papers)} indexed papers; {len(queue)} pending review leads")


def main():
    parser = argparse.ArgumentParser(description="Update the literature index safely")
    parser.add_argument("--render-only", action="store_true",
                        help="Regenerate README from committed data; no internet calls")
    args = parser.parse_args()
    run(render_only=args.render_only)


if __name__ == "__main__":
    main()
