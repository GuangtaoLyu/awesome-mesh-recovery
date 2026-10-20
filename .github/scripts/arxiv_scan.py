#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
arxiv_scan.py — lightweight arXiv discovery for small awesome-lists.

Queries arXiv for recent papers on a topic, skips ones already listed in
README.md, and opens a GitHub Issue listing the new candidates for the
maintainer to review & add manually (the curated README stays the source of
truth). No heavy pipeline, no JSON, no auto-edits.

Uses only the Python standard library. Designed to run inside a GitHub
Actions runner where the `gh` CLI is preinstalled.

Environment:
  QUERY         topic keywords. May combine concepts with | (arXiv OR),
                e.g. "text motion retrieval"|"motion grounding"
  WINDOW_DAYS   only consider papers published in the last N days (default 40)
  MAX_RESULTS   max arXiv results to fetch (default 100)
  README_PATH   path to the curated readme (default README.md)
  GH_TOKEN      GitHub token (provided by the workflow)
"""
import os
import re
import sys
import datetime
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

NS = {"atom": "http://www.w3.org/2005/Atom"}

QUERY = os.environ.get("QUERY", "").strip()
WINDOW_DAYS = int(os.environ.get("WINDOW_DAYS", "40"))
MAX_RESULTS = int(os.environ.get("MAX_RESULTS", "100"))
README = os.environ.get("README_PATH", "README.md")


def norm_title(t):
    t = t.lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split())


def build_search(raw):
    """Wrap the user query for the arXiv API. Supports | as OR."""
    raw = raw.strip()
    if "|" in raw:
        parts = [p.strip() for p in raw.split("|") if p.strip()]
        inner = " OR ".join(parts)
    else:
        inner = raw
    return urllib.parse.quote(f"all:({inner})")


def fetch(query, max_results):
    q = build_search(query)
    url = (
        "http://export.arxiv.org/api/query"
        f"?search_query={q}&sortBy=submittedDate"
        f"&sortOrder=descending&max_results={max_results}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "arxiv-scan/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse(xml_bytes):
    root = ET.fromstring(xml_bytes)
    out = []
    for e in root.findall("atom:entry", NS):
        title = " ".join(
            e.findtext("atom:title", default="", namespaces=NS).split()
        )
        published = e.findtext("atom:published", default="", namespaces=NS)[:10]
        url = e.findtext("atom:id", default="", namespaces=NS)
        authors = [
            a.findtext("atom:name", default="", namespaces=NS)
            for a in e.findall("atom:author", namespaces=NS)
        ]
        out.append({"title": title, "published": published, "url": url, "authors": authors})
    return out


def readme_titles(path):
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        text = f.read()
    titles = set()
    for m in re.finditer(r"\*\*(.+?)\*\*", text):
        t = m.group(1).strip()
        if len(t) > 15:  # skip short headings / badges
            titles.add(norm_title(t))
    return titles


def main():
    import subprocess

    if not QUERY:
        print("QUERY not set; nothing to do.")
        return

    print(f"Querying arXiv for: {QUERY!r} (window={WINDOW_DAYS}d, max={MAX_RESULTS})")
    try:
        xml = fetch(QUERY, MAX_RESULTS)
    except Exception as ex:  # network blip must not fail the workflow loudly
        print(f"arXiv fetch failed: {ex!r}; skipping this run.")
        return

    papers = parse(xml)
    print(f"Fetched {len(papers)} recent papers from arXiv.")

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=WINDOW_DAYS)
    existing = readme_titles(README)
    print(f"Already listed in README: {len(existing)} normalized titles.")

    new = []
    for p in papers:
        try:
            pub = datetime.datetime.strptime(p["published"], "%Y-%m-%d")
        except Exception:
            continue
        if pub < cutoff:
            continue
        if norm_title(p["title"]) in existing:
            continue
        new.append(p)

    if not new:
        print("No new candidate papers found. Nothing to do.")
        return

    print(f"Found {len(new)} new candidate(s).")
    rows = []
    for p in new:
        first = p["authors"][0].split()[-1] if p["authors"] else "?"
        others = len(p["authors"]) - 1
        auth = f"{first} et al." if others > 0 else (p["authors"][0] if p["authors"] else "")
        rows.append(f"| {p['published']} | {p['title']} | {auth} | {p['url']} |")
    table = "\n".join(rows)
    body = (
        f"Automated arXiv scan found **{len(new)}** new candidate paper(s) "
        f"for **{QUERY}** (published in the last {WINDOW_DAYS} days, not yet in README).\n\n"
        "Please review and add the relevant ones to the list (keep the existing format).\n\n"
        "| Date | Title | Authors | Link |\n|---|---|---|---|\n"
        f"{table}\n"
    )
    title = (
        f"\uD83D\uDCE1 arXiv scan: {len(new)} new candidate paper(s) "
        f"for '{QUERY}' ({datetime.date.today().isoformat()})"
    )

    p = subprocess.run(
        ["gh", "issue", "create", "--title", title, "--body", body],
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        print("gh issue create failed:")
        print(p.stdout)
        print(p.stderr, file=sys.stderr)
        sys.exit(1)
    print("Issue created:", p.stdout.strip())


if __name__ == "__main__":
    main()
