# Scientific Status

This document fixes the current, verified state of the experimental campaign
and its interpretation. It is a snapshot, not a living summary: update the
date and campaign identifiers below whenever new results are consolidated,
rather than editing findings in place.

Status as of: 2026-09-19. Applies to: Campaign A only (see below).

## Experimental campaigns

**Campaign A** (fully established, all findings below refer to this
campaign unless stated otherwise):
- 3 knowledge graphs: FrenchRoyalty, DB100K, YAGO3-10
- 4 retrievers: OneHop, ToG, PoG, StructGPT
- 2 language models: Qwen2.5-3B, Llama-3.1-8B
- 8 experimental conditions: E0-E7
- 100 questions per cell, 192/192 cells complete
- SHACL health verified sound on all 24 model x KG x retriever combinations

**Campaign B** (independent reproduction, in progress):
- Same protocol, run on a separate machine
- Llama-3.1-8B: complete (96/96 cells)
- Qwen2.5-3B: executed on the same machine, results not yet extracted
- See `docs/KNOWN_LIMITATIONS.md` item 12 for the reproducibility
  discrepancy found between Campaign A and Campaign B's Llama results

## Main findings (Campaign A)

- E6 >= E0 in 24/24 model x KG x retriever combinations
- E0 >= E2 in 24/24 combinations
- E2 >= E1 in 22/24 combinations (2 exceptions, both Qwen/YAGO3-10)
- E2 >= E4 in 21/24 combinations (3 exceptions, all Qwen/YAGO3-10)
- Retriever tier structure (OneHop/ToG > PoG/StructGPT) holds on all 3 KGs
- No backbone (Qwen2.5-3B vs Llama-3.1-8B) dominates universally across KGs

## Differential SHACL rejection rate (real filtering, not label change)

| KG | Rejection rate |
|---|---:|
| DB100K | 0.00% |
| FrenchRoyalty | 1.83% |
| YAGO3-10 | 14.86% |

No dose-response is visible between this rejection rate and the size of the
E2-to-E7 gap (see `docs/METHODOLOGY.md` section 6.5).

## Interpretation

SHACL (`$\Delta$SHACL`, the differential gate) is evaluated here as an
**evidence-admission mechanism** for candidate facts shown to the LLM, not
as a general-purpose accuracy booster. The current experiments do not
establish that constraint gating improves downstream answer accuracy over
ungated symbolic reconstruction (E2). This is a reportable negative result,
not an inconclusive one: real filtering intensity varies 0% to 14.86% by KG
with no corresponding change in the E2-E7 gap, which is inconsistent with
filtering being the dominant explanation.

E2-to-E7 is **not a pure SHACL-validation ablation**: the protocol also
changes the candidate's provenance label from `INFERRED(conf=...)` to
`SHACL_VALIDATED`. The observed E2-E7 differences cannot yet be attributed
exclusively to the validator; a dedicated label ablation (identical
candidates and context, label changed alone) would be required to isolate
the two effects, and no such ablation is currently in this codebase.

## Important limitation: evidence-pipeline decomposition

A complete account of where recoverable information is lost requires
distinguishing, per question:

```
N_pool (candidates generated)
  -> N_proven (candidates with a backward-chained proof)
    -> N_admitted (candidates passing Delta-SHACL)
      -> N_shown (candidates surviving the context budget)
```

`N_proven`, `N_admitted`, and `N_shown` are already logged per question
(`inferred_count`, `shacl_valid_count`, `context_count` respectively); the
raw pre-proof candidate pool (`N_pool`) is recoverable from the
checkpointed candidate lists. Reporting all four jointly, and the
attrition between each stage, is the natural next diagnostic layer and has
not yet been compiled into a single table.

## What this status document does not claim

See `docs/KNOWN_LIMITATIONS.md` for the full, itemized list. In brief: this
document does not claim SHACL universally improves accuracy, that E7 is
better than E2, that the label-effect hypothesis is proven, or that
GRR = 0 on YAGO3-10 means the pipeline has no value there -- it means the
correct answers measured on that KG are not attributable to supplied
evidence, which is a scope limitation of that KG's symbolic coverage, not
a general verdict on the method.
