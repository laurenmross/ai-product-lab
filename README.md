# AI Product Lab

**Hands-on experiments in building, evaluating and improving AI systems: prompts, retrieval, tools, skills and agents, each measured against a known answer key.**

I'm a product leader who has spent years asking engineering teams to build AI features. This lab is where I build them myself, to understand how the pieces actually work and when each approach is worth its cost.

Everything runs on **Lorem**, a fictional company (named after "lorem ipsum" placeholder text). It has realistic, messy product data and a hidden answer key, so every claim here comes with a measurement, not a demo.

## Ground rules

1. **I own the architecture.** AI coding tools help write implementation code; design decisions and their tradeoffs are mine, and they're documented.
2. **Every experiment runs.** Anyone can reproduce it from the setup instructions.
3. **Every claim has evidence:** evals, example failures, cost and latency, and tradeoffs.
4. **I document what I learned,** including decisions I reversed and mistakes I found, not just what worked.

## Experiments

| # | Experiment | Question | Status |
|---|---|---|---|
| 01 | [AI product analyst](experiments/01_product_analyst/) | Does retrieval, a SQL tool, or a skill make an agent answer product questions more accurately, and at what cost? | Planned |
| 02 | [Growth agent](experiments/02_growth_agent/) | Can an agent diagnose why trial users stall and pick the right nudge better than a rules engine? | Baselines built |

### Early result (experiment 02)

| Policy | Picks the right nudge | Simulated activation lift |
|---|---|---|
| Generic tips (status quo) | 0% | +4.5 pts |
| Rules engine | 77% | +15.4 pts |
| Perfect targeting (ceiling) | 100% | +20.6 pts |
| LLM agent | not yet run | |

## The sandbox

**Lorem Work** is Lorem's project-management SaaS: 2,000 trial signups with an event stream, onboarding survey answers and message history. Each stalled user also has a hidden reason for stalling that only evals can see. [About the sandbox →](sandbox/README.md)

## Quickstart

```bash
python3 sandbox/generate.py
cd experiments/02_growth_agent
python3 run.py --policy rules && python3 eval.py
```

Baselines and evals use only the Python standard library (3.9+). LLM experiments need Python 3.10+, `pip install -r requirements.txt`, and an Anthropic API key.

## Layout

```
sandbox/          the fictional company: data generator, loaders, outcome simulator
experiments/NN_*/ one experiment per folder: code, eval, README, LEARNINGS.md
```

## License

MIT
