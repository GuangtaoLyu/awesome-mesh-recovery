# -*- coding: utf-8 -*-
"""Review unpublished candidates without editing generated README.md.

Examples:
  python scripts/review_candidates.py list
  python scripts/review_candidates.py approve 3 --category "Hand, Face & Expressive Mesh"
  python scripts/review_candidates.py reject 5

Embodied candidates are suggestions only: verify the paper, repository, input
modality, and released components, then edit data/embodied.md yourself. The
next generator run removes candidates already present in that curated file.
"""
import argparse
import datetime
import sys

import generate_readme
import pipeline
from lib_common import load_json


def main():
    parser = argparse.ArgumentParser(description="Triage the unlisted literature leads")
    parser.add_argument("action", choices=["list", "approve", "reject"])
    parser.add_argument("index", type=int, nargs="?", help="1-based index from list")
    parser.add_argument("--category", help="Confirmed category for core paper approval")
    args = parser.parse_args()

    config = load_json(str(pipeline.CONFIG), {})
    queue = load_json(str(pipeline.QUEUE), {"items": []})["items"]
    if args.action == "list":
        if not queue:
            print("Review queue is empty.")
        for i, p in enumerate(queue, 1):
            print(f"{i:3d} [{p.get('track', '?')}] "
                  f"{p.get('year') or '?'}  {p.get('title')}  "
                  f"({p.get('reason', 'needs review')})")
        return

    if not args.index or args.index < 1 or args.index > len(queue):
        parser.error("Choose a current 1-based index from the list command")
    candidate = dict(queue[args.index - 1])
    if args.action == "approve" and candidate.get("track") != "core":
        parser.error("Embodied proposals must be verified and added to data/embodied.md manually")
    if args.category and args.category not in config["taxonomy"]:
        parser.error("Category must match config.json taxonomy")

    queue.pop(args.index - 1)
    if args.action == "reject":
        ignored = load_json(str(pipeline.IGNORED), {"keys": []})
        ignored["keys"] = sorted(set(ignored["keys"]) | pipeline.keys(candidate))
        pipeline._write_if_changed(pipeline.IGNORED, ignored)
        pipeline._write_if_changed(pipeline.QUEUE, {"items": queue})
        print("Rejected candidate; all known identifiers are suppressed on future runs.")
        return

    for key in ("track", "reason", "first_seen"):
        candidate.pop(key, None)
    candidate["category"] = args.category or pipeline.classify.classify(candidate, config)
    candidate["added"] = datetime.date.today().isoformat()
    candidate["reviewed"] = True

    store = load_json(str(pipeline.PAPERS), {"papers": []})
    if not store["papers"]:
        raise ValueError("Cannot approve into an empty source-of-truth store")
    papers = pipeline.dedup_records(store["papers"] + [candidate])
    pipeline._write_if_changed(pipeline.PAPERS, {"papers": papers})
    pipeline._write_if_changed(pipeline.QUEUE, {"items": queue})
    generate_readme.generate(papers, config, str(pipeline.README))
    print(f"Approved into {candidate['category']}; regenerated README.")


if __name__ == "__main__":
    main()
