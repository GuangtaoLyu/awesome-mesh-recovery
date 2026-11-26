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
PENDING = ROOT / "data" / "pending.json"
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
    for field in ("arxiv_id", "doi", "year", "authors", "abstract",
                  "comment", "journal_ref", "submitted_at", "updated_at"):
        if not merged.get(field) and new.get(field):
            merged[field] = new[field]
    if not merged.get("url") and new.get("url"):
        merged["url"] = new["url"]
    # Preserve source agreement, but do not treat number of sources as proof.
    sources = set(merged.get("sources") or ([merged["source"]] if merged.get("source") else []))
    sources.update(new.get("sources") or ([new["source"]] if new.get("source") else []))
    if len(sources) > 1:
        merged["sources"] = sorted(sources)
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


def _recent_key(paper):
    """Use actual update/submission dates, never alphabetical title order."""
    updated = str(paper.get("updated_at") or paper.get("submitted_at") or "")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", updated):
        return updated
    year = paper.get("year")
    return f"{year:04d}-01-01" if isinstance(year, int) else "0000-01-01"


def _target(candidate, track, config):
    """Return the *confirmed* category, or unresolved if evidence is marginal."""
    core = selection.assess(candidate, config, "core")
    robot = selection.assess(candidate, config, "embodied")
    # An explicit human-to-robot contribution takes priority over a generic
    # HMR category, even when found by a core query.
    if robot["decision"] == "auto":
        return "embodied", robot
    if core["decision"] == "auto":
        return "core", core
    if track == "embodied" and robot["decision"] == "verify":
        return "pending", robot
    if core["decision"] == "verify":
        return "pending", core
    return "ignore", robot if track == "embodied" else core


def process_candidates(papers, embodied, blocked_keys, batches, config, today,
                       *, verify_code=True):
    """Pure automatic admission; no silent truncation on alphabetically sorted papers."""
    papers = [dict(p) for p in papers]
    embodied = copy.deepcopy(embodied)
    embodied.setdefault("papers", [])
    core_index = _known_index(papers)
    robot_index = _known_index(embodied["papers"])
    blocked = set(blocked_keys)
    stats = {"core_added": 0, "embodied_added": 0,
             "metadata_updated": 0, "ambiguous": 0, "skipped": 0}

    for track in ("embodied", "core"):
        candidates = dedup_records(batches.get(track, []))
        # Stable sorting: newly updated papers first. Ties preserve source
        # discovery order rather than excluding papers late in the alphabet.
        candidates.sort(key=_recent_key, reverse=True)
        for candidate in candidates:
            identity = keys(candidate)
            if not identity or identity & blocked:
                continue
            robot_id = next((robot_index[k] for k in identity if k in robot_index), None)
            core_id = next((core_index[k] for k in identity if k in core_index), None)
            if robot_id is not None:
                updated = embodied_index.enrich(
                    embodied["papers"][robot_id], candidate, verify_code=verify_code)
                if updated != embodied["papers"][robot_id]:
                    embodied["papers"][robot_id] = updated
                    stats["metadata_updated"] += 1
                for k in keys(updated):
                    robot_index[k] = robot_id
                continue
            if core_id is not None:
                updated = enrich(papers[core_id], candidate)
                updated = embodied_index.discover_code(
                    updated, candidate, verify=verify_code)
                if updated != papers[core_id]:
                    papers[core_id] = updated
                    stats["metadata_updated"] += 1
                for k in keys(updated):
                    core_index[k] = core_id
                continue

            target, assessment = _target(candidate, track, config)
            if target == "pending":
                stats["ambiguous"] += 1
                continue
            if target == "ignore":
                stats["skipped"] += 1
                continue
            if not (candidate.get("arxiv_id") or
                    str(candidate.get("url") or "").startswith("https://")):
                stats["skipped"] += 1
                continue
            if target == "embodied":
                record = embodied_index.new_paper(candidate, today=today)
                record = embodied_index.discover_code(
                    record, candidate, verify=verify_code)
                embodied["papers"].append(record)
                idx = len(embodied["papers"]) - 1
                for k in keys(record):
                    robot_index[k] = idx
                stats["embodied_added"] += 1
            else:
                record = dict(candidate)
                record["category"] = classify.classify(record, config)
                record["added"] = today.isoformat()
                record = embodied_index.discover_code(
                    record, candidate, verify=verify_code)
                papers.append(record)
                idx = len(papers) - 1
                for k in keys(record):
                    core_index[k] = idx
                stats["core_added"] += 1

    # Safety caps protect against a runaway broad query, but do NOT silently
    # truncate. A failed run commits nothing and can be investigated/retried.
    discovery = config.get("discovery", {})
    for track, limit_name in (("core", "max_new_core_per_run"),
                               ("embodied", "max_new_embodied_per_run")):
        maximum = int(discovery.get(limit_name, 100))
        if stats[f"{track}_added"] > maximum:
            raise RuntimeError(
                f"{track} admission spike: {stats[track + '_added']} > {maximum}. "
                "No papers were dropped; raise the safety limit or inspect the query."
            )
    return dedup_records(papers), embodied, stats


