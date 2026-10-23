# Data collection and evaluation plan

This protocol was defined before full collection. The 120-user target is now met;
[the data report](data_report.md) records actual counts. No model performance results exist.

## Frozen recruitment

Target: 120 unique users, 20 in each of the existing six rating strata. Within each rated stratum,
sample 10 users from the current active-rated directory and 10 from the broad directory, excluding
already selected handles. Active-directory membership is a recruitment proxy, not verified recent
submission activity. Sample 20 unrated users from the pilot's frozen public recent-submission
candidate pool. Use seed 42 and case-insensitive deduplication; exclude `tourist`.

Reuse the pilot's broad-rated and unrated candidate snapshots rather than refreshing until a desired
cohort appears. Capture a new active-rated pool. Record each pool's source path and SHA-256 and
freeze selected handles before fetching histories. The full cohort may overlap the pilot; it is not
an independent replication. No pilot-trained models exist, and all model evaluation will use the new
cohort split manifest.

The protocol deliberately mixes active and broad-directory recruitment to improve future-data
coverage over the predominantly inactive pilot. History sizes are audited after collection, without
dropping sparse users. Inactive/no-history unrated users remain out of scope.

## Collection and failures

Run one collector, with at least 2.1 seconds between requests. Fetch complete histories, rating
timelines, and one shared catalog; check the newest submission again after pagination. Save
collection timestamps, missingness, verdict and participant-type counts, and pseudonymous IDs. Keep
expanded raw records ignored by Git. The team authorized publishing the reviewed public-data
snapshot as `data/raw_data.tar.gz`, including the selected public handles.

Do not silently replace unavailable users, changed rating strata, or unstable histories. Batch
current-profile verification can identify stale directory ratings. For a stratum mismatch, use
`check_users.py` to select deterministic reserves from the same frozen source and intended rating
stratum, confirmed by current profile. Keep the original selection, mismatch evidence, replacement
reason, and any existing capture in a timestamped amendment archive. This eligibility correction
must not depend on submission outcomes or model results. Retry other failures only after diagnosis;
record remaining gaps before claiming the target was met.

Profile checks may be batched (up to 50 per request) and cached with their timestamps. A single
exhausted history response has no offset-pagination gap and needs no extra head request. Multi-page
histories still require a newest-ID recheck. The metadata records which consistency check was used.

## Feature and split protocol

Use the same target eligibility policy and 17 numeric inputs plus tags documented in `features.md`.
Keep the default one-day outcome-availability proxy and its limitations. Fit no
imputation/scaling/tag vocabulary until training begins.

Hold out approximately 20% of users within rating strata using seed 42. Derive chronological
70/15/15 cutoffs using development users only. Never use held-out users for model fitting or tuning.
Evaluate held-out users only at/after the final chronological test cutoff; retain their earlier
history solely as personal context. Keep test outcomes out of model selection.

## Pre-model audit gates

These are minimum practical coverage checks, not statistical proof of representativeness or
sufficient power:

- 120 complete, unique, stable captures; 20 per rating group, with smoke-test exclusion.
- Report rating × source, activity/history, topic, difficulty, missingness, and excluded-verdict
  distributions.
- Training and validation each contain both classes and at least 10 represented users.
- Temporal test: at least 200 rows, 10 users, and 20 outcomes in each class.
- Unseen-user test: at least 100 rows, 10 users, 20 outcomes in each class, and at least one
  represented user from each rating stratum.
- Report subgroup counts even when insufficient; no claim of reliable subgroup performance merely
  because a group appears once.
- Report largest-user/top-10% row shares and training-only inverse-user-count weights.
- Verify time ordering, disjoint held-out users, source hashes, row uniqueness, and deterministic
  rebuilds.

If a gate fails, keep the artifacts, state the coverage limitation, and plan any recruitment
adjustment before model fitting. Do not move cutoffs, change seeds, or sample by labels to
manufacture passing gates. Broader collection may be needed; changing recruitment must be documented
and require a new frozen cohort version.

## Rating groups

Twenty users were collected in each group: unrated, below 1200, 1200–1399, 1400–1599, 1600–1899, and
1900+. Unrated does not mean beginner. Current ratings define collection groups only; historical
prediction features use earlier rating updates.

## Files retained after cleanup

The original candidate snapshots are kept under `data/raw/candidates/` (and the active-rated list
directly under `data/raw/`). Historical paths inside frozen metadata are retained as provenance; the
code locates moved snapshots by filename and verifies their original SHA-256. Excluded
rating-correction records stay under `data/raw/changes/`. They are not training rows. Retired pilot
captures, duplicate feature builds, and smoke-test data were removed.
