# Reproducibility Protocol

## Experimental grid (Campaign A)

```
Datasets
  |-- FrenchRoyalty
  |-- DB100K
  `-- YAGO3-10

Retrievers
  |-- OneHop
  |-- ToG
  |-- PoG
  `-- StructGPT

Language models
  |-- Qwen2.5-3B
  `-- Llama-3.1-8B

Conditions
  |-- E0  complete graph, declared facts only
  |-- E1  incomplete graph, declared facts only
  |-- E2  incomplete graph + symbolic candidates, PCA >= 0.4
  |-- E3  incomplete graph + symbolic candidates, no PCA filter
  |-- E4  incomplete graph + random distractor facts
  |-- E5  complete graph + symbolic candidates
  |-- E6  incomplete graph + oracle (the removed fact reinserted)
  `-- E7  incomplete graph + Delta-SHACL-validated candidates
```

192 cells total (3 x 4 x 2 x 8), 100 questions per cell.

## Fixed parameters

| Parameter | Value |
|---|---|
| Random seed | 42 |
| LLM temperature | 0 (greedy decoding) |
| Context budget | 12 facts maximum per prompt |
| PCA confidence threshold (E2) | >= 0.4 |
| Split policy | BRINK-style 80/10/10, with a documented small-pool test floor |
| SHACL mode | Differential (`$\Delta$SHACL`): pre/post validation-signature diff |

## Split integrity

Each frozen benchmark's pool and split are fingerprinted with SHA-256 at
construction time (see `results/<KG>/fingerprints.txt`). Re-running the
split construction on the same source data must reproduce the identical
fingerprint; this has been verified across two independent runs for all
three KGs.

## Software environment

- Python 3.10 required for SHACL-dependent conditions (E7); see
  `docs/KNOWN_LIMITATIONS.md` item 3 for the Python 3.12 / pyshacl
  incompatibility this avoids.
- Pinned dependencies: `rdflib==7.6.0`, `pyshacl==0.40.1` (see
  `requirements.txt` and `.github/workflows/ci.yml`).
- No API-based LLM backend was used for Campaign A (`--backend local`,
  the default); the optional `--backend api` path exists for convenience
  but its determinism has not been separately verified (see
  `docs/KNOWN_LIMITATIONS.md` item 9).

## Reproducing a single condition

```bash
python3 src/main.py --dataset FrenchRoyalty --retriever onehop \
    --model Qwen2.5-3B --tiers 100
```

Resuming an interrupted or partially-complete run requires no special
flag: existing checkpoints under `run_state/checkpoints/` are
automatically detected and only missing questions/conditions are
computed (see `README.md` for the full CLI reference).

## Verifying a campaign's completeness before trusting its numbers

1. Confirm cell count: every (model, KG, retriever, condition) should have
   exactly 100 checkpointed questions with `llm_status == "OK"`.
2. Confirm SHACL health for any campaign that includes E7: check
   `unresolved_share` in the SHACL diagnostic is 0 for every combination
   (a non-zero share indicates the Python 3.12 / pyshacl issue above, not
   a genuine result).
3. Confirm candidate-pool counts (`ns_candidates_total`,
   `shacl_valid`/`shacl_invalid`) match the expected, previously-verified
   values for that KG if comparing against a prior campaign -- a mismatch
   indicates a different code version, rule set, or benchmark fingerprint,
   not a directly comparable result (see `docs/KNOWN_LIMITATIONS.md`
   item 12 for a concrete instance of this check).

## Known non-determinism sources

- Cross-machine floating-point differences in 4-bit quantized inference
  are possible even at temperature 0, though the discrepancy documented
  in `docs/KNOWN_LIMITATIONS.md` item 12 is systematic rather than
  diffuse, suggesting a code or configuration difference rather than pure
  numerical jitter.
- The optional API backend (`--backend api`) inherits whatever
  determinism guarantee the chosen provider offers at temperature 0,
  which is outside this project's control.
