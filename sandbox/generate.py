"""Generate the Lorem sandbox (Lorem Work product): 2,000 trial signups with realistic, noisy behavior.

    python sandbox/generate.py            # default seed, 2,000 users
    python sandbox/generate.py --users 5000 --seed 1

Writes observable tables to sandbox/data/ and the hidden truth (each user's
lifecycle segment and real blocker) to sandbox/data/_hidden/truth.csv.

The signals are deliberately imperfect. A permissions-blocked user doesn't always
hit a permission error; some just start an integration and give up, which looks
like integration friction. A low-intent user sometimes creates an empty project,
which looks like a blank slate. Free text (survey answers, searches, help articles)
often carries the clearest signal, as it does in real products.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import timedelta

from world import DATA_DIR, HIDDEN_DIR, SANDBOX_TODAY

BLOCKER_MIX = {
    "no_teammates": 0.22,
    "integration_friction": 0.18,
    "blank_slate": 0.20,
    "value_unclear": 0.17,
    "permissions_blocked": 0.13,
    "low_intent": 0.10,
}
SEGMENT_MIX = {"activated": 0.48, "stalled": 0.42, "early": 0.10}

JOB_TITLES = ["Product Manager", "Engineering Manager", "Marketing Lead", "Operations Manager",
              "Founder", "Designer", "Project Coordinator", "Agency Account Lead"]
CHANNELS = ["organic_search", "referral", "paid_search", "paid_social", "content", "partner"]
COMPANY_SIZES = ["1-10", "11-50", "51-200", "201-1000"]
INTEGRATIONS = ["slack", "github", "jira", "google_drive"]

NEUTRAL_ANSWERS = [
    "Track our team's projects in one place",
    "Replace the spreadsheets we use for task tracking",
    "Manage client work across a few projects",
    "Plan our product roadmap",
    "Keep launches organized",
    "Get visibility into what everyone is working on",
]
HINT_ANSWERS = {
    "no_teammates": ["Trying it out myself before I bring the team in",
                     "I'm the only PM at my company right now",
                     "Want to see if it works for me first"],
    "integration_friction": ["Needs to work with our Slack and GitHub",
                             "Main thing is syncing with Jira",
                             "We live in Slack so the integration matters most"],
    "blank_slate": ["Not sure how to structure our projects yet",
                    "Looking for a better way to run sprints, open to suggestions",
                    "First time using a tool like this"],
    "value_unclear": ["Comparing a few tools, budget is tight",
                      "Need to justify the cost to my manager",
                      "Seeing if this is better than what we have for free"],
    "permissions_blocked": ["My manager set up the account and added me",
                            "IT controls which apps we can connect",
                            "Our admin asked me to evaluate it"],
    "low_intent": ["just browsing", "saw an ad", "idk"],
}
SEARCHES = {
    "no_teammates": ["invite team", "share project with coworker", "add members", "collaborators"],
    "integration_friction": ["slack not syncing", "github integration error", "jira connect failed",
                             "integration stuck loading"],
    "blank_slate": ["how to set up sprint board", "example project", "templates", "getting started"],
    "value_unclear": ["pricing per seat", "compare plans", "free plan limits", "discount"],
    "permissions_blocked": ["need admin access", "who is my admin", "request permission",
                            "can't connect integration"],
}
HELP_ARTICLES = {
    "integration_friction": ["Troubleshooting the Slack integration", "Fixing GitHub sync errors"],
    "blank_slate": ["Setting up your first project", "Using templates"],
    "value_unclear": ["What's included in Pro", "Billing FAQ"],
    "permissions_blocked": ["Roles and permissions", "What admins can do"],
    "no_teammates": ["Inviting your team"],
}
GENERIC_ARTICLES = ["Keyboard shortcuts", "Using due dates", "Mobile app overview"]


class UserBuilder:
    def __init__(self, rng: random.Random, user_id: str):
        self.rng = rng
        self.user_id = user_id
        self.events: list[dict] = []

    def add(self, ts, event: str, **props):
        self.events.append({"user_id": self.user_id, "timestamp": ts.isoformat(timespec="minutes"),
                            "event": event, "properties": json.dumps(props) if props else ""})

    def random_ts(self, start, end):
        span = max((end - start).total_seconds(), 60)
        return start + timedelta(seconds=self.rng.uniform(0, span))


def chance(rng, p):
    return rng.random() < p


def build_user(rng: random.Random, idx: int):
    user_id = f"u_{idx:04d}"
    segment = rng.choices(list(SEGMENT_MIX), weights=list(SEGMENT_MIX.values()))[0]
    blocker = ""
    if segment == "stalled":
        blocker = rng.choices(list(BLOCKER_MIX), weights=list(BLOCKER_MIX.values()))[0]

    # Signup and activity window
    if segment == "early":
        signup = SANDBOX_TODAY - timedelta(days=rng.uniform(0.5, 6.5))
        last_active = SANDBOX_TODAY - timedelta(hours=rng.uniform(1, 30))
    elif segment == "activated":
        signup = SANDBOX_TODAY - timedelta(days=rng.uniform(8, 45))
        quiet = rng.uniform(6, 12) if chance(rng, 0.08) else rng.uniform(0.1, 4)
        last_active = SANDBOX_TODAY - timedelta(days=quiet)
    else:
        signup = SANDBOX_TODAY - timedelta(days=rng.uniform(8, 40))
        active_days = 0.3 if blocker == "low_intent" else rng.uniform(1, 6)
        last_active = signup + timedelta(days=active_days)
        if chance(rng, 0.06):
            # A few true stalls went quiet too recently for a 5-day inactivity rule to catch.
            last_active = SANDBOX_TODAY - timedelta(days=rng.uniform(3, 4.5))
        elif (SANDBOX_TODAY - last_active).days < 5.2:
            last_active = SANDBOX_TODAY - timedelta(days=5.2)
    last_active = max(last_active, signup + timedelta(minutes=20))

    role = "member" if blocker == "permissions_blocked" else ("admin" if blocker == "low_intent" or chance(rng, 0.75) else "member")
    if blocker == "low_intent":
        channel = "paid_social" if chance(rng, 0.7) else rng.choice(CHANNELS)
        email_type = "personal" if chance(rng, 0.75) else "work"
    else:
        channel = rng.choice(CHANNELS)
        email_type = "work" if chance(rng, 0.85) else "personal"

    user = {"user_id": user_id, "signup_at": signup.isoformat(timespec="minutes"), "role": role,
            "job_title": rng.choice(JOB_TITLES), "company_size": rng.choice(COMPANY_SIZES),
            "acquisition_channel": channel, "email_type": email_type}

    b = UserBuilder(rng, user_id)
    t = lambda: b.random_ts(signup, last_active)  # noqa: E731
    b.add(signup, "signed_up")

    def sessions(lo, hi, short=False):
        for _ in range(rng.randint(lo, hi)):
            b.add(t(), "session_start", duration_min=round(rng.uniform(1, 4) if short else rng.uniform(4, 35)))
        b.add(last_active, "session_start", duration_min=round(rng.uniform(2, 20)))

    def tasks(lo, hi):
        for _ in range(rng.randint(lo, hi)):
            b.add(t(), "task_created")

    def search(pool, p, n=(1, 2)):
        if chance(rng, p):
            for q in rng.sample(pool, k=min(len(pool), rng.randint(*n))):
                b.add(t(), "search", query=q)

    def help_article(pool, p):
        if chance(rng, p):
            b.add(t(), "help_article_viewed", title=rng.choice(pool))

    if segment in ("activated", "early"):
        full = segment == "activated"
        sessions(4, 14) if full else sessions(1, 4)
        b.add(t(), "project_created")
        tasks(10, 40) if full else tasks(1, 10)
        hits = rng.sample(MILESTONES_AFTER_PROJECT, k=rng.choice([2, 3]) if full else rng.choice([0, 1]))
        for m in hits:
            if m == "integration_connected":
                b.add(t(), "integration_connect_started", integration=rng.choice(INTEGRATIONS))
                b.add(t(), "integration_connected", integration=rng.choice(INTEGRATIONS))
            elif m == "teammate_invited":
                for _ in range(rng.randint(1, 5)):
                    b.add(t(), "teammate_invited")
            else:
                b.add(t(), m)
        if chance(rng, 0.3):
            b.add(t(), "pricing_page_viewed")
        search(rng.choice(list(SEARCHES.values())), 0.2, (1, 1))
    else:
        if blocker == "no_teammates":
            sessions(3, 8)
            b.add(t(), "project_created")
            for _ in range(rng.randint(0, 2)):
                b.add(t(), "project_created")
            tasks(8, 30)
            if chance(rng, 0.4):
                integ = rng.choice(INTEGRATIONS)
                b.add(t(), "integration_connect_started", integration=integ)
                b.add(t(), "integration_connected", integration=integ)
            elif chance(rng, 0.25):
                b.add(t(), "automation_created")
            search(SEARCHES["no_teammates"], 0.45)
            help_article(HELP_ARTICLES["no_teammates"], 0.25)
        elif blocker == "integration_friction":
            sessions(2, 5)
            b.add(t(), "project_created")
            tasks(2, 10)
            integ = rng.choice(INTEGRATIONS)
            for _ in range(rng.randint(1, 3)):
                b.add(t(), "integration_connect_started", integration=integ)
            if chance(rng, 0.7):
                b.add(t(), "integration_connect_failed", integration=integ,
                      error=rng.choice(["oauth_timeout", "missing_scope", "webhook_rejected"]))
            if chance(rng, 0.35):
                b.add(t(), "teammate_invited")
            search(SEARCHES["integration_friction"], 0.4)
            help_article(HELP_ARTICLES["integration_friction"], 0.5)
        elif blocker == "blank_slate":
            sessions(1, 3)
            b.add(t(), "project_created")
            tasks(0, 2)
            if chance(rng, 0.5):
                b.add(t(), "template_gallery_viewed")
            if chance(rng, 0.15):
                b.add(t(), "teammate_invited")
            search(SEARCHES["blank_slate"], 0.4)
            help_article(HELP_ARTICLES["blank_slate"], 0.35)
        elif blocker == "value_unclear":
            sessions(2, 6, short=True)
            b.add(t(), "project_created")
            tasks(3, 8)
            for _ in range(rng.randint(2, 5) if chance(rng, 0.8) else 1):
                b.add(t(), "pricing_page_viewed")
            if chance(rng, 0.4):
                b.add(t(), "teammate_invited")
            search(SEARCHES["value_unclear"], 0.4)
            help_article(HELP_ARTICLES["value_unclear"], 0.3)
        elif blocker == "permissions_blocked":
            sessions(2, 5)
            b.add(t(), "project_created")
            tasks(3, 12)
            if chance(rng, 0.65):
                for _ in range(rng.randint(1, 2)):
                    b.add(t(), "permission_denied",
                          attempted=rng.choice(["connect_integration", "create_automation", "invite_guest"]))
            if chance(rng, 0.3):
                b.add(t(), "integration_connect_started", integration=rng.choice(INTEGRATIONS))
            search(SEARCHES["permissions_blocked"], 0.4)
            help_article(HELP_ARTICLES["permissions_blocked"], 0.3)
        elif blocker == "low_intent":
            b.add(signup + timedelta(minutes=2), "session_start", duration_min=rng.randint(1, 3))
            if chance(rng, 0.4):
                b.add(signup + timedelta(minutes=5), "project_created")

        # Noise that shows up regardless of blocker
        if blocker != "low_intent":
            if chance(rng, 0.25):
                b.add(t(), "pricing_page_viewed")
            if chance(rng, 0.2):
                b.add(t(), "template_gallery_viewed")
            help_article(GENERIC_ARTICLES, 0.2)

    # Onboarding survey at signup
    survey = None
    response_rate = 0.15 if blocker == "low_intent" else 0.5
    if chance(rng, response_rate):
        if blocker and (blocker == "low_intent" or chance(rng, 0.45)):
            survey = rng.choice(HINT_ANSWERS[blocker])
        else:
            survey = rng.choice(NEUTRAL_ANSWERS)

    # Past messages (frequency-cap guardrail input)
    notifications = []
    if chance(rng, 0.7):
        notifications.append(("welcome_email", signup + timedelta(minutes=1)))
    recent_p = 0.15 if segment == "stalled" else 0.1
    if chance(rng, recent_p):
        campaign = rng.choice(["weekly_digest", "trial_ending_soon", "feature_announcement"])
        notifications.append((campaign, SANDBOX_TODAY - timedelta(hours=rng.uniform(4, 70))))
    elif chance(rng, 0.3):
        notifications.append(("weekly_digest", SANDBOX_TODAY - timedelta(days=rng.uniform(4, 10))))
    notif_rows = [{"user_id": user_id, "campaign": c, "channel": "email",
                   "sent_at": ts.isoformat(timespec="minutes"),
                   "opened": str(chance(rng, 0.35)).lower()} for c, ts in notifications]

    truth = {"user_id": user_id, "segment": segment, "blocker": blocker}
    return user, b.events, survey, notif_rows, truth


MILESTONES_AFTER_PROJECT = ["teammate_invited", "integration_connected", "automation_created"]


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--users", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    users, events, surveys, notifs, truth = [], [], [], [], []
    for i in range(1, args.users + 1):
        u, ev, s, n, tr = build_user(rng, i)
        users.append(u)
        events.extend(ev)
        notifs.extend(n)
        truth.append(tr)
        if s:
            surveys.append({"user_id": u["user_id"], "question": "What are you hoping to do with Lorem Work?", "answer": s})
    events.sort(key=lambda e: (e["timestamp"], e["user_id"]))

    write_csv(DATA_DIR / "users.csv", users, list(users[0]))
    write_csv(DATA_DIR / "events.csv", events, ["user_id", "timestamp", "event", "properties"])
    write_csv(DATA_DIR / "survey_responses.csv", surveys, ["user_id", "question", "answer"])
    write_csv(DATA_DIR / "notifications.csv", notifs, ["user_id", "campaign", "channel", "sent_at", "opened"])
    write_csv(HIDDEN_DIR / "truth.csv", truth, ["user_id", "segment", "blocker"])

    stalled = sum(t["segment"] == "stalled" for t in truth)
    print(f"Lorem Work sandbox written to {DATA_DIR}")
    print(f"  {len(users):,} users ({stalled:,} truly stalled), {len(events):,} events, "
          f"{len(surveys):,} survey answers, {len(notifs):,} notifications")


if __name__ == "__main__":
    main()
