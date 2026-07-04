"""Kaggle pilot run (design §10 pilot gate): 6 cells x 5 tasks (one per slice)
x 2 seeds = 60 episodes on the free GPU.

Purpose: (1) replace episode-time estimates with cloud measurements,
(2) difficulty gate (base success within 20-80%?), (3) produce diverse
trajectories for hand-label validation of the failure-attribution classifier.
Outputs land in /kaggle/working/runs/ (kernel output artifact).
"""

import json
import subprocess
import time
import urllib.request

REPO = "https://github.com/DhruvilShah22/slm-agent-eval.git"
WORK = "/kaggle/working"
MODELS = ["qwen2.5:1.5b-instruct-q4_K_M",
          "qwen2.5:1.5b-instruct-q8_0",
          "qwen2.5:3b-instruct-q4_K_M"]
PILOT_TASKS = "t02,t06,t14,t18,t22"   # one task per slice S1..S5
PILOT_SEEDS = "1,2"


def sh(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    print("+", cmd, flush=True)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.stdout:
        print(r.stdout[-4000:], flush=True)
    if r.stderr:
        print("STDERR:", r.stderr[-1500:], flush=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"command failed ({r.returncode}): {cmd}")
    return r


def main() -> None:
    sh("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader")
    sh("apt-get install -y -qq zstd || "
       "(apt-get update -qq && apt-get install -y -qq zstd)")
    sh("curl -fsSL https://ollama.com/install.sh | sh")
    subprocess.Popen(["ollama", "serve"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            urllib.request.urlopen("http://localhost:11434/api/version",
                                   timeout=5)
            break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError("ollama serve did not come up")

    sh(f"git clone --depth 1 {REPO} {WORK}/repo")
    sh("python -c \"import yaml, requests\"")  # both ship in Kaggle's image
    for m in MODELS:
        sh(f"ollama pull {m}")

    sh(f"cd {WORK}/repo && python -m grading.check_tasks")
    t0 = time.time()
    sh(f"cd {WORK}/repo && python run.py --config configs/core.yaml "
       f"--tasks {PILOT_TASKS} --seeds {PILOT_SEEDS} --out {WORK}/runs")
    mins = (time.time() - t0) / 60

    # Compact summary for quick reading from the kernel log.
    summary: dict = {"pilot_wall_min": round(mins, 1), "cells": {}}
    import pathlib
    for cell_dir in sorted(pathlib.Path(f"{WORK}/runs/core_v1").iterdir()):
        if not cell_dir.is_dir():
            continue
        eps = [json.loads(p.read_text(encoding="utf-8"))
               for p in cell_dir.glob("*.json")]
        summary["cells"][cell_dir.name] = {
            "n": len(eps),
            "pass": sum(e["grade"]["success"] for e in eps),
            "mean_wall_s": round(sum(e["wall_s"] for e in eps) / max(len(eps), 1), 1),
            "first_failures": sorted(
                {str(e["attribution"].get("first_failure")) for e in eps}),
        }
    print("PILOT SUMMARY:", json.dumps(summary, indent=1), flush=True)
    with open(f"{WORK}/pilot_summary.json", "w") as fh:
        json.dump(summary, fh, indent=1)


if __name__ == "__main__":
    main()
