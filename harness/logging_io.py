"""Episode logging and run manifests: every number must trace back to these files.

Layout:  runs/<run_id>/manifest.json
         runs/<run_id>/<cell>/<task_id>_s<seed>.json   (one file per episode)

Episode files are written atomically (tmp + replace) and carry
`"completed": true`, so an interrupted run can `--resume` by skipping files
that already exist and are complete — the property that makes Kaggle session
kills harmless.
"""

import hashlib
import json
import os
import platform
import subprocess
import time
from pathlib import Path


def episode_path(run_dir: Path, cell: str, task_id: str, seed: int) -> Path:
    return run_dir / cell / f"{task_id}_s{seed}.json"


def is_completed(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with open(path, encoding="utf-8") as fh:
            return bool(json.load(fh).get("completed"))
    except (json.JSONDecodeError, OSError):
        return False  # partial/corrupt file -> redo


def write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, cwd=Path(__file__).resolve().parent.parent)
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def write_manifest(run_dir: Path, config: dict, model_infos: list[dict]) -> None:
    config_hash = hashlib.sha256(
        json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]
    write_atomic(run_dir / "manifest.json", {
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": _git_commit(),
        "config_sha256_16": config_hash,
        "config": config,
        "models": model_infos,
        "platform": {"python": platform.python_version(),
                     "system": platform.platform()},
    })
