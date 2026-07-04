"""Kaggle extension-matrix run (design §9 extensions): E1–E6 = llama3.2-1b Q8,
qwen2.5-3b Q8, qwen2.5-7b Q4, each baseline/guardrail. 1,200 episodes.
Identical skeleton to the core kernel; different config + models.
"""

import json
import subprocess
import time
import urllib.request

REPO = "https://github.com/DhruvilShah22/slm-agent-eval.git"
WORK = "/kaggle/working"
MODELS = ["llama3.2:1b",
          "qwen2.5:3b-instruct-q8_0",
          "qwen2.5:7b-instruct-q4_K_M"]


def sh(cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    print("+", cmd, flush=True)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.stdout:
        print(r.stdout[-6000:], flush=True)
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
    sh("cd " + WORK + "/repo && git rev-parse HEAD")
    for m in MODELS:
        sh(f"ollama pull {m}")
    sh(f"cd {WORK}/repo && python -m grading.check_tasks")

    t0 = time.time()
    sh(f"cd {WORK}/repo && python run.py --config configs/extensions.yaml "
       f"--out {WORK}/runs")
    mins = (time.time() - t0) / 60

    summary: dict = {"ext_wall_min": round(mins, 1), "cells": {}}
    import pathlib
    for cell_dir in sorted(pathlib.Path(f"{WORK}/runs/ext_v1").iterdir()):
        if not cell_dir.is_dir():
            continue
        eps = [json.loads(p.read_text(encoding="utf-8"))
               for p in cell_dir.glob("*.json")]
        ff: dict = {}
        for e in eps:
            key = str(e["attribution"].get("first_failure"))
            ff[key] = ff.get(key, 0) + 1
        summary["cells"][cell_dir.name] = {
            "n": len(eps),
            "pass": sum(e["grade"]["success"] for e in eps),
            "mean_wall_s": round(sum(e["wall_s"] for e in eps) / max(len(eps), 1), 1),
            "first_failures": dict(sorted(ff.items())),
        }
    print("EXT SUMMARY:", json.dumps(summary, indent=1), flush=True)
    with open(f"{WORK}/ext_summary.json", "w") as fh:
        json.dump(summary, fh, indent=1)


if __name__ == "__main__":
    main()
