"""Validation diagnostic boundaries and user-level uncertainty checks."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'code'))
from check_models import calibration, delayed_rows, paired_bootstrap


class ModelCheckTests(unittest.TestCase):
    def test_calibration_includes_endpoints_and_omits_empty_bins(self):
        bins = calibration([{'target': 0}, {'target': 1}, {'target': 1}], np.array([0., .5, 1.]))
        self.assertEqual(sum(b['rows'] for b in bins), 3)
        self.assertEqual(len(bins), 3)
        self.assertEqual(bins[-1]['upper'], 1)
        self.assertEqual(bins[-1]['observed'], 1)

    def test_bootstrap_equal_user_weight_and_pairing(self):
        rows = [{'analysis_id': 'a', 'target': 1}] * 20 + [{'analysis_id': 'b', 'target': 0}]
        result = paired_bootstrap(rows, np.full(21, .7), .7, repeats=50)
        self.assertEqual(result['paired_difference'], 0)
        self.assertEqual(result['paired_difference_95_percent'], [0, 0])
        duplicate = paired_bootstrap(rows, np.full(21, .7), .7, repeats=50)
        self.assertEqual(result, duplicate)
        self.assertEqual(result['users'], 2)

    def test_lag_rebuild_preserves_split_and_filters_future_submissions(self):
        base = {'analysis_id': 'a', 'submission_id': 1, 'problem_id': '1:A',
                'timestamp': 10, 'target': 1, 'split': 'train', 'training_weight': 1}
        valid = {**base, 'submission_id': 2, 'timestamp': 20, 'split': 'validation'}
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'users').mkdir()
            (folder / 'users/a.json').write_text(json.dumps({'submissions': [
                {'creationTimeSeconds': 10}, {'creationTimeSeconds': 20}, {'creationTimeSeconds': 30}]}))
            def build(capture, uid, lag):
                self.assertEqual(len(capture['submissions']), 2)
                self.assertEqual(lag, 604800)
                return [base, valid]
            with patch('check_models.user_features', side_effect=build):
                train, val = delayed_rows([base], [valid], folder, 604800)
            self.assertEqual(train, [base])
            self.assertEqual(val, [valid])
            with patch('check_models.user_features', return_value=[{**base, 'target': 0}, valid]):
                with self.assertRaises(ValueError):
                    delayed_rows([base], [valid], folder, 604800)


if __name__ == '__main__':
    unittest.main()
