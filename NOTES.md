# NOTES.md — Project log, lessons, and corrections

Project: Evaluating failure modes of small open-weight LLM agents (working title).
Goal: portfolio research project → resume entry + workshop/arXiv paper. Rigor of the
evaluation is the contribution; the agent is the test subject.

All claims in reports must trace to logged artifacts. This file records decisions,
evidence, lessons, and corrections in chronological order.

---

## 2026-07-04 — Phase 0 (research framing)

### Hardware verification (measured, this machine)
- CPU: 11th Gen Intel Core i3-1115G4 @ 3.00GHz — **2 cores / 4 threads** (Win32_Processor)
- RAM: **7.7 GB** total (Win32_ComputerSystem)
- GPU: Intel UHD integrated only, no discrete GPU (Win32_VideoController)
- Disk: 90.8 GB free on C:
- Ollama: **not installed** at session start → installing v0.31.1 via winget (in progress)

**Consequence (decision):** 14B models are infeasible (Q4 ≈ 9 GB weights > RAM).
7–8B Q4 (~4.5–5 GB weights + KV cache) is marginal against ~4 GB free after
Windows overhead — likely heavy paging. The agent-under-test class is therefore
**~1B–4B models** (e.g., Llama 3.2 1B/3B, Qwen2.5 1.5B/3B, Qwen3 1.7B/4B,
Phi-3.5-mini). This deviates from the brief's example list (Llama 3.1 8B,
Qwen 2.5 7B/14B) — surfaced to user in Phase 0 report. A 7B may be *attempted*
once, timed, and reported as evidence, but must not be load-bearing for the
experiment matrix. Throughput numbers below are TO BE MEASURED once Ollama is
installed; no experiment-scale claims before that.

### Literature verified via web search this session (Phase 0)
(Only these may be cited until further verification.)
- τ-bench, Yao et al. 2024, arXiv:2406.12045 — tool-agent-user benchmark; pass^k
  reliability metric; GPT-4o <50% success, pass^8 <25% (retail). τ²-bench:
  github.com/sierra-research/tau2-bench.
- AgentBench, Liu et al., ICLR 2024 (arXiv:2308.03688) — 8 envs; OSS models ≤70B
  lag far behind API models.
- ToolEmu, Ruan et al., ICLR 2024 spotlight, arXiv:2309.15817 — LM-emulated
  sandbox for agent risk identification (GPT-4 as emulator).
- BFCL v3/v4 (Berkeley) — function-calling leaderboard; v3 added multi-turn +
  missing-params/long-context subsets; state-based grading; OpenReview paper
  id=2GmDdhBdDk.
- Belcak et al. 2025, arXiv:2506.02153 — NVIDIA position paper: SLMs (<10B) are
  the future of agentic AI. Position, not empirical eval → framing support.
- MAST, "Why Do Multi-Agent LLM Systems Fail?", arXiv:2503.13657, NeurIPS 2025
  D&B — 14 failure modes, 3 categories; multi-agent focus.
- RULER (effective context length ≪ claimed) and "Lost in the Middle"
  (U-shaped position curve); "Context Length Alone Hurts LLM Performance
  Despite Perfect Retrieval", arXiv:2510.05381. All non-agentic single-call evals.
- ToolMaze, arXiv:2606.05806 (June 2026) — **closest prior for error-recovery
  RQ**: DAG topologies × 2×2 tool-perturbation taxonomy; recovery rate drops
  ~37% on implicit semantic failures; fault-tolerance scales 3.66× slower than
  task performance.
- PALADIN, arXiv:2509.25238 — training-based recovery (failure-injected data).
- AgentCE-Bench, arXiv:2604.06111 — random tool-call rejection p∈{0,.1,.3}.
- ACBench, "Can Compressed LLMs Truly Act?", arXiv:2505.19433 — **closest prior
  for quantization RQ**: GPTQ/AWQ/pruning × agentic tasks; 4-bit ≈1–3% drop on
  tool use but 10–15% on real-world apps. Uses GPTQ/AWQ (not GGUF k-quants),
  static benchmarks, no repeated-trial reliability.
