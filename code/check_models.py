"""Validation robustness, calibration, uncertainty, and errors; no final-test scoring."""
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.base import clone

from make_features import user_features
from train_models import Features, SEED, development_rows, digest, evaluate


def calibration(rows, probabilities):
    """Fixed bins; probability 1 belongs to the last bin. Counts are submissions."""
    y = np.array([r['target'] for r in rows])
    bins = np.minimum((np.asarray(probabilities) * 10).astype(int), 9)
    result = []
    for i in range(10):
        mask = bins == i
        if mask.any():
            result.append({'lower': i / 10, 'upper': (i + 1) / 10,
                           'rows': int(mask.sum()),
                           'predicted': float(np.mean(probabilities[mask])),
                           'observed': float(np.mean(y[mask]))})
    return result


def paired_bootstrap(rows, probabilities, baseline, repeats=2000):
    """Resample users, retaining all their rows and equal-user influence."""
    y = np.array([r['target'] for r in rows])
    ids = np.array([r['analysis_id'] for r in rows])
    p = np.clip(probabilities, 1e-15, 1 - 1e-15)
    b = np.clip(baseline, 1e-15, 1 - 1e-15)
    losses = -(y * np.log(p) + (1-y) * np.log1p(-p))
    reference = -(y * np.log(b) + (1-y) * np.log1p(-b))
    means = np.array([losses[ids == u].mean() for u in sorted(set(ids))])
    differences = np.array([(losses-reference)[ids == u].mean() for u in sorted(set(ids))])
    indices = np.random.default_rng(SEED).integers(0, len(means), (repeats, len(means)))
    return {'users': len(means), 'resamples': repeats,
            'log_loss_95_percent': np.quantile(means[indices].mean(axis=1), [.025, .975]).tolist(),
            'paired_difference_95_percent': np.quantile(differences[indices].mean(axis=1), [.025, .975]).tolist(),
            'paired_difference': float(differences.mean())}


def delayed_rows(train, validation, source, lag):
    """Recompute development users only; retain exact frozen rows, labels, and splits."""
    original = train + validation
    wanted = {(r['analysis_id'], r['submission_id']): r for r in original}
    generated = {}
    for uid in sorted({r['analysis_id'] for r in original}):
        capture = json.loads((source / 'users' / f'{uid}.json').read_text())
        # Future submissions are excluded even from the sensitivity computation.
        cutoff = max(r['timestamp'] for r in original)
        capture['submissions'] = [s for s in capture['submissions'] if s['creationTimeSeconds'] <= cutoff]
        for row in user_features(capture, uid, lag):
            key = (uid, row['submission_id'])
            if key in wanted:
                old = wanted[key]
                if row['target'] != old['target'] or row['problem_id'] != old['problem_id']:
                    raise ValueError('Sensitivity check changed labels or row identity')
                generated[key] = {**row, 'split': old['split'], 'training_weight': old['training_weight']}
    if set(generated) != set(wanted):
        raise ValueError('Sensitivity check changed eligible development rows')
    return ([generated[(r['analysis_id'], r['submission_id'])] for r in train],
            [generated[(r['analysis_id'], r['submission_id'])] for r in validation])


def group_results(rows, probabilities, baseline, strata):
    groups = {}
    for i, r in enumerate(rows):
        count = r['prior_problems_attempted']
        rating = r['problem_rating']
        labels = [('Collection-time rating', strata[r['analysis_id']]),
                  ('Prior attempts', '0–19' if count < 20 else '20–99' if count < 100 else '100–499' if count < 500 else '500+'),
                  ('Historical rating', 'No prior rating' if r['historical_rating'] is None else 'Prior rating available'),
                  ('Difficulty', 'Not rated' if rating is None else 'Below 1200' if rating < 1200 else '1200–1599' if rating < 1600 else '1600+'),
                  ('Outcome history', 'No judged history' if r['prior_first_attempts_judged'] == 0 else 'Judged history available')]
        labels += [('Topic', tag) for tag in (r['problem_tags'] or ['No tags'])]
        for label in labels:
            groups.setdefault(label, []).append(i)
    result = []
    for (kind, label), indices in sorted(groups.items()):
        part = [rows[i] for i in indices]
        score = evaluate(part, probabilities[indices])
        base = evaluate(part, np.full(len(part), baseline))
        result.append({'kind': kind, 'label': {'unrated': 'Unrated', 'below_1200': 'Below 1200', '1200_1399': '1200–1399', '1400_1599': '1400–1599', '1600_1899': '1600–1899', '1900_plus': '1900+'}.get(label, label), **score,
                       'baseline_user_log_loss': base['user_average']['log_loss'],
                       'sparse': score['users'] < 10 or score['rows'] < 100})
    return result


