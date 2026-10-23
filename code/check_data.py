#!/usr/bin/env python3
"""Audit cohort/split coverage and publish aggregate evidence, not model scores."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from collect_data import STRATA, save
from select_users import saved_source


def coverage_gates(audit, rows):
    users = {u["analysis_id"]: u for u in audit["users"]}
    gates = {"complete_120_user_quota": audit["completed_users"] == 120 and audit["failures"] == 0
             and all(audit["actual_per_stratum"].get(g, 0) == 20 for g in STRATA)}
    details = {}
    for name in ("train", "validation", "temporal_test", "unseen_user_test"):
        part = [r for r in rows if r["split"] == name]
        ids = {r["analysis_id"] for r in part}
        outcomes = Counter(r["target"] for r in part)
        strata = Counter(users[uid]["stratum"] for uid in ids)
        details[name] = {"rows": len(part), "users": len(ids), "accepted": outcomes[1], "rejected": outcomes[0],
                         "users_per_stratum": dict(strata),
                         "cold_start_rows": sum(r["prior_first_attempts_judged"] == 0 for r in part)}
        if name in ("train", "validation"):
            gates[name + "_coverage"] = len(ids) >= 10 and outcomes[0] > 0 and outcomes[1] > 0
        else:
            minimum = 200 if name == "temporal_test" else 100
            gates[name + "_coverage"] = len(part) >= minimum and len(ids) >= 10 and min(outcomes[0], outcomes[1]) >= 20
            if name == "unseen_user_test":
                gates["unseen_rating_coverage"] = all(strata[g] >= 1 for g in STRATA)
    train_ids = {r["analysis_id"] for r in rows if r["split"] in ("train", "validation", "temporal_test")}
    held_ids = {r["analysis_id"] for r in rows if r["split"].startswith("unseen_")}
    gates["user_disjointness"] = not bool(train_ids & held_ids)
    gates["unique_user_problem_rows"] = len({(r["analysis_id"], r["problem_id"]) for r in rows}) == len(rows)
    times = {n: [r["timestamp"] for r in rows if r["split"] == n] for n in details}
    gates["time_ordering"] = bool(all(times.values())) and max(times["train"]) < min(times["validation"]) and max(times["validation"]) < min(times["temporal_test"] + times["unseen_user_test"])
    return gates, details


def plots(audit, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    output.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), constrained_layout=True)
    panels = [({g: audit["actual_per_stratum"].get(g, 0) for g in STRATA}, "Users by collection-time rating"),
              ({g: audit["history_bins"].get(g, 0) for g in ("0_19", "20_99", "100_499", "500_plus")}, "Users by unique-problem history"),
              ({g: audit["activity_bins"].get(g, 0) for g in ("0_30", "31_180", "181_plus", "no_history")}, "Users by submission recency (days)")]
    labels = {
        "unrated": "Unrated", "below_1200": "Below 1200", "1200_1399": "1200–1399",
        "1400_1599": "1400–1599", "1600_1899": "1600–1899", "1900_plus": "1900+",
        "0_19": "0–19", "20_99": "20–99", "100_499": "100–499", "500_plus": "500+",
        "0_30": "0–30", "31_180": "31–180", "181_plus": "181+", "no_history": "No history",
    }
    for ax, (counts, title) in zip(axes, panels):
        bars = ax.bar([labels[g] for g in counts], list(counts.values()), color="#386cb0")
        ax.set_title(title, fontsize=10)
        ax.set_ylabel("Users")
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        ax.tick_params(axis="x", labelrotation=45, labelsize=8)
        ax.bar_label(bars, fontsize=8)
        ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(output / "cohort_coverage.png", dpi=160)
    plt.close(fig)
    difficulty = Counter()
    for rating, n in audit["difficulty_submission_counts"].items():
        group = "missing" if rating == "missing" else "<1200" if int(rating) < 1200 else "1200–1599" if int(rating) < 1600 else "1600–1999" if int(rating) < 2000 else "2000+"
        difficulty[group] += n
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    ordered_difficulty = ["<1200", "1200–1599", "1600–1999", "2000+", "missing"]
    axes[0].bar(["Not rated" if g == "missing" else g for g in ordered_difficulty], [difficulty[g] for g in ordered_difficulty], color="#2c8b75")
    axes[0].set_title("Submission difficulty coverage")
    axes[0].set_ylabel("Submissions (retries included)")
    topics = Counter(audit["tag_submission_counts"]).most_common(12)
    axes[1].barh([t for t, _ in reversed(topics)], [n for _, n in reversed(topics)], color="#386cb0")
    axes[1].set_title("12 most frequent topic tags")
    axes[1].set_xlabel("Tag assignments across submissions (not exclusive)")
    fig.savefig(output / "problem_coverage.png", dpi=160)
    plt.close(fig)


def main():
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=repo / "data/raw")
    parser.add_argument("--features", type=Path, default=repo / "data/processed")
    parser.add_argument("--report", type=Path, default=repo / "reports/data_report.md")
    parser.add_argument("--plots", type=Path, default=repo / "reports/images")
    args = parser.parse_args()
    audit = json.loads((args.source / "audit.json").read_text())
    selection = json.loads((args.source / "selection.json").read_text())
    rows = json.loads((args.features / "features.json").read_text())
    manifest = json.loads((args.features / "manifest.json").read_text())
    schema = json.loads((args.features / "schema.json").read_text())
    splits = json.loads((args.features / "splits.json").read_text())
    gates, details = coverage_gates(audit, rows)
    gates["source_integrity"] = all(hashlib.sha256((args.source / name).read_bytes()).hexdigest() == digest
                                    for name, digest in manifest["source_sha256"].items())
    gates["candidate_snapshot_integrity"] = all(saved_source(args.source, record).is_file() for record in selection["source_snapshots"].values())
    handles = [u["handle"].casefold() for u in selection["users"]]
    gates["unique_handles_and_smoke_exclusion"] = len(handles) == len(set(handles)) and "tourist" not in handles
    inputs = set(schema["numeric_features"] + schema["multilabel_features"])
    gates["feature_input_allowlist"] = not bool(inputs & set(schema["forbidden_model_inputs"]))
    weight_totals = defaultdict(float)
    for row in rows:
        if row["split"] == "train":
            weight_totals[row["analysis_id"]] += row["training_weight"]
    gates["balanced_training_user_weights"] = bool(weight_totals) and max(weight_totals.values()) - min(weight_totals.values()) < 1e-6
    save(args.features / "coverage_gates.json", {"gates": gates, "split_details": details,
                                               "all_passed": all(gates.values()), "model_results": False})
    plots(audit, args.plots)
    lines = ["# Full cohort data and split audit", "", "Generated from captured data and frozen feature artifacts. No models have been trained; these are coverage checks, not model results or proof of generalization.", "", "## Collection", "", f"Selection frozen: `{selection['created_at']}`. Random seed: 42. Raw data and handle mappings remain excluded from Git.", "", "| Measure | Observed |", "| --- | ---: |"]
    for label, key in (("Completed users", "completed_users"), ("Submissions", "submissions"),
                       ("Eligible first-attempt rows", "eligible_first_attempt_rows"), ("Submissions without difficulty", "missing_problem_ratings"),
                       ("Submissions without tags", "missing_tags"), ("Team submissions", "team_submissions"), ("Failed/review captures", "failures")):
        lines.append(f"| {label} | {audit[key]:,} |")
    replacement_count = sum(a.get("replacements", 0) for a in selection.get("amendments", []))
    lines += ["", f"Recorded rating-eligibility replacements: **{replacement_count}**. Directory/profile mismatches used seeded same-source reserves confirmed by current profile; original membership, mismatch evidence, and available captures are preserved under local `changes/`. No submission outcomes or model scores were used to choose replacements."]
    lines += ["", "| Rating group | Target users | Completed users |", "| --- | ---: | ---: |"]
    for group in STRATA:
        lines.append(f"| {group} | 20 | {audit['actual_per_stratum'].get(group, 0)} |")
    lines += ["", "![User rating, history, and activity coverage](images/cohort_coverage.png)", "", "![Problem difficulty and topic coverage](images/problem_coverage.png)", "", "## Recruitment sources", "", "| Rating group | Source | Completed users |", "| --- | --- | ---: |"]
    sources = Counter((u["stratum"], u.get("source", "unknown")) for u in audit["users"] if u["status"] == "complete")
    for (group, source), n in sorted(sources.items()):
        lines.append(f"| {group} | {source} | {n} |")
    for title, key in (("Participation across submissions", "participant_type_counts"),
                       ("Verdicts across submissions", "verdict_counts"),
                       ("First-attempt exclusions", "first_attempt_exclusions")):
        lines += ["", f"## {title}", "", "| Category | Count |", "| --- | ---: |"]
        for category, n in sorted(audit[key].items()):
            lines.append(f"| {category} | {n:,} |")
    lines += ["", "## Frozen split coverage", "", "| Split | Rows | Users | Accepted | Rejected | Cold-start rows |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, d in details.items():
        lines.append(f"| {name} | {d['rows']:,} | {d['users']} | {d['accepted']:,} | {d['rejected']:,} | {d['cold_start_rows']} |")
    context = manifest["split_counts"].get("unseen_user_context", {})
    lines += ["", f"Unseen-user context: {context.get('rows', 0):,} rows, excluded from fitting, tuning, and scoring. Only earlier personal history informs later held-out predictions.", "", "| Boundary | UTC timestamp |", "| --- | --- |"]
    for key in ("validation_start", "test_start"):
        lines.append(f"| {key} | {datetime.fromtimestamp(splits[key], timezone.utc).isoformat()} |")
    lines += ["", "| Split | Users represented per rating group |", "| --- | --- |"]
    for name, d in details.items():
        lines.append(f"| {name} | " + "; ".join(f"{g}: {d['users_per_stratum'].get(g, 0)}" for g in STRATA) + " |")
    lines += ["", "## Training feature missingness", "", "Measured on training rows only. No imputation, scaling, or tag vocabulary has been fitted.", "", "| Numeric input | Missing training rows |", "| --- | ---: |"]
    train_rows = [r for r in rows if r["split"] == "train"]
    for feature in schema["numeric_features"]:
        lines.append(f"| {feature} | {sum(r[feature] is None for r in train_rows):,} |")
    lines += ["", "## Pre-model gates", "", "Thresholds were declared in `sampling.md` before full collection. Passing them permits development to proceed; it does not establish statistical power or reliable subgroup predictions.", "", "| Gate | Result |", "| --- | --- |"]
    for name, passed in gates.items():
        lines.append(f"| {name} | {'PASS' if passed else 'FAIL'} |")
    lines += ["", "## User dominance and limitations", "", f"- Largest user's eligible-row share: **{audit['largest_user_row_fraction']:.1%}**.", f"- Top 10% of users' eligible-row share: **{audit['top_10_percent_user_row_fraction']:.1%}**.", "- Training weights use training counts only and equalize total weight across represented training users. Report both submission-level and user-averaged metrics after fitting."]
    lines += ["- " + item for item in selection["limitations"]]
    if not details["train"]["users_per_stratum"].get("unrated", 0):
        lines += ["- No users who are currently unrated have training-period rows under these chronological cutoffs. Historical unrated states of later-rated users can occur, but performance for never-rated users must be evaluated separately; aggregate coverage does not resolve that domain shift."]
    lines += ["- No reweighting establishes whole-platform representativeness. Within-group uncertainty, sparse groups, and errors must still be reported.", "- Historical verdict-availability timestamps are unavailable. Features use a one-day outcome lag; delayed judging and rejudging remain limitations. Problem tags/difficulty use current snapshots.", "- Static website, models, validation-only selection, final test evaluation, and student defense remain unfinished.", "", "## Reproduction", "", "```bash", "python3 code/select_users.py", "python3 code/collect_data.py --output data/raw --per-group 20 --batch-profiles", "# If profile checks flag stale rating strata, stop collection, verify, and resume:", "python3 code/check_users.py", "python3 code/make_features.py --source data/raw --output data/processed", "python3 code/check_data.py", "python3 -m unittest discover -s tests -v", "```", "", "Existing selection and completed captures are reused. Fresh live snapshots can differ; source SHA-256 hashes and capture timestamps identify this dataset. Generated aggregate plots need matplotlib; capture and feature scripts use only the Python standard library."]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"gates": gates, "all_passed": all(gates.values()), "split_details": details}, indent=2))
    return 0 if all(gates.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