- TinyLLM, arXiv:2511.22138 — **closest prior for SLM-agent framing**: <1B–3B
  models on BFCL; 1–3B ≫ <1B; improves via fine-tuning/DPO (training-side fix,
  not inference-time mitigation; no failure taxonomy; no repeated-trial stats).
- HammerBench, arXiv:2412.16516 — fine-grained mobile function calling.
- Ambiguity/clarification: "Learning to Ask" (EMNLP 2025 main.1104);
  ClarifyBench; Structured Uncertainty (arXiv:2511.08798); EIG-based
  clarification (arXiv:2606.03135). Active 2025–26 area; mostly larger models.

### Ollama installed + first measured throughput (evidence)
- Ollama 0.31.1 installed via winget (background task bc8835jgh, exit 0).
  CLI not on PATH in this session's shells → use
  `$env:LOCALAPPDATA\Programs\Ollama\ollama.exe`.
- Network: llama3.2:1b (1.3 GB) pulled in 173.7 s ≈ 7.5 MB/s.
- **llama3.2:1b (Q8_0, 1.3 GB), measured via `ollama run --verbose`:**
  - short prompt (36 tok): prefill 57.2 tok/s, decode 9.64 tok/s, load 4.0 s
  - long prompt (2312 tok): prefill **45.5 tok/s** (50.8 s total prefill),
    decode 14.4 tok/s (2-token sample, noisy)
- **Design consequence:** CPU inference here is *prefill-bound*. A 2.3k-token
  context costs ~51 s even on a 1B model. Agent episodes must exploit Ollama's
  prefix/KV caching (growing chat history, same model kept loaded), and the
  long-context RQ is only feasible in reduced form (1B model, ≤4–6k ctx).

### qwen2.5:3b measured + tool-call sanity checks (evidence)
- **qwen2.5:3b (Q4_K_M, 1.9 GB), `ollama run --verbose`:**
  - short (40 tok): prefill 12.2 tok/s, decode 4.27 tok/s, load 6.2 s
  - long (2316 tok): prefill **18.3 tok/s** (126.6 s), decode 6.25 tok/s
  - → a 3B episode w/ ~3k ctx ≈ 4–5 min; ~3× slower than the 1B class.
- **Tool-calling sanity via POST /api/chat with a weather-tool schema**
  (payload: `~/.claude/jobs/43863104/tmp/toolcall_test.json`):
  - qwen2.5:3b → correct: `get_current_weather({location:"Toronto",unit:"celsius"})`
  - llama3.2:1b → **malformed args on first try**: invented key `city` instead of
    schema-required `location`. n=1 anecdote, NOT a result — but it is exactly the
    argument-construction failure mode RQ1 targets, observed in the wild here.
- Note: both API tests ran during a concurrent model download → their latency
  numbers are polluted; only the `ollama run --verbose` runs above count as
  throughput evidence.

### Full timing matrix complete (evidence — all via `ollama run --verbose`, no concurrent load)
| Model (tag) | Quant / bytes | Load | Prefill short | Prefill ~1.5–2.3k | Decode |
|---|---|---|---|---|---|
| llama3.2:1b | Q8_0, 1.3 GB | 4.0 s | 57.2 t/s (36 t) | **45.5 t/s** (2312 t) | 9.6 t/s |
| qwen2.5:1.5b | Q4_K_M, 986 MB | 7.8 s | 51.0 t/s (40 t) | **47.5 t/s** (2316 t) | 8.2 t/s |
| qwen2.5:3b | Q4_K_M, 1.9 GB | 6.2 s | 12.2 t/s (40 t) | **18.3 t/s** (2316 t) | 4.3 t/s |
| qwen2.5:7b | Q4_K_M, 4.7 GB | 34.9 s | 3.8 t/s (40 t) | **6.9 t/s** (1556 t) | 1.5 t/s |

