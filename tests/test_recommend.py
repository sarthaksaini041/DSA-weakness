import copy
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'code'))
from recommend import candidates, query_features, recommend, topic_evidence, wilson
from test_make_features import capture, submission


class RecommendationTests(unittest.TestCase):
    def test_excludes_any_attempt_even_compile_error_or_team(self):
        s=submission(1,10,'COMPILATION_ERROR','A')
        s['author']['members'].append({'handle':'other'})
        raw=capture([s])
        p=s['problem']
        other={**p,'index':'B'}
        pool=candidates(raw,[p,other,other,{**p,'index':'C','rating':None}],800,1200)
        self.assertEqual([p['index'] for p in pool],['B'])

    def test_queries_do_not_change_history_or_each_other(self):
        raw=capture([submission(1,10)])
        original=copy.deepcopy(raw)
        problems=[{**submission(2,20)['problem'],'index':x} for x in ['X','Y']]
        rows=query_features(raw,problems,100000)
        self.assertEqual(raw,original)
        self.assertEqual(len(rows),2)
        for r in rows:
            self.assertNotIn('target',r)
            self.assertEqual(r['prior_problems_attempted'],1)
            self.assertEqual(r['prior_problems_solved'],1)
        self.assertEqual(rows[0]['prior_first_acceptance_rate'],rows[1]['prior_first_acceptance_rate'])
        with self.assertRaises(ValueError):
            query_features(raw,[raw['submissions'][0]['problem']],100000)

    def test_query_outcome_lag(self):
        raw=capture([submission(1,10)])
        p={**submission(2,20)['problem'],'index':'X'}
        row=query_features(raw,[p],100)[0]
        self.assertEqual(row['prior_first_attempts_judged'],0)
        self.assertEqual(row['prior_problems_attempted'],1)

    def test_topic_comparison_requires_matching_difficulty(self):
        rows=[{'problem_tags':['dp'],'problem_rating':800,'target':0}]*15
        rows += [{'problem_tags':['math'],'problem_rating':2000,'target':1}]*15
        self.assertTrue(all(x['status']=='Insufficient evidence' for x in topic_evidence(rows,np.full(30,.5))))
        for r in rows:
            r['problem_rating']=800
        result=topic_evidence(rows,np.full(30,.5))
        dp=next(r for r in result if r['topic']=='dp')
        self.assertEqual(dp['status'],'Practice candidate')
        self.assertEqual(dp['relative_gap'],-1)

    def test_sparse_user_gets_exploration_without_probability(self):
        raw=capture([])
        raw['collected_at']='2026-10-23T12:00:00+00:00'
        p=submission(2,20)['problem']
        class NeverPredict:
            def predict_proba(self, x):
                raise AssertionError('Sparse empty history should not be scored')
        out=recommend(raw,[p],NeverPredict(),None,0)
        self.assertEqual(out['mode'],'Insufficient evidence: exploration only')
        self.assertEqual(out['topics'],[])
        self.assertIsNone(out['recommendations'][0]['predicted_acceptance'])
        self.assertEqual(out['recommendations'][0]['kind'],'Exploration')

    def test_interval_contains_observed_rate(self):
        self.assertIsNone(wilson(0,0))
        lo,hi=wilson(5,10)
        self.assertLess(lo,.5)
        self.assertGreater(hi,.5)


if __name__=='__main__':
    unittest.main()