def run():
    folder, source, reports = Path('data/processed'), Path('data/raw'), Path('reports')
    artifact = joblib.load(folder / 'models.joblib')
    metadata = artifact['metadata']
    for name, expected in metadata['sha256'].items():
        if digest(folder / name) != expected:
            raise ValueError(f'Data changed since training: {name}')
    if digest(Path('code/train_models.py')) != metadata['code_sha256']:
        raise ValueError('Training code changed since fitting')
    manifest = json.loads((folder / 'manifest.json').read_text())
    for name, expected in manifest['source_sha256'].items():
        if digest(source / name) != expected:
            raise ValueError(f'Raw inputs changed: {name}')
    train, valid = development_rows(json.loads((folder / 'features.json').read_text()))
    features = Features(artifact['numeric_features'])
    features.tags, features.imputer, features.scaler = artifact['tags'], artifact['imputer'], artifact['scaler']
    name = artifact['selected']
    if name not in artifact['models']:
        raise ValueError('Selected candidate is baseline; revise sensitivity protocol for a constant model')
    model = artifact['models'][name]
    probabilities = model.predict_proba(features.transform(valid))[:, 1]
    sensitivities = [{'name': 'Original: one-day lag', **evaluate(valid, probabilities)}]
    variants = [('Without difficulty', train, valid,
                 [k for k in features.numeric if k not in {'problem_rating', 'problem_rating_missing', 'rating_gap'}])]
    delayed_train, delayed_valid = delayed_rows(train, valid, source, 7 * 86400)
    variants.append(('Seven-day outcome lag', delayed_train, delayed_valid, features.numeric))
    for title, fit_rows, score_rows, numeric in variants:
        print(f'Checking {title}', flush=True)
        transform = Features(numeric).fit(fit_rows)
        fitted = clone(model).fit(transform.transform(fit_rows), [r['target'] for r in fit_rows],
                                  sample_weight=[r['training_weight'] for r in fit_rows])
        p = fitted.predict_proba(transform.transform(score_rows))[:, 1]
        sensitivities.append({'name': title, **evaluate(score_rows, p)})
    strata = {u['analysis_id']: u['stratum'] for u in json.loads((source / 'audit.json').read_text())['users']}
    errors = []
    for target in (0, 1):
        indices = [i for i,r in enumerate(valid) if r['target'] == target and (probabilities[i] >= .5) != bool(target)]
        indices.sort(key=lambda i: abs(probabilities[i] - valid[i]['target']), reverse=True)
        for i in indices[:3]:
            r = valid[i]
            errors.append({k:r[k] for k in ['analysis_id', 'problem_id', 'target', 'problem_tags', 'problem_rating', 'historical_rating', 'prior_problems_attempted']} | {'probability': float(probabilities[i])})
    output = {'model': name, 'test_sets_scored': False, 'seed': SEED,
              'training_metadata': metadata, 'analysis_code_sha256': digest(Path(__file__)),
              'feature_code_sha256': digest(Path('code/make_features.py')),
              'artifact_sha256': digest(folder / 'models.joblib'),
              'sensitivity': sensitivities,
              'uncertainty': paired_bootstrap(valid, probabilities, artifact['baseline']),
              'calibration': calibration(valid, probabilities),
              'groups': group_results(valid, probabilities, artifact['baseline'], strata), 'errors': errors}
    reports.mkdir(exist_ok=True)
    (reports / 'model_checks.json').write_text(json.dumps(output, indent=2, allow_nan=False) + '\n')
    plot(output, reports / 'images' / 'validation_calibration.png')
    write_report(output, reports / 'model_checks.md')
    print(json.dumps({'sensitivity': [(r['name'],r['user_average']['log_loss']) for r in sensitivities],
                      'uncertainty': output['uncertainty']}, indent=2))


