#!/usr/bin/env python3
"""
Extract review data from OpenReview for multiple venues (ICLR, NeurIPS, ICML).
Supports both API v1 (api.openreview.net) and v2 (api2.openreview.net).
Output CSV has dynamic score columns per venue (different criteria and scales by year).
"""

import os
import re
import csv
import json
import argparse
from pathlib import Path
from typing import Any, Optional

# Load .env if present (OPENREVIEW_USERNAME, OPENREVIEW_PASSWORD)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Optional deps for progress and env
try:
    from tqdm import tqdm
except ImportError:
    def tqdm(it, **kwargs):
        return it

# ---------------------------------------------------------------------------
# Venue configuration: score field names and scale info by venue/year.
# Score fields are the OpenReview content keys for numeric/ordinal scores.
# Scale notes: 1-10 = overall rating, 1-5 = confidence (see OpenReview default).
# ---------------------------------------------------------------------------
VENUE_CONFIG = [
    # ---- ICLR (v1 = api.openreview.net for 2022-2023) ----
    {
        "name": "ICLR2022",
        "venue_id": "ICLR.cc/2022/Conference",
        "api_version": "v1",
        "submission_invitation": "ICLR.cc/2022/Conference/-/Blind_Submission",
        "score_fields": ["rating", "confidence"],  # v1 default: rating 1-10, confidence 1-5
        "scale_notes": "rating 1-10 (1=Trivial to 10=Top 5%), confidence 1-5",
    },
    {
        "name": "ICLR2023",
        "venue_id": "ICLR.cc/2023/Conference",
        "api_version": "v1",
        "submission_invitation": "ICLR.cc/2023/Conference/-/Blind_Submission",
        "score_fields": ["rating", "confidence"],
        "scale_notes": "rating 1-10, confidence 1-5",
    },
    # ---- ICLR (v2 = api2.openreview.net for 2024+) ----
    {
        "name": "ICLR2024",
        "venue_id": "ICLR.cc/2024/Conference",
        "api_version": "v2",
        "submission_invitation": "ICLR.cc/2024/Conference/-/Submission",
        "score_fields": ["soundness", "presentation", "contribution", "rating", "confidence"],
        "scale_notes": "soundness/presentation/contribution 1-5, rating 1-10, confidence 1-5",
    },
    {
        "name": "ICLR2025",
        "venue_id": "ICLR.cc/2025/Conference",
        "api_version": "v2",
        "submission_invitation": "ICLR.cc/2025/Conference/-/Submission",
        "score_fields": ["soundness", "presentation", "contribution", "rating", "confidence"],
        "scale_notes": "soundness/presentation/contribution 1-5, rating 1-10, confidence 1-5",
    },
    {
        "name": "ICLR2026",
        "venue_id": "ICLR.cc/2026/Conference",
        "api_version": "v2",
        "submission_invitation": "ICLR.cc/2026/Conference/-/Submission",
        "score_fields": ["soundness", "presentation", "contribution", "rating", "confidence"],
        "scale_notes": "soundness/presentation/contribution 1-5, rating 1-10, confidence 1-5",
    },
    # ---- NeurIPS (v1 for 2021-2023) ----
    {
        "name": "NeurIPS2021",
        "venue_id": "NeurIPS.cc/2021/Conference",
        "api_version": "v1",
        "submission_invitation": "NeurIPS.cc/2021/Conference/-/Blind_Submission",
        "score_fields": ["rating", "confidence"],
        "scale_notes": "rating 1-10 (or venue-specific), confidence 1-5",
    },
    {
        "name": "NeurIPS2022",
        "venue_id": "NeurIPS.cc/2022/Conference",
        "api_version": "v1",
        "submission_invitation": "NeurIPS.cc/2022/Conference/-/Blind_Submission",
        "score_fields": ["rating", "confidence"],
        "scale_notes": "rating 1-10, confidence 1-5",
    },
    {
        "name": "NeurIPS2023",
        "venue_id": "NeurIPS.cc/2023/Conference",
        "api_version": "v1",
        "submission_invitation": "NeurIPS.cc/2023/Conference/-/Blind_Submission",
        "score_fields": ["rating", "confidence"],
        "scale_notes": "rating 1-10, confidence 1-5",
    },
    # ---- NeurIPS (v2 for 2024-2025 if migrated) ----
    {
        "name": "NeurIPS2024",
        "venue_id": "NeurIPS.cc/2024/Conference",
        "api_version": "v2",
        "submission_invitation": "NeurIPS.cc/2024/Conference/-/Submission",
        "score_fields": ["rating", "confidence"],
        "scale_notes": "rating 1-10, confidence 1-5",
    },
    {
        "name": "NeurIPS2025",
        "venue_id": "NeurIPS.cc/2025/Conference",
        "api_version": "v2",
        "submission_invitation": "NeurIPS.cc/2025/Conference/-/Submission",
        "score_fields": ["rating", "confidence"],
        "scale_notes": "rating 1-10, confidence 1-5",
    },
    # ---- ICML 2025 (v2, overall score only) ----
    {
        "name": "ICML2025",
        "venue_id": "ICML.cc/2025/Conference",
        "api_version": "v2",
        "submission_invitation": "ICML.cc/2025/Conference/-/Submission",
        "score_fields": ["rating"],  # or "overall_score" - we'll discover from reply content if needed
        "scale_notes": "overall rating only (scale TBD from form)",
    },
]


