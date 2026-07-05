"""Primary analysis for slm-agent-eval (design §§8–9).

Re-grades EVERY episode from its raw event log with the current (validated)
grader — inline grades stored at run time are advisory only — then computes:

  - per-cell success rates with Wilson 95% CIs
  - pass^k for k in {1,2,4,8} (unbiased estimator over 8 seeds, mean over tasks)
  - the 5 pre-registered paired contrasts: McNemar exact test, risk
    difference, cluster-bootstrap 95% CI (clustered by task), Holm correction
  - first-failure distributions per cell
  - S4 behavior rates and S5 fault-recovery rates per cell
  - latency/token accounting and guardrail overhead (paired), plus *derived*
    consumer-CPU wall-clock (token counts x Phase 0 measured laptop tok/s;
    only for models measured on the laptop, else null)

Outputs analysis/results.json and analysis/tables.md. Deterministic
(bootstrap seed fixed). Usage: python analysis/analyze.py [--runs core_v1 ext_v1]
"""

import argparse
import json
import math
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from grading.attribute import attribute  # noqa: E402
from grading.grade import grade  # noqa: E402

BOOT_B = 10_000
BOOT_SEED = 123

# Phase 0 measured laptop throughput (NOTES.md timing matrix): tok/s.
LAPTOP_RATES = {
    "qwen2.5:1.5b-instruct-q4_K_M": (47.5, 8.2),
    "qwen2.5:3b-instruct-q4_K_M": (18.3, 4.3),
    "qwen2.5:7b-instruct-q4_K_M": (6.9, 1.5),
    "llama3.2:1b": (45.5, 9.6),
}

CONTRASTS = [  # (name, cell_b, cell_a) -> effect = rate(a) - rate(b)
    ("guardrail@1.5B-Q4", "C1", "C2"),
    ("guardrail@1.5B-Q8", "C3", "C4"),
    ("guardrail@3B-Q4", "C5", "C6"),
    ("Q8-vs-Q4@1.5B(base)", "C1", "C3"),
    ("3B-vs-1.5B@Q4(base)", "C1", "C5"),
]


def wilson(successes: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (round(centre - half, 4), round(centre + half, 4))


def pass_hat_k(c: int, n: int, k: int) -> float:
    if c < k:
        return 0.0
    return math.comb(c, k) / math.comb(n, k)


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar on discordant counts (binomial, p=0.5)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def holm(pvals: list[float]) -> list[float]:
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adj, running = [0.0] * m, 0.0
    for rank, idx in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvals[idx]))
        adj[idx] = round(running, 5)
    return adj


def cluster_boot_ci(diff_by_task: dict[str, list[int]]) -> tuple[float, float]:
    """95% CI for mean paired difference, resampling tasks (clusters)."""
    rng = np.random.default_rng(BOOT_SEED)
    tasks = sorted(diff_by_task)
    arrs = [np.array(diff_by_task[t], dtype=float) for t in tasks]
    stats = np.empty(BOOT_B)
    for i in range(BOOT_B):
        picks = rng.integers(0, len(arrs), len(arrs))
        stats[i] = np.concatenate([arrs[j] for j in picks]).mean()
    return (round(float(np.percentile(stats, 2.5)), 4),
            round(float(np.percentile(stats, 97.5)), 4))


def load_episodes(run_dir: Path, tasks: dict) -> list[dict]:
    records = []
    for f in sorted(run_dir.glob("*/*.json")):
        ep = json.loads(f.read_text(encoding="utf-8"))
        task = dict(tasks[ep["task_id"]])
        g = grade(ep, task)
        a = attribute(ep, task, g)
        mc = [e for e in ep["events"] if e["type"] == "model_call"]
        records.append({
            "cell": ep["cell"], "model": ep["model"],
            "condition": ep["condition"], "task": ep["task_id"],
            "slice": ep["slice"], "seed": ep["seed"],
            "success": bool(g["success"]),
            "parse_failure": bool(g.get("parse_failure")),
            "first_failure": a["first_failure"],
            "s4": a.get("s4_behavior"), "s5": a.get("s5"),
            "asked": bool(ep.get("asked_clarification")),
            "wall_s": ep["wall_s"], "calls": len(mc),
            "tok_prompt": ep["token_totals"]["prompt_eval"],
            "tok_eval": ep["token_totals"]["eval"],
            "blocks": ep.get("blocks_used", 0),
        })
    return records


