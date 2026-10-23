#!/usr/bin/env python3
"""Replace snapshot-ineligible selections with recorded, same-source reserves.

Run with the collector stopped. Eligibility depends only on public profile rating,
never on submission outcomes, feature values, or model performance.
"""

import argparse
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import random

from collect_data import minimized, save, stratum
from get_data import Client
from select_users import saved_source


def main():
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=repo / "data/raw")
    args = parser.parse_args()
    root = args.source
    with (root / ".collector.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        selection = json.loads((root / "selection.json").read_text())
        cache = json.loads((root / "profile_snapshots.json").read_text())
        mismatches = [(i, u) for i, u in enumerate(selection["users"])
                      if u["handle"].casefold() in cache["users"] and
                      stratum(cache["users"][u["handle"].casefold()]["user"].get("rating")) != u["stratum"]]
        if not mismatches:
            print("No verified rating-stratum mismatches; selection preserved.")
            return
        client = Client()
        pools = {}
        used = {u["handle"].casefold() for u in selection["users"]} | {"tourist"}
        replacements = []
        for index, original in mismatches:
            source = original["source"]
            group = original["stratum"]
            if source not in pools:
                key = "unrated_public_feed" if source == "recent_public_submissions" else source
                pools[source] = json.loads(saved_source(root, selection["source_snapshots"][key]).read_text())
            candidates = sorted((u for u in pools[source] if stratum(u.get("rating")) == group and u["handle"].casefold() not in used), key=lambda u: u["handle"].casefold())
            random.Random(f"42:{source}:{group}").shuffle(candidates)
            replacement = None
            for offset in range(0, min(200, len(candidates)), 20):
                batch = candidates[offset:offset + 20]
                missing = [u for u in batch if u["handle"].casefold() not in cache["users"]]
                if missing:
                    result = client.get("user.info", handles=";".join(u["handle"] for u in missing))
                    for user in result:
                        cache["users"][user["handle"].casefold()] = {"user": minimized(user), "checked_at": datetime.now(timezone.utc).isoformat()}
                    save(root / "profile_snapshots.json", cache)
                for candidate in batch:
                    profile = cache["users"][candidate["handle"].casefold()]["user"]
                    if stratum(profile.get("rating")) == group and profile["handle"].casefold() not in used:
                        replacement = {**profile, "source": source, "stratum": group}
                        break
                if replacement:
                    break
            if replacement is None:
                raise ValueError(f"No verified reserve found for {group}/{source}; no selection changes saved")
            used.add(replacement["handle"].casefold())
            replacements.append((index, original, replacement))
        # Preserve original membership and any already collected records.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        archive = root / "changes" / stamp
        save(archive / "selection_before.json", selection)
        if (root / "audit.json").exists():
            save(archive / "audit_before.json", json.loads((root / "audit.json").read_text()))
        changes = []
        for index, original, replacement in replacements:
            analysis_id = f"{selection.get('id_prefix', 'pilot')}_{index + 1:03d}"
            path = root / "users" / f"{analysis_id}.json"
            if path.exists():
                path.rename(archive / path.name)
            selection["users"][index] = replacement
            changes.append({"analysis_id": analysis_id, "original": original,
                            "observed_profile": cache["users"][original["handle"].casefold()],
                            "replacement": replacement,
                            "reason": "Current profile rating not in directory-snapshot selection stratum"})
        save(archive / "changes.json", changes)
        selection.setdefault("amendments", []).append({"created_at": stamp, "record": str(archive),
                                                       "replacements": len(changes),
                                                       "rule": "Seeded same-source, same-stratum reserves, verified via current profile; no submission outcomes used"})
        save(root / "selection.json", selection)
        print(f"Recorded {len(changes)} rating-eligibility replacements; original membership and available captures preserved.")


if __name__ == "__main__":
    main()
