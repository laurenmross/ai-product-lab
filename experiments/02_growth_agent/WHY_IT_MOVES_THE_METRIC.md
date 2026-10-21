# Why it moves the metric: next-best-action onboarding

## The metric

**Primary:** share of stalled trial users who hit a new activation milestone within 7 days of the nudge.
Activation (3 of 4 milestones: project, teammate, integration, automation) is the leading indicator for trial-to-paid conversion, so this is the number to move.

**Guardrail:** share of nudged users who mute in-app messages. A nudge that lifts activation by burning the channel is borrowing from next quarter.

**Secondary (in a real launch):** trial-to-paid conversion at day 30, and support tickets per 1,000 trial users.

## The hypothesis

Stalled users don't share one problem. They stall for different reasons: no team, a broken integration, a blank project, doubts about price, missing permissions, or no real intent. A generic "here are some tips" nudge is weak for everyone. A nudge that addresses *their* blocker is strong for the people it fits.

So the lift comes from **targeting**, not from messaging more. The sandbox makes this concrete:

| | Re-engagement if nudged |
|---|---|
| Nudge fits their blocker | 30% |
| Generic tips | 10% |
| Nudge aimed at the wrong blocker | 7% |
| No nudge (control) | 6% |

A wrong specific nudge does barely better than nothing, and worse than generic tips. **Targeting accuracy is the whole game**, which is why the eval measures it directly and doesn't just report lift.

## Rules first, then the LLM

The rules engine is the baseline the LLM has to beat. It's free, instant, and explainable, and in the sandbox it already gets 77% targeting accuracy and most of the available lift.

Its failures are instructive, and they're the same ones real rules engines have:

- **Rule order decides everything.** "No invites → invite_teammates" fires before "visited pricing twice → roi_showcase", so most value-unclear users get an invite prompt (27.6% accuracy on that blocker).
- **It can't read.** A member who searched "need admin access" but never triggered a permission error looks like a solo user to the rules. The survey answer "IT controls which apps we can connect" is invisible to it.
- **Signals overlap.** Starting an integration and stopping can mean a technical failure *or* a permissions wall.

The LLM's job is to close the gap between rules (about +15 points of lift) and the oracle ceiling (about +21). **If it can't close a meaningful part of that gap, ship the rules.** That's a legitimate outcome, not a failure.

## Guardrails (in code, not the prompt)

Every policy's decision passes through [`guardrails.py`](guardrails.py) before anything is sent:

1. **Frequency cap.** No nudge within 72 hours of any other message. Over-messaged users respond less and unsubscribe more.
2. **Role validity.** `request_admin` is rewritten to generic tips if the user *is* the admin.
3. **Unknown actions are dropped.** If a model invents an action, nothing is sent.

The prompt even tells the model to ignore frequency, because that's not its job. Separating "what would help" from "are we allowed to send it" keeps each part testable.

## Knowing when not to nudge

About 10% of stalled users are low intent: one short session, often from paid social, often a personal email. Nudging them barely moves re-engagement (1% → 1.5%) and gets 12% of them to mute messages. The correct action is `no_nudge`, and the eval scores it that way. A policy that messages everyone will look busier and do worse.

## How I'd run this for real

- **Unit:** user (or account, for team products, to avoid teammates landing in different arms).
- **Design:** a persistent 10% global holdout that gets no nudges, plus a 50/50 split of the rest between the current nudge and the new policy. The holdout tells you the absolute value of nudging at all; the split tells you whether the new policy beats the old one.
- **Sample size:** to detect a 20% → 25% change at 80% power, you need about 1,100 users per arm. At the sandbox's scale (800 stalled per cohort) that's a multi-cohort test, so plan for 3 to 4 weeks.
- **Ramp:** rules policy first (cheap, safe), then LLM policy on 10% of treatment, compared on targeting-proxy metrics (click-through on the nudge, milestone hit for the *targeted* milestone) before going wide.
- **Readout:** primary metric with a confidence interval, the guardrail metric, and lift broken out by inferred blocker. Lift concentrated in one or two blockers tells you where to invest next.

## Cost

The LLM prompt is about 850 input tokens per user, and each decision outputs a few hundred tokens. On Claude Opus 5.5 at list price that's roughly **$0.01 per decision, or about $10 per 1,000 stalled users**. `run.py` prints the actual figure after each LLM run. Compare that with the value of one extra activated trial and the math usually works. Still, the rules engine costs nothing, so the LLM has to earn its place on targeting accuracy.

## What's not in v1

- Channel choice (in-app vs email vs push) and send-time optimization.
- An LLM-as-judge for copy quality. v1 checks only length and tone rules.
- Learning from outcomes, such as a bandit that shifts traffic toward the actions that work for each inferred blocker.
