"""run_python tool — short Python snippets in an isolated subprocess.

Isolation is best-effort (documented in the paper's limitations): `-I` isolated
mode, temp working dir, 5 s timeout, output truncation. Tasks only require
simple string/date/arithmetic computation; no network or filesystem use.
"""

import subprocess
import sys
import tempfile

TIMEOUT_S = 5
MAX_OUT = 2000

SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_python",
        "description": "Execute a short Python 3 snippet and return its stdout. "
                       "Use print() to output results. 5-second time limit; "
                       "no network access.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string",
                         "description": "Python source code to execute"},
            },
            "required": ["code"],
        },
    },
}


def run(code: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-c", str(code)],
                capture_output=True, text=True, timeout=TIMEOUT_S, cwd=tmp,
            )
        except subprocess.TimeoutExpired:
            return {"error": f"execution timed out after {TIMEOUT_S}s"}
    out = {"stdout": proc.stdout[:MAX_OUT]}
    if proc.returncode != 0:
        out["error"] = (proc.stderr or "nonzero exit")[-MAX_OUT:]
    return out
