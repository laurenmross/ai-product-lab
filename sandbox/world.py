"""The Lorem sandbox: shared constants, data loaders, and the outcome simulator.

Lorem is a fictional company (the name comes from "lorem ipsum" placeholder text).
Its first product, Lorem Work, is a B2B project-management SaaS with a 14-day free
trial. Every experiment in this lab runs against the same synthetic company, so
results are comparable and anyone can reproduce them without real customer data.

Two kinds of data live here:
  * Observable data (sandbox/data/*.csv): what a real product team would have in
    its warehouse. Agents may read this.
  * Hidden truth (sandbox/data/_hidden/): why each user actually stalled, plus the
    simulator's response model. Only evals may read this. An agent that peeks is
    cheating, the same way a model trained on its test set is.
"""
from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from datetime import datetime
from pathlib import Path

SANDBOX_DIR = Path(__file__).resolve().parent
DATA_DIR = SANDBOX_DIR / "data"
HIDDEN_DIR = DATA_DIR / "_hidden"

# "Today" inside the sandbox. Fixed so every run is reproducible.
SANDBOX_TODAY = datetime(2026, 10, 1, 9, 0)

# The four activation milestones. A user who hits 3 of 4 counts as activated.
MILESTONES = ["project_created", "teammate_invited", "integration_connected", "automation_created"]
ACTIVATION_THRESHOLD = 3

# Why a stalled user stalled. This is the hidden variable a good agent has to infer.
BLOCKERS = [
    "no_teammates",          # using it solo; the product only clicks with a team
    "integration_friction",  # tried to connect Slack/GitHub/Jira and it failed or confused them
    "blank_slate",           # created a project, didn't know how to set it up
    "value_unclear",         # poking at pricing, not convinced it's worth paying for
    "permissions_blocked",   # non-admin who hit something only an admin can do
    "low_intent",            # tire-kicker; messaging them mostly annoys them
]

# The in-app nudges an onboarding agent can choose from.
ACTIONS = {
    "invite_teammates": "Prompt to invite teammates, with a one-click invite link to the project they already made.",
    "integration_help": "Guided fix for a failed or abandoned integration setup, with a link to live chat.",
    "template_starter": "Offer a ready-made template matched to their use case so their project isn't blank.",
    "roi_showcase": "Show what similar teams get out of Lorem Work (time saved, plan comparison) plus a 7-day trial extension.",
    "request_admin": "Help a non-admin ask their workspace admin for the access they need, in one click.",
    "generic_tips": "Generic 'get the most out of Lorem Work' tips. This is the status-quo onboarding nudge.",
    "no_nudge": "Don't message this user. A nudge is more likely to annoy than help.",
}

# The action that addresses each blocker. Evals score targeting against this.
BEST_ACTION = {
    "no_teammates": "invite_teammates",
    "integration_friction": "integration_help",
    "blank_slate": "template_starter",
    "value_unclear": "roi_showcase",
    "permissions_blocked": "request_admin",
    "low_intent": "no_nudge",
}

# Actions that don't send a message. Guardrails can also turn a nudge into a hold.
SILENT_ACTIONS = {"no_nudge", "hold"}

# Frequency cap: don't nudge anyone who got a message in the last N hours.
FREQUENCY_CAP_HOURS = 72


# ---------------------------------------------------------------------------
# Loaders (observable data only)
# ---------------------------------------------------------------------------

def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"Missing {path}. Run `python sandbox/generate.py` first.")
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def load_users() -> list[dict]:
    return _read_csv(DATA_DIR / "users.csv")


def load_events_by_user() -> dict[str, list[dict]]:
    by_user: dict[str, list[dict]] = defaultdict(list)
    for row in _read_csv(DATA_DIR / "events.csv"):
        row["properties"] = json.loads(row["properties"]) if row["properties"] else {}
        by_user[row["user_id"]].append(row)
    for events in by_user.values():
        events.sort(key=lambda e: e["timestamp"])
    return by_user


def load_notifications_by_user() -> dict[str, list[dict]]:
    by_user: dict[str, list[dict]] = defaultdict(list)
    for row in _read_csv(DATA_DIR / "notifications.csv"):
        by_user[row["user_id"]].append(row)
    return by_user


def load_survey_by_user() -> dict[str, str]:
    return {r["user_id"]: r["answer"] for r in _read_csv(DATA_DIR / "survey_responses.csv")}


# ---------------------------------------------------------------------------
# Hidden truth + simulator (evals only)
# ---------------------------------------------------------------------------

def load_truth() -> dict[str, dict]:
    """Ground truth per user. Evals only; agents must not call this."""
    return {r["user_id"]: r for r in _read_csv(HIDDEN_DIR / "truth.csv")}


# Probability a stalled user re-engages (hits a new milestone) within 7 days.
CONTROL_RATE = 0.06        # no message
MATCHED_RATE = 0.30        # nudge addresses their actual blocker
GENERIC_RATE = 0.10        # generic tips
MISMATCHED_RATE = 0.07     # a specific nudge aimed at the wrong problem
LOW_INTENT_RATE = 0.01     # low-intent users barely respond to anything

BASE_UNSUB_RATE = 0.01     # chance any in-app nudge gets them to mute Lorem Work messages
LOW_INTENT_UNSUB_RATE = 0.12
OVER_CAP_UNSUB_PENALTY = 0.08
OVER_CAP_RESPONSE_MULTIPLIER = 0.6


def outcome_probabilities(blocker: str, action: str, recently_messaged: bool) -> tuple[float, float]:
    """Return (p_reengage, p_unsubscribe) for one user receiving one action."""
    if action in SILENT_ACTIONS:
        return (LOW_INTENT_RATE if blocker == "low_intent" else CONTROL_RATE), 0.0

    if blocker not in BEST_ACTION:
        # Not actually stalled (a false positive from detection): any nudge is just a generic reminder.
        p, unsub = GENERIC_RATE, BASE_UNSUB_RATE
    elif blocker == "low_intent":
        p, unsub = LOW_INTENT_RATE * 1.5, LOW_INTENT_UNSUB_RATE
    elif action == BEST_ACTION[blocker]:
        p, unsub = MATCHED_RATE, BASE_UNSUB_RATE
    elif action == "generic_tips":
        p, unsub = GENERIC_RATE, BASE_UNSUB_RATE
    else:
        p, unsub = MISMATCHED_RATE, BASE_UNSUB_RATE

    if recently_messaged:
        p *= OVER_CAP_RESPONSE_MULTIPLIER
        unsub += OVER_CAP_UNSUB_PENALTY
    return p, unsub


def simulate_outcome(user_id: str, blocker: str, action: str, recently_messaged: bool, seed: int = 7) -> tuple[bool, bool]:
    """Draw (reengaged, unsubscribed) for one user.

    Uses common random numbers: the same user gets the same underlying draws no
    matter which policy is being tested, so differences between policies come
    from the decisions, not from luck.
    """
    rng = random.Random(f"{seed}:{user_id}")
    u_reengage, u_unsub = rng.random(), rng.random()
    p, unsub = outcome_probabilities(blocker, action, recently_messaged)
    return u_reengage < p, u_unsub < unsub
