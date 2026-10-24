# Model validation results

> This report records the development stage before final testing. The subsequent
> [final test report](test_results.md) contains the completed reserved-test evaluation.

## Scope and selection

Fitted on 22,752 rows from 61 users; evaluated on 4,875 validation rows from 46 users. Final
temporal and unseen-user tests have not been scored. These are development results, not evidence of
generalization.

Selection uses the lowest user-averaged validation log loss (lower is better), including the
baseline as a candidate. Each user has equal influence on this metric. The small search has two
settings per model; all settings are shown below. Classification uses a fixed threshold of 0.5, with
acceptance as the positive class.

Selected candidate: **Random Forest depth=16**. This is provisional until the planned development
sensitivity checks are complete.

## Preprocessing and model choices

Only training rows fit numeric medians, missing-value indicators, standard scaling, and the
topic-tag vocabulary. Unknown tags are ignored; an entirely missing training column is filled with
zero. Metadata and identifiers are excluded by an explicit feature allowlist. Scaling helps Logistic
Regression; trees receive the same inputs for consistency and do not require scaling. Preprocessing
summaries are unweighted; training loss uses the frozen equal-user sample weights for every model
and the baseline.

The baseline predicts the weighted training acceptance rate for every row. Logistic Regression
models linear log odds with L2 regularization. Random Forest averages nonlinear trees; depth and
minimum leaf size limit overfitting. Gradient Boosting adds shallow trees sequentially to optimize
log loss. Seed 42 is used throughout. Exact settings, versions, and data/code hashes are in
`model_results.json`; trained objects stay in ignored `data/processed/models.joblib`.

## Submission-level metrics

| Model                     | Log loss |  Brier | ROC-AUC | Precision | Recall |     F1 | Accuracy |
| ------------------------- | -------: | -----: | ------: | --------: | -----: | -----: | -------: |
| Acceptance-rate baseline  |   0.6668 | 0.2369 |  0.5000 |    0.6396 | 1.0000 | 0.7802 |   0.6396 |
| Logistic Regression C=0.1 |   0.6144 | 0.2119 |  0.6750 |    0.7003 | 0.8560 | 0.7704 |   0.6736 |
| Logistic Regression C=1.0 |   0.6199 | 0.2131 |  0.6725 |    0.7014 | 0.8521 | 0.7695 |   0.6734 |
| Random Forest depth=8     |   0.6052 | 0.2086 |  0.6956 |    0.6854 | 0.8964 | 0.7768 |   0.6706 |
| Random Forest depth=16    |   0.5993 | 0.2062 |  0.6978 |    0.7013 | 0.8691 | 0.7763 |   0.6796 |
| Gradient Boosting depth=2 |   0.6072 | 0.2097 |  0.6822 |    0.7019 | 0.8156 | 0.7545 |   0.6605 |
| Gradient Boosting depth=3 |   0.6072 | 0.2094 |  0.6847 |    0.7020 | 0.8454 | 0.7671 |   0.6716 |

## User-averaged metrics

| Model                     | Log loss |  Brier | ROC-AUC | Precision | Recall |     F1 | Accuracy |
| ------------------------- | -------: | -----: | ------: | --------: | -----: | -----: | -------: |
| Acceptance-rate baseline  |   0.6697 | 0.2383 |  0.5000 |    0.6274 | 1.0000 | 0.7609 |   0.6274 |
| Logistic Regression C=0.1 |   0.6428 | 0.2249 |  0.6243 |    0.6624 | 0.7460 | 0.6866 |   0.6359 |
| Logistic Regression C=1.0 |   0.6481 | 0.2264 |  0.6239 |    0.6634 | 0.7440 | 0.6861 |   0.6365 |
| Random Forest depth=8     |   0.6137 | 0.2127 |  0.6612 |    0.6784 | 0.8090 | 0.7207 |   0.6584 |
| Random Forest depth=16    |   0.6074 | 0.2102 |  0.6658 |    0.6917 | 0.7704 | 0.7094 |   0.6640 |
| Gradient Boosting depth=2 |   0.6127 | 0.2122 |  0.6575 |    0.6890 | 0.7392 | 0.6928 |   0.6524 |
| Gradient Boosting depth=3 |   0.6183 | 0.2142 |  0.6569 |    0.6929 | 0.7531 | 0.7024 |   0.6525 |

## Interpretation and remaining work

The selected candidate has user-averaged log loss 0.6074, compared with 0.6697 for the constant
baseline. This supports further development, but does not establish that the best validation
candidate will win on future or unseen users.

Log loss penalizes confident wrong probabilities; Brier measures squared probability error (both
lower is better). ROC-AUC measures ranking rather than calibration. User metrics are computed per
user then averaged; ROC-AUC excludes users with only one outcome. Undefined precision/recall/F1 are
set to zero, so sparse-user classification metrics need care.

User-averaged ROC-AUC includes 46 of 46 validation users. Repeated submissions from each user are
correlated; row counts are not independent sample counts. Model selection on this validation set
makes these scores optimistic as final estimates.

Still pending: no-difficulty and outcome-lag sensitivity checks, calibration plots, user-level
uncertainty estimates, subgroup and representative-error analysis, and final temporal/unseen-user
evaluation after settings are frozen. Snapshot tags/difficulty, verdict timing, self-selected
problems, sparse cold-start evidence, and the absence of currently unrated training users limit
claims. Predicting acceptance does not prove a DSA weakness or improved learning.

## Reproduce

```bash
python3 -m pip install -r requirements.txt
python3 code/train_models.py
python3 -m unittest discover -s tests -v
```

Restore the archive and generate features first using the README commands. This script scores only
training/validation development inputs and saves validation aggregates; it contains no final-test
scoring path.
