"""Score every policy you've run against the sandbox's hidden truth.

    python eval.py

Four checks, from cheapest to most realistic:
  1. Detection: did we find the users who really stalled?
  2. Targeting: did the policy pick the nudge that fits each user's real blocker?
  3. Copy: does the message meet the length and tone rules?
  4. Simulated A/B test: randomize users into control (no nudge) vs treatment,
     simulate who re-engages, and read it out like a real experiment, with the
     unsubscribe rate as a guardrail metric.

Also prints an "oracle" row: perfect targeting, the ceiling any policy can reach.
Writes the report to out/eval_report.md.
"""
from __future__ import annotations

import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

from _sandbox import world
from guardrails import apply_guardrails
from signals import build_profiles, is_stalled

OUT_DIR = Path(__file__).resolve().parent / "out"
POLICY_ORDER = ["generic", "rules", "llm"]
COPY_LIMITS = {"headline": 60, "body": 160, "cta": 25}


def load_decisions() -> dict[str, list[dict]]:
    found = {}
    for policy in POLICY_ORDER:
        path = OUT_DIR / f"decisions_{policy}.jsonl"
        if path.exists():
            found[policy] = [json.loads(line) for line in path.open()]
    if not found:
        raise SystemExit("No decisions found. Run `python run.py --policy rules` first.")
    return found


def two_proportion_test(x1, n1, x2, n2):
    """Difference in rates (treatment - control), its 95% CI, and a two-sided p-value."""
    p1, p2 = x1 / n1, x2 / n2
    diff = p1 - p2
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    pooled = (x1 + x2) / (n1 + n2)
    se_pooled = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2)) or 1e-9
    z = diff / se_pooled
    p_value = math.erfc(abs(z) / math.sqrt(2))
    return diff, (diff - 1.96 * se, diff + 1.96 * se), p_value


def in_treatment(user_id: str) -> bool:
    return random.Random(f"ab-split:{user_id}").random() < 0.5


def simulate_ab(rows, truth, profiles):
    """rows: [(user_id, final_action)]. Returns stats for control vs treatment."""
    arms = {"control": [0, 0, 0], "treatment": [0, 0, 0]}  # n, reengaged, unsubscribed
    for uid, action in rows:
        arm = "treatment" if in_treatment(uid) else "control"
        sent = action if arm == "treatment" else "no_nudge"
        hours = profiles[uid]["hours_since_last_message"]
        recent = hours is not None and hours < world.FREQUENCY_CAP_HOURS
        reengaged, unsub = world.simulate_outcome(uid, truth[uid]["blocker"], sent, recent)
        a = arms[arm]
        a[0] += 1
        a[1] += reengaged
        a[2] += unsub
    (nc, rc, uc), (nt, rt, ut) = arms["control"], arms["treatment"]
    diff, ci, p = two_proportion_test(rt, nt, rc, nc)
    return {"n_control": nc, "n_treatment": nt, "control_rate": rc / nc, "treatment_rate": rt / nt,
            "abs_lift": diff, "ci": ci, "p_value": p, "rel_lift": diff / (rc / nc) if rc else float("nan"),
            "unsub_rate": ut / nt}


def copy_ok(d: dict) -> bool:
    if d["proposed_action"] == "no_nudge":
        return True
    fields = {k: d.get(k) or "" for k in COPY_LIMITS}
    return all(fields.values()) and all(len(fields[k]) <= lim for k, lim in COPY_LIMITS.items()) \
        and not any("!" in v for v in fields.values())


def pct(x):
    return f"{x * 100:.1f}%"


