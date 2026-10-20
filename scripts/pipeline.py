# -*- coding: utf-8 -*-
"""Orchestrator (runs automatically on schedule — no human review).

1. If papers.json is empty, bootstrap from the existing README (seed).
2. Self-cleaning dedup: merge duplicates already present in the list.
3. Harvest candidates from all sources (arXiv/DBLP/S2/Crossref).
4. Dedup against existing papers; only genuinely new ones are added.
5. Classify each new paper with the per-repo classify.py.
6. Regenerate README.md from papers.json.
7. Auto-commit (the workflow pushes). Never pushes itself.

Deduplication
-------------
Two entries describe the same paper when ANY of these match:
  * normalized title
  * arXiv id
  * DOI
This matters because the same paper comes back from several sources with
different URLs (arXiv -> arxiv.org/abs/<id>, Semantic Scholar -> semanticscholar
.org/paper/<hash>, Crossref -> doi.org/<doi>). Keying on the URL as well — or
only on the title — either duplicates the same paper or misses real duplicates,
so all three identifiers are used and any match counts.

Run:  python scripts/pipeline.py
"""
import os
import sys
import re
import subprocess
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from lib_common import load_json, save_json, norm_title  # noqa: E402
import harvest  # noqa: E402
import generate_readme  # noqa: E402
import seed_from_readme  # noqa: E402

DATA = os.path.join(ROOT, "data")
PAPERS = os.path.join(DATA, "papers.json")
CONFIG = os.path.join(ROOT, "config.json")
README = os.path.join(ROOT, "README.md")


def _doi_of(p):
    url = (p.get("url") or "").lower()
    m = re.search(r"doi\.org/(10\.[^\s&]+)", url)
    if m:
        return m.group(1).rstrip(".")
    d = p.get("doi")
    return str(d).lower() if d else None


def keys(p):
    """All identifiers for a paper. Any shared key => same paper."""
    ks = set()
    nt = norm_title(p.get("title", ""))
    if nt:
        ks.add(("title", nt))
    if p.get("arxiv_id"):
        ks.add(("arxiv", str(p["arxiv_id"]).lower()))
    d = _doi_of(p)
    if d:
        ks.add(("doi", d))
    return ks


def _score(p):
    """Richer entries win when merging duplicates (curated seed wins most)."""
    s = 0
    if p.get("source") == "seed":
        s += 10
    if p.get("arxiv_id"):
        s += 4
    if p.get("venue") and p.get("venue") != "arXiv":
        s += 3
    if p.get("url"):
        s += 2
    if p.get("year"):
        s += 1
    if p.get("authors"):
        s += 1
    return s


def _merge(a, b):
    """Keep the richer entry and backfill any missing fields from the other."""
    keep, drop = (a, b) if _score(a) >= _score(b) else (b, a)
    for f in ("arxiv_id", "url", "venue", "year", "abstract", "doi"):
        if not keep.get(f) and drop.get(f):
            keep[f] = drop[f]
    if not keep.get("authors") and drop.get("authors"):
        keep["authors"] = drop["authors"]
    return keep


def dedup_inplace(papers):
    """Merge duplicates (same title OR arXiv id OR DOI). Returns (clean, removed)."""
    index = {}
    clean = []
    removed = 0
    for p in papers:
        ks = keys(p)
        hit = None
        for k in ks:
            if k in index:
                hit = index[k]
                break
        if hit is not None:
            merged = _merge(clean[hit], p)
            clean[hit] = merged
            for k in keys(merged):
                index[k] = hit
            removed += 1
            continue
        idx = len(clean)
        clean.append(p)
        for k in ks:
            index[k] = idx
    if removed:
        print(f"[pipeline] dedup merged {removed} duplicate(s)")
    return clean, removed


def main():
    config = load_json(CONFIG, {})
    store = load_json(PAPERS, {"papers": []})
    papers = store.get("papers", [])

    # First run: import the existing curated README so we don't lose it.
    if not papers:
        print("[pipeline] papers.json empty -> seeding from existing README")
        try:
            papers = seed_from_readme.run(config, README, PAPERS)
            print(f"[pipeline] seeded {len(papers)} papers")
        except Exception as ex:
            print(f"[pipeline] seed failed: {ex!r}")

    # Self-cleaning: never carry duplicates forward, even if some slipped in.
    papers, removed = dedup_inplace(papers)

    existing = set()
    for p in papers:
        existing |= keys(p)

    cands = harvest.harvest(config)
    # Relevance gate: for fully-automated lists with no human review, only keep
    # candidates whose TITLE contains a core term for this topic.
    must = [m.lower() for m in config.get("must_include", [])]
    if must:
        before = len(cands)
        cands = [
            c for c in cands
            if any(k in (c.get("title", "") or "").lower() for k in must)
        ]
        print(f"[pipeline] relevance filter: {before} -> {len(cands)} candidates")

    import classify
    added = 0
    for c in cands:
        cks = keys(c)
        if cks & existing:      # any identifier already known -> duplicate
            continue
        try:
            c["category"] = classify.classify(c, config)
        except Exception:
            c["category"] = config.get("default_category")
        c["added"] = datetime.date.today().isoformat()
        papers.append(c)
        existing |= cks
        added += 1

    papers, removed2 = dedup_inplace(papers)  # final safety net before saving
    removed += removed2

    save_json(PAPERS, {"papers": papers})
    generate_readme.generate(papers, config, README)
    print(f"[pipeline] +{added} new paper(s), -{removed} duplicate(s); total {len(papers)}")
    git_commit(added, removed)


def git_commit(added, removed=0):
    if added == 0 and removed == 0:
        print("[pipeline] nothing changed, skip commit")
        return
    try:
        subprocess.check_output(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=ROOT, stderr=subprocess.DEVNULL,
        )
    except Exception:
        return
    subprocess.call(["git", "add", "-A"], cwd=ROOT)
    msg = (
        f"auto-update: +{added} paper(s), dedup removed {removed} duplicate(s) "
        f"({datetime.date.today().isoformat()})"
    )
    subprocess.call(["git", "commit", "-q", "-m", msg], cwd=ROOT)


if __name__ == "__main__":
    main()
