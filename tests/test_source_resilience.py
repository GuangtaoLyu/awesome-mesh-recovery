# -*- coding: utf-8 -*-
"""Provider resilience: soft source outage, mirror retry and source health."""
import datetime
import io
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import harvest
import pipeline


class ProviderParsingTests(unittest.TestCase):
    def test_html_challenge_not_treated_as_empty_dblp_result(self):
        with self.assertRaisesRegex(harvest.BadSourceResponse, "HTML/challenge"):
            harvest._json_response(b"<!DOCTYPE html><html>Verify your request</html>", "dblp")
        with self.assertRaisesRegex(harvest.BadSourceResponse, "non-JSON"):
            harvest._json_response(b"", "dblp")

    def test_dblp_official_mirror_fallback(self):
        payload = (
            b'{"result":{"hits":{"hit":{"info":{"title":"Human Mesh Recovery",'
            b'"year":"2026","venue":"CVPR","authors":{"author":'
            b'{"text":"Ada Researcher"}},"ee":"https://doi.org/10.1234/abc"}}}}}'
        )
        urls = []

        def fetch(url, **kwargs):
            urls.append(url)
            return b"<html>challenge</html>" if len(urls) == 1 else payload

        with mock.patch.object(harvest, "_get", side_effect=fetch), \
                mock.patch.object(harvest.time, "sleep"):
            papers = harvest.dblp("human mesh recovery", 2024, 5)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["title"], "Human Mesh Recovery")
        self.assertEqual(papers[0]["authors"], ["Ada Researcher"])
        self.assertIn("dblp.org", urls[0])
        self.assertIn("dblp.dagstuhl.de", urls[1])

    def test_dblp_429_does_not_bypass_rate_limit_using_mirror(self):
        calls = []

        def throttled(url, **kwargs):
            calls.append(url)
            raise urllib.error.HTTPError(url, 429, "Rate limited", {}, None)

        with mock.patch.object(harvest, "_get", side_effect=throttled):
            with self.assertRaises(urllib.error.HTTPError):
                harvest.dblp("human mesh recovery", 2024, 5)
        self.assertEqual(len(calls), 1)

    def test_unauthenticated_semantic_scholar_429_no_repeated_retries(self):
        url = "https://api.semanticscholar.org/graph/v1/paper/search?query=hand"
        error = urllib.error.HTTPError(url, 429, "Quota", {}, None)
        with mock.patch.dict(os.environ, {"SEMANTIC_SCHOLAR_API_KEY": ""}), \
                mock.patch.object(harvest.urllib.request, "urlopen", side_effect=error) as call, \
                mock.patch.object(harvest.time, "sleep") as sleep:
            with self.assertRaises(urllib.error.HTTPError):
                harvest._get(url, retries=2)
        call.assert_called_once()
        sleep.assert_not_called()

    def test_optional_semantic_scholar_api_key(self):
        url = "https://api.semanticscholar.org/graph/v1/paper/search?query=hand"
        seen = []

        class Reply:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return b'{"data": []}'

        def fake(request, **_kwargs):
            seen.append({k.lower(): v for k, v in request.header_items()})
            return Reply()

        with mock.patch.object(harvest.urllib.request, "urlopen", side_effect=fake), \
                mock.patch.dict(os.environ, {"SEMANTIC_SCHOLAR_API_KEY": "test-key"}):
            harvest._get(url)
        self.assertEqual(seen[0].get("x-api-key"), "test-key")


class CircuitBreakerTests(unittest.TestCase):
    def test_429_stops_s2_for_core_and_embodied(self):
        calls = []

        def s2_failure(query, *_args):
            calls.append(query)
            raise urllib.error.HTTPError("https://api.semanticscholar.org", 429,
                                         "rate-limit", {}, None)

        def arxiv_good(*_args):
            return [{"title": "Human Mesh Recovery", "year": 2026}]

        cfg = {"year_from": 2015,
               "queries": {"arxiv": ["human mesh recovery"],
                           "s2": ["query one", "query two"]},
               "embodied_queries": {"s2": ["query three", "query four"]}}
        health = {}
        with mock.patch.object(harvest, "SOURCES",
                               {"arxiv": arxiv_good, "s2": s2_failure}):
            core, first = harvest.harvest(
                cfg, track="core", today=datetime.date(2026, 11, 26), health=health)
            robot, second = harvest.harvest(
                cfg, track="embodied", today=datetime.date(2026, 11, 26), health=health)
        self.assertEqual(len(core), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(first["skipped"].get("s2"), 1)
        self.assertEqual(second["skipped"].get("s2"), 2)
        self.assertEqual(health["s2"], "HTTP 429")

    def test_dblp_bad_html_breaks_remaining_queries(self):
        calls = []

        def bad(_query, *_args):
            calls.append(1)
            raise harvest.BadSourceResponse("dblp returned HTML")
        def arxiv_good(*_args):
            return [{"title": "Human Mesh Recovery", "year": 2026}]
        cfg = {"year_from": 2015,
               "queries": {"arxiv": ["hmr"], "dblp": ["q1", "q2", "q3"]},
               "embodied_queries": {"dblp": ["q4"]}}
        health = {}
        with mock.patch.object(harvest, "SOURCES",
                               {"arxiv": arxiv_good, "dblp": bad}):
            _, first = harvest.harvest(cfg, track="core", health=health)
            _, second = harvest.harvest(cfg, track="embodied", health=health)
        self.assertEqual(len(calls), 1)
        self.assertEqual(first["skipped"].get("dblp"), 2)
        self.assertEqual(second["skipped"].get("dblp"), 1)

    def test_source_health_summary_includes_degraded_provider(self):
        reports = [
            {"per_source": {"arxiv": {"succeeded": 3, "results": 42},
                            "crossref": {"succeeded": 2, "results": 6},
                            "s2": {"succeeded": 0, "results": 0},
                            "dblp": {"succeeded": 0, "results": 0}}},
            {"per_source": {"arxiv": {"succeeded": 2, "results": 12}}},
        ]
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / "summary.md")
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": path}), \
                    mock.patch("builtins.print") as printer:
                pipeline._report_provider_health(
                    reports, {"s2": "HTTP 429", "dblp": "challenge"})
            txt = Path(path).read_text(encoding="utf-8")
            self.assertIn("| arXiv | 5 | 54 | OK |", txt)
            self.assertIn("| Semantic Scholar | 0 | 0 | Degraded: HTTP 429 |", txt)
            warnings = [x for call in printer.call_args_list for x in call.args
                        if isinstance(x, str) and x.startswith("::warning")]
            self.assertEqual(len(warnings), 2)


if __name__ == "__main__":
    unittest.main()
