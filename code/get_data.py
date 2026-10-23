#!/usr/bin/env python3
"""Capture a Codeforces pilot and report data quality; no ML labels are made here."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class APIError(RuntimeError):
    pass


class Client:
    def __init__(self):
        self.last_request = None

    def get(self, method, **params):
        if self.last_request is not None:
            time.sleep(max(0, 2.1 - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        url = f"https://codeforces.com/api/{method}?{urlencode(params)}"
        request = Request(url, headers={"User-Agent": "DSA-Compass-course-project/0.1"})
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except HTTPError as exc:
            # Codeforces also sends structured FAILED responses with HTTP 400.
            try:
                failure = json.loads(exc.read())
            except (ValueError, OSError, UnicodeError):
                failure = None
            if isinstance(failure, dict) and failure.get("status") == "FAILED":
                raise APIError(f"{method}: {failure.get('comment', 'request rejected')} (HTTP {exc.code})") from exc
            raise APIError(f"{method}: HTTP {exc.code}; check API availability and network policy") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise APIError(f"{method}: network request failed: {exc}") from exc
        except (ValueError, UnicodeError) as exc:
            raise APIError(f"{method}: expected JSON; received an invalid response") from exc
        if not isinstance(payload, dict) or payload.get("status") != "OK":
            comment = payload.get("comment", "invalid response") if isinstance(payload, dict) else "invalid response"
            raise APIError(f"{method}: {comment}")
        if "result" not in payload:
            raise APIError(f"{method}: missing result")
        return payload["result"]


def fetch_submissions(client, handle, page_size, max_pages):
    """Fetch newest-first pages. Only an exhausted endpoint establishes completeness."""
    submissions, seen = [], set()
    page = 0
    while max_pages == 0 or page < max_pages:
        batch = client.get("user.status", handle=handle, **{"from": page * page_size + 1, "count": page_size})
        if not isinstance(batch, list):
            raise APIError("user.status: expected a list")
        for submission in batch:
            if not isinstance(submission, dict) or "id" not in submission:
                raise APIError("user.status: submission has no ID")
            if submission["id"] not in seen:
                submissions.append(submission)
                seen.add(submission["id"])
        page += 1
        if len(batch) < page_size:
            return submissions, True, page
    return submissions, False, page


def summarize(submissions, complete):
    verdicts = Counter(s.get("verdict") or "PENDING" for s in submissions)
    tags = Counter()
    problems = set()
    missing_rating = missing_tags = missing_key = team = 0
    timestamps = []
    for submission in submissions:
        problem = submission.get("problem", {})
        if "contestId" in problem and "index" in problem:
            problems.add((problem["contestId"], problem["index"]))
        else:
            missing_key += 1
        missing_rating += problem.get("rating") is None
        missing_tags += not problem.get("tags")
        tags.update(problem.get("tags", []))
        team += len(submission.get("author", {}).get("members", [])) > 1
        if submission.get("creationTimeSeconds") is not None:
            timestamps.append(submission["creationTimeSeconds"])
    return {
        "submission_count": len(submissions),
        "history_complete": complete,
        "first_ever_attempts_safe_to_derive": complete,
        "unique_contest_problems": len(problems),
        "submissions_missing_problem_key": missing_key,
        "submissions_missing_problem_rating": missing_rating,
        "submissions_without_tags": missing_tags,
        "team_submissions": team,
        "verdict_counts": dict(sorted(verdicts.items())),
        "tag_submission_counts": dict(sorted(tags.items())),
        "oldest_submission_timestamp": min(timestamps) if timestamps else None,
        "newest_submission_timestamp": max(timestamps) if timestamps else None,
        "warning": "No labels or weakness scores generated. Completeness is necessary but not sufficient for modeling.",
    }


def collect(client, handle, page_size, max_pages):
    users = client.get("user.info", handles=handle)
    if not isinstance(users, list) or len(users) != 1 or not isinstance(users[0], dict):
        raise APIError("user.info: expected one user")
    # Avoid retaining real name, country, organization, email, or other profile fields.
    user = {k: users[0][k] for k in ("handle", "rating", "maxRating", "rank", "maxRank") if k in users[0]}
    ratings = client.get("user.rating", handle=handle)
    if not isinstance(ratings, list):
        raise APIError("user.rating: expected a list")
    submissions, complete, pages = fetch_submissions(client, handle, page_size, max_pages)
    problemset = client.get("problemset.problems")
    if not isinstance(problemset, dict) or not isinstance(problemset.get("problems"), list):
        raise APIError("problemset.problems: expected a problems list")
    summary = summarize(submissions, complete)
    summary.update({
        "rating_history_count": len(ratings),
        "catalog_problem_count": len(problemset["problems"]),
        "catalog_problems_missing_rating": sum(p.get("rating") is None for p in problemset["problems"]),
        "pages_fetched": pages,
    })
    return {"user": user, "rating_history": ratings, "submissions": submissions,
            "problemset": problemset, "summary": summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handle")
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--max-pages", type=int, default=2, help="0 fetches until exhausted")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "data/raw")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,24}", args.handle) or args.handle in (".", ".."):
        parser.error("handle must be 1–24 letters, digits, underscores, dots, or hyphens")
    if not 1 <= args.page_size <= 10000 or args.max_pages < 0:
        parser.error("page-size must be 1–10000 and max-pages must be nonnegative")
    started = datetime.now(timezone.utc)
    try:
        capture = collect(Client(), args.handle, args.page_size, args.max_pages)
        run = args.output / args.handle / started.strftime("%Y%m%dT%H%M%S.%fZ")
        run.mkdir(parents=True, exist_ok=False)
        for name, data in capture.items():
            (run / f"{name}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        metadata = {"started_at": started.isoformat(), "finished_at": datetime.now(timezone.utc).isoformat(),
                    "source": "https://codeforces.com/api/", "handle": args.handle,
                    "page_size": args.page_size, "max_pages": args.max_pages,
                    "endpoints": ["user.info", "user.rating", "user.status", "problemset.problems"]}
        (run / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    except (APIError, OSError) as exc:
        print(f"Capture failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(capture["summary"], indent=2))
    print(f"Capture saved: {run}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
