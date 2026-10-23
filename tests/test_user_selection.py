import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from check_data import coverage_gates
from collect_data import STRATA
from select_users import choose_cohort, saved_source


class CohortProtocolTests(unittest.TestCase):
    def test_moved_candidate_snapshot_preserves_original_digest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "candidates").mkdir()
            path = root / "candidates/users.json"
            path.write_bytes(b"[]")
            record = {"path": str(root / "old_location/users.json"), "sha256": hashlib.sha256(b"[]").hexdigest()}
            self.assertEqual(saved_source(root, record), path)

    def test_changed_candidate_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "candidates").mkdir()
            (root / "candidates/users.json").write_bytes(b"changed")
            record = {"path": str(root / "old_location/users.json"), "sha256": hashlib.sha256(b"[]").hexdigest()}
            with self.assertRaisesRegex(ValueError, "Missing or changed"):
                saved_source(root, record)

    def test_full_selection_covers_quotas_and_distinct_sources(self):
        ratings = [1000, 1300, 1500, 1700, 2000]
        broad = [{"handle": f"r{r}_u{i}", "rating": r} for r in ratings for i in range(40)]
        active = [{"handle": f"r{r}_u{i}", "rating": r} for r in ratings for i in range(20)]
        unrated = [{"handle": f"unrated{i}"} for i in range(30)]
        selected, counts = choose_cohort(broad, active, unrated)
        self.assertEqual(len(selected), 120)
        self.assertEqual(len({u["handle"].casefold() for u in selected}), 120)
        for group in STRATA:
            self.assertEqual(sum(u["stratum"] == group for u in selected), 20)
            if group != "unrated":
                self.assertEqual(sum(u["stratum"] == group and u["source"] == "active_rated" for u in selected), 10)
        self.assertEqual(selected, choose_cohort(list(reversed(broad)), active, unrated)[0])

    def test_missing_unrated_quota_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "Insufficient unrated"):
            choose_cohort([], [], [])

    def test_single_class_and_sparse_unseen_test_fail_gates(self):
        audit = {"completed_users": 120, "failures": 0, "actual_per_stratum": {g: 20 for g in STRATA},
                 "users": [{"analysis_id": "a", "stratum": "unrated"}, {"analysis_id": "b", "stratum": "below_1200"}]}
        rows = [{"analysis_id": uid, "timestamp": t, "problem_id": str(t), "target": 0,
                 "prior_first_attempts_judged": 0, "split": split}
                for uid, t, split in (("a", 1, "train"), ("a", 2, "validation"), ("a", 3, "temporal_test"), ("b", 4, "unseen_user_test"))]
        gates, details = coverage_gates(audit, rows)
        self.assertFalse(gates["unseen_user_test_coverage"])
        self.assertFalse(gates["unseen_rating_coverage"])
        self.assertTrue(gates["time_ordering"])
        self.assertTrue(gates["user_disjointness"])
        self.assertEqual(details["unseen_user_test"]["accepted"], 0)
        changed = copy.deepcopy(rows)
        changed[-1]["analysis_id"] = "a"
        self.assertFalse(coverage_gates(audit, changed)[0]["user_disjointness"])


if __name__ == "__main__":
    unittest.main()
