import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from collect_data import STRATA, complete_history, eligible_first_attempts, stratum
from test_get_data import FakeClient


class DatasetTests(unittest.TestCase):
    def test_single_page_history_needs_no_redundant_head_request(self):
        client = FakeClient([[{"id": 1}]])
        rows, complete, pages, stable, method = complete_history(client, "example")
        self.assertEqual(len(client.calls), 1)
        self.assertTrue(complete and stable)
        self.assertEqual((pages, method), (1, "single_exhausted_response"))

    def test_shifting_multi_page_history_is_flagged(self):
        client = FakeClient([[{"id": i} for i in range(1000, 0, -1)], [], [{"id": 1001}]])
        _, complete, pages, stable, method = complete_history(client, "example")
        self.assertTrue(complete)
        self.assertFalse(stable)
        self.assertEqual(pages, 2)

    def test_rating_boundaries(self):
        self.assertEqual([stratum(r) for r in (None, 1199, 1200, 1400, 1600, 1900)], list(STRATA))


    def test_filtering_does_not_promote_later_success_to_first(self):
        def submission(sid, verdict):
            return {"id": sid, "creationTimeSeconds": sid, "verdict": verdict,
                    "author": {"members": [{"handle": "example"}]},
                    "problem": {"contestId": 1, "index": "A", "type": "PROGRAMMING", "tags": ["dp"]}}
        audit = eligible_first_attempts([submission(2, "OK"), submission(1, "COMPILATION_ERROR")], "example")
        self.assertEqual(audit["eligible_rows"], 0)
        self.assertEqual(audit["exclusions"], {"excluded_or_pending_verdict": 1})

    def test_failure_and_success_labels_are_counted(self):
        rows = [{"id": i, "creationTimeSeconds": i, "verdict": verdict,
                 "author": {"members": [{"handle": "example"}]},
                 "problem": {"contestId": 1, "index": str(i), "type": "PROGRAMMING", "tags": ["dp"]}}
                for i, verdict in enumerate(("OK", "WRONG_ANSWER"))]
        self.assertEqual(eligible_first_attempts(rows, "example")["eligible"], {"accepted": 1, "rejected": 1})


if __name__ == "__main__":
    unittest.main()
