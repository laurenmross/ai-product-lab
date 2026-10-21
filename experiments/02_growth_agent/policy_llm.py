"""LLM policy: Claude reads one stalled user's profile, picks the nudge, and writes it.

Where it should beat the rules engine:
  * It reads free text (survey answers, search queries, help articles) that rules ignore.
  * It weighs conflicting signals instead of taking the first rule that matches.
  * It writes copy specific to what the user actually did.

Requires Python 3.10+, `pip install -r requirements.txt`, and Anthropic credentials
(ANTHROPIC_API_KEY or `ant auth login`).
"""
from __future__ import annotations

import json

from _sandbox import world
from policy_rules import decide_rules

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = f"""You are the next-best-action engine for Lorem Work, a project-management SaaS for teams with a 14-day free trial.

You will see one trial user who signed up at least a week ago, hasn't activated, and has gone quiet. Activation means hitting 3 of these 4 milestones: creating a project, inviting a teammate, connecting an integration, creating an automation.

Your job is to work out what most likely stopped this user, pick the single in-app nudge most likely to get them to their next milestone, and write it.

Available actions:
{json.dumps({k: v for k, v in world.ACTIONS.items()}, indent=2)}

How to decide:
- Use all the evidence. Free text (the onboarding survey answer, search queries, help articles they read) is often the clearest signal of what they were trying to do and where they got stuck. Event counts can mislead: for example, a user who started an integration and stopped may have hit a permissions wall rather than a technical problem.
- request_admin only makes sense for users whose role is "member".
- Choose no_nudge when the evidence says the user never had real intent, such as one very short session with no meaningful activity. Messaging them costs goodwill and rarely helps.
- Choose generic_tips only when there is genuinely no signal pointing to a specific blocker.
- Ignore message frequency; a separate system enforces send limits.

How to write the nudge (leave headline, body and cta empty for no_nudge):
- headline: at most 60 characters. body: at most 160 characters. cta: at most 25 characters.
- Refer to something specific they did, such as the project they made or the integration they tried.
- Plain, warm, helpful. No exclamation marks, no guilt ("you haven't..."), no invented features, discounts or numbers beyond what the action description offers."""

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "likely_blocker": {"type": "string", "description": "One sentence on what most likely stopped this user."},
        "action": {"type": "string", "enum": list(world.ACTIONS)},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "rationale": {"type": "string", "description": "The evidence behind the choice, in one or two sentences."},
        "headline": {"type": "string"},
        "body": {"type": "string"},
        "cta": {"type": "string"},
    },
    "required": ["likely_blocker", "action", "confidence", "rationale", "headline", "body", "cta"],
    "additionalProperties": False,
}

# Events that are just volume; summarize them as counts instead of listing each one.
_BULK_EVENTS = {"session_start", "task_created"}


def profile_to_prompt(p: dict) -> str:
    """A compact, readable profile. No hidden truth, only what the product can see."""
    timeline = []
    for ts, event, props in p["timeline"]:
        if event in _BULK_EVENTS:
            continue
        detail = ", ".join(f"{k}={v}" for k, v in props.items())
        timeline.append(f"- {ts} {event}" + (f" ({detail})" if detail else ""))
    lines = [
        f"User {p['user_id']}",
        f"Role: {p['role']} | Job title: {p['job_title']} | Company size: {p['company_size']}",
        f"Signed up {p['days_since_signup']} days ago via {p['acquisition_channel']} ({p['email_type']} email)",
        f"Inactive for {p['days_inactive']} days",
        f"Milestones hit: {', '.join(p['milestones_hit']) or 'none'}",
        f"Sessions: {p['counts'].get('session_start', 0)} | Tasks created: {p['counts'].get('task_created', 0)}",
        f"Onboarding survey ('What are you hoping to do with Lorem Work?'): {p['survey_answer'] or 'no answer'}",
        "",
        "Other events (sessions and task creation omitted):",
        *(timeline or ["- none"]),
    ]
    return "\n".join(lines)


def make_client():
    try:
        import anthropic
    except ImportError as e:
        raise SystemExit("LLM policy needs the Anthropic SDK: pip install -r requirements.txt (Python 3.10+)") from e
    return anthropic.Anthropic()


def decide_llm(p: dict, client) -> dict:
    import anthropic

    try:
        # Refusal fallbacks are on: if the model declines, the API retries on a fallback model.
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=4000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            # Low effort: this is a short classification-plus-copy task, not deep reasoning.
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": DECISION_SCHEMA}},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": profile_to_prompt(p)}],
        )
    except (anthropic.BadRequestError, anthropic.AuthenticationError, anthropic.PermissionDeniedError,
            anthropic.NotFoundError):
        raise  # configuration problems: fail loudly, don't silently fall back for every user
    except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        return _fallback(p, f"llm_error: {type(e).__name__}")

    if response.stop_reason != "end_turn":
        return _fallback(p, f"llm_stop_reason: {response.stop_reason}")

    text = next(b.text for b in response.content if b.type == "text")
    decision = json.loads(text)
    decision["usage"] = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
    return decision


def _fallback(p: dict, reason: str) -> dict:
    """If the model can't answer, fall back to the rules engine rather than skipping the user."""
    d = decide_rules(p)
    d["rationale"] = f"[fallback to rules: {reason}] {d['rationale']}"
    return d
