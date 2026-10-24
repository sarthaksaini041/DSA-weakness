# ES 335 requirements and project checklist

Source: team-uploaded _Machine Learning Course Portal.html_, checked on 2026-10-23. The portal is
the course reference; this document records our implementation and evidence plan. It does not claim
unfinished requirements are complete.

## Track and submission

- Work individually or with one partner: **maximum two students**. Names and roll numbers still need
  to be added to the proposal. Do not commit private student details without the team's agreement.
- Deliver an **interactive static website published on GitHub Pages** and submit both the live site
  and source-repository links. Neither site deployment nor submission has happened yet.
- Python collection and model training run offline. The published deliverable must work without a
  Python/Node backend. Use precomputed examples or browser-compatible inference; live handle entry
  depends on separately verified browser access and model export. A precomputed demo must be clearly
  labeled.
- A graduate LaTeX paper and graduate depth component are **not ES 335 requirements**.

## Dates from the uploaded portal

- Proposal deadline: **15 October 2026, 11:59 PM IST**. This date has passed as of this audit. The
  repository proposal is not evidence of portal submission. If the team has not submitted, check the
  course staff's late-submission arrangement.
- Final project: **17 November 2026**. The uploaded page does not specify a final-submission time;
  do not invent one.

## Rubric evidence

Use the checklist below to track all 80 shared ML points and all 20 undergraduate deliverable
points. Every result must link to actual scripts, artifacts, or a reproducible command.

Before training, freeze the target verdict policy, row definition, temporal split rules, feature
definitions, and model-selection procedure. Record the data inventory, exclusions, missingness, and
sampling limitations. Fit learned preprocessing on training data only. Report the simple baseline
alongside all three models. Do not pick a model or revise preprocessing based on final-test results.

Do not optimize for a headline accuracy claim: justify metrics, inspect representative errors, show
uncertainty and evidence counts, and explain limits of recommendations. Statistical significance
tests and deep learning are not mandatory.

## Required website content and useful interaction

The final site must visibly cover: question, data, preprocessing, baseline and methods, evaluation,
results, errors, limitations, conclusion, and reproduction steps.

The planned meaningful interaction is to select a user/example, inspect topic performance at
different difficulties, and see why candidate practice problems were suggested. Add a
model-comparison view or probability/evidence breakdown so visitors can understand a result, rather
than merely submit a handle. Show insufficient evidence explicitly. Verify navigation and
interactions on the deployed GitHub Pages site.

## Individual understanding and defense

Before submission, each student should fill in a contribution statement and explain:

1. What one row and the target mean, and why prediction-time features avoid leakage.
2. Why the baseline and each of the three methods were selected.
3. How the data was sampled, split, and evaluated.
4. One representative error and one limitation.
5. What would change if a rating feature, topic feature, threshold, or split were changed.

Do not fabricate individual contributions or claim that the students verified work they have not
reviewed.

## Responsible sharing and AI assistance

Keep secrets and unnecessary personal profile fields out of the published site and Git. The team
authorized a reviewed archive of public Codeforces data, including handles; expanded working files
remain ignored. Audit shareable data before deployment. Cite Codeforces and any external
code/materials used. Public API access does not by itself establish permission to redistribute all
captured records.

The portal explicitly permits AI assistance and requires its disclosure and independent checking.
Keep [ai_usage.md](../ai_usage.md) accurate. This disclosure is separate from Git authorship: follow
the user's instruction not to add an assistant as author or co-author.

## Current gaps

The proposal, sampling plan, API validation, and [120-user data report](data_report.md) exist.
Full-cohort historical features and split artifacts are frozen; all declared coverage gates passed,
with recruitment, historical-availability, and sparse-group limitations disclosed. Training-only
preprocessing, model comparison, validation diagnostics, and frozen final evaluation are documented
in `model_results.md`, `model_checks.md`, and `test_results.md`. Offline topic analysis and
recommendations are implemented in `recommend.py` and documented in `recommendations.md`. The static
website and its meaningful interactions are implemented and locally browser-tested (see
`website.md`). Deployment, student details, contribution statements, and final submission remain
unfinished. They must stay marked pending until supported by evidence.