def extract_score_value(val: Any) -> Optional[float]:
    """Parse score from OpenReview value: int, float, or string like '8: Accept' or '5'."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        s = val.strip()
        # "8: Top 50%..." or "5"
        m = re.match(r"^(\d+)", s)
        if m:
            return float(m.group(1))
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _is_numeric_score_candidate(val: Any) -> bool:
    """
    Heuristic: return True only for real numeric scores, not for
    textual fields that just start with a digit (e.g. '1. Strengths...').
    """
    if isinstance(val, (int, float)):
        return True
    if isinstance(val, str):
        s = val.strip()
        # Match:
        #   - "8", "8.0"
        #   - "8: Accept", "8 : Accept"
        if re.match(r"^\d+(\.\d+)?(\s*:\s*.*)?$", s):
            return True
    return False


def get_content_value(content: dict, key: str) -> Any:
    """Get value for key from API v2-style content (nested {'value': x}) or v1-style."""
    if key not in content:
        return None
    v = content[key]
    if isinstance(v, dict) and "value" in v:
        return v["value"]
    return v


def fetch_reviews_v1(
    client,
    venue: dict,
    limit: Optional[int] = None,
) -> list[dict]:
    """Fetch submissions and reviews using OpenReview API v1 (api.openreview.net)."""
    import openreview

    venue_id = venue["venue_id"]
    submission_invitation = venue["submission_invitation"]
    score_fields = venue.get("score_fields") or ["rating", "confidence"]
    name = venue["name"]

    # When limit is provided, use get_notes with server-side limit
    if limit is not None:
        print("Getting V1 Notes (limited via get_notes)...")
        submissions = list(
            client.get_notes(
                invitation=submission_invitation,
                details="directReplies",
                limit=limit,
            )
        )
        # Fallback: some venues use Submission instead of Blind_Submission
        if not submissions and "/Blind_Submission" in submission_invitation:
            alt_inv = submission_invitation.replace("/Blind_Submission", "/Submission")
            try:
                submissions = list(
                    client.get_notes(
                        invitation=alt_inv,
                        details="directReplies",
                        limit=limit,
                    )
                )
                if submissions:
                    print(f"  Using invitation {alt_inv} (Blind_Submission returned 0)")
            except Exception:
                pass
    else:
        print("Getting V1 Notes (all via get_all_notes)...")
        submissions = list(
            client.get_all_notes(
                invitation=submission_invitation,
                details="directReplies",
            )
        )
        # Fallback: some venues use Submission instead of Blind_Submission
        if not submissions and "/Blind_Submission" in submission_invitation:
            alt_inv = submission_invitation.replace("/Blind_Submission", "/Submission")
            try:
                submissions = list(
                    client.get_all_notes(invitation=alt_inv, details="directReplies")
                )
                if submissions:
                    print(f"  Using invitation {alt_inv} (Blind_Submission returned 0)")
            except Exception:
                pass

    rows = []
    for submission in submissions:
        replies = submission.details.get("directReplies") or []
        status = _status_from_submission_v1(submission, venue_id)

        for reply_dict in replies:
            inv = reply_dict.get("invitation", "") or ""
            if "Official_Review" not in inv and "Review" not in inv:
                continue
            try:
                note = openreview.Note.from_json(reply_dict)
            except Exception:
                note = None
            if note is None:
                continue
            content = getattr(note, "content", None) or {}
            # v1 content: sometimes key -> value, sometimes key -> {value: x}
            review_row = {
                "venue": name,
                # v1 client returns Note objects
                "submission_id": getattr(submission, "id", None),
                "review_id": getattr(note, "id", reply_dict.get("id")),
                "status": status or "Unknown",
            }
            for key in score_fields:
                raw = content.get(key)
                if raw is not None and isinstance(raw, dict) and "value" in raw:
                    raw = raw["value"]
                review_row[key] = extract_score_value(raw)
            # Include any other numeric-like content keys not in score_fields
            for key, raw in content.items():
                if key in review_row or key in ("title", "review"):
                    continue
                v = raw.get("value", raw) if isinstance(raw, dict) else raw
                if v is not None and _is_numeric_score_candidate(v):
                    review_row[key] = extract_score_value(v)
            if any(v is not None for k, v in review_row.items() if k not in ("venue", "submission_id", "review_id", "status")):
                rows.append(review_row)
    return rows


def _status_from_submission_v1(submission, venue_id: str) -> str:
    """Infer decision status from v1 submission (venueid or decision in directReplies)."""
    # Try submission.content first (v1 Note)
    content = getattr(submission, "content", None) or {}
    venueid = content.get("venueid") or content.get("venue_id")
    if isinstance(venueid, dict):
        venueid = venueid.get("value", "")
    s = (venueid or "").lower()
    if "withdrawn" in s:
        return "Withdrawn"
    if "desk" in s and "reject" in s:
        return "Desk Reject"
    if "reject" in s:
        return "reject"
    if "accept" in s or venue_id.lower().split("/")[0] in s:
        return "accept"
    # Check decision in directReplies
    for reply in (getattr(submission, "details", None) or {}).get("directReplies") or []:
        inv = (reply.get("invitation") or "").lower()
        if "decision" not in inv:
            continue
        c = reply.get("content", {})
        dec = c.get("decision")
        if isinstance(dec, dict):
            dec = dec.get("value", "")
        dec = (dec or "").lower()
        if "accept" in dec:
            return "accept"
        if "reject" in dec:
            return "reject"
    return "Pending/Unknown"


def fetch_reviews_v2(
    client,
    venue: dict,
    limit: Optional[int] = None,
) -> list[dict]:
    """Fetch submissions and reviews using OpenReview API v2 (api2.openreview.net)."""
    venue_id = venue["venue_id"]
    submission_invitation = venue["submission_invitation"]
    score_fields = venue.get("score_fields") or ["rating", "confidence"]
    name = venue["name"]

    # When limit is provided, use get_notes with server-side limit
    if limit is not None:
        print("Getting V2 Notes (limited via get_notes)...")
        submissions = list(
            client.get_notes(
                invitation=submission_invitation,
                details="replies",
                limit=limit,
            )
        )
    else:
        print("Getting V2 Notes (all via get_all_notes)...")
        submissions = list(
            client.get_all_notes(invitation=submission_invitation, details="replies")
        )

    rows = []
    for sub in submissions:
        replies = (getattr(sub, "details", None) or {}).get("replies") or []
        status = _status_from_submission_v2(sub, venue_id, replies)

        for reply in replies:
            invs = reply.get("invitations") or reply.get("invitation") or []
            if isinstance(invs, str):
                invs = [invs]
            is_review = any(
                "Review" in i or "Official_Review" in i for i in invs
            )
            if not is_review:
                continue
            content = reply.get("content") or {}
            review_row = {
                "venue": name,
                # v2 client returns Note objects
                "submission_id": getattr(sub, "id", None),
                "review_id": reply.get("id"),
                "status": status or "Pending/Unknown",
            }
            for key in score_fields:
                raw = get_content_value(content, key)
                review_row[key] = extract_score_value(raw)
            # Include any other numeric-like keys from content
            for key in content:
                if key in review_row or key in ("title", "review"):
                    continue
                raw = get_content_value(content, key)
                if raw is not None and _is_numeric_score_candidate(raw):
                    review_row[key] = extract_score_value(raw)
            # Keep row if at least one score present
            if any(v is not None for k, v in review_row.items() if k not in ("venue", "submission_id", "review_id", "status")):
                rows.append(review_row)
    return rows


def _status_from_submission_v2(sub, venue_id: str, replies: list) -> str:
    venueid = get_content_value(getattr(sub, "content", None) or {}, "venueid")
    s = (venueid or "").lower()
    if "withdrawn" in s:
        return "Withdrawn"
    if "desk" in s and "reject" in s:
        return "Desk Reject"
    if "reject" in s:
        return "reject"
    if "accept" in s or venue_id.lower().split("/")[0] in s:
        return "accept"
    for reply in replies:
        invs = reply.get("invitations") or reply.get("invitation") or []
        if isinstance(invs, str):
            invs = [invs]
        if not any("Decision" in i for i in invs):
            continue
        c = reply.get("content", {})
        dec = get_content_value(c, "decision")
        dec = (dec or "").lower()
        if "accept" in dec:
            return "accept"
        if "reject" in dec:
            return "reject"
    return "Pending/Unknown"


def collect_all_score_columns(rows: list[list[dict]]) -> list[str]:
    """Union of all score-like keys across rows (excluding fixed columns)."""
    fixed = {"venue", "submission_id", "review_id", "status"}
    keys = set()
    for batch in rows:
        for r in batch:
            keys.update(k for k in r if k not in fixed)
    return sorted(keys)


def main():
    parser = argparse.ArgumentParser(description="Extract OpenReview reviews for multiple venues")
    parser.add_argument("--venues", nargs="*", help="Venue names to process (default: all)")
    parser.add_argument("--limit", type=int, default=None, help="Max submissions per venue (e.g. 1 for testing)")
    parser.add_argument("--output", default="data/openreview_reviews.csv", help="Output CSV path")
    parser.add_argument("--output-meta", default="data/openreview_venue_metadata.json", help="Output metadata JSON (scales per venue)")
    parser.add_argument("--dry-run", action="store_true", help="Only print venue config, do not call API")
    args = parser.parse_args()

    venues = [v for v in VENUE_CONFIG if not args.venues or v["name"] in args.venues]
    if not venues:
        print("No venues selected. Use --venues to list names, or leave empty for all.")
        return

    if args.dry_run:
        for v in venues:
            print(v["name"], v["venue_id"], v["api_version"], v.get("score_fields"), v.get("scale_notes"))
        return

    username = os.environ.get("OPENREVIEW_USERNAME")
    password = os.environ.get("OPENREVIEW_PASSWORD")
    if not username or not password:
        print("Set OPENREVIEW_USERNAME and OPENREVIEW_PASSWORD (e.g. in .env or export).")
        return

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    meta = {}

    # Reuse clients across venues to avoid repeated logins (and rate limits)
    v1_client = None
    v2_client = None

    for venue in venues:
        name = venue["name"]
        api_version = venue["api_version"]
        print(f"\n--- {name} (API {api_version}) ---")
        try:
            if api_version == "v1":
                import openreview

                if v1_client is None:
                    v1_client = openreview.Client(
                        baseurl="https://api.openreview.net",
                        username=username,
                        password=password,
                    )
                rows = fetch_reviews_v1(v1_client, venue, limit=args.limit)
            else:
                import openreview

                if v2_client is None:
                    v2_client = openreview.api.OpenReviewClient(
                        baseurl="https://api2.openreview.net",
                        username=username,
                        password=password,
                    )
                rows = fetch_reviews_v2(v2_client, venue, limit=args.limit)
            print(f"  Extracted {len(rows)} reviews.")
            all_rows.extend(rows)

            # Derive actual numeric score fields from the rows we saw for this venue.
            # Split into:
            #   - atomic_score_fields: per-aspect scores (soundness, correctness, ...)
            #   - overall_score_fields: overall recommendation/rating-style fields
            #   - confidence_fields: confidence-style fields
            fixed_cols_for_meta = {
                "venue",
                "submission_id",
                "review_id",
                "status",
                # Never treat this logging field as a score
                "time_spent_reviewing",
            }
            discovered_keys = {
                k for r in rows for k in r.keys() if k not in fixed_cols_for_meta
            }

            # Some venues (ICLR 2022/2023, ICML 2025) should not treat any
            # `rating` field as a score at all.
            if name in {"ICLR2022", "ICLR2023", "ICML2025"} and "rating" in discovered_keys:
                discovered_keys.remove("rating")

            # Confidence-like fields
            confidence_fields = sorted(
                [k for k in discovered_keys if "confidence" in k.lower()]
            )

            # Overall recommendation / rating fields
            overall_candidates = {
                "rating",
                "overall_recommendation",
                "recommendation",
                "overall_score",
            }
            overall_score_fields = sorted(
                [k for k in discovered_keys if k in overall_candidates]
            )

            # Special-case: user notes that "rating" should not be used for ICLR 2022/2023
            if name in {"ICLR2022", "ICLR2023"} and "rating" in overall_score_fields:
                overall_score_fields = [k for k in overall_score_fields if k != "rating"]

            # Atomic per-aspect scores: everything numeric that's not overall or confidence
            atomic_score_fields = sorted(
                [
                    k
                    for k in discovered_keys
                    if k not in overall_score_fields and k not in confidence_fields
                ]
            )

            meta[name] = {
                "venue_id": venue["venue_id"],
                "api_version": api_version,
                "atomic_score_fields": atomic_score_fields,
                "overall_score_fields": overall_score_fields,
                "confidence_fields": confidence_fields,
                "scale_notes": venue.get("scale_notes", ""),
            }
        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()

    if not all_rows:
        print("\nNo rows to write.")
        return

    # Dynamic columns: fixed first, then all score columns seen
    fixed_cols = ["venue", "submission_id", "review_id", "status"]
    score_cols = collect_all_score_columns([all_rows])
    fieldnames = fixed_cols + score_cols

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in all_rows:
            row = {k: r.get(k, "") for k in fieldnames}
            w.writerow(row)

    with open(args.output_meta, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"\nWrote {len(all_rows)} rows to {args.output}")
    print(f"Metadata: {args.output_meta}")


if __name__ == "__main__":
    main()
