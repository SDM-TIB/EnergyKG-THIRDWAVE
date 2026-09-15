# Testing Strategy

This pipeline mixes pure logic (parsing, canonicalization, metrics) with
stages that need real data, a GPU, and hours of runtime (symbolic inference,
SHACL validation, LLM generation). The testing strategy reflects that split.

## 1. Unit tests — no data, no GPU, seconds to run

```bash
python3 -m pytest tests/
```

`test_pure_functions.py` extracts and tests functions in isolation:
canonicalization (`local_name`, `canonical_fact`, `dedup_triples`,
`fact_id`), answer parsing/normalization (`Evaluation/brink_metrics.py`), the F1 metric's algebraic equivalence to BRINK's
definition, and rule-term cleaning (`_clean_term`, `norm_col`). These are the
functions most likely to silently break in a way that corrupts every
downstream result, so they are checked directly, not just exercised
incidentally by a full run.

Add a new test here whenever you change one of these functions, or add a
similarly pure one.

## 2. Split-construction smoke test — no GPU, seconds to run

```bash
python3 src/main.py --dataset FrenchRoyalty --stop-after-split
```

Runs dataset loading, rule parsing, SHACL loading, and the BRINK-style split
construction, then exits before any model loads. Confirms the source data
resolves correctly and prints the pool/split SHA-256 fingerprints — compare
them to `results/FrenchRoyalty/fingerprints.txt` to catch any accidental
change to the frozen benchmark before it reaches a multi-hour run.

## 3. End-to-end smoke test — needs data + a GPU or CPU, minutes to run

```bash
python3 src/main.py --dataset FrenchRoyalty --retriever onehop --max-questions 2
```

Runs the complete pipeline (both LLM backbones, all eight conditions) on
just 2 questions. This is the fastest way to catch a break introduced
anywhere in the pipeline, including the parts that unit tests cannot reach
(model loading, generation, SHACL validation against real data). Expect this
to take a few minutes, dominated by model download/loading on the first run.

Check for:
- No traceback.
- A results table printed for each of E0–E7.
- `run_state/artifacts/FrenchRoyalty/*` and
  `run_state/checkpoints/*/FrenchRoyalty/onehop/*.jsonl` created.

## 4. Determinism check

Run the same command twice and diff the printed `pool_sha256` /
`split_sha256`, and the `prediction_raw` field in the resulting checkpoints
(temperature is 0, so these must match exactly):

```bash
python3 src/main.py --dataset FrenchRoyalty --max-questions 2 --campaign-name run1
python3 src/main.py --dataset FrenchRoyalty --max-questions 2 --campaign-name run2
diff <(jq .prediction_raw run_state/campaigns/run1/checkpoints/*/FrenchRoyalty/onehop/E1_incomplete_baseline.jsonl) \
     <(jq .prediction_raw run_state/campaigns/run2/checkpoints/*/FrenchRoyalty/onehop/E1_incomplete_baseline.jsonl)
```

## 5. Before trusting a full campaign's results

1. Run the split-construction smoke test first; confirm the fingerprints match.
2. Run the same command twice on a small `--max-questions` sample and diff
   the checkpoints (see determinism check above) — a mismatch means
   something upstream is non-deterministic and needs investigating before
   any other number from that run is trusted.
3. Only then launch the full campaign, ideally via `scripts/launch.sh` so it
   survives an interrupted connection.
