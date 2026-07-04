# Phase 1 — Design Document (for approval)

Date: 2026-07-04
Approved framing: **RQ1 + quantization axis, 1–3B model class** (user, this session).
Status: awaiting user approval before any Phase 2 code.

---

## 1. Closest prior work and positioning (written first, per instruction)

### 1.1 Self-Healing Agentic Orchestrators (arXiv:2606.01416) — closest on mitigation
Presents an orchestration framework treating reliability as a bounded runtime
control problem: failure signals → categories → budgeted recovery → validation.
On a 100-task fault-injection benchmark: 98.8% success vs 94.5% (retry-only)
and 93.8% (replanning); verifier-enabled healing eliminated silent failures.

**Verified limitations that define our gap** (from the paper itself): the live
model used is *never named* ("a live tool-calling model"), with no size,
provider, or quantization stated; results are aggregate percentages with **no
pass^k and no confidence intervals**; latency is a **call-count proxy**
("CostProxy = Ntool + Nmodel + Nverify"), not wall-clock; the authors state
that in deployment verifier cost "would depend on the model, prompt length,
evidence context, tool latency, and verifier implementation."

**Our positioning:** complementary measurement study. Where they contribute a
*mechanism* evaluated under controlled abstraction, we contribute *evidence*:
named, fully reproducible open-weight 1–3B models at explicit quantization
levels on commodity CPU hardware; repeated-trial reliability (pass^k) with
confidence intervals and paired significance tests; real wall-clock and
token-count overhead for the mitigation; and per-step failure attribution.
Our guardrail is deliberately the *simplest deterministic instance* of their
recovery family (schema validation + typed error feedback + bounded retry) —
quantifying how much the cheapest rung of that ladder buys on the smallest
viable models.

### 1.2 τ-bench (arXiv:2406.12045) — closest on reliability methodology
Introduced pass^k over repeated trials; found frontier API models inconsistent
(GPT-4o <50% success, pass^8 <25% retail). We adopt pass^k as our headline
reliability metric but change the object of study: small local open-weight
models under quantization, with failure-mode attribution and a mitigation
experiment, none of which τ-bench attempts. We do not reuse τ-bench's domains
(its user simulator is a frontier LLM — incompatible with the zero-paid-API
constraint); our user interaction is a scripted, deterministic clarifier.

### 1.3 BFCL v3/v4 (OpenReview 2GmDdhBdDk) — closest on tool-call grading
Defines the de-facto standard for function-call correctness grading (AST/
state-based checks, multi-turn, missing-parameter and long-context subsets)
and covers open models on a leaderboard. We adopt its schema-validity grading
philosophy but differ in aims: BFCL ranks models by single-score accuracy;
we measure *within-model reliability across repeated trials*, decompose
failures by pipeline stage, and test an inference-time mitigation with
statistics. BFCL reports no pass^k, no mitigation, no quantization axis.

### 1.4 Secondary positioning
- **ACBench (arXiv:2505.19433):** compression × agentic ability, but GPTQ/AWQ
  on static benchmarks, single-shot; we study the GGUF k-quants (Q4_K_M/Q8_0)
  actually shipped by Ollama, in a live agent loop, with repeated trials.
- **TinyLLM (arXiv:2511.22138):** SLM function calling on BFCL; improves via
  fine-tuning/DPO (training-side). Our mitigation is inference-time and
  model-free; our contribution is measurement, not training.
- **ToolMaze (arXiv:2606.05806), AgentCE-Bench (arXiv:2604.06111), PALADIN
  (arXiv:2509.25238):** tool-fault robustness; we reuse the *idea* of
  controlled fault injection as one task slice, cited accordingly.
- **MAST (arXiv:2503.13657):** failure taxonomy for multi-agent systems; ours
  is a single-agent, pipeline-stage taxonomy, programmatically assignable.
- **NVIDIA SLM position paper (arXiv:2506.02153):** argues SLMs are the future
  of agentic AI on economic grounds; we supply reliability measurements that
  test the operational side of that argument.

**Positioning sentence for the paper:** "Prior work contributes recovery
mechanisms (self-healing orchestrators), reliability metrics on frontier APIs
(τ-bench), and single-shot function-call leaderboards (BFCL); we contribute
the missing measurement: how reliably do the small open-weight models anyone
can run for free actually execute multi-step tool tasks, why do they fail,
and how much does the cheapest deterministic guardrail recover, at what
measured latency cost, as a function of quantization."