def analyze_run(records: list[dict], contrasts: list) -> dict:
    cells = sorted({r["cell"] for r in records})
    by_cell = {c: [r for r in records if r["cell"] == c] for c in cells}
    out: dict = {"cells": {}, "contrasts": [], "s4": {}, "s5": {}}

    for c, rows in by_cell.items():
        n = len(rows)
        s = sum(r["success"] for r in rows)
        seeds = sorted({r["seed"] for r in rows})
        per_task = Counter(r["task"] for r in rows if r["success"])
        task_ids = sorted({r["task"] for r in rows})
        passk = {f"pass^{k}": round(
            sum(pass_hat_k(per_task.get(t, 0), len(seeds), k)
                for t in task_ids) / len(task_ids), 4)
            for k in (1, 2, 4, 8) if k <= len(seeds)}
        model = rows[0]["model"]
        rate = LAPTOP_RATES.get(model)
        mean_prompt = sum(r["tok_prompt"] for r in rows) / n
        mean_eval = sum(r["tok_eval"] for r in rows) / n
        out["cells"][c] = {
            "model": model, "condition": rows[0]["condition"], "n": n,
            "successes": s, "rate": round(s / n, 4), "wilson95": wilson(s, n),
            **passk,
            "parse_failure_rate": round(
                sum(r["parse_failure"] for r in rows) / n, 4),
            "first_failures": dict(Counter(
                str(r["first_failure"]) for r in rows if not r["success"])),
            "mean_wall_s": round(sum(r["wall_s"] for r in rows) / n, 2),
            "mean_model_calls": round(sum(r["calls"] for r in rows) / n, 2),
            "mean_tok_prompt": round(mean_prompt, 1),
            "mean_tok_eval": round(mean_eval, 1),
            "mean_blocks": round(sum(r["blocks"] for r in rows) / n, 3),
            "derived_cpu_s": (round(mean_prompt / rate[0]
                                    + mean_eval / rate[1], 1)
                              if rate else None),
        }
        s4_rows = [r for r in rows if r["slice"] == "S4"]
        if s4_rows:
            out["s4"][c] = {b: round(sum(r["s4"] == b for r in s4_rows)
                                     / len(s4_rows), 3)
                            for b in ("asked", "looked_up", "guessed")}
        s5_rows = [r for r in rows if r["slice"] == "S5" and r["s5"]]
        if s5_rows:
            fired = [r for r in s5_rows if r["s5"].get("fault_fired")]
            out["s5"][c] = {
                "n_s5": len(s5_rows),
                "fault_fired": len(fired),
                "recovered": sum(r["s5"].get("recovered", False) for r in fired),
                "answered_unrecovered": sum(
                    r["s5"].get("answered_after_unrecovered_fault", False)
                    for r in fired),
                "refused": sum(r["s5"].get("refused", False) for r in fired),
                "hallucinated_answer": sum(
                    r["s5"].get("hallucinated_answer", False) for r in fired),
            }

    pvals = []
    for name, cb, ca in contrasts:
        if cb not in by_cell or ca not in by_cell:
            continue
        key = lambda r: (r["task"], r["seed"])  # noqa: E731
        a_map = {key(r): r for r in by_cell[ca]}
        b_map = {key(r): r for r in by_cell[cb]}
        common = sorted(set(a_map) & set(b_map))
        b_disc = sum(b_map[k]["success"] and not a_map[k]["success"]
                     for k in common)
        c_disc = sum(a_map[k]["success"] and not b_map[k]["success"]
                     for k in common)
        diff_by_task: dict[str, list[int]] = {}
        for k in common:
            diff_by_task.setdefault(k[0], []).append(
                int(a_map[k]["success"]) - int(b_map[k]["success"]))
        rd = sum(sum(v) for v in diff_by_task.values()) / len(common)
        p = mcnemar_exact(b_disc, c_disc)
        pvals.append(p)
        # paired overhead (only meaningful for guard-vs-base contrasts)
        d_wall = sum(a_map[k]["wall_s"] - b_map[k]["wall_s"]
                     for k in common) / len(common)
        d_tok = sum((a_map[k]["tok_prompt"] + a_map[k]["tok_eval"])
                    - (b_map[k]["tok_prompt"] + b_map[k]["tok_eval"])
                    for k in common) / len(common)
        out["contrasts"].append({
            "name": name, "cells": f"{ca} vs {cb}", "n_pairs": len(common),
            "risk_difference": round(rd, 4),
            "rd_ci95_cluster_boot": cluster_boot_ci(diff_by_task),
            "discordant_only_" + ca: c_disc, "discordant_only_" + cb: b_disc,
            "mcnemar_p": round(p, 5),
            "delta_wall_s_paired": round(d_wall, 2),
            "delta_tokens_paired": round(d_tok, 1),
        })
    for contrast, p_adj in zip(out["contrasts"], holm(pvals)):
        contrast["mcnemar_p_holm"] = p_adj
    return out


