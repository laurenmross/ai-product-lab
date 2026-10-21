"""Find stalled users, decide a nudge for each, apply guardrails, and write the decisions.

    python run.py --policy generic          # status quo: same tips for everyone
    python run.py --policy rules            # hand-written rules (no API key needed)
    python run.py --policy llm --limit 50   # Claude (costs money; start small)

Writes out/decisions_<policy>.jsonl. Then run `python eval.py` to score every policy you've run.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from guardrails import apply_guardrails
from policy_rules import decide_generic, decide_rules
from signals import stalled_profiles

OUT_DIR = Path(__file__).resolve().parent / "out"


def main():
    ap = argparse.ArgumentParser(description="Next-best-action onboarding agent")
    ap.add_argument("--policy", choices=["generic", "rules", "llm"], required=True)
    ap.add_argument("--limit", type=int, help="Only decide for a random sample of N stalled users")
    ap.add_argument("--workers", type=int, default=8, help="Parallel API calls for the LLM policy")
    args = ap.parse_args()

    profiles = sorted(stalled_profiles(), key=lambda p: p["user_id"])
    if args.limit:
        # Fixed sample so different policies can be compared on the same users.
        profiles = sorted(random.Random(0).sample(profiles, min(args.limit, len(profiles))), key=lambda p: p["user_id"])
    print(f"{len(profiles)} stalled users to decide for (policy: {args.policy})")

    if args.policy == "llm":
        from policy_llm import decide_llm, make_client
        client = make_client()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            decisions = list(pool.map(lambda p: decide_llm(p, client), profiles))
    else:
        decide = decide_rules if args.policy == "rules" else decide_generic
        decisions = [decide(p) for p in profiles]

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"decisions_{args.policy}.jsonl"
    final_counts, guardrail_counts = Counter(), Counter()
    with out_path.open("w") as f:
        for p, d in zip(profiles, decisions):
            final, fired = apply_guardrails(p, d["action"])
            final_counts[final] += 1
            if fired:
                guardrail_counts[fired] += 1
            f.write(json.dumps({"user_id": p["user_id"], "policy": args.policy, "proposed_action": d["action"],
                                "final_action": final, "guardrail": fired, **{k: v for k, v in d.items() if k != "action"}}) + "\n")

    print(f"Wrote out/{out_path.name}")
    print("Final actions:", dict(final_counts.most_common()))
    print("Guardrails fired:", dict(guardrail_counts) or "none")
    if args.policy == "llm":
        tokens_in = sum(d.get("usage", {}).get("input_tokens", 0) for d in decisions)
        tokens_out = sum(d.get("usage", {}).get("output_tokens", 0) for d in decisions)
        cost = tokens_in / 1e6 * 4.00 + tokens_out / 1e6 * 20.00  # Claude Opus 5.5 list price
        print(f"Tokens: {tokens_in:,} in / {tokens_out:,} out, about ${cost:.2f} "
              f"(${cost / max(len(decisions), 1) * 1000:.2f} per 1,000 users)")


if __name__ == "__main__":
    main()