def plot(output, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    bins = output['calibration']
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout='constrained')
    axes[0].plot([0,1], [0,1], '--', color='gray', label='Perfect calibration')
    axes[0].plot([b['predicted'] for b in bins], [b['observed'] for b in bins], 'o-', label='Validation')
    axes[0].set(xlabel='Mean predicted acceptance probability', ylabel='Observed acceptance fraction',
                title='Validation calibration', xlim=(0,1), ylim=(0,1))
    axes[0].legend()
    axes[1].bar([(b['lower']+b['upper'])/2 for b in bins], [b['rows'] for b in bins], width=.09)
    axes[1].set(xlabel='Predicted acceptance probability', ylabel='Validation rows', title='Evidence per probability bin', xlim=(0,1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def write_report(x, path):
    u = x['uncertainty']
    lines = ['# Validation model checks', '', f"Model: **{x['model']}**. Final tests remain unscored.", '',
             '## Sensitivity checks', '',
             'The selected model settings are held fixed. Each variant refits preprocessing and the model using training rows only, then scores the identical validation rows. These are stress tests, not new hyperparameter searches. The original one-day policy remains the primary specification; a longer lag cannot reconstruct unavailable historical verdict times. Removing difficulty also removes its missing indicator and rating gap, but does not remove snapshot topic bias.', '',
             '| Variant | User log loss | Submission log loss | User Brier |', '| --- | ---: | ---: | ---: |']
    for r in x['sensitivity']:
        lines.append(f"| {r['name']} | {r['user_average']['log_loss']:.4f} | {r['submission']['log_loss']:.4f} | {r['user_average']['brier']:.4f} |")
    lines += ['', '## Uncertainty', '',
              f"Paired bootstrap with {u['resamples']:,} resamples of {u['users']} validation users, seed 42. Each sampled user contributes their full history and equal weight. The 95% percentile interval for user-averaged log loss is {u['log_loss_95_percent'][0]:.4f}–{u['log_loss_95_percent'][1]:.4f}. Model minus baseline log loss is {u['paired_difference']:.4f}, with interval [{u['paired_difference_95_percent'][0]:.4f}, {u['paired_difference_95_percent'][1]:.4f}]; negative favors the model.", '',
              'These intervals condition on the fitted model and this sampled cohort. They do not account for model-selection optimism, recruitment bias, or dependence between users attempting shared problems. They are not final-test confidence intervals.', '',
              '## Calibration', '', '![Validation reliability and bin counts](images/validation_calibration.png)', '',
              'Fixed bins of width 0.1 show submission-weighted observed versus predicted acceptance. Empty bins are omitted; the second panel shows evidence counts. Brier and log loss complement this diagnostic. No calibration mapping is fitted on these validation labels.', '',
              '## Subgroups', '',
              'User log loss is averaged within each subgroup. Collection-time rating is descriptive metadata, never a model input; it is not the rating at prediction time. Topics overlap, so their counts cannot be added. Sparse means fewer than 10 users or 100 rows, a descriptive warning rather than a statistical guarantee.', '',
              '| Group | Value | Rows | Users | User log loss | Baseline | Sparse |', '| --- | --- | ---: | ---: | ---: | ---: | --- |']
    for g in x['groups']:
        lines.append(f"| {g['kind']} | {g['label']} | {g['rows']} | {g['users']} | {g['user_average']['log_loss']:.4f} | {g['baseline_user_log_loss']:.4f} | {'Yes' if g['sparse'] else 'No'} |")
    lines += ['', '## Findings to carry into the website', '']
    for g in x['groups']:
        if g['kind'] in {'Historical rating', 'Outcome history', 'Difficulty'} and g['user_average']['log_loss'] > g['baseline_user_log_loss']:
            lines.append(f"- **{g['label']}**: model user log loss {g['user_average']['log_loss']:.4f} exceeds baseline {g['baseline_user_log_loss']:.4f} ({g['rows']} rows, {g['users']} users). Treat advice for this group cautiously; sparse evidence should be shown explicitly.")
    lines += ['', 'Calibration is imperfect, and extreme probability bins have few observations. The website should present probabilities as estimates, include history/evidence counts, and avoid confident weakness rankings for users without enough judged history. These checks do not establish a safe minimum history threshold.', '']
    lines += ['', '## Error examples', '',
              'The three most confident false positives and false negatives at threshold 0.5 are selected deterministically below. These are extreme diagnostic cases, not typical error frequencies or explanations of why a particular submission failed. Target 1 means accepted; target 0 means judged rejection. Features cannot capture code quality or the user’s unobserved preparation.', '',
              '| User ID | Problem | Tags | Difficulty | Historical user rating | Prior attempts | Predicted acceptance | Actual |', '| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for e in x['errors']:
        lines.append(f"| {e['analysis_id']} | {e['problem_id']} | {', '.join(e['problem_tags']) or 'No tags'} | {e['problem_rating'] if e['problem_rating'] is not None else 'Missing'} | {e['historical_rating'] if e['historical_rating'] is not None else 'Missing'} | {e['prior_problems_attempted']} | {e['probability']:.4f} | {e['target']} |")
    lines += ['', '## Next evaluation step', '',
              'Review these development diagnostics, freeze model/preprocessing/threshold choices, then evaluate the temporal and unseen-user tests once. No claims about reliable cold-start advice, universal generalization, or learning gains follow from validation alone. The original model artifact and frozen dataset are unchanged by this script.', '',
              '## Reproduce', '', '```bash', 'python3 code/train_models.py', 'python3 code/check_models.py', 'python3 -m unittest discover -s tests -v', '```', '',
              'The script verifies original data and training hashes, rebuilds seven-day features only for development users, preserves row identity and split assignments, and saves aggregate results with code/artifact hashes in `model_checks.json`.']
    path.write_text('\n'.join(lines)+'\n')


if __name__ == '__main__':
    run()
