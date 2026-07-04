# Phase 0 — Research Framing (for approval)

Date: 2026-07-04
Status: awaiting user approval of one research question.

## 1. Hardware reality (measured on this machine)

| Component | Found | Consequence |
|---|---|---|
| CPU | Intel i3-1115G4, 2 cores / 4 threads | CPU-only inference; prefill-bound for long prompts |
| RAM | 7.7 GB total | hard ceiling on model + KV cache size |
| GPU | Intel UHD integrated (no discrete GPU) | no CUDA; Ollama runs CPU-only |
| Disk | 90.8 GB free | model storage is not a constraint |

**Model class implications** (measured; timing table in §2):
- 14B: infeasible (Q4 weights ≈ 9 GB > total RAM). Not attempted.
- 7B: **measured out** — 6.9 tok/s prefill, 1.5 tok/s decode, 35 s load
  (qwen2.5:7b Q4_K_M). ~15+ min per agent episode.
- **1–3B: the viable agent-under-test class** (measured: Llama 3.2 1B,
  Qwen2.5 1.5B/3B). This deviates from the brief's example list (8B/14B)
  and is surfaced here for explicit sign-off.

This is a framing feature, not only a limitation: the NVIDIA position paper
(Belcak et al., arXiv:2506.02153) argues sub-10B SLMs are the economically
rational substrate for agents, and TinyLLM (arXiv:2511.22138) shows 1–3B models
are the smallest class with usable function calling. "How reliable are the
models people can actually run for free, and what cheap fixes help" is a live
research question, and everything here reproduces on any laptop at zero cost.

## 2. Measured throughput (evidence)

Ollama 0.31.1 installed this session (winget). All numbers from
`ollama run --verbose` on this machine, one model loaded at a time, no
concurrent downloads. "Prefill long" is the design-relevant number: agent
loops are prompt-heavy.

| Model | Quant / bytes | Load | Prefill (~1.5–2.3k-tok prompt) | Decode |
|---|---|---|---|---|
| llama3.2:1b | Q8_0, 1.3 GB | 4.0 s | 45.5 tok/s (2312 t in 50.8 s) | 9.6 tok/s |
| qwen2.5:1.5b | Q4_K_M, 986 MB | 7.8 s | 47.5 tok/s (2316 t in 48.8 s) | 8.2 tok/s |
| qwen2.5:3b | Q4_K_M, 1.9 GB | 6.2 s | 18.3 tok/s (2316 t in 126.6 s) | 4.3 tok/s |
| qwen2.5:7b | Q4_K_M, 4.7 GB | 34.9 s | 6.9 tok/s (1556 t in 224.7 s) | 1.5 tok/s |

**Implications.**
- **7B is measured out**, not assumed out: 5.1 GB resident, ~4 min to read a
  1.5k prompt, 1.5 tok/s generation → ~15+ min per agent episode. Unusable for
  a many-hundreds-of-episodes matrix.
- **1B–1.5B class is the workhorse** (~2.5 min/episode at ~2.3k prefill + ~870
  decoded tokens, using Ollama prefix caching); **3B is the "large" condition**
  (~5 min/episode). E.g., 500 episodes ≈ 21 h (1.5B) / ≈ 42 h (3B) — overnight
  runs across several days. Exact matrix sizing happens in Phase 1.
- **Tool calling verified functional** on this stack: via `POST /api/chat`
  with a weather-tool schema, qwen2.5:3b produced a correct structured call;
  llama3.2:1b produced a malformed one on first try (invented argument key
  `city` for the schema-required `location`) — an n=1 anecdote, but it is
  precisely the argument-construction failure mode RQ1 studies.

## 3. Verified prior work (all found via web search this session)

**Agent benchmarks / reliability.** τ-bench (arXiv:2406.12045) introduced the
pass^k reliability metric — even GPT-4o solves <50% of tasks and pass^8 <25%
(retail); studied frontier API models only. AgentBench (ICLR 2024,
arXiv:2308.03688): open models ≤70B lag far behind API models across 8
environments. BFCL v3/v4 (OpenReview id=2GmDdhBdDk): function-calling
leaderboard, multi-turn + missing-parameter + long-context subsets,
state-based grading — leaderboard scores, not failure anatomy or mitigations.

**Small-model agents.** TinyLLM (arXiv:2511.22138): <1B–3B models on BFCL;
finds 1–3B ≫ sub-1B; improves them by fine-tuning/DPO (training-side).
HammerBench (arXiv:2412.16516): mobile function calling. NVIDIA SLM position
paper (arXiv:2506.02153): argument, not measurement.

**Failure analysis.** MAST (arXiv:2503.13657, NeurIPS 2025 D&B): 14 failure
modes for *multi-agent* systems on frontier models. ToolEmu (ICLR 2024,
arXiv:2309.15817): GPT-4-emulated sandbox for *safety* risks.

