"""Task-suite integrity checker: resolves every gold against the generated
world and asserts authoring-time assumptions. Run after ANY change to
tasks.yaml or data/generate.py:  python -m grading.check_tasks
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from grading import gold as goldmod  # noqa: E402
from tools import REGISTRY  # noqa: E402

EXPECTED_SLICES = {"S1": 5, "S2": 8, "S3": 4, "S4": 4, "S5": 4}


def main() -> int:
    tasks = yaml.safe_load(
        (Path(__file__).resolve().parent.parent / "tasks" / "tasks.yaml")
        .read_text(encoding="utf-8"))
    problems = []
    counts: dict[str, int] = {}
    ids = set()
    for t in tasks:
        counts[t["slice"]] = counts.get(t["slice"], 0) + 1
        if t["id"] in ids:
            problems.append(f"duplicate id {t['id']}")
        ids.add(t["id"])
        for tool in t.get("allowed_tools", []) + t.get("required_tools", []):
            if tool not in REGISTRY:
                problems.append(f"{t['id']}: unknown tool '{tool}'")
        if t.get("fault") and t["fault"]["tool"] not in REGISTRY:
            problems.append(f"{t['id']}: fault on unknown tool")
        try:
            for asked in ((False, True) if t["gold"].get("fn") == "conditional"
                          else (False,)):
                value, gtype, _ = goldmod.resolve(t["gold"], asked)
                print(f"{t['id']} [{t['slice']}] gold"
                      f"{'(asked)' if asked else ''} = {value!r} ({gtype})")
        except Exception as exc:
            problems.append(f"{t['id']}: gold resolution failed: {exc!r}")

    # Authoring-time assumptions that keep golds unambiguous:
    if goldmod.order_subtotal("ORD-1002") <= goldmod.fact("bulk_discount.subtotal_threshold"):
        problems.append("t07: ORD-1002 subtotal must exceed bulk threshold")
    if goldmod.order_subtotal("ORD-1016") > goldmod.fact("bulk_discount.subtotal_threshold"):
        problems.append("t09: ORD-1016 subtotal must be below bulk threshold "
                        "(otherwise total is ambiguous)")
    if counts != EXPECTED_SLICES:
        problems.append(f"slice counts {counts} != {EXPECTED_SLICES}")
    if len(tasks) != 25:
        problems.append(f"expected 25 tasks, found {len(tasks)}")

    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print(" -", p)
        return 1
    print(f"\nOK: {len(tasks)} tasks, all golds resolve, slices {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
