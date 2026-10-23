#!/usr/bin/env python3
"""Freeze a 120-user cohort before collection or model fitting."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random

from collect_data import STRATA, minimized, save, stratum
from get_data import Client


def saved_source(folder, record):
    """Find an original snapshot after folder cleanup, preserving its hash."""
    original = Path(record["path"])
    for path in (original, folder / "candidates" / original.name, folder / original.name):
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]:
            return path
    raise ValueError(f"Missing or changed candidate snapshot: {original.name}")


def get_candidates(client, folder):
    folder.mkdir(parents=True, exist_ok=True)
    broad = folder / "rated_candidates.json"
    if not broad.exists():
        save(broad, [minimized(u) for u in client.get("user.ratedList", activeOnly="false", includeRetired="true")])
    unrated = folder / "recent_submission_candidates.json"
    if not unrated.exists():
        feed = client.get("problemset.recentStatus", count=1000)
        handles = sorted({m["handle"] for s in feed for m in s.get("author", {}).get("members", [])
                          if len(s.get("author", {}).get("members", [])) == 1}, key=str.casefold)
        random.Random(42).shuffle(handles)
        users = []
        for i in range(0, min(200, len(handles)), 50):
            users.extend(minimized(u) for u in client.get("user.info", handles=";".join(handles[i:i+50])) if u.get("rating") is None)
        save(unrated, users)
        save(folder / "recent_source_metadata.json", {"collected_at": datetime.now(timezone.utc).isoformat(), "feed_rows": len(feed), "distinct_handles": len(handles)})
    return broad, unrated


def choose_cohort(broad, active, unrated, seed=42):
    rng = random.Random(seed)
    selected, counts = [], {}
    used = {"tourist"}
    for group in STRATA:
        pools = [("recent_public_submissions", unrated, 20)] if group == "unrated" else [
            ("active_rated", active, 10), ("broad_rated", broad, 10)]
        counts[group] = {}
        for source, candidates, quota in pools:
            unique = {u["handle"].casefold(): u for u in candidates
                      if stratum(u.get("rating")) == group and u["handle"].casefold() not in used}
            pool = sorted(unique.values(), key=lambda u: u["handle"].casefold())
            counts[group][source] = len(pool)
            rng.shuffle(pool)
            if len(pool) < quota:
                raise ValueError(f"Insufficient {group}/{source} candidates: {len(pool)} < {quota}")
            for user in pool[:quota]:
                selected.append({**user, "stratum": group, "source": source})
                used.add(user["handle"].casefold())
    return selected, counts


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root / "data/raw")
    parser.add_argument("--candidates", type=Path, help="Saved candidate lists; defaults to OUTPUT/candidates")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / "selection.json").exists():
        print("Selection already frozen; no users changed.")
        return
    inputs = {}
    def load(name, path):
        raw = path.read_bytes()
        inputs[name] = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}
        return json.loads(raw)
    client = Client()
    broad_path, unrated_path = get_candidates(client, args.candidates or args.output / "candidates")
    broad = load("broad_rated", broad_path)
    unrated = load("unrated_public_feed", unrated_path)
    active_path = args.output / "active_rated_candidates.json"
    if not active_path.exists():
        print("Fetching active-rated candidate directory", flush=True)
        users = client.get("user.ratedList", activeOnly="true", includeRetired="false")
        save(active_path, [minimized(u) for u in users])
    active = load("active_rated", active_path)
    selected, counts = choose_cohort(broad, active, unrated)
    selection = {"created_at": datetime.now(timezone.utc).isoformat(), "seed": 42,
                 "per_group": 20, "id_prefix": "cohort", "candidate_counts": counts,
                 "source_snapshots": inputs, "users": selected,
                 "limitations": ["Quota sampling is not population-representative.",
                                  "Rated strata mix 10 active-directory and 10 broad-directory users; active-directory membership is not the same as recent submission activity.",
                                  "Candidate snapshots and selection dates are retained for reproducibility.",
                                  "Unrated candidates are recent public submitters; inactive and zero-history unrated users are not covered.",
                                  "History size and submission recency are audited after selection; no performance-based resampling is allowed."]}
    save(args.output / "selection.json", selection)
    print(f"Frozen {len(selected)} users, 20 per rating group; no model outcomes inspected.")


if __name__ == "__main__":
    main()
