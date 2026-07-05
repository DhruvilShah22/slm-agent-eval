"""Compare blind hand labels against the programmatic grader/attributor.

Recomputes grade+attribution with the CURRENT code (not the inline values
stored at run time), so this validates whatever grader version analysis will
use. Reports raw agreement and Cohen's kappa for (a) binary success and
(b) first-failure category (with 'success' as its own class), plus a list of
disagreements for reconciliation.
"""

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from grading.attribute import attribute  # noqa: E402
from grading.grade import grade  # noqa: E402


def cohen_kappa(pairs: list[tuple]) -> float:
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def main() -> None:
    tasks = {t["id"]: t for t in yaml.safe_load(
        (ROOT / "tasks" / "tasks.yaml").read_text(encoding="utf-8"))}
    keys = json.loads((ROOT / "analysis" / "labeling" / "sample_keys.json")
                      .read_text(encoding="utf-8"))
    labels = json.loads((ROOT / "analysis" / "labeling" / "labels.json")
                        .read_text(encoding="utf-8"))["labels"]
    by_key = {(l["cell"], l["task"], l["seed"]): l for l in labels}

    succ_pairs, ff_pairs, disagreements = [], [], []
    for k in keys:
        ep = json.loads((ROOT / k["file"]).read_text(encoding="utf-8"))
        task = dict(tasks[k["task"]])
        g = grade(ep, task)
        a = attribute(ep, task, g)
        lab = by_key[(k["cell"], k["task"], k["seed"])]
        auto_ff = a["first_failure"] or "success"
        hum_ff = lab["first_failure"] or "success"
        succ_pairs.append((g["success"], lab["success"]))
        ff_pairs.append((auto_ff, hum_ff))
        if g["success"] != lab["success"] or auto_ff != hum_ff:
            disagreements.append(
                f"{k['cell']}/{k['task']}/s{k['seed']}: auto=({g['success']},"
                f"{auto_ff}) human=({lab['success']},{hum_ff}) "
                f"answer={ep['final_answer']!r:.60}")

    n = len(succ_pairs)
    print(f"n={n}")
    print(f"success: agreement {sum(a == b for a, b in succ_pairs)}/{n} "
          f"= {sum(a == b for a, b in succ_pairs)/n:.3f}, "
          f"kappa = {cohen_kappa(succ_pairs):.3f}")
    print(f"first_failure: agreement {sum(a == b for a, b in ff_pairs)}/{n} "
          f"= {sum(a == b for a, b in ff_pairs)/n:.3f}, "
          f"kappa = {cohen_kappa(ff_pairs):.3f}")
    for d in disagreements:
        print("DISAGREE:", d)


if __name__ == "__main__":
    main()