## Rubric and evidence checklist

This checklist is a completion gate, not a claim that the criteria are already satisfied. Update
evidence as work is completed. Accuracy alone is not sufficient.

| Criterion                               |  Points | Evidence required                                                                                                          | Current status                                                                                                                                                     |
| --------------------------------------- | ------: | -------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Problem formulation and scope           |      10 | Question, target, row meaning, prediction time, available inputs, and limits                                               | Defined in proposal; validate assumptions with data                                                                                                                |
| Data understanding                      |      10 | Source, actual size, variables, access limits, missingness, participation and sampling audits                              | 120-user cohort, aggregate plots, distributions, and limitations documented in `data_report.md`                                                                    |
| Preprocessing and statistical reasoning |      10 | Justified cleaning, plots, training-only transformations, temporal feature audit                                           | Full-cohort features, temporal tests, missingness audit, and data plots implemented; training-only learned preprocessing implemented                               |
| Baseline and method selection           |      15 | Acceptance-rate baseline; objectives, assumptions, and rationale for Logistic Regression, Random Forest, Gradient Boosting | Baseline and all three models fitted; validation comparison in `model_results.md`                                                                                  |
| Evaluation design and metrics           |      20 | Frozen time splits, validation-only tuning, held-out final test, justified probability/classification metrics              | Full-cohort manifests frozen; all declared coverage gates pass, including user-disjoint test; validation and frozen final results available in `test_results.md`   |
| Results, errors, and limitations        |      10 | Baseline comparison, representative errors, uncertainty, calibration, subgroup limits, no causal overclaim                 | Validation sensitivity, calibration, user-bootstrap intervals and error/subgroup analysis in `model_checks.md`; final metrics and uncertainty in `test_results.md` |
| Reproducibility and technical integrity |       5 | Data access, capture metadata, seeds, dependencies, split details, commands, responsible data handling                     | Collection through final-evaluation commands, hashes and tests available; static export and browser checks available; published-site verification pending          |
| Interactive website                     |      10 | Clear, navigable static site published on GitHub Pages, explaining evidence and conclusions                                | Static site implemented and locally browser-tested; GitHub Pages publication pending                                                                               |
| Useful interaction                      |       5 | Handle/example selection, topic evidence, difficulty filtering, and explained recommendations that help inspect results    | Saved-handle selection, topic/difficulty filters, and test/averaging comparison implemented; local browser checks pass                                             |
| Individual understanding and defense    |       5 | Each student explains contribution, choices, evaluation, limitation, and effects of a small change                         | Team details and defense notes pending                                                                                                                             |
| **Total**                               | **100** | **80 shared ML reasoning + 20 ES 335 deliverable**                                                                         | **No score claimed**                                                                                                                                               |

## Final website sections

- [x] Question and prediction scope
- [x] Data source, row meaning, collection date, cohort size, and data quality
- [x] Varied user cohort verified against `sampling.md`, including target-versus-actual rating
      counts, activity/history coverage, and user dominance
- [x] Preprocessing and leakage prevention
- [x] Baseline and three methods with reasons
- [x] Evaluation splits and metrics
- [x] Results and useful interactive exploration
- [x] Representative errors, uncertainty, and limitations
- [x] Conclusions supported by evidence
- [x] Reproduction steps, references, and AI assistance disclosure
- [ ] Verified GitHub Pages deployment
- [ ] Individual contribution and defense notes

## Rules to keep throughout

- Do not substitute synthetic/offline test success for real API validation or model evaluation.
- Do not count truncated histories as complete first-attempt data.
- Do not optimize models using final test results.
- Do not interpret missing evidence as a weakness, or recommendations as demonstrated learning
  gains.
- Keep secrets and unnecessary personal fields out of Git; publish public raw data only through the
  reviewed snapshot archive.