def to_markdown(res: dict, run_name: str) -> str:
    lines = [f"## {run_name}", "", "### Per-cell results", "",
             "| cell | model | cond | n | pass | rate | Wilson95 | pass^1 | "
             "pass^4 | pass^8 | wall s | derived CPU s |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c, v in res["cells"].items():
        lines.append(
            f"| {c} | {v['model']} | {v['condition']} | {v['n']} | "
            f"{v['successes']} | {v['rate']:.3f} | {v['wilson95']} | "
            f"{v.get('pass^1', '')} | {v.get('pass^4', '')} | "
            f"{v.get('pass^8', '')} | {v['mean_wall_s']} | "
            f"{v['derived_cpu_s']} |")
    lines += ["", "### Pre-registered contrasts (paired; Holm-corrected)", "",
              "| contrast | RD | 95% CI (cluster boot) | discordants | "
              "p (McNemar) | p (Holm) | Δwall s | Δtokens |",
              "|---|---|---|---|---|---|---|---|"]
    for ct in res["contrasts"]:
        disc = ", ".join(f"{k.split('_only_')[1]}:{v}" for k, v in ct.items()
                         if k.startswith("discordant_only_"))
        lines.append(
            f"| {ct['name']} | {ct['risk_difference']:+.3f} | "
            f"{ct['rd_ci95_cluster_boot']} | {disc} | {ct['mcnemar_p']} | "
            f"{ct['mcnemar_p_holm']} | {ct['delta_wall_s_paired']:+.2f} | "
            f"{ct['delta_tokens_paired']:+.1f} |")
    lines += ["", "### First-failure distributions", ""]
    for c, v in res["cells"].items():
        lines.append(f"- **{c}** ({v['model']}, {v['condition']}): "
                     + ", ".join(f"{k} {n}" for k, n in
                                 sorted(v["first_failures"].items(),
                                        key=lambda x: -x[1])))
    lines += ["", "### S4 (ambiguity) behavior rates", ""]
    for c, v in res["s4"].items():
        lines.append(f"- {c}: asked {v['asked']}, looked_up {v['looked_up']}, "
                     f"guessed {v['guessed']}")
    lines += ["", "### S5 (fault injection) outcomes", ""]
    for c, v in res["s5"].items():
        lines.append(f"- {c}: fired {v['fault_fired']}/{v['n_s5']}, recovered "
                     f"{v['recovered']}, answered-unrecovered "
                     f"{v['answered_unrecovered']} (refused {v['refused']}, "
                     f"hallucinated {v['hallucinated_answer']})")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", default=["core_v1"])
    args = ap.parse_args()
    tasks = {t["id"]: t for t in yaml.safe_load(
        (ROOT / "tasks" / "tasks.yaml").read_text(encoding="utf-8"))}
    all_results, md = {}, []
    for run in args.runs:
        run_dir = ROOT / "runs" / run
        records = load_episodes(run_dir, tasks)
        contrasts = (CONTRASTS if run.startswith("core")
                     else [("guardrail@1B-Q8", "E1", "E2"),
                           ("guardrail@3B-Q8", "E3", "E4"),
                           ("guardrail@7B-Q4", "E5", "E6")])
        res = analyze_run(records, contrasts)
        all_results[run] = res
        md.append(to_markdown(res, run))
        print(f"{run}: {len(records)} episodes analyzed")
    (ROOT / "analysis" / "results.json").write_text(
        json.dumps(all_results, indent=1), encoding="utf-8")
    (ROOT / "analysis" / "tables.md").write_text(
        "# Analysis tables (generated by analysis/analyze.py)\n\n"
        + "\n".join(md), encoding="utf-8")
    print("wrote analysis/results.json and analysis/tables.md")


if __name__ == "__main__":
    main()
