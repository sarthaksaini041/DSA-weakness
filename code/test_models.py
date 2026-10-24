"""Freeze development choices, then evaluate reserved tests without fitting or tuning."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import joblib
import numpy as np

from check_models import calibration, group_results, paired_bootstrap
from train_models import Features, digest, evaluate

FAMILIES = ('Logistic Regression', 'Random Forest', 'Gradient Boosting')
TESTS = ('temporal_test', 'unseen_user_test')


def save_new(path, value):
    # Exclusive creation prevents silently replacing a frozen plan or final results.
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def select_comparisons(results):
    """Select one setting per family using validation only."""
    names = ['Acceptance-rate baseline']
    for family in FAMILIES:
        candidates = [r for r in results if r['name'].startswith(family)]
        if not candidates:
            raise ValueError(f'Missing validation family: {family}')
        names.append(min(candidates, key=lambda r: r['user_average']['log_loss'])['name'])
    return names


def verify_hashes(expected, root):
    for name, value in expected.items():
        if digest(root / name) != value:
            raise ValueError(f'Frozen input changed: {name}')


def freeze(folder, reports, output):
    metadata = json.loads((reports / 'model_results.json').read_text())
    checks = json.loads((reports / 'model_checks.json').read_text())
    verify_hashes(metadata['sha256'], folder)
    if digest(Path('code/train_models.py')) != metadata['code_sha256']:
        raise ValueError('Training code changed since fitting')
    if checks['artifact_sha256'] != digest(folder / 'models.joblib'):
        raise ValueError('Checked model artifact changed')
    if checks['analysis_code_sha256'] != digest(Path('code/check_models.py')):
        raise ValueError('Development analysis code changed')
    artifact = joblib.load(folder / 'models.joblib')
    if artifact['metadata'] != metadata or checks['training_metadata'] != metadata:
        raise ValueError('Model and development reports do not match')
    selected = min(metadata['results'], key=lambda r: r['user_average']['log_loss'])['name']
    if selected != metadata['selected']:
        raise ValueError('Selection does not match validation rule')
    names = select_comparisons(metadata['results'])
    plan = {'frozen_at_utc': datetime.now(timezone.utc).isoformat(),
            'selected': selected, 'comparisons': names, 'threshold': .5,
            'primary_metric': 'user_average.log_loss', 'test_splits': list(TESTS),
            'training_policy': 'Original training-only fits; no train+validation refit',
            'feature_policy': 'Original features, one-day outcome lag; train-fitted preprocessing unchanged',
            'calibration_policy': 'No additional calibration fit',
            'sensitivity_decision': 'Retain original specification; seven-day and no-difficulty variants were robustness checks',
            'test_use': 'Report all results without changing model, threshold, or feature choices',
            'artifact_sha256': digest(folder / 'models.joblib'),
            'data_sha256': metadata['sha256'],
            'development_sha256': {name: digest(reports / name) for name in ('model_results.json', 'model_checks.json')},
            'code_sha256': {str(p): digest(p) for p in [Path('code/test_models.py'), Path('code/train_models.py'), Path('code/check_models.py')]},
            'model_parameters': {r['name']: r['parameters'] for r in metadata['results'] if r['name'] in names},
            'versions': metadata['versions'], 'bootstrap_seed': 42, 'bootstrap_resamples': 2000}
    output.mkdir(parents=True, exist_ok=True)
    save_new(output / 'test_plan.json', plan)
    print('Frozen test plan saved. No test predictions made.')


def test_rows(rows, split, splits):
    """Check test boundaries and user identities before scoring targets."""
    if split not in TESTS:
        raise ValueError('Only reserved test splits can be evaluated here')
    part = [r for r in rows if r['split'] == split]
    if not part:
        raise ValueError('Empty test split')
    heldout = set(splits['heldout_users'])
    development = {r['analysis_id'] for r in rows if r['split'] in ('train', 'validation')}
    if heldout & development:
        raise ValueError('Held-out user entered development')
    for r in part:
        if r['timestamp'] < splits['test_start']:
            raise ValueError('Test row precedes frozen test cutoff')
        if (r['analysis_id'] in heldout) != (split == 'unseen_user_test'):
            raise ValueError('Test row violates frozen held-out user assignment')
    return part


def run(folder, source, reports, output):
    plan = json.loads((output / 'test_plan.json').read_text())
    verify_hashes(plan['code_sha256'], Path('.'))
    verify_hashes(plan['data_sha256'], folder)
    verify_hashes(plan['development_sha256'], reports)
    if plan['artifact_sha256'] != digest(folder / 'models.joblib'):
        raise ValueError('Frozen model artifact changed')
    if (output / 'test_results.json').exists():
        print('Final results already exist; preserving them. No test predictions repeated.')
        return
    manifest = json.loads((folder / 'manifest.json').read_text())
    verify_hashes(manifest['source_sha256'], source)
    rows = json.loads((folder / 'features.json').read_text())
    splits = json.loads((folder / 'splits.json').read_text())
    artifact = joblib.load(folder / 'models.joblib')
    features = Features(artifact['numeric_features'])
    features.tags, features.imputer, features.scaler = artifact['tags'], artifact['imputer'], artifact['scaler']
    strata = {u['analysis_id']: u['stratum'] for u in json.loads((source / 'audit.json').read_text())['users']}
    output_data = {'plan_sha256': digest(output / 'test_plan.json'), 'selected_before_testing': plan['selected'],
                   'evaluated_at_utc': datetime.now(timezone.utc).isoformat(), 'splits': {}}
    for split in TESTS:
        part = test_rows(rows, split, splits)
        matrix = features.transform(part)
        results, predictions = [], {}
        for name in plan['comparisons']:
            probability = (np.full(len(part), artifact['baseline']) if name == 'Acceptance-rate baseline'
                           else artifact['models'][name].predict_proba(matrix)[:, 1])
            predictions[name] = probability
            results.append({'name': name, **evaluate(part, probability)})
        chosen = predictions[plan['selected']]
        y = np.array([r['target'] for r in part])
        predicted = chosen >= plan['threshold']
        output_data['splits'][split] = {
            'results': results, 'accepted': int(y.sum()), 'rejected': int(len(y)-y.sum()),
            'selected_uncertainty': paired_bootstrap(part, chosen, artifact['baseline']),
            'selected_calibration': calibration(part, chosen),
            'selected_groups': group_results(part, chosen, artifact['baseline'], strata),
            'selected_confusion': {'true_negative': int(((y == 0) & ~predicted).sum()),
                                   'false_positive': int(((y == 0) & predicted).sum()),
                                   'false_negative': int(((y == 1) & ~predicted).sum()),
                                   'true_positive': int(((y == 1) & predicted).sum())}}
    save_new(output / 'test_results.json', output_data)
    write_report(output_data, output / 'test_results.md')
    plot(output_data, output / 'images' / 'test_calibration.png')
    print(json.dumps({s: [(r['name'], r['user_average']['log_loss']) for r in v['results']]
                      for s,v in output_data['splits'].items()}, indent=2))


def write_report(data, path):
    lines = ['# Final test results', '', f"Model selected before testing: **{data['selected_before_testing']}**.", '',
             'The frozen plan in `test_plan.json` records model settings, artifact/data/code hashes, the original one-day outcome lag, training-only preprocessing and fits, and threshold 0.5. One setting per model family was chosen using validation log loss. Neither final test changed these choices. The baseline is the equal-user-weighted training acceptance rate.', '',
             '## Results', '', 'Lower log loss and Brier are better. Acceptance is the positive class. User averages give every test user equal influence; submission metrics weight each row equally. Single-class users are excluded only from user-averaged ROC-AUC; undefined precision/recall/F1 are zero.', '']
    for split, part in data['splits'].items():
        title = 'Future submissions' if split == 'temporal_test' else 'Unseen users'
        first = part['results'][0]
        lines += [f'## {title}', '', f"{first['rows']:,} rows from {first['users']} users: {part['accepted']:,} accepted and {part['rejected']:,} rejected. User-averaged ROC-AUC includes {first['users_with_auc']} users.", '']
        for level in ('user_average', 'submission'):
            lines += [f"### {'User-averaged' if level == 'user_average' else 'Submission-level'} metrics", '',
                      '| Model | Log loss | Brier | ROC-AUC | Precision | Recall | F1 | Accuracy |',
                      '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
            for r in part['results']:
                values = [r[level][k] for k in ('log_loss','brier','roc_auc','precision','recall','f1','accuracy')]
                lines.append('| '+r['name']+' | '+' | '.join('N/A' if v is None else f'{v:.4f}' for v in values)+' |')
            lines += ['']
        u = part['selected_uncertainty']
        lines += [f"Selected-model user log loss 95% bootstrap interval: [{u['log_loss_95_percent'][0]:.4f}, {u['log_loss_95_percent'][1]:.4f}]. Paired model-minus-baseline difference: {u['paired_difference']:.4f}, interval [{u['paired_difference_95_percent'][0]:.4f}, {u['paired_difference_95_percent'][1]:.4f}]. Negative favors the model.", '',
                  '### Selected-model subgroup checks', '',
                  '| Group | Value | Rows | Users | User log loss | Baseline | Sparse |', '| --- | --- | ---: | ---: | ---: | ---: | --- |']
        for g in part['selected_groups']:
            if g['kind'] != 'Topic':
                lines.append(f"| {g['kind']} | {g['label']} | {g['rows']} | {g['users']} | {g['user_average']['log_loss']:.4f} | {g['baseline_user_log_loss']:.4f} | {'Yes' if g['sparse'] else 'No'} |")
        lines += ['', 'Topic-level results and the selected-model confusion counts are in `test_results.json`. Topics overlap. Sparse denotes fewer than 10 users or 100 rows; passing those counts does not establish statistical reliability.', '']
    lines += ['## Calibration and uncertainty', '', '![Final-test calibration and evidence counts](images/test_calibration.png)', '',
              'Calibration uses fixed probability bins of width 0.1 with submission-weighted means. Empty bins are omitted; extreme bins can have very little evidence. No calibration mapping was fitted on test labels.', '',
              'Intervals use 2,000 paired bootstrap resamples of users, seed 42, retaining each user’s full set of rows and equal-user influence. They condition on this fitted model and sampled cohort, do not account for recruitment bias or shared-problem dependence, and are particularly uncertain for the 17-user unseen test. Subgroup comparisons are descriptive, without multiple-comparison correction.', '',
              '## Interpretation and limitations', '']
    for split, part in data['splits'].items():
        chosen = next(r for r in part['results'] if r['name'] == data['selected_before_testing'])
        baseline = part['results'][0]
        better = chosen['user_average']['log_loss'] < baseline['user_average']['log_loss']
        lines += [f"- **{'Future submissions' if split == 'temporal_test' else 'Unseen users'}:** the preselected model {'improves on' if better else 'does not improve on'} the baseline on user-averaged log loss ({chosen['user_average']['log_loss']:.4f} versus {baseline['user_average']['log_loss']:.4f})."]
    lines += ['', 'These tests measure future first-attempt outcomes for this cohort and held-out users from the same recruitment process. They do not prove performance for all Codeforces users or arbitrary unattempted problems. Personal history can update causally under the lag while model parameters stay fixed; unseen user means unseen during fitting, not necessarily no history.', '',
              'Snapshot problem ratings/tags, unavailable historical verdict timing, missing difficulty, cold-start evidence, and self-selection of attempted problems remain limitations. Predictions do not prove DSA mastery or that recommendations improve learning. Do not choose a new winner or adjust thresholds using these final scores; further tuning requires a new untouched evaluation set.', '',
              '## Reproduce', '', '```bash', 'python3 code/test_models.py --freeze', 'python3 code/test_models.py', '```', '',
              'Run training and validation checks first as documented in the README. A plan is created exclusively before scoring. Existing final results are preserved on reruns. For an independent clean reproduction, use `--output /tmp/dsa-final-reproduction` on both commands; the new plan records the regenerated artifact hashes. The script contains no fitting or hyperparameter search.']
    path.write_text('\n'.join(lines)+'\n')


def plot(data, path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2,2,figsize=(11,8),layout='constrained')
    for index,(split,part) in enumerate(data['splits'].items()):
        bins = part['selected_calibration']
        ax, counts = axes[index]
        ax.plot([0,1],[0,1],'--',color='gray',label='Perfect calibration')
        ax.plot([b['predicted'] for b in bins],[b['observed'] for b in bins],'o-',label='Selected model')
        ax.set(title='Future submissions' if split=='temporal_test' else 'Unseen users',
               xlabel='Mean predicted acceptance probability',ylabel='Observed acceptance fraction',xlim=(0,1),ylim=(0,1))
        ax.legend()
        counts.bar([(b['lower']+b['upper'])/2 for b in bins],[b['rows'] for b in bins],width=.09)
        counts.set(title='Evidence per probability bin',xlabel='Predicted acceptance probability',ylabel='Test rows',xlim=(0,1))
    path.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(path,dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('reports'))
    args = parser.parse_args()
    if args.freeze:
        freeze(Path('data/processed'), Path('reports'), args.output)
    else:
        run(Path('data/processed'), Path('data/raw'), Path('reports'), args.output)
