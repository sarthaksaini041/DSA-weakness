# Features and evaluation splits

The current dataset contains **41,828 first-attempt rows from 120 users**. Feature generation fits
no preprocessing or models. See [the data report](data_report.md) for distributions, exclusions,
limitations, and coverage checks.

## Build the table

```bash
python3 code/make_features.py
python3 code/check_data.py
python3 -m unittest discover -s tests -v
```

Generated files stay in ignored `data/processed/`: `features.csv`, `features.json`, `schema.json`,
`splits.json`, `manifest.json`, and `coverage_gates.json`. Identifiers and sample weights are
metadata, never model inputs.

## Target policy

One row represents the first recorded submission to a contest/index problem. Target is 1 for `OK`, 0
for `WRONG_ANSWER`, `TIME_LIMIT_EXCEEDED`, `MEMORY_LIMIT_EXCEEDED`, `RUNTIME_ERROR`,
`IDLENESS_LIMIT_EXCEEDED`, or `PRESENTATION_ERROR`. Exclude team and special/non-programming
submissions and other/pending verdicts, including compilation errors and partial scores. Do not
promote a retry when the first submission is excluded. Missing difficulty/tags are retained for an
explicit training-only missing-data policy.

## Model input dictionary

| Feature                       | Definition at prediction time                                                                                  |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `prior_problems_attempted`    | Distinct problems in strictly earlier individual submissions, including attempts with excluded target verdicts |
| `prior_problems_solved`       | Distinct problems with an earlier individual `OK`, subject to outcome lag                                      |
| `prior_first_attempts_judged` | Earlier eligible first attempts whose outcomes pass the lag                                                    |
| `prior_first_acceptance_rate` | Accepted fraction of those eligible first attempts; missing when none                                          |
| `recent_20_acceptance_rate`   | Accepted fraction among the most recent 20 eligible first attempts available under the lag                     |
| `recent_20_count`             | Number of available attempts in that window                                                                    |
| `topic_prior_attempts_mean`   | Mean earlier unique-problem attempt count over the current problem's tags                                      |
| `topic_prior_judged_mean`     | Mean available eligible-first-attempt count over those tags                                                    |
| `topic_acceptance_rate_mean`  | Mean historical first-acceptance rate over tags with outcome evidence; missing if none                         |
| `historical_rating`           | Latest `newRating` with rating-update timestamp strictly before the submission; missing for no previous update |
| `historical_rating_missing`   | Indicator for absent historical rating                                                                         |
| `problem_rating`              | API snapshot difficulty; missing is retained                                                                   |
| `problem_rating_missing`      | Indicator for absent difficulty                                                                                |
| `rating_gap`                  | Problem difficulty minus historical user rating; missing if either is unavailable                              |
| `days_since_previous_attempt` | Days since the previous distinct individual problem attempt; missing for no prior attempt                      |
| `attempts_previous_30_days`   | Earlier distinct individual problem attempts within the preceding 30 days                                      |
| `tag_count`                   | Number of distinct tags on the current problem                                                                 |
| `problem_tags`                | Sorted list of tags; encode with a vocabulary learned on training only and ignore unknown test tags            |

There are **17 numeric inputs plus one multilabel tag field**. Identifiers, timestamps, problem
identity, target, split assignment, and training weights are metadata, not model inputs. Current
profile rating, maximum rating, current rank, runtime, memory usage, and passed tests are not
inputs.

Feature generation preserves missing values. `code/train_models.py` fits median imputation, missing
indicators, scaling, and the tag vocabulary on training data only, then reuses them unchanged for
validation. Cold-start rates are never filled using future outcomes. Frozen final-test results are
available in [the final report](test_results.md).

## Historical availability and limitations

All attempts at the same second receive a snapshot of history before that second. Submission ID
breaks ties only to identify a first attempt, never to let same-second outcomes enter another row's
features. Rating updates at the same timestamp are excluded.

The API records submission creation time but not historical verdict-availability time. Default
outcome lag is **86,400 seconds (one day)**: an outcome enters history only when its submission time
is strictly more than one day earlier. Attempt counts do not require an outcome and update from
strictly earlier events. This conservative proxy reduces ordinary judging overlap but does **not**
prove availability for delayed judging, later rejudging, or corrections. Training-label availability
at historical cutoffs also cannot be reconstructed exactly. State these limits in results, and plan
lag sensitivity analysis using training/validation data rather than final tests.

Problem tags and ratings are collection-time snapshots. Their historical values are unavailable;
test a no-difficulty variant on development data and disclose snapshot bias. Offline feature tests
establish the implementation's temporal rules, not the historical truth of API metadata.

## Evaluation splits

Seed 42 holds out approximately 20% of users within each rating group. Chronological cutoffs are
derived only from the remaining development users, approximately 70/15/15. Equal timestamps stay
together. Models and learned preprocessing remain fixed during testing.

Use validation only for tuning. Test rows must never choose preprocessing, features, thresholds, or
models. Earlier history can inform later predictions under the outcome lag, including personal
history from held-out users; those users never enter model fitting. Their earlier rows are context,
not scored data.

| Split               |   Rows | Users |
| ------------------- | -----: | ----: |
| temporal_test       |  4,876 |    65 |
| train               | 22,752 |    61 |
| unseen_user_context |  8,143 |    22 |
| unseen_user_test    |  1,182 |    17 |
| validation          |  4,875 |    46 |

The unseen-user test has 1,182 rows from 17 users and both outcomes. All six collection-time rating
groups are represented. Coverage permitted model development; prediction quality and subgroup
uncertainty are now reported in [the final evaluation](test_results.md). No currently unrated users
have training-period rows, so never-rated-user performance needs separate assessment.

Source hashes and cutoffs are saved. Changed raw inputs or outcome lag require a new output folder;
do not alter splits after inspecting model results.

## User balance

For training rows, `training_weight = N / (U × n_user)`, using only training counts. Each
represented training user has equal total weight and the overall mean weight is one. Pass this as
sample weight consistently to the baseline and all three models. Do not use it as an input feature.

Report submission-level metrics and user-averaged metrics, plus subgroup sample sizes and cold-start
behavior. Balanced training weights do not make the sampled cohort representative of all Codeforces
users.

## Checks

Tests cover future-event invariance, current-target isolation, same-second batching, delayed
outcomes, historical rating boundaries, excluded first attempts, retry handling, incomplete
histories, user-disjoint splits, and balanced weights. Real-data rebuilds preserve feature values
and split assignments.