- Decode column = short-run eval rate (long-run decode samples were 2 tokens, noisy).
- 7B loaded at 5.1 GB resident, 100% CPU (`ollama ps`); its 2-token decode under
  long-context memory pressure fell to 0.32 t/s. **7B ruled out by measurement**:
  ~15+ min/episode.
- Episode-time estimates derived from measurements (assumes ~2.3k prefill + ~870
  decode tokens/episode with prefix caching): 1B/1.5B ≈ 2.5 min, 3B ≈ 5 min.
  → e.g. 500 episodes ≈ 21 h (1.5B) / 42 h (3B). Matrix sizing is a Phase 1 decision.

## 2026-07-04 — Phase 1 (design doc)

- **User approved:** RQ1 + quantization axis, 1–3B model class. Also directed:
  position explicitly against arXiv:2606.01416, τ-bench, BFCL; write the
  closest-prior-work section first.
- **arXiv:2606.01416 verified this session** (abstract + HTML): "Self-Healing
  Agentic Orchestrators for Reliable Tool-Augmented LLM Systems". Budgeted
  runtime recovery; 100-task fault injection; 98.8% vs 94.5% retry-only.
  Gap we fill (verified from their own text): live model never named, no
  pass^k, no CIs, latency = call-count proxy not wall-clock. Our study is the
  complementary measurement: named 1–3B GGUF models, pass^k + CIs + paired
  tests, real wall-clock/token overhead, quantization as controlled variable.
- **Ollama tags verified** (ollama.com/library/qwen2.5/tags):
  1.5b-instruct-q8_0 (1.6 GB), 3b-instruct-q8_0 (3.3 GB) exist. Local `ollama
  show`: pulled 1.5b/3b are Q4_K_M; llama3.2:1b is Q8_0 (1.2B params).
- **PHASE1_DESIGN.md written** — core matrix 6 cells × 25 tasks × 8 seeds
  = 1,200 episodes ≈ 105 h buffered; extension +800 eps. Fully programmatic
  grading (no LLM judge); failure-attribution classifier to be validated vs
  ~40 hand-labeled trajectories (κ reported). Pilot gate (10 eps/cell) before
  full matrix; Q8 episode times are extrapolations until then.
- **Infrastructure amendment (user directive):** fastest completion, free
  tools, must run with user's device off / offline (remote location, flaky
  wifi). Verified this session: Kaggle "Save & Run All" commit runs continue
  server-side after browser close/device off; ~30 predictable GPU-h/week;
  GitHub Actions free on public repos (6 h/job, 20 concurrent). Design now:
  GitHub repo = source of truth; Kaggle background runs = primary compute
  (core ≈ 5–10 GPU-h, est. pending mandatory cloud timing benchmark); laptop
  = fallback only; consumer-CPU latency reported as token-overhead × Phase 0
  measured rates (labeled derived). 7B extension pair (E5/E6) added —
  GPU-feasible though measured out locally. Colab rejected as primary: free
  tier requires the browser/device to stay alive (background execution is a
  paid feature there).
- Awaiting user approval on the 6 checklist items in PHASE1_DESIGN.md §13.
  User one-time to-dos if approved: free GitHub account; free Kaggle account
  with phone verification (needed for GPU).

### Infrastructure credentials verified (evidence)
- GitHub: `gh auth status` → logged in as **DhruvilShah22**, scopes repo+workflow
  (gh CLI 2.96.0 installed via winget; full path `C:\Program Files\GitHub CLI\gh.exe`).