def main():
    truth = world.load_truth()
    profiles = build_profiles()
    decisions = load_decisions()
    lines = ["# Next-best-action eval", ""]

    # 1. Detection
    flagged = {uid for uid, p in profiles.items() if is_stalled(p)}
    actual = {uid for uid, t in truth.items() if t["segment"] == "stalled"}
    tp = len(flagged & actual)
    lines += ["## 1. Stall detection", "",
              f"Flagged {len(flagged)} users. Precision {pct(tp / len(flagged))} "
              f"(flagged users who really stalled), recall {pct(tp / len(actual))} (stalled users we found).", ""]

    # 2-4. Per policy
    summary = ["| Policy | Users | Targeting accuracy | Copy passes | Held by guardrails | Control | Treatment | Lift (abs) | 95% CI | p | Unsub rate |",
               "|---|---|---|---|---|---|---|---|---|---|---|"]
    per_blocker = defaultdict(dict)
    confusion = {}
    ab_rows = {}
    for policy, ds in decisions.items():
        scored = [d for d in ds if truth[d["user_id"]]["segment"] == "stalled"]
        correct = sum(d["proposed_action"] == world.BEST_ACTION[truth[d["user_id"]]["blocker"]] for d in scored)
        by_blocker = defaultdict(lambda: [0, 0])
        conf = defaultdict(Counter)
        for d in scored:
            b = truth[d["user_id"]]["blocker"]
            by_blocker[b][1] += 1
            by_blocker[b][0] += d["proposed_action"] == world.BEST_ACTION[b]
            conf[b][d["proposed_action"]] += 1
        for b, (c, n) in by_blocker.items():
            per_blocker[b][policy] = c / n
        confusion[policy] = conf
        held = sum(d["final_action"] == "hold" for d in ds)
        ab = simulate_ab([(d["user_id"], d["final_action"]) for d in ds], truth, profiles)
        ab_rows[policy] = ab
        copy_rate = sum(copy_ok(d) for d in ds) / len(ds)
        summary.append(f"| {policy} | {len(ds)} | {pct(correct / len(scored))} | {pct(copy_rate)} | {held} | "
                       f"{pct(ab['control_rate'])} | {pct(ab['treatment_rate'])} | {ab['abs_lift'] * 100:+.1f} pts "
                       f"({ab['rel_lift'] * 100:+.0f}%) | {ab['ci'][0] * 100:+.1f} to {ab['ci'][1] * 100:+.1f} | "
                       f"{ab['p_value']:.3g} | {pct(ab['unsub_rate'])} |")

    # Oracle: perfect targeting on the same users as the largest decisions file
    base = max(decisions.values(), key=len)
    oracle_rows = []
    for d in base:
        t = truth[d["user_id"]]
        best = world.BEST_ACTION.get(t["blocker"], "generic_tips")
        oracle_rows.append((d["user_id"], apply_guardrails(profiles[d["user_id"]], best)[0]))
    ab = simulate_ab(oracle_rows, truth, profiles)
    summary.append(f"| *oracle (ceiling)* | {len(base)} | 100.0% | n/a | {sum(a == 'hold' for _, a in oracle_rows)} | "
                   f"{pct(ab['control_rate'])} | {pct(ab['treatment_rate'])} | {ab['abs_lift'] * 100:+.1f} pts "
                   f"({ab['rel_lift'] * 100:+.0f}%) | {ab['ci'][0] * 100:+.1f} to {ab['ci'][1] * 100:+.1f} | "
                   f"{ab['p_value']:.3g} | {pct(ab['unsub_rate'])} |")

    sizes = {len(ds) for ds in decisions.values()}
    lines += ["## 2-4. Targeting, copy, and simulated A/B test", "",
              "Primary metric: share of users who hit a new activation milestone within 7 days. "
              "Guardrail metric: share of treated users who mute Lorem Work messages.", ""]
    if len(sizes) > 1:
        lines += ["> Policies were run on different numbers of users (e.g. `--limit` on the LLM run), "
                  "so compare their rows with care.", ""]
    lines += summary + [""]

    lines += ["## Targeting accuracy by real blocker", "",
              "| Blocker | Right action | " + " | ".join(decisions) + " |",
              "|---|---|" + "---|" * len(decisions)]
    for b in world.BLOCKERS:
        lines.append(f"| {b} | {world.BEST_ACTION[b]} | " +
                     " | ".join(pct(per_blocker[b][p]) if p in per_blocker[b] else "-" for p in decisions) + " |")
    lines.append("")

    for policy, conf in confusion.items():
        if policy == "generic":
            continue
        lines += [f"### Where `{policy}` goes wrong (real blocker → actions chosen)", ""]
        for b in world.BLOCKERS:
            wrong = {a: n for a, n in conf[b].items() if a != world.BEST_ACTION[b]}
            if wrong:
                lines.append(f"- **{b}**: " + ", ".join(f"{a} ×{n}" for a, n in sorted(wrong.items(), key=lambda x: -x[1])))
        lines.append("")

    report = "\n".join(lines)
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "eval_report.md").write_text(report)
    print(report)
    print(f"(saved to {OUT_DIR / 'eval_report.md'})")


if __name__ == "__main__":
    main()
