# Experiment 02 · Growth agent: next-best-action onboarding

Finds trial users who stalled before activating, works out *why* each one stalled, and picks the one in-app nudge most likely to get them moving again. Then it checks the decision against hard guardrails before anything is sent.

## Run it (2 minutes, no API key)

```bash
python ../../sandbox/generate.py      # once: build the Lorem sandbox
python run.py --policy generic        # status quo: same tips for everyone
python run.py --policy rules          # hand-written rules engine
python eval.py                        # score both against the hidden truth
```

## Run the LLM version

Needs Python 3.10+ and Anthropic credentials (`ANTHROPIC_API_KEY`, or `ant auth login`).

```bash
pip install -r ../../requirements.txt
python run.py --policy llm --limit 50   # about $0.50; drop --limit for all ~800 users (about $8)
python eval.py
```

The LLM policy uses Claude Opus 5.5 with structured outputs, so every decision is valid JSON in a fixed schema. It runs at low effort because this is a short task. Server-side refusal fallbacks are on. If a call fails or is declined, that user falls back to the rules engine instead of being skipped.

## Results on the sandbox (seed 42, 800 stalled users)

| Policy | Targeting accuracy | Re-engaged (treatment vs control) | Lift | Unsub rate |
|---|---|---|---|---|
| Generic tips (status quo) | 0% | 9.1% vs 4.6% | +4.5 pts | 2.0% |
| Rules engine | 77.2% | 20.0% vs 4.6% | +15.4 pts | 0.7% |
| LLM (Claude) | run it ↑ | | | |
| *Oracle: perfect targeting* | *100%* | *25.1% vs 4.6%* | *+20.6 pts* | *0.7%* |

The gap between rules and the oracle is what the LLM is competing for. Most of it sits in three blockers the rules handle poorly: value-unclear (27.6%), integration friction (64.2%) and permissions (66.3%). [`WHY_IT_MOVES_THE_METRIC.md`](WHY_IT_MOVES_THE_METRIC.md) explains why.

## How it works

```
sandbox tables ──► signals.py ──► policy (generic | rules | llm) ──► guardrails.py ──► decisions_<policy>.jsonl
                   one profile         proposes an action                 frequency cap,          │
                   per user,           + message copy                     role checks             ▼
                   stall detection                                                            eval.py
                                                                                     (scores against hidden truth)
```

| File | What it does |
|---|---|
| [`signals.py`](signals.py) | Builds one profile per user from observable data and flags stalled users (7+ days since signup, < 3 milestones, 5+ days inactive). |
| [`policy_rules.py`](policy_rules.py) | The two baselines: generic tips for everyone, and a priority-ordered rules engine. |
| [`policy_llm.py`](policy_llm.py) | Claude reads the profile, including free text the rules ignore, then picks an action and writes the nudge. |
| [`guardrails.py`](guardrails.py) | Hard rules applied to every policy: 72-hour frequency cap, role validity, unknown-action drop. |
| [`run.py`](run.py) | Runs a policy over all stalled users and writes `out/decisions_<policy>.jsonl`. |
| [`eval.py`](eval.py) | Detection precision/recall, targeting accuracy (overall, by blocker, and a confusion list), copy checks, and a simulated A/B test with CI, p-value and guardrail metric. |

## Make it yours

- **Beat the rules:** edit `decide_rules` in `policy_rules.py` and rerun `eval.py`. Fixing the rule order alone is worth several points.
- **Tune the prompt:** edit `SYSTEM_PROMPT` in `policy_llm.py`, run on `--limit 100`, and compare.
- **Add a policy:** write any function `profile -> {action, confidence, rationale, headline, body, cta}` and add it to `run.py`.
