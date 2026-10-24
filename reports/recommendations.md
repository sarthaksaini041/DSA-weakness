# Topic analysis and practice recommendations

`code/recommend.py` accepts a Codeforces handle from the saved cohort and produces an explained
recommendation JSON file. It uses the frozen Random Forest selected before final testing, without
refitting, changing the threshold, or tuning against final results. This is an offline prototype;
arbitrary live-handle collection and the interactive website are not implemented yet.

## Run it

From the repository root, after restoring data and running the documented training steps:

```bash
python3 code/recommend.py ethanxupro
python3 code/recommend.py ethanxupro --topic graphs --min-rating 1000 --max-rating 1200 --limit 3 --output data/processed/graph_recommendations.json
python3 code/recommend.py rahma_hisham925 --output data/processed/sparse_recommendations.json
```

Handles are matched case-insensitively against the saved cohort. An unknown handle returns a clear
error instead of invented results. Output defaults to `data/processed/recommendations.json` and
stays ignored by Git. The output records capture/catalog dates, input hashes, code hash and selected
model. Existing frozen artifact, preprocessing and feature-code hashes are checked before inference.

## How topic evidence works

Use at most the latest 200 eligible first attempts after the original training cutoff, whose
outcomes are more than one day old at the capture timestamp. Excluding training-period rows avoids
presenting in-sample model residuals as new evidence. This application uses available post-training
history, including the elapsed evaluation period; it is not a new independent model evaluation.

For each topic, report attempted/accepted counts, observed acceptance, average model expectation,
and a descriptive 95% Wilson interval for the observed acceptance rate. Attempts are correlated and
topics overlap, so the interval is not proof of a statistically significant weakness.

For difficulty-adjusted comparison:

1. Compute each eligible attempt's residual: actual outcome minus its historical model prediction.
2. Find the user's other problems without that topic in the same 400-rating band.
3. Subtract the average residual of those comparison problems from the topic attempt's residual.
4. Average these contrasts across topic attempts with comparison evidence.

This compares against the user's own performance at broadly similar difficulty while accounting for
model expectations. Missing-difficulty rows contribute to raw summaries but not to matched
contrasts. If other problems lack a comparable band, they supply no comparison evidence. Model
predictions already include topic history, so this contrast is an exploratory relative-performance
signal, not an independent measure of topic mastery or a causal diagnosis.

A topic becomes a **practice candidate** only with at least 30 eligible recent evidence rows
overall, 10 matched topic attempts, 10 distinct comparison problems, a negative contrast, and a
historical user rating. Otherwise it shows **insufficient evidence**, or **no lower-performance
signal** when adequate evidence does not indicate a negative contrast. Unseen topics are never
inferred to be weak.

The 30/10/10 counts, 200-row window and 400-rating bands are explicit product heuristics. They were
not optimized on final-test scores and are not validated reliability thresholds. Small negative
contrasts may be noise. The website should use “practice candidate,” never “proven weakness.”

## How problems are selected

- Exclude every previously attempted problem, including accepted solutions, unsuccessful retries,
  compilation errors and team attempts. This prototype recommends new problems only; retry support
  remains optional future work.
- Require a rated, tagged programming problem without special `*` tags in the saved catalog.
- Apply the requested difficulty and topic filters. Without a chosen range, use the historical user
  rating rounded down to the nearest 100, plus/minus 200, with a lower limit of 800. For users
  without a rating, offer 800–1200 exploration problems without personalized probabilities.
- Build all candidate features at the same capture timestamp with the original one-day outcome lag.
  Temporary query records reuse the frozen historical feature builder. Their placeholder outcomes
  are discarded; they never enter the dataset, fit a model, or update another candidate's history.
- Prioritize problems matching supported practice topics, then higher predicted acceptance, with a
  deterministic problem-ID tie-break. There is no tuned success-probability cutoff. This may favor
  easier practice and is not a demonstrated optimal learning strategy.
- Show topic relevance, difficulty, an estimated probability when evidence permits, and a Codeforces
  problem link. If no eligible problems remain, return an empty list rather than relax the filters.

Users with fewer than 30 evidence rows or no historical rating get **exploration only**, no weakness
labels and no candidate probability estimates. This is a conservative display choice motivated by
known evidence limitations, not a test-tuned model change. Sparse topics remain unranked as
weaknesses.

## Checked examples

Using the saved 23 October 2026 captures:

| Example           | Evidence                                    | Output                                               |
| ----------------- | ------------------------------------------- | ---------------------------------------------------- |
| `ethanxupro`      | 126 eligible post-training, mature attempts | Personalized estimates; default difficulty 1000–1400 |
| `rahma_hisham925` | No mature evidence rows at capture time     | Exploration only; no predicted probabilities         |

In the first example, graphs have 20 matched attempts and 72 distinct comparison problems, with a
relative gap of approximately −0.117. Greedy has 46 matched attempts, 79 comparison problems, and a
gap of approximately −0.064. Both are descriptive practice candidates. Shortest paths has only 7
attempts and therefore remains insufficient evidence even though its estimated contrast is more
negative. This prevents a very small sample from dominating the advice.

Examples demonstrate implementation behavior, not recommendation effectiveness. The model is
imperfectly calibrated and predicts acceptance on self-selected attempted problems; applying it to
new candidate problems is an extrapolation. Saved histories may be stale, and problem tags/ratings
are snapshots. Live fetching, browser integration, user feedback and prospective learning-benefit
measurement remain unfinished.

## Checks

Automated tests cover attempted-problem exclusion, compilation/team attempts, duplicate catalog
entries, same-time query isolation, unchanged capture contents, the outcome lag, matched-difficulty
requirements, sparse-history fallback and descriptive rate intervals. End-to-end checks use the
actual saved model and captures. Final test scores and model artifacts are preserved.
