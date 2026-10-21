"""Turn raw sandbox tables into one profile per user, and decide who is stalled.

Everything here uses observable data only. This is the "feature layer" that every
policy (rules, LLM, or anything you add) shares, so policies compete on decisions,
not on who got better inputs.
"""
from __future__ import annotations

from collections import Counter

from _sandbox import world

STALL_MIN_DAYS_SINCE_SIGNUP = 7
STALL_MIN_DAYS_INACTIVE = 5


def build_profiles() -> dict[str, dict]:
    users = world.load_users()
    events = world.load_events_by_user()
    notifications = world.load_notifications_by_user()
    surveys = world.load_survey_by_user()
    today = world.SANDBOX_TODAY

    profiles = {}
    for u in users:
        uid = u["user_id"]
        evs = events.get(uid, [])
        counts = Counter(e["event"] for e in evs)
        signup = world.parse_ts(u["signup_at"])
        last_active = max((world.parse_ts(e["timestamp"]) for e in evs if e["event"] == "session_start"),
                          default=signup)
        hours_since_message = min(
            ((today - world.parse_ts(n["sent_at"])).total_seconds() / 3600 for n in notifications.get(uid, [])),
            default=None,
        )
        profiles[uid] = {
            **u,
            "days_since_signup": round((today - signup).total_seconds() / 86400, 1),
            "days_inactive": round((today - last_active).total_seconds() / 86400, 1),
            "counts": dict(counts),
            "milestones_hit": [m for m in world.MILESTONES if counts.get(m)],
            "searches": [e["properties"]["query"] for e in evs if e["event"] == "search"],
            "help_articles": [e["properties"]["title"] for e in evs if e["event"] == "help_article_viewed"],
            "integration_errors": [e["properties"].get("error") for e in evs if e["event"] == "integration_connect_failed"],
            "permission_denials": [e["properties"].get("attempted") for e in evs if e["event"] == "permission_denied"],
            "survey_answer": surveys.get(uid),
            "hours_since_last_message": None if hours_since_message is None else round(hours_since_message, 1),
            "timeline": [(e["timestamp"], e["event"], e["properties"]) for e in evs],
        }
    return profiles


def is_stalled(p: dict) -> bool:
    """Signed up a week+ ago, not activated, and gone quiet."""
    return (
        p["days_since_signup"] >= STALL_MIN_DAYS_SINCE_SIGNUP
        and len(p["milestones_hit"]) < world.ACTIVATION_THRESHOLD
        and p["days_inactive"] >= STALL_MIN_DAYS_INACTIVE
    )


def stalled_profiles() -> list[dict]:
    return [p for p in build_profiles().values() if is_stalled(p)]