## 2. Research question and pre-registered hypotheses

**RQ:** How reliably do 1–3B open-weight models execute multi-step tool-use
tasks (pass^k over seeded repeated trials); where in the pipeline do failures
occur; how much of the gap does a deterministic verification-and-retry
guardrail close, at what latency cost; and how does quantization (Q4_K_M vs
Q8_0) modulate all of the above?

Pre-registered hypotheses (falsifiable; negative results reported as such):
- **H1:** pass^8 is substantially below pass^1 for all cells (unreliability is
  the norm, echoing τ-bench at frontier scale).
- **H2:** The guardrail improves success rate, concentrated on
  malformed-argument failures; it does not repair wrong-tool-selection.
- **H3:** Q4_K_M underperforms Q8_0 on tool-call validity at equal model size
  (per ACBench's instruction-following sensitivity), with the gap larger at
  1.5B than 3B.
- **H4:** Guardrail latency overhead is modest (<15% median episode time) in
  success cases and concentrated in failure-recovery episodes.

## 3. Agent architecture

- **Language/runtime:** Python 3.11+, Windows. No agent framework (no
  LangChain/LangGraph) — a hand-rolled ReAct-style loop (~200 lines) for full
  control of prompts, logging, and determinism. Direct HTTP to Ollama
  `POST /api/chat` with native `tools` support (verified working this session).
- **Loop:** system prompt (role, tool-use policy) → user task → iterate:
  model responds with tool_calls → harness executes tool → append tool result
  → repeat until final answer or `max_turns=10`.
- **Sampling:** temperature 0.7, top_p 0.9, `seed ∈ {1..8}` per task, all
  passed via Ollama options and logged. `num_ctx=4096` fixed (measured
  contexts stay ≤3k). One model loaded at a time; `keep_alive` pinned for a
  cell; model digest recorded via `ollama show`.
- **Models (Ollama tags, verified to exist):**
  - `qwen2.5:1.5b-instruct-q4_K_M` (986 MB, pulled)
  - `qwen2.5:1.5b-instruct-q8_0` (1.6 GB, to pull)
  - `qwen2.5:3b-instruct-q4_K_M` (1.9 GB, pulled)
  - `llama3.2:1b` = Q8_0 (1.3 GB, pulled) — cross-family replicate (extension)
  - `qwen2.5:3b-instruct-q8_0` (3.3 GB, to pull) — completes factorial (extension)

## 4. Tool suite (5 tools; all local, deterministic, seeded)

| Tool | Signature (JSON schema) | Implementation |
|---|---|---|
| `calculator` | `expr: string` | AST-whitelisted arithmetic evaluator (no eval()) |
| `search_docs` | `query: string, top_k?: int` | Hand-rolled BM25 (~40 lines) over a synthetic corpus of ~80 short documents (fictional company wiki), generated by a seeded script and shipped in-repo |
| `get_order` | `order_id: string` | SQLite lookup, seeded synthetic DB (orders/products/customers) |
| `find_products` | `category: string, max_price?: number, in_stock?: bool` | SQLite parameterized query |
| `run_python` | `code: string` | Subprocess with 5 s timeout, no network, temp CWD; tasks need only simple string/date/aggregation computation. Best-effort isolation, documented |

Determinism: identical (task, tool call) → identical observation, always.
All entities are synthetic/fictional so answers cannot come from parametric
memory — a no-tool answer is detectably ungrounded.

## 5. Task suite (25 tasks × 8 seeds per cell)

Hand-authored task specs (YAML): prompt, gold answer + normalizer, allowed
gold tool-plan constraints (acceptable tool-name sequences as a small DAG),
slice tags, scripted clarifier text where applicable.

| Slice | n | Probes |
|---|---|---|
| S1 single-tool | 5 | baseline competence |
| S2 multi-tool chained (2–4 calls, output feeds input) | 8 | planning, argument construction |
| S3 distractor (plausible-but-wrong tool available) | 4 | tool selection |
| S4 ambiguous/underspecified (needed parameter absent; recoverable via `search_docs` or by asking — harness returns a *scripted* clarification if asked) | 4 | guess vs. look-up vs. ask |
| S5 fault-injection (first call to a designated tool returns a controlled fault: error string / empty result / timeout message; retry succeeds) | 4 | error recovery, hallucinated success |

Long-context degradation is *not* a designed axis (that was RQ3); trajectory
length is logged and analyzed observationally only.

## 6. Grading and failure attribution (fully programmatic — no LLM judge)

- **Success:** normalized exact match of final answer against gold (numeric
  tolerance / case-and-whitespace folding / set equality as declared per task).
- **First-failure attribution**, deterministic rules over the logged trajectory
  + gold metadata, applied in pipeline order:
  1. `no_tool_call` — final answer with zero tool calls
  2. `wrong_tool` — call outside the task's allowed tool DAG
  3. `malformed_args` — schema violation (unknown key, missing required, type/enum error)
  4. `bad_arg_values` — schema-valid but wrong content (e.g., nonexistent order_id)
  5. `ignored_tool_error` — proceeded to answer after fault without any retry/alternative (S5)
  6. `synthesis_error` — all calls valid and sufficient, final answer wrong
  7. `max_turns` — budget exhausted
  Plus S4 behavior codes: `asked_clarification` / `looked_up` / `guessed`.
- **Validation:** before running the matrix, the classifier is checked against
  ~40 hand-labeled pilot trajectories; agreement (Cohen's κ) reported in the
  paper. Disagreements → rule fixes, re-validated. (Satisfies the brief's
  grader-validation requirement without any model-as-judge.)

## 7. Guardrail (the mitigation under test)

Deterministic, model-free, wraps the same agent loop:
1. **Schema gate:** every tool_call validated against JSON schema before
   execution. On violation → tool result is a *typed* error naming the exact
   violation ("unknown argument 'city'; expected 'location' (string, required)")
   → model retries; max 2 schema retries per step.
2. **Fault feedback:** on tool execution error, structured error object
   (`error_type`, `message`, `retriable: true/false`) instead of a bare string.
3. **Budget:** guardrail may add at most 4 extra model calls per episode
   (logged), so latency overhead is bounded and attributable.
Baseline condition: same loop, no schema gate (invalid calls go to the tool,
which errors naturally), bare-string errors.

## 8. Metrics

Per cell: success rate (Wilson 95% CI); pass^k for k ∈ {1,2,4,8} (unbiased
estimator over 8 seeds); tool-call schema-validity rate per step;
first-failure distribution; S5 recovery rate + hallucinated-success rate;
S4 asked/looked-up/guessed rates; episode wall-clock, model token counts
(prompt/eval from Ollama), retry counts. Guardrail overhead = paired Δ
wall-clock and Δ tokens.

## 9. Experiment matrix and statistics

**Core (must-run): 6 cells × 25 tasks × 8 seeds = 1,200 episodes**
| Cell | Model | Quant | Condition |
|---|---|---|---|
| C1/C2 | qwen2.5-1.5b | Q4_K_M | baseline / guardrail |
| C3/C4 | qwen2.5-1.5b | Q8_0 | baseline / guardrail |
| C5/C6 | qwen2.5-3b | Q4_K_M | baseline / guardrail |

**Extension (optional, after core results): up to 6 cells = +800–1,200 episodes**
| E1/E2 | llama3.2-1b | Q8_0 | baseline / guardrail | (family generality) |
| E3/E4 | qwen2.5-3b | Q8_0 | baseline / guardrail | (completes size×quant factorial) |
| E5/E6 | qwen2.5-7b | Q4_K_M | baseline / guardrail | (extends size axis; GPU-only — measured out on laptop) |

**Pre-registered primary contrasts** (Holm-corrected family):
1. guardrail vs baseline within each model×quant (McNemar exact test on
   paired (task, seed) outcomes; effect = risk difference with cluster
   bootstrap CI, clustered by task);
2. Q8 vs Q4 at 1.5B (paired by task,seed);
3. 3B-Q4 vs 1.5B-Q4 (paired by task,seed).
Everything else (slice-level patterns, failure-mode shifts, latency) is
reported as descriptive/secondary with CIs, labeled exploratory.

Power note: 200 paired episodes per contrast; McNemar detects ~8–10 pp
success-rate differences at α=0.05 with reasonable power given expected
discordance; CIs reported regardless — including for null results.

## 10. Execution infrastructure and runtime (amended per user requirements:
fastest completion, free tools only, device may be off / offline)

**Primary compute: Kaggle background runs ("Save & Run All").** Verified this
session: committed notebook runs execute server-side and continue after the
browser is closed or the device powers off; interactive-session idle timers do
not apply. Free quota ≈ 30 GPU-hours/week (P100 or 2×T4), 12 h/session,
predictable. The same GGUF models run via Ollama (or llama.cpp) with CUDA
offload inside the notebook. Episode logs are checkpointed to a Kaggle Dataset
per episode, so a killed session resumes losslessly; the user's wifi is needed
only to *launch* a run and *collect* results.

**Source of truth: a GitHub repository** (free). All code, task specs, configs,
and collected run logs are committed; the Kaggle notebook clones the repo and
pins a commit hash in every run manifest.

**Reproduction CI: GitHub Actions** (verified free on public repos; 6 h/job,
20 concurrent): one workflow regenerates every table and figure from the
committed logs on each push — the "every number traces to an artifact"
guarantee, mechanized. Actions is used for analysis/verification CI only, not
bulk inference (keeps us comfortably within GitHub's acceptable-use intent).

**Runtime (T4-class GPU, estimates — mandatory cloud timing benchmark before
the matrix, same discipline as Phase 0):**
| Block | Episodes | Est. GPU time |
|---|---|---|
| Cloud timing benchmark + pilot (10 eps/cell) | ~60 | ~1–2 h |
| Core matrix C1–C6 | 1,200 | **~5–10 h** |
| Extensions E1–E4 (+ E5/E6: qwen2.5-7b Q4, now GPU-feasible) | 800–1,200 | ~6–10 h |

Everything fits inside one week's free quota. **Laptop fallback retained:**
the identical harness runs against local Ollama (core ≈ 105 h, measured basis)
if free quotas are throttled — quotas are not contractual.

**Consumer-CPU latency reporting (framing preserved):** guardrail overhead is
measured primarily in tokens and extra model calls (hardware-independent),
converted to consumer-CPU wall-clock using Phase 0's measured tok/s rates and
labeled *derived*; an optional one-night local confirmation run (1 reduced
cell pair) can make it *measured* if desired.

**Pilot gate (unchanged in spirit):** 10 episodes/cell on Kaggle replace all
estimates with measurements before the full matrix; >30% overrun → rescale
(seeds 8→6 or tasks 25→20), logged in NOTES.md. Difficulty gate: base success
outside 20–80% band → one task-suite adjustment, logged, before the matrix.

## 11. Reproducibility and logging

- Every model call: full request (messages, tools, options incl. seed), full
  response, Ollama timing fields → JSONL, one file per episode; run manifest
  with config hash, model digests, package versions, machine fingerprint.
- Config-driven (YAML) cells; `--resume` skips completed episodes.
- Seeded generation of corpus/DB; `requirements.txt` pinned; README with exact
  repro steps incl. `ollama pull` commands and expected runtimes.
- Every number in the final report generated by `analysis/` scripts directly
  from logs; tables/plots regenerable with one command.

## 12. Risks and out-of-scope

- **Risk:** guardrail helps less than expected → reported as a negative result
  with CIs (H2 falsified is still a finding).
- **Risk:** Q8 extrapolations wrong → pilot gate catches before commitment.
- **Risk:** ceiling/floor effects (tasks too easy/hard for 1–3B) → pilot
  checks base success is in 20–80% band; task difficulty adjusted once, before
  the matrix, logged.
- **Out of scope:** UIs, additional agent capabilities, training/fine-tuning,
  multi-agent, paid APIs anywhere (hard constraint), long-context axis (RQ3).

## 13. Approval checklist for the user

1. Approve the 6-cell core matrix (1,200 episodes; ~5–10 GPU-h on Kaggle,
   105 h laptop fallback)?
2. Extension cells (incl. new 7B pair): run after core, decide later, or drop?
3. 25 tasks × 8 seeds OK (pass^k up to k=8, τ-bench-comparable)?
4. Any objection to temperature 0.7 (needed for meaningful pass^k)?
5. Guardrail budget (2 schema retries/step, +4 calls/episode) reasonable?
6. Infrastructure: GitHub repo (public recommended — free Actions + portfolio
   visibility) + Kaggle background runs as primary compute. **Requires from
   you, one time:** a free GitHub account and a free Kaggle account with phone
   verification (Kaggle requires it to enable GPU). OK?
