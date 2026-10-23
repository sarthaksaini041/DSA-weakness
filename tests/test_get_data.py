"""Synthetic API responses test logic; they are not evidence of live access."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import URLError

spec = importlib.util.spec_from_file_location("fetch", Path(__file__).resolve().parents[1] / "code/get_data.py")
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


class FakeClient:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []

    def get(self, method, **params):
        self.calls.append((method, params))
        return next(self.pages)


class FetchTests(unittest.TestCase):
    def test_pagination_and_duplicate_ids(self):
        client = FakeClient([[{"id": 3}, {"id": 2}], [{"id": 2}, {"id": 1}], []])
        rows, complete, pages = fetch.fetch_submissions(client, "example", 2, 0)
        self.assertEqual([r["id"] for r in rows], [3, 2, 1])
        self.assertTrue(complete)
        self.assertEqual(pages, 3)
        self.assertEqual([p["from"] for _, p in client.calls], [1, 3, 5])

    def test_capped_history_is_not_complete(self):
        rows, complete, _ = fetch.fetch_submissions(FakeClient([[{"id": 1}]]), "example", 1, 1)
        self.assertFalse(complete)
        self.assertFalse(fetch.summarize(rows, complete)["first_ever_attempts_safe_to_derive"])

    def test_empty_history_is_valid(self):
        rows, complete, _ = fetch.fetch_submissions(FakeClient([[]]), "example", 10, 2)
        summary = fetch.summarize(rows, complete)
        self.assertEqual(summary["submission_count"], 0)
        self.assertIsNone(summary["oldest_submission_timestamp"])

    def test_quality_counts_and_missing_verdict(self):
        rows = [
            {"id": 1, "verdict": "OK", "problem": {"contestId": 1, "index": "A", "rating": 800, "tags": ["dp"]}},
            {"id": 2, "problem": {"contestId": 1, "index": "A", "tags": []}, "author": {"members": [{}, {}]}},
        ]
        summary = fetch.summarize(rows, True)
        self.assertEqual(summary["unique_contest_problems"], 1)
        self.assertEqual(summary["verdict_counts"], {"OK": 1, "PENDING": 1})
        self.assertEqual(summary["submissions_missing_problem_rating"], 1)
        self.assertEqual(summary["team_submissions"], 1)

    def test_profile_is_minimized(self):
        client = FakeClient([[{"handle": "example", "rating": 1000, "firstName": "Private"}], [], [], {"problems": []}])
        capture = fetch.collect(client, "example", 10, 1)
        self.assertEqual(capture["user"], {"handle": "example", "rating": 1000})
        self.assertTrue(capture["summary"]["history_complete"])

    @patch.object(fetch, "urlopen", side_effect=URLError("Tunnel connection failed: 403 Forbidden"))
    def test_network_failure_is_explicit(self, _):
        with self.assertRaisesRegex(fetch.APIError, "network request failed"):
            fetch.Client().get("user.info", handles="example")

    @patch.object(fetch, "urlopen")
    def test_api_rejects_unknown_handle(self, opener):
        opener.return_value.__enter__.return_value.read.return_value = b'{"status":"FAILED","comment":"handle: User not found"}'
        with self.assertRaisesRegex(fetch.APIError, "User not found"):
            fetch.Client().get("user.info", handles="missing")


if __name__ == "__main__":
    unittest.main()
