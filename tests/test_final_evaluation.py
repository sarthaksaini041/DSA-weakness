"""Protect held-out boundaries, validation selection, and frozen records."""
import sys
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'code'))
from test_models import select_comparisons, test_rows, save_new, verify_hashes


class FinalEvaluationTests(unittest.TestCase):
    def test_selects_each_family_from_validation(self):
        rows = [{'name': family+str(i), 'user_average': {'log_loss': loss}}
                for family in ('Logistic Regression','Random Forest','Gradient Boosting')
                for i,loss in [(1,.6),(2,.7)]]
        self.assertTrue(all(n.endswith('1') for n in select_comparisons(rows)[1:]))

    def test_only_frozen_test_users_and_times(self):
        splits={'heldout_users':['held'], 'test_start':10}
        row={'analysis_id':'held','timestamp':10,'split':'unseen_user_test'}
        self.assertEqual(test_rows([row], 'unseen_user_test', splits),[row])
        with self.assertRaises(ValueError):
            test_rows([{**row,'timestamp':9}], 'unseen_user_test', splits)
        with self.assertRaises(ValueError):
            test_rows([row,{'split':'train','analysis_id':'held'}], 'unseen_user_test',splits)
        with self.assertRaises(ValueError):
            test_rows([{**row,'analysis_id':'other'}], 'unseen_user_test', splits)
        with self.assertRaises(ValueError):
            test_rows([row], 'validation', splits)

    def test_frozen_files_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'plan.json'
            save_new(p,{'selected':'original'})
            with self.assertRaises(FileExistsError):
                save_new(p,{'selected':'replacement'})
            with self.assertRaises(ValueError):
                verify_hashes({'plan.json':'wrong'},Path(tmp))


if __name__=='__main__':
    unittest.main()
