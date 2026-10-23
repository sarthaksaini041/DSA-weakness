#!/usr/bin/env python3
"""Build a reproducible pilot feature table; does not fit preprocessing or models."""

import argparse
from collections import Counter, defaultdict, deque
import csv
import hashlib
from itertools import groupby
import json
from pathlib import Path
import random

from collect_data import REJECTIONS, save

NUMERIC_FEATURES = [
    "prior_problems_attempted", "prior_problems_solved", "prior_first_attempts_judged",
    "prior_first_acceptance_rate", "recent_20_acceptance_rate", "recent_20_count",
    "topic_prior_attempts_mean", "topic_prior_judged_mean", "topic_acceptance_rate_mean",
    "historical_rating", "historical_rating_missing", "problem_rating", "problem_rating_missing",
    "rating_gap", "days_since_previous_attempt", "attempts_previous_30_days", "tag_count",
]
CATEGORICAL_FEATURES = ["problem_tags"]


def problem_key(submission):
    p = submission.get("problem", {})
    return (p["contestId"], p["index"]) if "contestId" in p and "index" in p else None


def individual(submission, handle):
    members = submission.get("author", {}).get("members", [])
    return len(members) == 1 and members[0].get("handle", "").casefold() == handle.casefold()


def eligible(submission, handle):
    p = submission.get("problem", {})
    return (individual(submission, handle) and p.get("type") == "PROGRAMMING"
            and not any(t.startswith("*") for t in p.get("tags", []))
            and submission.get("verdict") in REJECTIONS | {"OK"})


def mean(values):
    return sum(values) / len(values) if values else None


def user_features(capture, analysis_id, outcome_lag_seconds=86400):
    """Snapshot each equal-time batch before adding its attempts or outcomes.

    API verdict-availability timestamps are absent. A conservative outcome lag is
    a proxy, not proof that historical verdicts were observable at prediction time.
    """
    if not capture["summary"]["history_complete"] or not capture["head_stable"]:
        raise ValueError(f"{analysis_id}: incomplete or shifting history")
    handle = capture["user"]["handle"]
    unique = {}
    for s in capture["submissions"]:
        if s["id"] in unique and unique[s["id"]] != s:
            raise ValueError("Conflicting duplicate submission ID")
        unique[s["id"]] = s
    submissions = sorted(unique.values(), key=lambda s: (s["creationTimeSeconds"], s["id"]))
    ratings = sorted(capture["rating_history"], key=lambda r: r["ratingUpdateTimeSeconds"])
    rating_cursor = 0
    historical_rating = None
    seen, attempted, solved = set(), set(), set()
    topic_attempts, topic_judged, topic_accepted = Counter(), Counter(), Counter()
    judged = accepted = 0
    recent = deque(maxlen=20)
    attempts_30 = deque()
    last_attempt = None
    pending = deque()
    rows = []
    for timestamp, batch_iter in groupby(submissions, key=lambda s: s["creationTimeSeconds"]):
        batch = list(batch_iter)
        while rating_cursor < len(ratings) and ratings[rating_cursor]["ratingUpdateTimeSeconds"] < timestamp:
            historical_rating = ratings[rating_cursor]["newRating"]
            rating_cursor += 1
        while pending and pending[0][0] < timestamp - outcome_lag_seconds:
            _, key, tags, ok, first_eligible = pending.popleft()
            if ok:
                solved.add(key)
            if first_eligible:
                judged += 1
                accepted += ok
                recent.append(int(ok))
                topic_judged.update(tags)
                if ok:
                    topic_accepted.update(tags)
        while attempts_30 and attempts_30[0] < timestamp - 30 * 86400:
            attempts_30.popleft()
        # Equal-second submissions never supply features to each other. Tie-break
        # by ID only to identify the single first recorded attempt to a problem.
        first_in_batch = set()
        updates = []
        for s in batch:
            key = problem_key(s)
            if key is None:
                continue
            is_first = key not in seen and key not in first_in_batch
            first_in_batch.add(key)
            p = s["problem"]
            tags = sorted(set(p.get("tags", [])))
            first_eligible = is_first and eligible(s, handle)
            if first_eligible:
                problem_rating = p.get("rating")
                rows.append({
                    "analysis_id": analysis_id, "submission_id": s["id"], "timestamp": timestamp,
                    "problem_id": f"{key[0]}:{key[1]}", "target": int(s["verdict"] == "OK"),
                    "prior_problems_attempted": len(attempted), "prior_problems_solved": len(solved),
                    "prior_first_attempts_judged": judged,
                    "prior_first_acceptance_rate": accepted / judged if judged else None,
                    "recent_20_acceptance_rate": mean(list(recent)), "recent_20_count": len(recent),
                    "topic_prior_attempts_mean": mean([topic_attempts[t] for t in tags]),
                    "topic_prior_judged_mean": mean([topic_judged[t] for t in tags]),
                    "topic_acceptance_rate_mean": mean([topic_accepted[t] / topic_judged[t] for t in tags if topic_judged[t]]),
                    "historical_rating": historical_rating, "historical_rating_missing": int(historical_rating is None),
                    "problem_rating": problem_rating, "problem_rating_missing": int(problem_rating is None),
                    "rating_gap": problem_rating - historical_rating if problem_rating is not None and historical_rating is not None else None,
                    "days_since_previous_attempt": (timestamp - last_attempt) / 86400 if last_attempt is not None else None,
                    "attempts_previous_30_days": len(attempts_30), "tag_count": len(tags),
                    "problem_tags": tags,
                })
            if individual(s, handle):
                updates.append((key, tags, s, first_eligible))
        seen.update(first_in_batch)
        for key, tags, s, first_eligible in updates:
            if key not in attempted:
                attempted.add(key)
                topic_attempts.update(tags)
                attempts_30.append(timestamp)
                last_attempt = timestamp
            if s.get("verdict") in REJECTIONS | {"OK"}:
                pending.append((timestamp, key, tags, s["verdict"] == "OK", first_eligible))
    return rows