**Tool-failure robustness.** ToolMaze (arXiv:2606.05806, June 2026):
perturbation taxonomy (explicit/implicit × transient/permanent), recovery rate
drops ~37% on implicit failures; fault tolerance improves 3.66× slower than
task performance. AgentCE-Bench (arXiv:2604.06111): random tool-call rejection
p∈{0, .1, .3} degrades all models. PALADIN (arXiv:2509.25238): fixes recovery
by *training* on failure-injected trajectories.

**Long context.** RULER and "Lost in the Middle": effective context ≪ claimed,
U-shaped position effects — single-call, non-agentic. arXiv:2510.05381: length
alone hurts even with perfect retrieval. ACBench (arXiv:2505.19433) covers
compression × agent tasks: 4-bit GPTQ/AWQ costs 1–3% on tool use but 10–15% on
end-to-end applications — static benchmarks, no repeated-trial reliability, and
not the GGUF k-quants local users actually run.

**Ambiguity.** "Learning to Ask" (EMNLP 2025), ClarifyBench, structured-
uncertainty clarification (arXiv:2511.08798), EIG-based clarification
(arXiv:2606.03135) — active area, mostly larger models, mostly method papers.

## 4. Candidate research questions

### RQ1 (recommended) — Reliability anatomy of tiny tool agents + a model-free guardrail
> How reliably do 1–4B open-weight models execute multi-step tool tasks
> (pass^k over many seeded trials); where in the pipeline do failures occur
> (tool selection vs. argument construction vs. error recovery vs. synthesis);
> and how much of the gap does a deterministic verification layer (schema
> validation + typed error feedback + bounded retry) close, at what latency cost?

- **Closest prior:** τ-bench (pass^k, but frontier API models, no mitigation);
  TinyLLM/BFCL (SLM function-call accuracy, single-shot scores, training-side
  fixes); MAST (taxonomy, but multi-agent + frontier).
- **Delta:** repeated-trial reliability + per-step failure attribution +
  *inference-time, model-free* mitigation with CIs and latency accounting, on
  models runnable on any consumer CPU. No searched paper combines these.
- **Feasibility: best fit.** Moderate contexts (1–3k tokens), short episodes,
  arbitrarily many seeds. Covers all three probe axes required by the brief
  (the ambiguity and long-context probes become task-suite slices).
- **Risk: low.** A negative result ("guardrails fix malformed calls but not
  wrong-tool choice") is itself a clean, publishable finding.

### RQ2 — Do tiny agents recover when tools fail? (controlled fault injection)
> When tool calls fail in controlled ways (timeout, error string, empty or
> wrong-schema result), do 1–4B agents retry/re-plan/switch tools or
> hallucinate success — and does structured error feedback improve recovery?

- **Closest prior:** ToolMaze (June 2026) is uncomfortably close on taxonomy
  and metrics, though not SLM-focused; AgentCE-Bench (random rejection);
  PALADIN (training-time fix).
- **Delta:** SLM focus, hallucinated-success rate as headline metric,
  inference-time mitigation, repeated-trial statistics.
- **Feasibility: high.** Deterministic injection, moderate contexts.
- **Risk: medium.** Novelty overlap with ToolMaze must be prominently cited;
  contribution narrows to "the SLM + mitigation + statistics slice."

### RQ3 — Effective *agentic* context of small models
> As an agent's trajectory grows (accumulated tool outputs and distractors),
> at what length do tool selection and argument accuracy degrade — is the
> effective agentic context far below the advertised window — and does
> trajectory compression (truncating/summarizing old tool outputs) mitigate?

- **Closest prior:** RULER / Lost-in-the-Middle / arXiv:2510.05381 (single-call,
  non-agentic); BFCL v3 long-context subset (leaderboard slice).
- **Delta:** in-the-loop degradation curve for 1–4B models + mitigation; the
  "advertised 128K vs. usable agentic context on a laptop" story is compelling.
- **Feasibility: hardest here.** CPU prefill is slow and KV cache competes with
  weights in 7.7 GB RAM; contexts must cap ≈8K and episodes take minutes →
  fewer seeds → wider CIs.
- **Risk: medium-high**, dominated by hardware.

### Optional secondary axis (any RQ): quantization level
Q4_K_M vs Q8_0 (GGUF) as an experimental factor. Closest prior ACBench used
GPTQ/AWQ on static benchmarks; the GGUF k-quants actually shipped by Ollama,
measured in-loop with reliability statistics, are unstudied per this session's
searches. Feasible for 1.5–3B models; multiplies runtime by ~2.

## 5. Recommendation

**RQ1**, with RQ2-style fault injection reused as one probe slice inside RQ1's
task suite (the brief requires probing tool-call errors regardless). This gives
the strongest hardware fit, the clearest delta from prior work, and a headline
that survives a negative mitigation result.
