# -*- coding: utf-8 -*-
"""Best-effort, per-query multi-source discovery with explicit diagnostics.

Sources can fail independently (notably Semantic Scholar rate limits). A
zero-success CORE discovery must fail the weekly run rather than masquerade
as a successful update. Each query is retried and bounded; no paid APIs.
"""
import datetime
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ATOM = {"a": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom"}


def _get(url, *, retries=2, timeout=20):
    req = urllib.request.Request(
        url, headers={"User-Agent": "awesome-mesh-recovery/2.0 (GitHub literature index)"}
    )
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries:
                raise
        time.sleep(2 * (attempt + 1))


def _norm_title(text):
    return " ".join(str(text or "").split()).rstrip(".")


def _authors(values):
    return [str(v).strip() for v in values if str(v).strip()]


def _arxiv_id(value):
    match = re.search(r"arxiv.org/(?:abs|pdf)/(\d{4}\.\d{4,5})", str(value or ""), flags=re.I)
    return match.group(1) if match else None


def _param(url, **params):
    return url + "?" + urllib.parse.urlencode(params)


# arXiv guidance asks automated clients to space requests, including batches.
_last_arxiv_request = 0.0


def _arxiv_fetch(url):
    global _last_arxiv_request
    elapsed = time.monotonic() - _last_arxiv_request
    if _last_arxiv_request and elapsed < 3.0:
        time.sleep(3.0 - elapsed)
    _last_arxiv_request = time.monotonic()
    return _get(url)


def arxiv(query, since_year, limit, *, sort_by="lastUpdatedDate"):
    """Search a bounded number of arXiv results with pagination.

    Weekly scans sort on lastUpdatedDate to catch revised preprints; monthly
    backfills use submittedDate to recover previously missed original papers.
    """
    out, seen = [], set()
    page_size = 75
    for start in range(0, limit, page_size):
        url = _param(
            "https://export.arxiv.org/api/query",
            search_query='all:"' + query + '"',
            sortBy=sort_by,
            sortOrder="descending",
            start=start,
            max_results=min(page_size, limit - start),
        )
        root = ET.fromstring(_arxiv_fetch(url))
        entries = root.findall("a:entry", ATOM)
        if not entries:
            break
        for entry in entries:
            title = _norm_title(entry.findtext("a:title", default="", namespaces=ATOM))
            posted = entry.findtext("a:published", default="", namespaces=ATOM)
            updated = entry.findtext("a:updated", default="", namespaces=ATOM)
            year = int(posted[:4]) if posted[:4].isdigit() else None
            arxiv_id = _arxiv_id(entry.findtext("a:id", default="", namespaces=ATOM))
            if not title or not arxiv_id or arxiv_id in seen or (year and year < since_year):
                continue
            seen.add(arxiv_id)
            out.append({
                "title": title,
                "authors": _authors(e.findtext("a:name", default="", namespaces=ATOM)
                                    for e in entry.findall("a:author", ATOM)),
                "year": year,
                "submitted_at": posted[:10],
                "updated_at": updated[:10],
                "venue": "arXiv",
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "arxiv_id": arxiv_id,
                "abstract": _norm_title(entry.findtext("a:summary", default="", namespaces=ATOM)),
                "comment": _norm_title(entry.findtext("arxiv:comment", default="", namespaces=ATOM)),
                "journal_ref": _norm_title(entry.findtext("arxiv:journal_ref", default="", namespaces=ATOM)),
                "source": "arxiv",
            })
        if len(entries) < min(page_size, limit - start):
            break
    return out


def dblp(query, since_year, limit):
    url = _param("https://dblp.org/search/publ/api", q=query, format="json", h=limit)
    data = json.loads(_get(url))
    found = []
    for result in data.get("result", {}).get("hits", {}).get("hit", []):
        item = result.get("info", {})
        title = _norm_title(item.get("title"))
        raw_year = item.get("year")
        year = int(raw_year) if str(raw_year).isdigit() else None
        if not title or (year and year < since_year):
            continue
        raw_authors = item.get("authors", {}).get("author", [])
        if isinstance(raw_authors, dict):
            raw_authors = [raw_authors]
        authors = _authors(a.get("text", "") if isinstance(a, dict) else a
                           for a in raw_authors)
        ee = item.get("ee") or item.get("url") or ""
        if isinstance(ee, list):
            ee = ee[0] if ee else ""
        found.append({
            "title": title, "authors": authors, "year": year,
            "venue": item.get("venue") or "", "url": ee,
            "arxiv_id": _arxiv_id(ee), "source": "dblp",
        })
    return found


def semantic_scholar(query, since_year, limit):
    url = _param(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        query=query, fields="title,authors,year,venue,externalIds,url,abstract",
        limit=min(limit, 100),
    )
    data = json.loads(_get(url))
    found = []
    for item in data.get("data", []):
        title = _norm_title(item.get("title"))
        year = item.get("year")
        if not title or (year and year < since_year):
            continue
        ids = item.get("externalIds") or {}
        arxiv_id = ids.get("ArXiv")
        doi = ids.get("DOI")
        url = (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else
               (f"https://doi.org/{doi}" if doi else item.get("url") or ""))
        found.append({
            "title": title,
            "authors": _authors(a.get("name", "") for a in item.get("authors") or []),
            "year": year,
            "venue": item.get("venue") or "",
            "url": url, "arxiv_id": arxiv_id, "doi": doi,
            "abstract": _norm_title(item.get("abstract")),
            "source": "s2",
        })
    return found


def crossref(query, since_year, limit):
    url = _param(
        "https://api.crossref.org/works",
        **{
            "query.title": query,
            "filter": f"from-pub-date:{since_year}-01-01",
            "sort": "published",
            "order": "desc",
            "rows": limit,
        },
    )
    data = json.loads(_get(url))
    found = []
    for item in data.get("message", {}).get("items", []):
        titles = item.get("title") or []
        title = _norm_title(titles[0] if titles else "")
        date_parts = []
        for field in ("published", "issued", "published-print"):
            parts = (item.get(field) or {}).get("date-parts") or []
            if parts and parts[0]:
                date_parts = parts[0]
                break
        year = date_parts[0] if date_parts and isinstance(date_parts[0], int) else None
        if not title or (year and year < since_year):
            continue
        doi = item.get("DOI")
        raw_venue = item.get("container-title") or []
        found.append({
            "title": title,
            "authors": _authors(" ".join((a.get("given", ""), a.get("family", "")))
                                for a in item.get("author") or []),
            "year": year,
            "venue": " ".join(raw_venue) if isinstance(raw_venue, list) else raw_venue,
            "url": f"https://doi.org/{doi}" if doi else item.get("URL") or "",
            "arxiv_id": None, "doi": doi, "source": "crossref",
        })
    return found


SOURCES = {
    "arxiv": arxiv,
    "dblp": dblp,
    "s2": semantic_scholar,
    "crossref": crossref,
}


def harvest(config, *, track="core", today=None, mode="weekly"):
    """Return candidates and diagnostics, using rotating balanced source scans.

    A larger monthly backfill avoids weekly search-rank truncation. Source
    failures do not block other sources; a complete core outage fails safely.
    """
    if mode not in ("weekly", "backfill"):
        raise ValueError(f"Unsupported discovery mode: {mode}")
    today = today or datetime.date.today()
    lookback = int(config.get("discovery", {}).get("years_back", 3))
    since_year = max(int(config.get("year_from", 2015)), today.year - lookback + 1)
    query_map = config["queries" if track == "core" else "embodied_queries"]
    discovery = config.get("discovery", {})
    limit = int(discovery.get(
        "backfill_query_limit" if mode == "backfill" else "weekly_query_limit",
        180 if mode == "backfill" else 75,
    ))
    found = []
    status = {"track": track, "mode": mode, "attempted": 0,
              "succeeded": 0, "nonempty": 0, "failures": [],
              "per_source": {}}
    for name, handler in SOURCES.items():
        queries = list(dict.fromkeys(query_map.get(name, [])))
        if not queries:
            continue
        # Do not systematically starve the last query if an API is rate limited.
        shift = today.isocalendar().week % len(queries)
        queries = queries[shift:] + queries[:shift]
        for query in queries:
            status["attempted"] += 1
            try:
                if name == "arxiv" and handler is arxiv:
                    items = arxiv(
                        query, since_year, limit,
                        sort_by=("submittedDate" if mode == "backfill" else "lastUpdatedDate"),
                    )
                else:
                    items = handler(query, since_year, min(limit, 100))
                found.extend(items)
                status["succeeded"] += 1
                if items:
                    status["nonempty"] += 1
                info = status["per_source"].setdefault(name, {"queries": 0, "results": 0})
                info["queries"] += 1
                info["results"] += len(items)
            except Exception as ex:
                msg = f"{name}: {query}: {type(ex).__name__}: {ex}"
                status["failures"].append(msg)
                print(f"[harvest] WARNING {msg}")
    if track == "core" and not status["nonempty"]:
        raise RuntimeError("All core discovery requests failed or returned no papers")
    return found, status


def arxiv_by_ids(ids, *, chunk_size=30):
    """Refresh older indexed preprints regardless of the discovery time window.

    Used to look for author-supplied code URLs in abstract/comment updates.
    Failure of this optional enrichment does not block weekly discovery.
    """
    ids = list(dict.fromkeys(
        str(x).split("v")[0] for x in ids if re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", str(x))
    ))
    out = []
    for start in range(0, len(ids), chunk_size):
        chunk = ids[start:start + chunk_size]
        try:
            url = _param("https://export.arxiv.org/api/query",
                         id_list=",".join(chunk), max_results=len(chunk))
            root = ET.fromstring(_arxiv_fetch(url))
            for entry in root.findall("a:entry", ATOM):
                aid = _arxiv_id(entry.findtext("a:id", default="", namespaces=ATOM))
                if not aid or aid not in chunk:
                    continue
                pub = entry.findtext("a:published", default="", namespaces=ATOM)
                out.append({
                    "title": _norm_title(entry.findtext("a:title", default="", namespaces=ATOM)),
                    "arxiv_id": aid,
                    "year": int(pub[:4]) if pub[:4].isdigit() else None,
                    "submitted_at": pub[:10],
                    "updated_at": entry.findtext("a:updated", default="", namespaces=ATOM)[:10],
                    "venue": "arXiv",
                    "url": "https://arxiv.org/abs/" + aid,
                    "abstract": _norm_title(entry.findtext("a:summary", default="", namespaces=ATOM)),
                    "comment": _norm_title(entry.findtext("arxiv:comment", default="", namespaces=ATOM)),
                    "journal_ref": _norm_title(entry.findtext("arxiv:journal_ref", default="", namespaces=ATOM)),
                    "source": "arxiv",
                })
        except Exception as ex:
            print(f"[arxiv-refresh] optional batch failed: {type(ex).__name__}: {ex}")
    return out
