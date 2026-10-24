# DSA Compass: Codeforces Weakness Analysis and Practice Recommendations

## Project details

- Course / track: **ES 335 — undergraduate interactive website**
- Student name(s) and roll number(s): **To be filled by the team**
- Platform: Codeforces
- Status: API access, the 12-user pilot, and the 120-user cohort are collected and audited.
  Full-cohort features and evaluation splits are frozen; baseline and three-model validation
  comparisons and frozen final testing are complete; see `reports/test_results.md`. Offline
  recommendations and the static website are implemented and locally tested. GitHub Pages
  publication and live handle support remain pending.

Track completion using [the rubric evidence checklist](reports/checklist.md).

## Question and motivation

Can historical Codeforces submissions predict whether a user's first submission to a new problem
will be accepted, and help identify topics for further practice?

A visitor enters a Codeforces handle. The system summarizes their past performance, estimates
first-submission success on suitable problems, and recommends unsolved problems in topics needing
practice. Predictions describe observed submission behavior, not intelligence, overall DSA mastery,
or guaranteed learning gains.

## Data source and unit of observation

Use the public [Codeforces API](https://codeforces.com/apiHelp), subject to its current access
rules:

| Endpoint              | Intended use                                                                                      |
| --------------------- | ------------------------------------------------------------------------------------------------- |
| `user.info`           | Validate a handle; retrieve rating metadata without retaining unnecessary personal profile fields |
| `user.status`         | Retrieve paginated submissions, timestamps, verdicts, participant type, and problem metadata      |
| `user.rating`         | Reconstruct the rating available before a historical prediction                                   |
| `problemset.problems` | Retrieve candidate problem identifiers, tags, and difficulty ratings                              |

One modeling row represents a user's **first recorded submission to a problem**, identified by
contest ID and problem index. Target: `1` for verdict `OK`, `0` for a finalized judged rejection.
Pending/testing, compilation errors, infrastructure failures, and skipped submissions will be
excluded from the primary target and counted separately. The exact included verdict list will be
frozen before training. Only individual participation is included in the primary analysis.

Pilot collection: at least one user from each of six rating strata to establish data quality.
Working dataset goal: 120 users (20 per stratum, including unrated users) and approximately
10,000–50,000 eligible user–problem rows; these are targets, not collected counts. Include different
activity levels and history sizes, audit prolific-user dominance, and report metrics by user group.
Follow the [cohort sampling plan](reports/sampling.md); keep the elite smoke-test account separate
from training.

Public API access was verified on 2026-10-23. No private account access or credentials are planned.
Initial smoke-test and pilot captures have been removed after completing the full dataset; the
smoke-test account is excluded from modeling.

The [full-cohort audit](reports/data_report.md) now records 120 users, 100,919 submissions, and
41,828 eligible first-attempt rows. All six rating quotas were met. Temporal and unseen-user test
coverage gates passed before any model fitting; this does not establish model generalization. See
[the full-cohort protocol](reports/sampling.md) for recruitment, profile-rating corrections, and
split rules.

## Features and preprocessing

- Previous unique problems attempted and solved, overall and by tag.
- Historical first-submission acceptance rates, overall and by tag.
- Recent performance and activity, computed over earlier submissions only.
- User rating from the latest rating update strictly before the submission; retain a missing-rating
  indicator for unrated users.
- Problem tags, difficulty rating, and rating gap when available.

Sort events chronologically and compute features before updating history with the current result.
Never use the current verdict, future attempts, current profile rating, post-submission rating
changes, or full-history aggregates as historical input. Fit imputation, scaling, and categorical
transformations on training data only.

Deduplicate submission IDs and retrieve complete histories before identifying first attempts. A
truncated recent-history sample cannot establish a true first submission. Audit missing
tags/ratings, team participation, repeated attempts, and rejudged verdicts. Current problem
tags/ratings may differ from their historical values; disclose this snapshot limitation and examine
sensitivity to excluding difficulty.

## Baseline and three models

| Method                                   | Reason                                                                            |
| ---------------------------------------- | --------------------------------------------------------------------------------- |
| Smoothed historical user acceptance rate | Simple baseline; fall back to a training-only global rate for new users           |
| Logistic Regression                      | Interpretable classifier with a linear relationship between features and log-odds |
| Random Forest                            | Captures nonlinear relationships and feature interactions                         |
| Gradient Boosting                        | Sequential tree model for comparison on structured features                       |

All methods use the same target, eligible rows, and evaluation splits. Hyperparameters are selected
using validation data, with fixed random seeds and a modest search budget.

## Evaluation plan

Define global chronological cutoffs after inspecting timestamps but before comparing model results:
approximately the earliest 70% for training, next 15% for validation, and latest 15% for final
testing. Keep equal timestamps together. Reserve the test set until preprocessing and model
selection are fixed. Later predictions may use earlier observed outcomes, as in deployment, but
models remain fixed during test evaluation.

Primary metric: log loss for probability quality. Also report ROC-AUC (where both classes exist),
precision, recall, F1, and calibration. Choose any classification threshold on validation data only.
Compare against the baseline; inspect errors by topic, difficulty, rating band, and history length.
Report a held-out-user analysis if sample size permits, because a time split mainly measures future
performance for the sampled population.

First-submission success applies only to problems users choose to attempt. Selection bias limits
predictions for arbitrary unattempted problems. Recommendation usefulness will be illustrated with
case studies; improvement in learning requires a separate prospective study.

## Weakness analysis and recommendations

Compare topic performance at similar difficulty and relative to the user's overall level. Show
evidence counts and uncertainty; use “insufficient evidence” for sparse topics. Do not rank
weaknesses from raw acceptance rates alone.

Recommend problems with no previous accepted submission, label previously attempted problems as
retries, and prioritize new problems for first-attempt predictions. Filter by weak-topic relevance
and achievable difficulty; the offline prototype ranks supported-topic candidates by estimated
acceptance within a chosen difficulty range, with no tuned probability cutoff. Explain each
recommendation using its tags, difficulty, and relevant history. Avoid treating unseen topics as
demonstrated weaknesses.

## Deliverables and course alignment

- Reproducible collection, cleaning, chronological feature generation, and training scripts.
- Data dictionary, sampling details, split cutoffs, model settings, evaluation tables, plots, and
  representative errors.
- Interactive interface: handle input, topic evidence, difficulty controls, and explained practice
  suggestions.
- ES 335: a static GitHub Pages site with question, data, preprocessing, baseline/methods,
  evaluation, results, errors, limitations, conclusions, and reproduction instructions. Use
  precomputed examples or browser-compatible inference; verify API CORS separately before promising
  live browser fetching.
- Disclose AI assistance in planning, code, debugging, and writing; independently check outputs and
  cite external materials.

## Work phases

1. Define the problem and proposal (this document).
2. Verify API access, inspect fields, and implement a reproducible single-user pilot.
3. Collect a multi-user dataset and document coverage.
4. Explore, clean, and generate leakage-safe features.
5. Train the baseline and three models.
6. Evaluate and analyze errors.
7. Implement topic analysis and recommendations.
8. Build the interactive course deliverable.
9. Verify reproduction and prepare submission materials.

## Risks and responsible handling

API availability, request limits, missing difficulty ratings, small histories, and participant
selection can restrict scope. Respect API pacing and cache responses. Retain only necessary fields,
publish only the reviewed compressed raw-data snapshot authorized by the team, and avoid publishing
names, locations, or other unnecessary profile information. Codeforces handles remain identifiable;
use pseudonymous IDs in shared analysis where possible. No accuracy or learning-improvement claims
will be made before supporting evaluation.

## References

- [Codeforces API help](https://codeforces.com/apiHelp)
- [Codeforces API methods](https://codeforces.com/apiHelp/methods)
- [Codeforces API objects](https://codeforces.com/apiHelp/objects)
- Team-provided _Machine Learning Course Portal_: project guide and rubric.
