"""Explain topic evidence and suggest new Codeforces problems from saved captures."""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path

import joblib
import numpy as np

from make_features import problem_key, user_features
from train_models import Features, digest

MIN_HISTORY = 30
MIN_TOPIC = 10
MIN_REFERENCE = 10
LAG = 86400


def wilson(successes, count):
    """Descriptive binomial interval; correlated attempts limit its interpretation."""
    if count == 0:
        return None
    z = 1.96
    p = successes / count
    center = (p + z*z/(2*count)) / (1+z*z/count)
    radius = z * math.sqrt(p*(1-p)/count + z*z/(4*count*count)) / (1+z*z/count)
    return [max(0,center-radius), min(1,center+radius)]


def topic_evidence(rows, probabilities):
    """Compare model residuals against other problems in the same 400-rating bands."""
    topics = sorted({t for r in rows for t in r['problem_tags']})
    result = []
    for topic in topics:
        indices = [i for i,r in enumerate(rows) if topic in r['problem_tags']]
        matched = []
        reference_ids = set()
        for i in indices:
            rating = rows[i]['problem_rating']
            if rating is None:
                continue
            references = [j for j,r in enumerate(rows) if topic not in r['problem_tags']
                          and r['problem_rating'] is not None and r['problem_rating']//400 == rating//400]
            if references:
                contrast = (rows[i]['target'] - probabilities[i]) - np.mean([
                    rows[j]['target'] - probabilities[j] for j in references])
                matched.append(float(contrast))
                reference_ids.update(references)
        accepted = sum(rows[i]['target'] for i in indices)
        sufficient = len(rows) >= MIN_HISTORY and len(matched) >= MIN_TOPIC and len(reference_ids) >= MIN_REFERENCE
        gap = float(np.mean(matched)) if matched else None
        result.append({'topic': topic, 'attempts': len(indices), 'accepted': accepted,
                       'acceptance_rate': accepted / len(indices), 'acceptance_interval': wilson(accepted,len(indices)),
                       'expected_acceptance': float(np.mean(probabilities[indices])),
                       'matched_attempts': len(matched), 'reference_problems': len(reference_ids),
                       'relative_gap': gap,
                       'status': 'Practice candidate' if sufficient and gap < 0 else
                                 'No lower-performance signal' if sufficient else 'Insufficient evidence'})
    return sorted(result, key=lambda r: (r['status'] != 'Practice candidate',
                                         r['relative_gap'] if r['relative_gap'] is not None else 1, r['topic']))


def candidates(capture, catalog, lower, upper):
    # Any prior attempt excludes the problem, including team attempts and excluded verdicts.
    attempted = {problem_key(s) for s in capture['submissions']}
    unique = {}
    for p in catalog:
        key = problem_key({'problem': p})
        if (key is None or key in attempted or p.get('type') != 'PROGRAMMING'
                or p.get('rating') is None or not lower <= p['rating'] <= upper
                or not p.get('tags') or any(t.startswith('*') for t in p['tags'])):
            continue
        unique[key] = p
    return [unique[k] for k in sorted(unique)]


def query_features(capture, problems, as_of):
    """Reuse frozen historical feature logic with temporary, simultaneous query records.

    Query verdicts are placeholders needed by the row builder, never observations,
    training examples, or saved data. Equal-second batching prevents cross-query history.
    Only allow never-attempted problems, and discard the placeholder target immediately.
    """
    if any(s['creationTimeSeconds'] >= as_of for s in capture['submissions']):
        raise ValueError('Query time must be after the captured history')
    attempted = {problem_key(s) for s in capture['submissions']}
    keys = [problem_key({'problem': p}) for p in problems]
    if any(k is None or k in attempted for k in keys) or len(keys) != len(set(keys)):
        raise ValueError('Query problems must be unique and never attempted')
    ids = {s['id'] for s in capture['submissions']}
    first_id = min(ids | {0}) - len(problems) - 1
    queries = [{'id': first_id+i, 'creationTimeSeconds': as_of, 'problem': p,
                'author': {'members': [{'handle': capture['user']['handle']}]}, 'verdict': 'OK'}
               for i,p in enumerate(problems)]
    query_ids = {q['id'] for q in queries}
    temporary = {**capture, 'submissions': capture['submissions'] + queries}
    rows = [r for r in user_features(temporary, 'query', LAG) if r['submission_id'] in query_ids]
    if len(rows) != len(problems):
        raise ValueError('Some query problems are not eligible')
    for row in rows:
        del row['target']
    return rows


def load_model(folder, plan_path):
    plan = json.loads(plan_path.read_text())
    if digest(folder/'models.joblib') != plan['artifact_sha256']:
        raise ValueError('Frozen model artifact changed')
    if digest(Path('code/train_models.py')) != plan['code_sha256']['code/train_models.py']:
        raise ValueError('Frozen preprocessing code changed')
    checks = json.loads(Path('reports/model_checks.json').read_text())
    if digest(Path('code/make_features.py')) != checks['feature_code_sha256']:
        raise ValueError('Historical feature code changed')
    artifact = joblib.load(folder/'models.joblib')
    if artifact['selected'] != plan['selected']:
        raise ValueError('Model selection changed')
    transformer = Features(artifact['numeric_features'])
    transformer.tags, transformer.imputer, transformer.scaler = artifact['tags'], artifact['imputer'], artifact['scaler']
    return artifact['models'][plan['selected']], transformer, plan


def recommend(capture, catalog, model, transformer, train_end, limit=10, lower=None, upper=None, topic=None):
    as_of = int(datetime.fromisoformat(capture['collected_at']).timestamp())
    # Capture timestamp can be rounded to the same second as a newest submission.
    if any(s['creationTimeSeconds'] >= as_of for s in capture['submissions']):
        raise ValueError('Capture timestamp must be later than all submissions')
    rows = user_features(capture, 'user', LAG)
    evidence = [r for r in rows if train_end <= r['timestamp'] < as_of-LAG]
    # Most recent 200 eligible attempts: bounded, current evidence and no train-fit rows.
    evidence = evidence[-200:]
    probabilities = model.predict_proba(transformer.transform(evidence))[:,1] if evidence else np.array([])
    topics = topic_evidence(evidence, probabilities)
    prior_ratings = [r for r in capture['rating_history'] if r['ratingUpdateTimeSeconds'] < as_of]
    rating = max(prior_ratings,key=lambda r:r['ratingUpdateTimeSeconds'])['newRating'] if prior_ratings else None
    if lower is None:
        lower = max(800, (rating//100)*100 - 200) if rating is not None else 800
    if upper is None:
        upper = max(lower, (rating//100)*100 + 200) if rating is not None else 1200
    if lower > upper:
        raise ValueError('Minimum difficulty must not exceed maximum difficulty')
    pool = candidates(capture, catalog, lower, upper)
    if topic:
        pool = [p for p in pool if topic in p['tags']]
    practice = {t['topic']: t for t in topics if t['status']=='Practice candidate'}
    personalized = len(evidence) >= MIN_HISTORY and rating is not None
    if not personalized:
        practice = {}
        for item in topics:
            item['status'] = 'Insufficient evidence'
    predictions = {}
    if pool and personalized:
        queries = query_features(capture, pool, as_of)
        predicted = model.predict_proba(transformer.transform(queries))[:,1]
        predictions = {r['problem_id']: float(p) for r,p in zip(queries,predicted)}
    suggestions = []
    for p in pool:
        key = f"{p['contestId']}:{p['index']}"
        relevant = sorted(set(p['tags']) & practice.keys())
        probability = predictions.get(key)
        suggestions.append({'problem_id': key, 'name': p.get('name',key), 'rating': p['rating'],
                            'tags': p['tags'], 'url': f"https://codeforces.com/problemset/problem/{p['contestId']}/{p['index']}",
                            'predicted_acceptance': probability, 'practice_topics': relevant,
                            'kind': 'Topic practice' if relevant else 'Exploration',
                            'reason': ('Matches practice topics: '+', '.join(relevant)+'.' if relevant else
                                       'Explore a new problem within the chosen difficulty range; no weakness claim.') +
                                      ' No previous attempt appears in the captured history.'})
    # Prioritize supported topics, then estimated attainability, then deterministic identifiers.
    # No success-probability cutoff has been tuned using final tests.
    suggestions.sort(key=lambda p:(not bool(p['practice_topics']),
                                  -p['predicted_acceptance'] if p['predicted_acceptance'] is not None else p['rating'],
                                  p['problem_id']))
    return {'handle': capture['user']['handle'], 'as_of': capture['collected_at'],
            'mode': 'Personalized estimates' if personalized else 'Insufficient evidence: exploration only',
            'historical_rating': rating, 'evidence_rows': len(evidence),
            'evidence_window': 'Latest 200 eligible, one-day-mature first attempts after the training cutoff',
            'difficulty_range': [lower,upper], 'topic_filter':topic, 'candidate_count':len(pool),
            'topics':topics, 'recommendations':suggestions[:limit],
            'unseen_topics': 'No observed attempts means insufficient evidence, never an inferred weakness.',
            'limitations': 'Offline snapshot; probability estimates are not calibrated guarantees. Topic contrasts are descriptive, overlapping and noncausal. Recommendation benefit has not been evaluated.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('handle',help='A handle present in the saved cohort')
    parser.add_argument('--min-rating',type=int)
    parser.add_argument('--max-rating',type=int)
    parser.add_argument('--topic')
    parser.add_argument('--limit',type=int,default=10)
    parser.add_argument('--output',type=Path,default=Path('data/processed/recommendations.json'))
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 50:
        parser.error('--limit must be between 1 and 50')
    source = Path('data/raw')
    audit = json.loads((source/'audit.json').read_text())
    user = next((u for u in audit['users'] if u['handle'].casefold()==args.handle.casefold()),None)
    if user is None:
        parser.error('Handle is not in the saved cohort. Live handle collection is not implemented in this command.')
    capture = json.loads((source/'users'/f"{user['analysis_id']}.json").read_text())
    catalog_data = json.loads((source/'problemset.json').read_text())
    model, transformer, plan = load_model(Path('data/processed'),Path('reports/test_plan.json'))
    splits = json.loads(Path('data/processed/splits.json').read_text())
    result = recommend(capture,catalog_data['result']['problems'],model,transformer,
                       splits['validation_start'],args.limit,args.min_rating,args.max_rating,args.topic)
    result['provenance'] = {'model':plan['selected'], 'artifact_sha256':plan['artifact_sha256'],
                            'capture_sha256':digest(source/'users'/f"{user['analysis_id']}.json"),
                            'catalog_sha256':digest(source/'problemset.json'),
                            'catalog_collected_at':catalog_data['collected_at'],
                            'code_sha256':digest(Path(__file__))}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'handle':result['handle'],'mode':result['mode'],'evidence_rows':result['evidence_rows'],
                      'recommendations':len(result['recommendations']),'output':str(args.output)},indent=2))


if __name__=='__main__':
    main()
