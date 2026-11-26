# -*- coding: utf-8 -*-
"""Best-effort, per-query multi-source discovery with explicit diagnostics.

Sources can fail independently (notably Semantic Scholar rate limits). A
zero-success CORE discovery must fail the weekly run rather than masquerade
as a successful update. Each query is retried and bounded; no paid APIs.
"""
import datetime
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ATOM = {"a": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom"}


class BadSourceResponse(RuntimeError):
    """Provider served a challenge/error page or malformed structured data."""


def _json_response(body, provider):
    """Explicitly recognize 200/HTML bot challenges instead of generic JSON errors."""
    stripped = body.lstrip()
    if not stripped or stripped[:1] not in (b"{", b"["):
        kind = "HTML/challenge page" if stripped.startswith((b"<", b"<!")) else "empty/non-JSON response"
        raise BadSourceResponse(f"{provider}: {kind} instead of JSON")
    try:
        parsed = json.loads(stripped)
    except (UnicodeDecodeError, json.JSONDecodeError) as ex:
        raise BadSourceResponse(f"{provider}: invalid JSON payload") from ex
    if not isinstance(parsed, dict):
        raise BadSourceResponse(f"{provider}: unexpected JSON document type")
    return parsed


# dblp recommends pausing between requests to avoid temporary blocking.
_last_dblp_request = 0.0


def _dblp_json(query, limit):
    """Try canonical dblp and one official mirror, not an arbitrary proxy.

    A genuine 429/403 is a request to stop; do not use mirrors to evade a
    provider's explicit throttling/access restrictions.
    """
    global _last_dblp_request
    failures = []
    for host in ("https://dblp.org", "https://dblp.dagstuhl.de"):
        url = _param(host + "/search/publ/api", q=query, format="json", h=limit)
        elapsed = time.monotonic() - _last_dblp_request
        if _last_dblp_request and elapsed < 2.0:
            time.sleep(2.0 - elapsed)
        _last_dblp_request = time.monotonic()
        try:
            obj = _json_response(_get(url, retries=0, timeout=12), "dblp")
            if "result" not in obj:
                raise BadSourceResponse("dblp: JSON did not contain search results")
            return obj
        except urllib.error.HTTPError as ex:
            if ex.code in (401, 403, 429):
                raise
            failures.append(f"{host}: HTTP {ex.code}")
        except (BadSourceResponse, urllib.error.URLError, TimeoutError) as ex:
            failures.append(f"{host}: {type(ex).__name__}: {ex}")
    raise BadSourceResponse("dblp could not return valid JSON from its official hosts: " +
                            "; ".join(failures))



def _get(url, *, retries=2, timeout=20):
    headers = {"User-Agent": "awesome-mesh-recovery/3.1 (GitHub paper index)",
               "Accept": "application/json, application/atom+xml, */*"}
    if "api.semanticscholar.org" in url:
        key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
        if key:
            headers["x-api-key"] = key
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            # Shared unauthenticated Semantic Scholar quota is often saturated.
            # A 429 should stop this run, not trigger 13 more queries.
            if error.code in (401, 403, 429) and "api.semanticscholar.org" in url:
                raise
            if error.code not in (429, 500, 502, 503, 504) or attempt == retries:
                raise
            delay = min(12, 2 * (attempt + 1))
            if error.code == 429:
                try:
                    delay = min(12, max(delay, int(error.headers.get("Retry-After", "0"))))
                except (TypeError, ValueError):
                    pass
            time.sleep(delay)
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
    data = _dblp_json(query, limit)
    found = []
    hits = data.get("result", {}).get("hits", {}).get("hit", [])
    if isinstance(hits, dict):
        hits = [hits]
    for result in hits:
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
    data = _json_response(_get(url, retries=0), "s2")
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
    data = _json_response(_get(url), "crossref")
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


def harvest(config, *, track="core", today=None, mode="weekly", health=None):
    """Search sources independently; stop querying providers that throttle/block.

    health is shared by core + embodied scans in the same process so a provider
    that returned 429 or an HTML challenge is not hammered by the other track.
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
    health = {} if health is None else health
    found = []
    status = {"track": track, "mode": mode, "attempted": 0,
              "succeeded": 0, "nonempty": 0, "failures": [],
              "per_source": {}, "skipped": {}}
    for name, handler in SOURCES.items():
        queries = list(dict.fromkeys(query_map.get(name, [])))
        if not queries:
            continue
        info = status["per_source"].setdefault(
            name, {"attempted": 0, "succeeded": 0, "results": 0}
        )
        if name in health:
            status["skipped"][name] = len(queries)
            continue
        shift = today.isocalendar().week % len(queries)
        queries = queries[shift:] + queries[:shift]
        for position, query in enumerate(queries):
            status["attempted"] += 1
            info["attempted"] += 1
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
                info["succeeded"] += 1
                info["results"] += len(items)
                if items:
                    status["nonempty"] += 1
            except Exception as ex:
                message = f"{name}: {query}: {type(ex).__name__}: {ex}"
                status["failures"].append(message)
                print(f"[harvest] WARNING {message}")
                blocked = (
                    isinstance(ex, BadSourceResponse) or
                    isinstance(ex, urllib.error.HTTPError) and ex.code in (401, 403, 429)
                )
                if blocked:
                    reason = (
                        f"HTTP {ex.code}" if isinstance(ex, urllib.error.HTTPError)
                        else str(ex)
                    )
                    health[name] = reason
                    status["skipped"][name] = len(queries) - position - 1
                    print(f"[harvest] {name} is unavailable ({reason}); "
                          "skipping remaining requests this run")
                    break
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
