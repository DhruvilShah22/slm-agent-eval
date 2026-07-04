"""Experiment runner CLI.

  python run.py --config configs/core.yaml [--cells C1,C2] [--tasks t01,t02]
                [--seeds 1,2] [--limit N] [--out runs] [--no-resume] [--dry]

Iterates cells x tasks x seeds sequentially. Each episode is graded and
attributed inline and written atomically to its own JSON file; completed
episodes are skipped on re-run (resume-by-default), so interrupted sessions
(Kaggle kills, laptop sleep) lose at most the in-flight episode.
"""

import argparse
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from grading.attribute import attribute  # noqa: E402
from grading.grade import grade  # noqa: E402
from harness import logging_io  # noqa: E402
from harness.agent import run_episode  # noqa: E402
from harness.ollama_client import OllamaClient  # noqa: E402


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--cells", default=None, help="comma-separated cell names")
    ap.add_argument("--tasks", default=None, help="comma-separated task ids")
    ap.add_argument("--seeds", default=None, help="comma-separated seeds")
    ap.add_argument("--limit", type=int, default=None,
                    help="stop after N new episodes (for pilots)")
    ap.add_argument("--out", default="runs")
    ap.add_argument("--no-resume", action="store_true",
                    help="re-run episodes even if completed logs exist")
    ap.add_argument("--dry", action="store_true", help="print plan and exit")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parent
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    tasks = yaml.safe_load((root / "tasks" / "tasks.yaml").read_text(encoding="utf-8"))

    cells = {name: {"name": name, **spec} for name, spec in cfg["cells"].items()}
    if args.cells:
        cells = {k: v for k, v in cells.items() if k in args.cells.split(",")}
    if args.tasks:
        wanted = args.tasks.split(",")
        tasks = [t for t in tasks if t["id"] in wanted]
    seeds = ([int(s) for s in args.seeds.split(",")] if args.seeds
             else cfg["seeds"])

    run_dir = root / args.out / cfg["run_id"]
    plan = [(c, t, s) for c in cells.values() for t in tasks for s in seeds]
    todo = [(c, t, s) for c, t, s in plan if args.no_resume or
            not logging_io.is_completed(
                logging_io.episode_path(run_dir, c["name"], t["id"], s))]
    print(f"plan: {len(plan)} episodes | already done: {len(plan) - len(todo)} "
          f"| to run: {len(todo)}" + (f" (limit {args.limit})" if args.limit else ""))
    if args.dry:
        return 0

    client = OllamaClient(cfg["ollama_url"])
    model_infos = []
    for name in sorted({c["model"] for c in cells.values()}):
        try:
            model_infos.append(client.show(name))
        except Exception as exc:
            print(f"FATAL: cannot inspect model '{name}': {exc}")
            return 1
    logging_io.write_manifest(run_dir, cfg, model_infos)

    done = succ = 0
    t_start = time.time()
    for cell, task, seed in todo:
        if args.limit is not None and done >= args.limit:
            break
        task = dict(task)
        task["_seed"] = seed
        ep = run_episode(task, cell, cfg, client)
        g = grade(ep, task)
        ep["grade"] = g
        ep["attribution"] = attribute(ep, task, g)
        ep["completed"] = True
        logging_io.write_atomic(
            logging_io.episode_path(run_dir, cell["name"], task["id"], seed), ep)
        done += 1
        succ += int(g["success"])
        print(f"[{done}] {cell['name']} {task['id']} s{seed} "
              f"{'PASS' if g['success'] else 'fail'} "
              f"({ep['wall_s']}s, {ep['turns']} turns, "
              f"ff={ep['attribution'].get('first_failure')})", flush=True)
    mins = (time.time() - t_start) / 60
    print(f"ran {done} episodes in {mins:.1f} min | pass {succ}/{done}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
