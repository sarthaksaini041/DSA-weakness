#!/usr/bin/env python3
"""Collect and audit the frozen, diverse Codeforces dataset. Public data stays ignored."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import json
import math
from pathlib import Path
import sys

from get_data import APIError, Client, fetch_submissions, summarize

STRATA = ("unrated", "below_1200", "1200_1399", "1400_1599", "1600_1899", "1900_plus")
REJECTIONS = {"WRONG_ANSWER", "TIME_LIMIT_EXCEEDED", "MEMORY_LIMIT_EXCEEDED",
              "RUNTIME_ERROR", "IDLENESS_LIMIT_EXCEEDED", "PRESENTATION_ERROR"}


def stratum(rating):
    if rating is None:
        return "unrated"
    for limit, name in zip((1200, 1400, 1600, 1900), STRATA[1:5]):
        if rating < limit:
            return name
    return "1900_plus"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def minimized(user):
    return {k: user[k] for k in ("handle", "rating", "maxRating", "rank") if k in user}








def eligible_first_attempts(submissions, handle):
    """Audit target eligibility only; features and model splits are not built here."""
    seen = set()
    exclusions = Counter()
    eligible = Counter()
    for s in sorted(submissions, key=lambda x: (x["creationTimeSeconds"], x["id"])):
        p = s.get("problem", {})
        if "contestId" not in p or "index" not in p:
            exclusions["missing_problem_identity"] += 1
            continue
        key = (p["contestId"], p["index"])
        if key in seen:
            continue
        # Mark first BEFORE filtering: do not turn a later success into a first attempt.
        seen.add(key)
        members = s.get("author", {}).get("members", [])
        if len(members) != 1 or members[0].get("handle", "").casefold() != handle.casefold():
            exclusions["non_individual"] += 1
        elif p.get("type") != "PROGRAMMING" or any(t.startswith("*") for t in p.get("tags", [])):
            exclusions["special_or_non_programming"] += 1
        elif s.get("verdict") not in REJECTIONS | {"OK"}:
            exclusions["excluded_or_pending_verdict"] += 1
        else:
            eligible["accepted" if s["verdict"] == "OK" else "rejected"] += 1
    return {"eligible": dict(eligible), "exclusions": dict(exclusions),
            "eligible_rows": sum(eligible.values())}


def user_audit(capture, now):
    summary = capture["summary"]
    submissions = capture["submissions"]
    n = summary["unique_contest_problems"]
    history = "0_19" if n < 20 else "20_99" if n < 100 else "100_499" if n < 500 else "500_plus"
    latest = summary["newest_submission_timestamp"]
    days = max(0, (now - latest) // 86400) if latest is not None else None
    activity = "no_history" if days is None else "0_30" if days <= 30 else "31_180" if days <= 180 else "181_plus"
    audit = {"history_bin": history, "activity_bin": activity, "days_since_last_submission": days,
             "submission_count": len(submissions), "unique_problems": n,
             "participant_types": dict(Counter(s.get("author", {}).get("participantType", "UNKNOWN") for s in submissions)),
             "difficulty_counts": dict(Counter(str(s.get("problem", {}).get("rating", "missing")) for s in submissions))}
    if summary["history_complete"] and capture.get("head_stable", False):
        audit["first_attempt_audit"] = eligible_first_attempts(submissions, capture["user"]["handle"])
    else:
        audit["first_attempt_audit"] = {"eligible_rows": 0, "blocked": "Incomplete or shifting history"}
    return audit


def aggregate(selection, records):
    completed = [r for r in records if r["status"] == "complete"]
    rows = sorted([r["audit"]["first_attempt_audit"]["eligible_rows"] for r in completed], reverse=True)
    total = sum(rows)
    submissions = sum(r["summary"]["submission_count"] for r in completed)
    def counts(key):
        return dict(Counter(r["audit"][key] for r in completed))
    def combined(items):
        counter = Counter()
        for item in items:
            counter.update(item)
        return dict(sorted(counter.items()))
    return {"selected_users": len(selection["users"]), "completed_users": len(completed),
            "target_per_stratum": selection["per_group"],
            "actual_per_stratum": {g: sum(r["stratum"] == g for r in completed) for g in STRATA},
            "history_bins": counts("history_bin"), "activity_bins": counts("activity_bin"),
            "submissions": submissions, "eligible_first_attempt_rows": total,
            "largest_user_row_fraction": rows[0] / total if total else None,
            "top_10_percent_user_row_fraction": sum(rows[:max(1, math.ceil(len(rows) * .1))]) / total if total else None,
            "missing_problem_ratings": sum(r["summary"]["submissions_missing_problem_rating"] for r in completed),
            "missing_tags": sum(r["summary"]["submissions_without_tags"] for r in completed),
            "team_submissions": sum(r["summary"]["team_submissions"] for r in completed),
            "verdict_counts": combined(r["summary"]["verdict_counts"] for r in completed),
            "tag_submission_counts": combined(r["summary"]["tag_submission_counts"] for r in completed),
            "difficulty_submission_counts": combined(r["audit"]["difficulty_counts"] for r in completed),
            "participant_type_counts": combined(r["audit"]["participant_types"] for r in completed),
            "first_attempt_outcomes": combined(r["audit"]["first_attempt_audit"].get("eligible", {}) for r in completed),
            "first_attempt_exclusions": combined(r["audit"]["first_attempt_audit"].get("exclusions", {}) for r in completed),
            "failures": sum(r["status"] != "complete" for r in records),
            "limitations": selection["limitations"], "users": records}


def complete_history(client, handle):
    submissions, complete, pages = fetch_submissions(client, handle, 1000, 0)
    if pages == 1:
        # A single exhausted response has no offset-pagination consistency gap.
        return submissions, complete, pages, True, "single_exhausted_response"
    head = client.get("user.status", handle=handle, **{"from": 1, "count": 1})
    stable = (head[0]["id"] if head else None) == (submissions[0]["id"] if submissions else None)
    return submissions, complete, pages, stable, "newest_id_recheck_after_pagination"


def batch_profiles(client, root, selection):
    path = root / "profile_snapshots.json"
    cache = json.loads(path.read_text()) if path.exists() else {"users": {}, "errors": {}}
    prefix = selection.get("id_prefix", "cohort")
    missing = [u for i, u in enumerate(selection["users"], 1)
               if u["handle"].casefold() not in cache["users"] and not (root / "users" / f"{prefix}_{i:03d}.json").exists()]
    for offset in range(0, len(missing), 50):
        batch = missing[offset:offset + 50]
        print(f"Checking profile batch {offset // 50 + 1}", flush=True)
        try:
            users = client.get("user.info", handles=";".join(u["handle"] for u in batch))
        except APIError:
            # Isolate an invalid handle instead of failing all other users.
            users = []
            for selected in batch:
                try:
                    users.extend(client.get("user.info", handles=selected["handle"]))
                except APIError as exc:
                    cache["errors"][selected["handle"].casefold()] = str(exc)
        for user in users:
            cache["users"][user["handle"].casefold()] = {"user": minimized(user), "checked_at": datetime.now(timezone.utc).isoformat()}
            cache["errors"].pop(user["handle"].casefold(), None)
        save(path, cache)
    return cache


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "data/raw")
    parser.add_argument("--per-group", type=int, default=20)
    parser.add_argument("--batch-profiles", action="store_true", help="Cache minimized profile checks in groups of up to 50")
    args = parser.parse_args()
    if args.per_group < 1:
        parser.error("per-group must be positive")
    root = args.output
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".collector.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("Another collector is using this output directory")
        client = Client()
        try:
            selection_path = root / "selection.json"
            if not selection_path.exists():
                raise APIError("Run code/select_users.py before collecting this dataset")
            selection = json.loads(selection_path.read_text())
            if selection["per_group"] != args.per_group:
                raise APIError("Quota differs from the frozen selection")
            profiles = batch_profiles(client, root, selection) if args.batch_profiles else None
            catalog_path = root / "problemset.json"
            if not catalog_path.exists():
                save(catalog_path, {"collected_at": datetime.now(timezone.utc).isoformat(),
                                    "result": client.get("problemset.problems")})
            records = []
            for index, selected in enumerate(selection["users"], 1):
                handle = selected["handle"]
                analysis_id = f"{selection.get('id_prefix', 'cohort')}_{index:03d}"
                path = root / "users" / f"{analysis_id}.json"
                print(f"Collecting {analysis_id} ({selected['stratum']})", flush=True)
                try:
                    if path.exists():
                        capture = json.loads(path.read_text())
                    else:
                        if profiles is not None:
                            profile = profiles["users"].get(handle.casefold())
                            if profile is None:
                                raise APIError(profiles["errors"].get(handle.casefold(), "Profile check returned no matching handle"))
                            user = profile["user"]
                        else:
                            user = minimized(client.get("user.info", handles=handle)[0])
                        ratings = client.get("user.rating", handle=handle)
                        submissions, complete, pages, stable, consistency = complete_history(client, handle)
                        capture = {"user": user, "rating_history": ratings, "submissions": submissions,
                                   "summary": {**summarize(submissions, complete), "pages_fetched": pages},
                                   "head_stable": stable, "history_consistency_check": consistency,
                                   "profile_checked_at": profile["checked_at"] if profiles is not None else None,
                                   "collected_at": datetime.now(timezone.utc).isoformat()}
                        save(path, capture)
                    current = stratum(capture["user"].get("rating"))
                    status = "complete" if capture["summary"]["history_complete"] and capture["head_stable"] and current == selected["stratum"] else "needs_review"
                    records.append({"analysis_id": analysis_id, "handle": handle, "stratum": current,
                                    "selected_stratum": selected["stratum"], "source": selected["source"],
                                    "status": status, "summary": capture["summary"],
                                    "audit": user_audit(capture, int(datetime.fromisoformat(capture["collected_at"]).timestamp()))})
                except (APIError, OSError, ValueError) as exc:
                    records.append({"analysis_id": analysis_id, "handle": handle, "stratum": selected["stratum"],
                                    "status": "failed", "error": str(exc)})
                    print(f"  Failed: {exc}", flush=True)
                save(root / "audit.json", aggregate(selection, records))
            report = aggregate(selection, records)
            print(json.dumps({k: v for k, v in report.items() if k != "users"}, indent=2))
            return 0 if not report["failures"] and len(selection["users"]) == len(STRATA) * args.per_group else 1
        except (APIError, OSError, ValueError) as exc:
            print(f"Collection failed: {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main())