def _automated_pending(previous, batches, papers, embodied, blocked, config, today):
    """Keep uncertain leads for re-evaluation without a manual review queue.

    Pending entries are not rendered. Only metadata changes cause JSON writes.
    """
    accepted = set()
    for record in papers + embodied["papers"]:
        accepted.update(keys(record))
    deduped = {}
    for track in ("embodied", "core"):
        for candidate in dedup_records(batches.get(track, [])):
            identity = keys(candidate)
            if not identity or identity & accepted or identity & set(blocked):
                continue
            target, assessment = _target(candidate, track, config)
            if target != "pending":
                continue
            record = {k: v for k, v in candidate.items()
                      if k in ("title", "arxiv_id", "doi", "url", "year",
                               "venue", "abstract", "comment", "source",
                               "sources", "submitted_at", "updated_at")}
            record["track"] = track
            record["first_seen"] = candidate.get("first_seen") or today.isoformat()
            candidate_key = next((k for k in sorted(identity)
                                  if k.startswith("arxiv:")), None)
            candidate_key = candidate_key or next((k for k in sorted(identity)
                                                    if k.startswith("doi:")), None)
            candidate_key = candidate_key or next(iter(sorted(identity)))
            if candidate_key in deduped:
                deduped[candidate_key] = enrich(deduped[candidate_key], record)
            else:
                deduped[candidate_key] = record
    ranked = list(deduped.values())
    ranked.sort(key=_recent_key, reverse=True)
    maximum = int(config.get("discovery", {}).get("max_pending_candidates", 300))
    return ranked[:maximum]


def _resolve_ambiguous(batches, config, today=None):
    """Bounded, fair automatic metadata follow-up for inconclusive candidates.

    Split lookup capacity between newly discovered and previously deferred
    papers; rotate old IDs each week so ambiguous work cannot starve forever.
    """
    today = today or datetime.date.today()
    limit = int(config.get("discovery", {}).get("ambiguous_lookup_per_run", 24))
    targets, old_ids, new_ids = {}, [], []
    for track in ("embodied", "core"):
        for paper in dedup_records(batches.get(track, [])):
            if _target(paper, track, config)[0] != "pending":
                continue
            identifier = paper.get("arxiv_id")
            if not identifier:
                continue
            if identifier not in targets:
                targets[identifier] = set()
                (old_ids if paper.get("first_seen") else new_ids).append(identifier)
            targets[identifier].add(track)
    if not targets or limit <= 0:
        return 0
    if old_ids:
        shift = today.isocalendar().week % len(old_ids)
        old_ids = old_ids[shift:] + old_ids[:shift]
    # At least half the budget can discover *new* evidence; unused slots are
    # automatically filled by the other side of the backlog.
    old_quota = limit // 2 if new_ids else limit
    chosen = old_ids[:old_quota]
    chosen += new_ids[:limit - len(chosen)]
    if len(chosen) < limit:
        chosen += [identifier for identifier in old_ids[old_quota:]
                   if identifier not in chosen][:limit - len(chosen)]
    extra = harvest.arxiv_by_ids(chosen)
    for item in extra:
        for track in targets.get(item.get("arxiv_id"), ()):
            batches[track].append(item)
    return len(extra)


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


