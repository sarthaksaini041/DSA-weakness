"""Tests for training boundaries, missing inputs, and equal-user scoring."""
import sys
from pathlib import Path
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from train_models import Features, development_rows, evaluate, metrics


class TrainingTests(unittest.TestCase):
    def test_validation_cannot_change_preprocessing(self):
        transform = Features(numeric=["value"]).fit([
            {"value": 2, "problem_tags": ["dp"]},
            {"value": None, "problem_tags": []},
            {"value": 4, "problem_tags": []}])
        before = transform.imputer.statistics_.copy()
        result = transform.transform([{"value": 10000, "problem_tags": ["unseen"]},
                                      {"value": None, "problem_tags": []}])
        np.testing.assert_array_equal(transform.imputer.statistics_, before)
        self.assertEqual(before[0], 3)
        self.assertEqual(transform.tags, ["dp"])
        self.assertTrue(np.isfinite(result).all())
        self.assertTrue((result[:, -1] == 0).all())

    def test_final_test_targets_are_not_read(self):
        rows = [{"split": split, "timestamp": time, "target": y,
                 "analysis_id": "a", "training_weight": 1}
                for split, time in [("train", 1), ("validation", 2)] for y in [0, 1]]
        rows += [{"split": "temporal_test"}, {"split": "unseen_user_test"},
                 {"split": "unseen_user_context"}]
        train, valid = development_rows(rows)
        self.assertEqual((len(train), len(valid)), (2, 2))
        rows[0]["timestamp"] = 2
        with self.assertRaises(ValueError):
            development_rows(rows)

    def test_bad_training_weights_rejected(self):
        rows = [{"split": split, "timestamp": time, "target": y,
                 "analysis_id": "a", "training_weight": 2}
                for split, time in [("train", 1), ("validation", 2)] for y in [0, 1]]
        with self.assertRaises(ValueError):
            development_rows(rows)

    def test_user_average_does_not_favor_prolific_user(self):
        rows = [{"analysis_id": "a", "target": 1}] * 9 + [{"analysis_id": "b", "target": 0}]
        scores = evaluate(rows, np.full(10, 0.8))
        expected = (-np.log(0.8) - np.log(0.2)) / 2
        self.assertAlmostEqual(scores["user_average"]["log_loss"], expected)
        self.assertNotEqual(scores["submission"]["log_loss"], expected)
        self.assertIsNone(scores["user_average"]["roc_auc"])
        self.assertEqual(scores["users_with_auc"], 0)

    def test_single_class_metrics_are_defined_except_auc(self):
        score = metrics([0, 0], [0.2, 0.3])
        self.assertIsNone(score["roc_auc"])
        self.assertTrue(np.isfinite(score["log_loss"]))
        self.assertEqual(score["f1"], 0)


if __name__ == "__main__":
    unittest.main()
