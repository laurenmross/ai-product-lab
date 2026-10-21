# The Lorem sandbox

**Lorem** is a fictional company, named after "lorem ipsum" placeholder text so it's obviously a stand-in. Its first product, **Lorem Work**, is a B2B project-management SaaS with a 14-day free trial. Every experiment in this lab runs against it, so results are reproducible and comparable, and nobody needs real customer data.

```bash
python sandbox/generate.py                 # 2,000 users, seed 42 (default)
python sandbox/generate.py --users 10000 --seed 7
```

## Tables (`sandbox/data/`, observable)

| File | One row per | Columns |
|---|---|---|
| `users.csv` | trial signup | `user_id, signup_at, role, job_title, company_size, acquisition_channel, email_type` |
| `events.csv` | product event | `user_id, timestamp, event, properties` (JSON) |
| `survey_responses.csv` | onboarding survey answer | `user_id, question, answer` |
| `notifications.csv` | message sent | `user_id, campaign, channel, sent_at, opened` |

**Events:** `signed_up`, `session_start`, `project_created`, `task_created`, `teammate_invited`, `integration_connect_started`, `integration_connected`, `integration_connect_failed`, `automation_created`, `template_gallery_viewed`, `pricing_page_viewed`, `permission_denied`, `search`, `help_article_viewed`.

**Activation** = 3 of 4 milestones: `project_created`, `teammate_invited`, `integration_connected`, `automation_created`.

## Hidden truth (`sandbox/data/_hidden/`, evals only)

`truth.csv` records each user's segment (`activated`, `stalled`, `early`) and, for stalled users, the real reason they stalled:

| Blocker | Share of stalled | What it looks like (noisily) |
|---|---|---|
| `no_teammates` | 22% | Active solo user, many tasks, zero invites |
| `integration_friction` | 18% | Started an integration; usually a failure event, sometimes just abandoned |
| `blank_slate` | 20% | Created a project, barely added anything |
| `value_unclear` | 17% | Short sessions, repeated pricing visits |
| `permissions_blocked` | 13% | Non-admin; usually hits a permission error, sometimes only searches for help |
| `low_intent` | 10% | One short session, mostly paid social and personal email |

The signals are deliberately noisy and overlapping. Free text (survey answers, searches, help articles) often holds the clearest clue, as it does in real products.

**Agents must never read `_hidden/`.** It's the answer key.

## The simulator

`world.simulate_outcome()` decides whether a user re-engages (hits a new milestone within 7 days) and whether they mute messages, given the action they received. The rates are in [`world.py`](world.py): 30% if the nudge fits their blocker, 10% for generic tips, 7% for a wrong specific nudge, and 6% with no nudge. Messaging someone within the frequency cap cuts the response and raises unsubscribes.

It uses common random numbers: each user's random draws are fixed, so when two policies are compared, the difference comes from their decisions and not from luck.
