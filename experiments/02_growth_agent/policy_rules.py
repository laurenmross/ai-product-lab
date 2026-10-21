"""Baseline policies: the status quo (generic tips for everyone) and a hand-written rules engine.

Always build the rules version first. It's cheap, explainable, and it's the bar the
LLM has to clear to justify its cost.
"""
from __future__ import annotations

TEMPLATES = {
    "invite_teammates": ("Lorem Work works better with your team",
                         "Your project is set up. Invite a teammate so you can assign tasks and see progress together.",
                         "Invite a teammate"),
    "integration_help": ("Let's get your integration working",
                         "Looks like the connection didn't finish. This 2-minute guide fixes the most common issues.",
                         "Fix the connection"),
    "template_starter": ("Start from a template",
                         "Pick a ready-made board for sprints, launches, or client work and customize from there.",
                         "Browse templates"),
    "roi_showcase": ("See what teams save with Lorem Work",
                     "Teams your size save about 4 hours a week on status updates. We've added 7 days to your trial.",
                     "Compare plans"),
    "request_admin": ("Need access from your admin?",
                      "Some features need admin approval. Send your admin a one-click request.",
                      "Ask my admin"),
    "generic_tips": ("Get more out of Lorem Work",
                     "Three quick tips to help your team stay on top of projects.",
                     "See the tips"),
}


def _decision(action: str, rationale: str, confidence: str = "medium") -> dict:
    headline, body, cta = TEMPLATES.get(action, ("", "", ""))
    return {"action": action, "confidence": confidence, "rationale": rationale,
            "headline": headline, "body": body, "cta": cta}


def decide_generic(profile: dict) -> dict:
    return _decision("generic_tips", "Status quo: everyone stalled gets the same tips.", "low")


def decide_rules(p: dict) -> dict:
    c = p["counts"]
    sessions = c.get("session_start", 0)
    if sessions <= 1 and c.get("task_created", 0) == 0:
        return _decision("no_nudge", "One session and no real activity; likely low intent.")
    if p["permission_denials"] and p["role"] == "member":
        return _decision("request_admin", "Non-admin hit a permission error.", "high")
    if p["integration_errors"]:
        return _decision("integration_help", "Integration connection failed.", "high")
    if c.get("task_created", 0) < 3:
        return _decision("template_starter", "Project exists but is nearly empty.")
    if not c.get("teammate_invited"):
        return _decision("invite_teammates", "Active solo user who never invited anyone.")
    if c.get("pricing_page_viewed", 0) >= 2:
        return _decision("roi_showcase", "Repeated pricing page visits.")
    return _decision("generic_tips", "No clear signal.", "low")
