"""Blind-labeling sampler (design §6 validation, protocol per NOTES.md).

Draws a deterministic stratified sample of core-matrix episodes — one per
slice per cell plus two extra per cell (7 x 6 = 42) — and writes:

  analysis/labeling/blind_sample.md   trajectories WITHOUT grades/attribution
  analysis/labeling/sample_keys.json  which episodes were drawn

A human labeler reads blind_sample.md and fills labels.json with, per episode:
  success: true/false   and   first_failure: <category or null>
compare_labels.py then computes Cohen's kappa against the classifier.
"""

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs" / "core_v1"
OUT = ROOT / "analysis" / "labeling"
SEED = 7
SLICES = ["S1", "S2", "S3", "S4", "S5"]
EXTRA_PER_CELL = 2
RESULT_TRUNC = 400


def blind_view(ep: dict, gold) -> str:
    lines = [f"### {ep['cell']} / {ep['task_id']} / seed {ep['seed']} "
             f"({ep['slice']}, {ep['condition']})"]
    for e in ep["events"]:
        if e["type"] == "model_call" and e.get("content"):
            lines.append(f"- assistant text: {e['content'][:300]!r}")
        elif e["type"] == "tool_call":
            fault = f" [INJECTED FAULT: {e['fault_mode']}]" if e["fault_mode"] else ""
            blocked = " [call NOT executed]" if e["blocked"] else ""
            lines.append(f"- tool {e['name']}({json.dumps(e['args'])[:200]})"
                         f"{fault}{blocked} -> "
                         f"{json.dumps(e['result'])[:RESULT_TRUNC]}")
        elif e["type"] == "clarification":
            lines.append(f"- [scripted user clarification: {e['reply']!r}]")
        elif e["type"] == "nudge":
            lines.append("- [harness nudge sent]")
    lines.append(f"- FINAL ANSWER: {ep['final_answer']!r}")
    lines.append(f"- max_turns_hit: {ep['hit_max_turns']}")
    lines.append(f"- GOLD (for success judgment): {gold!r}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    import sys
    sys.path.insert(0, str(ROOT))
    import yaml
    from grading import gold as goldmod

    tasks = {t["id"]: t for t in yaml.safe_load(
        (ROOT / "tasks" / "tasks.yaml").read_text(encoding="utf-8"))}
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    keys, views = [], []

    for cell_dir in sorted(p for p in RUNS.iterdir() if p.is_dir()):
        files = sorted(cell_dir.glob("*.json"))
        by_slice: dict[str, list[Path]] = {s: [] for s in SLICES}
        for f in files:
            ep = json.loads(f.read_text(encoding="utf-8"))
            by_slice[ep["slice"]].append(f)
        chosen: list[Path] = [rng.choice(by_slice[s]) for s in SLICES if by_slice[s]]
        rest = [f for f in files if f not in chosen]
        chosen += rng.sample(rest, EXTRA_PER_CELL)
        for f in chosen:
            ep = json.loads(f.read_text(encoding="utf-8"))
            gold_value, _, _ = goldmod.resolve(
                tasks[ep["task_id"]]["gold"], ep.get("asked_clarification", False))
            keys.append({"cell": ep["cell"], "task": ep["task_id"],
                         "seed": ep["seed"], "file": str(f.relative_to(ROOT))})
            views.append(blind_view(ep, gold_value))

    (OUT / "sample_keys.json").write_text(json.dumps(keys, indent=1),
                                          encoding="utf-8")
    (OUT / "blind_sample.md").write_text(
        "# Blind labeling sample (no classifier output shown)\n\n"
        "Label each episode: success true/false (does FINAL ANSWER match GOLD"
        " under reasonable reading?) and first_failure category\n"
        "(no_tool_call | wrong_tool | malformed_args | bad_arg_values |"
        " ignored_tool_error | synthesis_error | max_turns | null-if-success).\n\n"
        + "\n".join(views), encoding="utf-8")
    print(f"sampled {len(keys)} episodes -> {OUT / 'blind_sample.md'}")


if __name__ == "__main__":
    main()
