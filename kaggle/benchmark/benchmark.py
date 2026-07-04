"""Kaggle GPU timing benchmark for slm-agent-eval — Phase 1 pilot gate, part 1.

Verifies on Kaggle's free GPU:
  1. GPU availability (fails loudly if phone verification / accelerator is off)
  2. Ollama + GGUF models work with CUDA offload
  3. Native tool-calling works through Ollama's /api/chat
  4. Measured prefill/decode throughput for every candidate model/quant

Output: /kaggle/working/benchmark_results.json (kernel output artifact) and a
printed summary. Every number in the project traces to artifacts like this.
"""

import json
import subprocess
import time
import urllib.request

RESULTS = {"env": {}, "models": {}, "tool_call_check": {}}
OLLAMA_URL = "http://localhost:11434"

# Candidate models (Phase 1 design §3): core cells + extension candidates.
MODELS = [
    "qwen2.5:1.5b-instruct-q4_K_M",
    "qwen2.5:1.5b-instruct-q8_0",
    "qwen2.5:3b-instruct-q4_K_M",
    "qwen2.5:3b-instruct-q8_0",
    "qwen2.5:7b-instruct-q4_K_M",
    "llama3.2:1b",
]

# Same long-prompt construction as the Phase 0 laptop benchmark (NOTES.md),
# so cloud and laptop numbers are directly comparable.
LONG_PROMPT = " ".join(
    ["The quick brown fox jumps over the lazy dog near the riverbank "
     "in the early morning light."] * 120
)

WEATHER_TOOL = {
    "type": "function",
    "function": {
        "name": "get_current_weather",
        "description": "Get the current weather for a location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name"},
                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
            },
            "required": ["location"],
        },
    },
}


def sh(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def api(path: str, payload: dict, timeout: int = 1800) -> dict:
    req = urllib.request.Request(
        OLLAMA_URL + path,
        json.dumps(payload).encode(),
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def timing_fields(resp: dict) -> dict:
    out = {k: resp.get(k) for k in (
        "prompt_eval_count", "prompt_eval_duration",
        "eval_count", "eval_duration", "total_duration", "load_duration",
    )}
    if resp.get("prompt_eval_duration"):
        out["prefill_tps"] = round(
            resp["prompt_eval_count"] / (resp["prompt_eval_duration"] / 1e9), 2)
    if resp.get("eval_duration"):
        out["decode_tps"] = round(
            resp["eval_count"] / (resp["eval_duration"] / 1e9), 2)
    return out


def main() -> None:
    # --- 1. Environment ---------------------------------------------------
    gpu = sh("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader")
    RESULTS["env"]["gpu"] = (gpu.stdout or gpu.stderr).strip()
    print("GPU:", RESULTS["env"]["gpu"], flush=True)
    if gpu.returncode != 0 or not gpu.stdout.strip():
        print("FATAL: no GPU visible. Check the kernel's accelerator setting "
              "and that the Kaggle account is phone-verified.", flush=True)

    # --- 2. Ollama install + serve ----------------------------------------
    # Kaggle's image lacks zstd, which the Ollama installer requires.
    dep = sh("apt-get install -y -qq zstd || "
             "(apt-get update -qq && apt-get install -y -qq zstd)")
    print("zstd install rc:", dep.returncode, flush=True)
    inst = sh("curl -fsSL https://ollama.com/install.sh | sh")
    print("ollama install tail:", inst.stdout[-300:], inst.stderr[-300:], flush=True)
    if sh("which ollama").returncode != 0:
        raise RuntimeError("ollama binary not found after install — see log above")
    subprocess.Popen(["ollama", "serve"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            with urllib.request.urlopen(OLLAMA_URL + "/api/version", timeout=5) as v:
                RESULTS["env"]["ollama_version"] = json.loads(v.read())
                break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError("ollama serve did not come up within 120 s")
    print("ollama:", RESULTS["env"]["ollama_version"], flush=True)

    # --- 3. Per-model pull + timed inference ------------------------------
    for model in MODELS:
        entry: dict = {}
        t0 = time.time()
        pull = sh(f"ollama pull {model}")
        entry["pull_s"] = round(time.time() - t0, 1)
        entry["pull_ok"] = pull.returncode == 0
        if not entry["pull_ok"]:
            entry["pull_err"] = (pull.stderr or pull.stdout)[-300:]
            RESULTS["models"][model] = entry
            print(model, "PULL FAILED", flush=True)
            continue

        for label, prompt, max_tokens in (
            ("short", "Explain in two sentences why the sky is blue.", 128),
            ("long", LONG_PROMPT + "\nReply with just the word OK.", 8),
        ):
            try:
                resp = api("/api/generate", {
                    "model": model, "prompt": prompt, "stream": False,
                    "options": {"num_predict": max_tokens,
                                "seed": 1, "temperature": 0.7},
                })
                entry[label] = timing_fields(resp)
            except Exception as exc:  # keep benchmarking remaining models
                entry[label] = {"error": repr(exc)[:300]}
        RESULTS["models"][model] = entry
        print(model, json.dumps(entry), flush=True)
        sh(f"ollama stop {model}")

    # --- 4. Tool-call sanity check (native /api/chat tools) ---------------
    try:
        resp = api("/api/chat", {
            "model": MODELS[0], "stream": False,
            "messages": [{"role": "user",
                          "content": "What is the weather in Toronto right now,"
                                     " in celsius?"}],
            "tools": [WEATHER_TOOL],
        })
        RESULTS["tool_call_check"] = {
            "model": MODELS[0],
            "tool_calls": resp.get("message", {}).get("tool_calls",
                                                      "NONE EMITTED"),
        }
    except Exception as exc:
        RESULTS["tool_call_check"] = {"error": repr(exc)[:300]}

    # --- 5. Persist --------------------------------------------------------
    with open("/kaggle/working/benchmark_results.json", "w") as fh:
        json.dump(RESULTS, fh, indent=2)
    print("=== SUMMARY ===", flush=True)
    print(json.dumps(RESULTS, indent=2), flush=True)


if __name__ == "__main__":
    main()
