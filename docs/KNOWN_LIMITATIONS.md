# Known Limitations

Documented explicitly, not hidden.

1. **Candidate-generation coverage, not gate design, is the dominant
   bottleneck.** Across all three knowledge graphs, a large share of test
   questions (58–81%, worst on YAGO3-10) receive zero symbolic candidate
   containing the gold answer at all, before SHACL is ever invoked.
   Improving the SHACL gate cannot help on these questions by construction.

2. **The E2-vs-E7 comparison is confounded by provenance-label presentation.**
   An internal ablation (not included in this codebase) found that switching
   a candidate's provenance label alone (`INFERRED(conf=X)` →
   `SHACL_VALIDATED`), with the underlying facts held fixed, changes model
   behavior, and that this label effect is consistently larger than the real
   filtering effect on the knowledge graphs tested. **Independently
   corroborated** on FrenchRoyalty's full 4-retriever × 2-model campaign: the
   real SHACL rejection rate is identical (4/218 candidates, 1.83%) across
   every retriever and both models (see
   `results/SHACL_REJECTION_DIAGNOSTIC.csv`), while the
   observed E7-minus-E2 deltas vary from -0.04 to +0.06 on Hits@Hard —
   filtering alone cannot explain variation it does not have. Any claim
   about "the effect of SHACL gating" should be read as the effect of gating
   **and** relabeling combined, unless independently re-isolated.

3. **`pyshacl` 0.40.1 fails under Python 3.12 for SPARQL-based constraints.**
   FrenchRoyalty's only shape (`FatherWithChildConstraint`) is
   SPARQL-based; evaluating it with `focus_nodes` under Python 3.12.13
   raises `ValidationFailure: 'Cannot use AS to re-bind potentially
   pre-bound variables such as this'` on every call, resolving every
   candidate as `unresolved`. Confirmed working correctly under Python
   3.10.12, with identical `rdflib`/`pyshacl` versions on both — the
   Python interpreter version itself is the variable, not a library
   version mismatch. **Mitigated**: `scripts/setup_kaggle_py310.sh`
   installs a 3.10 venv (needed on Kaggle, whose default kernel is 3.12),
   and `src/setup/platform_detection.py` auto-detects a non-3.10
   interpreter at launch and transparently re-execs into that venv if
   found, or prints a prominent warning otherwise. Confirmed on a real
   4-retriever, 2-model FrenchRoyalty campaign run under Kaggle's default
   3.12 kernel: E7 collapsed to E1 identically on every retriever/model
   pair, exactly as predicted — E0-E6 from that run remain valid (they
   never depend on real SHACL evaluation); only E7 needed rerunning
   under 3.10.

4. **This is a BRINK-style adaptation, not an exact reproduction** of
   BRINK's own benchmark-construction script, in several deliberate,
   documented respects (test-set sizing, topic-entity selection, no
   answer-frequency downsampling). See `docs/METHODOLOGY.md` §3–4 for the
   complete list.

5. **The optional API backend's determinism is not verified.** Local
   generation is deterministic by construction (temperature 0, fixed
   weights); a remote OpenAI-compatible API at temperature 0 depends on the
   provider's own guarantees, which vary and are outside this project's
   control. Prefer the local backend for any result meant to be exactly
   reproducible.

6. **The CoPCA-log audit cross-check has never been operative.**
    `reference_status()` was designed to compare a candidate against
    CoPCA's own valid/violated target logs, but those logs only yield flat
    extracted terms (see `Constraints/copca_reference_logs.py`), never
    structured triples -- so an exact-triple comparison was never actually
    possible, and this check has always returned `"unknown"` for every
    candidate, on every knowledge graph, throughout this project. This has
    **zero impact on any reported result**: `reference_status()` is
    explicitly audit-only, and `validate_fact_shacl_delta()` (the real,
    tested gate) is the sole authoritative decision. Fixed to state this
    explicitly in code rather than silently returning "unknown" through a
    dead key lookup; a genuine term-to-fact matching heuristic was not
    attempted, since an unverified one risks a false "disagreement" signal
    that would be worse than the honest status quo.

7. **The SHACL scope guard was silently vacuous until this codebase's most
    recent review.** `validate_fact_shacl_delta()` never populated a
    `scope_ok` field, while the diagnostic that reports "SHACL scope
    verified: no out-of-scope Focus Node detected" only ever checked for
    that field being explicitly `False` -- an absent field can never equal
    `False`, so this message printed unconditionally throughout the entire
    project, regardless of whether scope was ever actually correct. Fixed:
    `_shacl_validate_signature()` now computes and returns a real
    `scope_ok` (whether every reported Focus Node is within the candidate's
    own subject/object), propagated through `validate_fact_shacl_delta()`.
    This has **no known impact on any previously reported result** -- the
    deprecated `validate_fact_shacl()` (used for the original causal audit
    that motivated $\Delta$SHACL) always had a working version of this same
    check, and no scope violation was ever found there either -- but the
    "verified" claim for $\Delta$SHACL specifically should be treated as
    newly established by this fix, not as re-confirmed from earlier runs.

12. **An independent cross-machine reproduction of the Llama-3.1-8B
    campaign (96 cells: 3 KGs x 4 retrievers x 8 conditions) shows a
    localized, unexplained discrepancy, not full determinism.** SHACL
    candidate/rejection counts matched exactly across both runs (confirming
    an identical frozen benchmark and rule/constraint pool), but Hits@Hard
    differs systematically on the three conditions that expose the
    complete graph or the oracle fact (E0, E5, E6: mean delta +0.08 to
    +0.11), while the five incomplete-graph conditions (E1-E4, E7) show
    approximately zero difference (mean delta -0.004 to 0.000). This
    pattern rules out general data corruption (the SHACL counts are
    identical) and points to something specific to declared-fact
    retrieval or context construction when the complete graph is used,
    but the root cause has not been isolated -- no direct access to the
    second machine's exact code/hardware state was available for this
    investigation. Qwen2.5-3B ran on the same second machine but its
    results have not yet been extracted for comparison. Until resolved,
    treat E0/E5/E6 values as machine-dependent to within roughly +/-0.10
    on Hits@Hard, and E1-E4/E7 values as stable across the two
    environments tested.