def assign_splits(rows, users, seed=42):
    """Hold out users within strata, then derive time cutoffs from development only."""
    groups = defaultdict(list)
    for user in users:
        groups[user["stratum"]].append(user["analysis_id"])
    rng = random.Random(seed)
    heldout = []
    for group in sorted(groups):
        ids = sorted(groups[group])
        rng.shuffle(ids)
        heldout.extend(ids[:max(1, len(ids) // 5)] if len(ids) > 1 else [])
    development = [r for r in rows if r["analysis_id"] not in heldout]
    times = sorted(r["timestamp"] for r in development)
    unique_times = sorted(set(times))
    if len(unique_times) < 3:
        raise ValueError("Need at least three development timestamps for chronological splits")
    validation_start = times[min(len(times) - 1, int(len(times) * .70))]
    test_start = times[min(len(times) - 1, int(len(times) * .85))]
    if validation_start >= test_start or validation_start == unique_times[0]:
        raise ValueError("Timestamp ties prevent nonempty ordered splits")
    for row in rows:
        if row["analysis_id"] in heldout:
            row["split"] = "unseen_user_test" if row["timestamp"] >= test_start else "unseen_user_context"
        else:
            row["split"] = "train" if row["timestamp"] < validation_start else "validation" if row["timestamp"] < test_start else "temporal_test"
    train_counts = Counter(r["analysis_id"] for r in rows if r["split"] == "train")
    total = sum(train_counts.values())
    for row in rows:
        row["training_weight"] = total / (len(train_counts) * train_counts[row["analysis_id"]]) if row["split"] == "train" else None
    return {"seed": seed, "heldout_users": sorted(heldout), "validation_start": validation_start,
            "test_start": test_start, "cutoffs_derived_from": "development users only",
            "unseen_user_context": "Not training or evaluation data; earlier personal history can inform later heldout-user predictions.",
            "protocol": "Frozen models trained on train; validation-only tuning; tests never used for selection. Per-user history updates online from earlier events with the configured outcome lag.",
            "limitation": "Coverage must be audited before fitting: assigned heldout users may have no rows after the test cutoff. A pilot manifest does not substitute for the full-cohort manifest."}


def build(source, output, lag):
    audit = json.loads((source / "audit.json").read_text())
    if audit["failures"]:
        raise ValueError("Resolve cohort collection failures before building features")
    rows = []
    hashes = {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
              for name in ("audit.json", "selection.json")}
    for user in audit["users"]:
        path = source / "users" / f"{user['analysis_id']}.json"
        raw = path.read_bytes()
        hashes[str(path.relative_to(source))] = hashlib.sha256(raw).hexdigest()
        rows.extend(user_features(json.loads(raw), user["analysis_id"], lag))
    rows.sort(key=lambda r: (r["timestamp"], r["analysis_id"], r["submission_id"]))
    if len(rows) != audit["eligible_first_attempt_rows"]:
        raise ValueError("Feature-row count disagrees with the collection eligibility audit")
    split = assign_splits(rows, audit["users"])
    existing_manifest = output / "manifest.json"
    if existing_manifest.exists():
        previous = json.loads(existing_manifest.read_text())
        if previous["source_sha256"] != hashes or previous["outcome_lag_seconds"] != lag:
            raise ValueError("Inputs or outcome lag changed; choose a new --output directory to preserve the frozen pilot split")
    output.mkdir(parents=True, exist_ok=True)
    # Explicit whitelist separates model inputs from identifiers, targets, and splits.
    schema = {"numeric_features": NUMERIC_FEATURES, "multilabel_features": CATEGORICAL_FEATURES,
              "forbidden_model_inputs": ["analysis_id", "submission_id", "timestamp", "problem_id", "target", "split", "training_weight"],
              "missing_values": "null in JSON / empty in CSV; impute using training data only",
              "outcome_lag_seconds": lag,
              "availability_limitations": ["Final verdicts lack historical availability timestamps; outcome lag reduces ordinary judging overlap but cannot eliminate delayed judging/rejudging bias.",
                                          "Problem tags and difficulty are collection-time snapshots, not historical snapshots.",
                                          "Rating-history records and final verdicts may reflect later corrections."]}
    save(output / "features.json", rows)
    with (output / "features.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "problem_tags": json.dumps(row["problem_tags"])})
    save(output / "schema.json", schema)
    save(output / "splits.json", split)
    counts = {}
    for name in sorted({r["split"] for r in rows}):
        part = [r for r in rows if r["split"] == name]
        counts[name] = {"rows": len(part), "users": len({r["analysis_id"] for r in part}),
                        "outcomes": dict(Counter(r["target"] for r in part)),
                        "cold_start_rows": sum(r["prior_first_attempts_judged"] == 0 for r in part),
                        "min_timestamp": min(r["timestamp"] for r in part), "max_timestamp": max(r["timestamp"] for r in part)}
    manifest = {"source": str(source), "source_sha256": hashes,
                "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "row_count": len(rows), "split_counts": counts, "outcome_lag_seconds": lag,
                "preprocessing_fitted": False, "models_trained": False}
    save(output / "manifest.json", manifest)
    print(json.dumps({"row_count": len(rows), "split_counts": counts}, indent=2))


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=root / "data/raw")
    parser.add_argument("--output", type=Path, default=root / "data/processed")
    parser.add_argument("--outcome-lag-seconds", type=int, default=86400)
    args = parser.parse_args()
    if args.outcome_lag_seconds < 0:
        parser.error("outcome lag must be nonnegative")
    try:
        build(args.source, args.output, args.outcome_lag_seconds)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"Feature build failed: {exc}\n")


if __name__ == "__main__":
    main()
