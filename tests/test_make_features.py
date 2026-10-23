import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from make_features import NUMERIC_FEATURES, assign_splits, user_features


def submission(sid, timestamp, verdict="OK", index=None):
    return {"id": sid, "creationTimeSeconds": timestamp, "verdict": verdict,
            "author": {"members": [{"handle": "example"}]},
            "problem": {"contestId": 1, "index": index or str(sid), "type": "PROGRAMMING", "tags": ["dp"], "rating": 1000}}


def capture(rows, ratings=None):
    return {"user": {"handle": "example", "rating": 3000}, "submissions": rows,
            "rating_history": ratings or [], "summary": {"history_complete": True}, "head_stable": True}


class FeatureTests(unittest.TestCase):
    def test_current_target_never_enters_current_features(self):
        raw = capture([submission(1, 10), submission(2, 20)])
        before = user_features(raw, "u", 0)
        raw["submissions"][1]["verdict"] = "WRONG_ANSWER"
        after = user_features(raw, "u", 0)
        self.assertNotEqual(before[1]["target"], after[1]["target"])
        self.assertEqual({k: before[1][k] for k in NUMERIC_FEATURES}, {k: after[1][k] for k in NUMERIC_FEATURES})

    def test_future_events_do_not_change_earlier_rows(self):
        raw = capture([submission(1, 10), submission(2, 20)])
        before = user_features(raw, "u", 0)
        raw["submissions"].append(submission(3, 30, "WRONG_ANSWER"))
        raw["rating_history"].append({"ratingUpdateTimeSeconds": 40, "newRating": 2500})
        self.assertEqual(user_features(raw, "u", 0)[:2], before)

    def test_same_timestamp_events_do_not_leak(self):
        rows = user_features(capture([submission(1, 10), submission(2, 10)]), "u", 0)
        for row in rows:
            self.assertEqual(row["prior_problems_attempted"], 0)
            self.assertEqual(row["prior_problems_solved"], 0)
            self.assertIsNone(row["prior_first_acceptance_rate"])

    def test_delayed_outcomes_and_strict_rating_cutoff(self):
        raw = capture([submission(1, 10), submission(2, 20), submission(3, 21)],
                      [{"ratingUpdateTimeSeconds": 20, "newRating": 900}])
        rows = user_features(raw, "u", 10)
        self.assertEqual(rows[1]["prior_problems_attempted"], 1)
        self.assertEqual(rows[1]["prior_first_attempts_judged"], 0)
        self.assertIsNone(rows[1]["historical_rating"])
        self.assertEqual(rows[2]["prior_first_attempts_judged"], 1)
        self.assertEqual(rows[2]["historical_rating"], 900)
        self.assertEqual(rows[2]["rating_gap"], 100)

    def test_excluded_first_attempt_is_not_replaced_with_retry(self):
        raw = capture([submission(1, 10, "COMPILATION_ERROR", "A"), submission(2, 20, "OK", "A")])
        self.assertEqual(user_features(raw, "u", 0), [])

    def test_retries_update_solved_but_not_first_attempt_rate(self):
        raw = capture([submission(1, 10, "WRONG_ANSWER", "A"), submission(2, 20, "OK", "A"), submission(3, 30)])
        rows = user_features(raw, "u", 0)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]["prior_problems_solved"], 1)
        self.assertEqual(rows[-1]["prior_first_attempts_judged"], 1)
        self.assertEqual(rows[-1]["prior_first_acceptance_rate"], 0)

    def test_incomplete_history_rejected(self):
        raw = capture([])
        raw["summary"]["history_complete"] = False
        with self.assertRaisesRegex(ValueError, "incomplete"):
            user_features(raw, "u")

    def test_user_disjointness_order_and_balanced_training_weights(self):
        users = [{"analysis_id": f"u{i}", "stratum": "same"} for i in range(5)]
        rows = [{"analysis_id": u["analysis_id"], "timestamp": t, "target": t % 2}
                for i, u in enumerate(users) for t in range(1, 41 + i * 10)]
        manifest = assign_splits(rows, users)
        train = [r for r in rows if r["split"] == "train"]
        val = [r for r in rows if r["split"] == "validation"]
        test = [r for r in rows if r["split"] in ("temporal_test", "unseen_user_test")]
        self.assertLess(max(r["timestamp"] for r in train), min(r["timestamp"] for r in val))
        self.assertLess(max(r["timestamp"] for r in val), min(r["timestamp"] for r in test))
        self.assertTrue(all(r["analysis_id"] not in manifest["heldout_users"] for r in train + val))
        totals = [sum(r["training_weight"] for r in train if r["analysis_id"] == uid)
                  for uid in {r["analysis_id"] for r in train}]
        self.assertAlmostEqual(min(totals), max(totals))
        rows2 = copy.deepcopy(rows)
        self.assertEqual(assign_splits(rows2, users), manifest)


if __name__ == "__main__":
    unittest.main()
