"""Hard rules every policy's decision passes through before anything is sent.

Guardrails live in code, not in the prompt. A model can be told "don't message
people twice in three days" and still do it; a function can't. The policy proposes,
the guardrail layer disposes.
"""
from __future__ import annotations

from _sandbox import world


def apply_guardrails(profile: dict, proposed_action: str) -> tuple[str, str | None]:
    """Return (final_action, guardrail_that_fired or None)."""
    if proposed_action not in world.ACTIONS:
        return "no_nudge", "unknown_action"

    if proposed_action == "no_nudge":
        return "no_nudge", None

    # Asking your admin for access makes no sense if you are the admin.
    if proposed_action == "request_admin" and profile["role"] == "admin":
        proposed_action = "generic_tips"
        fired = "invalid_for_role"
    else:
        fired = None

    hours = profile["hours_since_last_message"]
    if hours is not None and hours < world.FREQUENCY_CAP_HOURS:
        return "hold", "frequency_cap"

    return proposed_action, fired