def run(*, render_only=False, backfill=False, today=None):
    today = today or datetime.date.today()
    config = load_json(str(CONFIG), {})
    store = load_json(str(PAPERS), None)
    if not isinstance(store, dict) or not isinstance(store.get("papers"), list):
        raise ValueError("Missing/invalid data/papers.json; never regenerate from README")
    if not store["papers"]:
        raise ValueError("Empty recovery source-of-truth; refusing destructive update")
    embodied = embodied_index.load(EMBODIED)
    ignored = load_json(str(IGNORED), None)
    if not isinstance(ignored, dict) or not isinstance(ignored.get("keys"), list):
        raise ValueError("Missing/invalid data/ignored.json")
    pending_store = load_json(str(PENDING), None)
    if not isinstance(pending_store, dict) or not isinstance(
        pending_store.get("candidates"), list
    ):
        raise ValueError("Missing/invalid data/pending.json")

    papers = dedup_records(store["papers"])
    if not render_only:
        # First weekly scheduled run of each month expands the scan depth.
        first_week_of_month = (today.weekday() == 0 and
                               (today - datetime.timedelta(days=7)).month != today.month)
        mode = "backfill" if backfill or first_week_of_month else "weekly"
        batches = {}
        for track in ("core", "embodied"):
            candidates, status = harvest.harvest(config, track=track, today=today, mode=mode)
            batches[track] = candidates
            print(f"[discover:{track}] {mode}: {status['succeeded']}/"
                  f"{status['attempted']} requests succeeded, "
                  f"{status['nonempty']} nonempty; {len(candidates)} raw papers")
            if status["failures"]:
                print(f"[discover:{track}] {len(status['failures'])} failed requests")
        # A pending entry is a *machine-only* recheck target, never a
        # requirement for someone to review or click Approve.
        for item in pending_store["candidates"]:
            if item.get("track") in batches:
                batches[item["track"]].append(item)
        # Refresh old arXiv IDs in their existing track to find newly
        # released code without confusing source provenance.
        refresh = _refresh_ids(papers, embodied, today)
        for item in refresh:
            batches["embodied" if any(
                item.get("arxiv_id") == x.get("arxiv_id") for x in embodied["papers"]
            ) else "core"].append(item)
        filled = _resolve_ambiguous(batches, config, today=today)
        papers, embodied, stats = process_candidates(
            papers, embodied, ignored["keys"], batches, config, today
        )
        pending = _automated_pending(
            pending_store["candidates"], batches, papers, embodied,
            ignored["keys"], config, today
        )
        print("[update] " + ", ".join(f"{k}: {v}" for k, v in stats.items()))
        print(f"[evidence] filled {filled} ambiguous arXiv records; "
              f"{len(pending)} auto-recheck candidates, none published without evidence")
        _write_if_changed(PAPERS, {"papers": papers})
        _write_if_changed(EMBODIED, embodied)
        _write_if_changed(PENDING, {"candidates": pending})

    generate_readme.generate(papers, config, str(README))
    print(f"[render] {len(papers)} recovery + {len(embodied['papers'])} embodied papers")


def main():
    parser = argparse.ArgumentParser(description="Update the literature index safely")
    parser.add_argument("--render-only", action="store_true",
                        help="Regenerate README from committed data; no internet calls")
    parser.add_argument("--backfill", action="store_true",
                        help="Force the deeper monthly discovery scan")
    args = parser.parse_args()
    run(render_only=args.render_only, backfill=args.backfill)


if __name__ == "__main__":
    main()