- Kaggle: CLI 2.2.3 (pip, Python 3.14.5); new-style KGAT token must go in
  `~/.kaggle/access_token` (NOT kaggle.json — that's legacy keys only).
  Verified: `kaggle kernels list --user contactshahdhruvil` returns kernels.
- Still unconfirmed: Kaggle **phone verification** status (gates GPU + internet
  in kernels) — will surface at first GPU kernel push if missing.
- Secrets hygiene: token was pasted in chat; recommended user revoke/rotate it
  after project completion. Never copy tokens into repo or NOTES.

### PHASE 1 APPROVED (user, 2026-07-04)
- Decisions: design **as-is** (25 tasks × 8 seeds); extensions **decided after
  core results**; repo **public** with explicit requirement that no sensitive
  keys are ever committed (.gitignore guards + pre-push grep for token strings).
- Kaggle phone verification confirmed by user.
- Budget note: user's Claude session near limit → this session ships only the
  setup/de-risk slice; full Phase 2 build next session.

### Session-end state (2026-07-04, budget-limited session)
- Public repo LIVE: https://github.com/DhruvilShah22/slm-agent-eval (main,
  commits 7996f35 + 5ec9983; author = user's noreply identity, no AI trailers
  per user requirement — recorded in memory).
- Kaggle benchmark kernel v1 FAILED (evidence: kernel log): Ollama installer
  needs `zstd`, absent from Kaggle image. **v1 log also confirms: P100 16GB
  granted (phone verification OK) + kernel internet OK.**
- Fix (apt-get zstd + binary guard) committed; **kernel v2 launched** — runs
  server-side on Kaggle's clock; expected ~20–40 min (≈14 GB of model pulls
  + timings). Results: benchmark_results.json in kernel output.

### Kaggle P100 benchmark COMPLETE (evidence: artifacts/benchmark_results.json, kernel v2)
| Model | Prefill @2.3k (t/s) | Decode (t/s) | vs laptop |
|---|---|---|---|
| qwen2.5:1.5b Q4_K_M | 2268 | 93.8 | ~48× / ~11× |
| qwen2.5:1.5b Q8_0 | 2399 | 90.0 | — |
| qwen2.5:3b Q4_K_M | 1362 | 56.7 | ~74× / ~13× |
| qwen2.5:3b Q8_0 | 1468 | 59.9 | — |
| qwen2.5:7b Q4_K_M | 688 | 36.3 | 7B viable on GPU |
| llama3.2:1b Q8_0 | 3056 | 123.3 | — |
- Episode estimate on P100 (~2.3k prefill + 870 decode): **10–30 s** → core
  matrix ≈ **4–6 GPU-h** (within prior 5–10 est.); ALL extensions cheap too.
- Q8 slightly *faster* than Q4 on GPU (dequant overhead) — quant axis costs
  nothing extra in cloud runtime.
- **New failure-mode anecdote (n=1):** tool_call_check on 1.5b-Q4 returned
  arguments as `{"location": {"description":..., "type":"string", "value":
  "Toronto"}}` — the model echoed the JSON-schema structure instead of plain
  values ("schema-echo" malformed-args variant). Add to grading taxonomy
  examples; guardrail schema gate should catch exactly this.
- Model pulls on Kaggle are fast (10–25 s each; one outlier 444 s).

### RESUME POINT (start of next session — read this first)
1. Check Kaggle benchmark run: `kaggle kernels status contactshahdhruvil/slm-agent-eval-benchmark`,
   then `kaggle kernels output` → benchmark_results.json → record T4 throughput
   into NOTES.md + PHASE1_DESIGN.md §10 (replace estimates), commit.
2. Begin Phase 2 build per PHASE1_DESIGN.md §§3–7: package layout
   `harness/` (agent loop, guardrail, ollama client, logging), `tools/`
   (calculator, BM25 search_docs, sqlite get_order/find_products, run_python),
   `tasks/` (25 YAML specs, 5 slices), `grading/` (checker + first-failure
   attribution), `configs/` (cells C1–C6), seeded corpus+DB generator.
3. Local smoke test vs laptop Ollama (qwen2.5:1.5b, 2–3 episodes), then Kaggle
   pilot (10 eps/cell), grader validation (~40 hand-labels, κ), THEN full matrix.
4. Constraints unchanged: zero paid APIs; every number traceable; stop for
   user approval only where design says; no scope creep.

### Lessons / corrections
- PowerShell tool shells don't inherit PATH updates made mid-session by
  installers; invoke new binaries by absolute path.
- `ollama pull` progress bars flood stdout (300 KB) — suppress with
  `| Out-Null` when running via tools.
