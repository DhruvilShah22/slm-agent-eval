# slm-agent-eval

**How reliable are the small open-weight LLMs anyone can run for free as
multi-step tool agents — where do they fail, and how much does the cheapest
deterministic guardrail recover, as a function of quantization?**

Research portfolio project. The contribution is the rigorous evaluation:
pass^k reliability over seeded repeated trials, programmatic failure
attribution, an inference-time model-free mitigation measured with paired
statistics, and a Q4_K_M-vs-Q8_0 quantization axis — on 1–3B GGUF models,
reproducible at zero cost (Kaggle free GPU or any consumer CPU).

## Status

- Phase 0 (research framing): done, approved — see `PHASE0_RESEARCH_FRAMING.md`
- Phase 1 (design): done, approved — see `PHASE1_DESIGN.md`
- Phase 2 (build): **in progress**
- Phase 3 (experiments + paper-style report): pending

`NOTES.md` is the chronological project log: every measurement, decision,
and correction, with evidence pointers.

## Layout

```
PHASE0_RESEARCH_FRAMING.md   research questions, verified prior work, hardware evidence
PHASE1_DESIGN.md             approved design: architecture, tasks, metrics, matrix, stats
NOTES.md                     running log (evidence for every claim)
kaggle/benchmark/            GPU timing benchmark kernel (pilot gate, part 1)
```

Full reproduction instructions land with Phase 2 code.
