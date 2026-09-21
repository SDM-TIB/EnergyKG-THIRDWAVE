# Methodology

This document describes exactly what this pipeline does, what it reuses
directly from BRINK / CoPCA / DIGIMON, and every point on which it
deliberately departs from those sources. It is written so that a reviewer can
verify each claim against the notebook's own code and printed provenance
banners, not just against this text.

## 1. Dataset loading

RDF graphs are parsed from their canonical RDF files: FrenchRoyalty from Turtle (`.ttl`), and DB100K/YAGO3-10 from N-Triples (`.nt`). `rdf:type` triples are excluded from the
semantic QA pool but retained in the RDF graph used for SHACL (SHACL shapes
can target by class). Literal-valued objects are detected via RDF term type
(`isinstance(o, rdflib.Literal)`), not via a string-prefix heuristic — an
earlier version's string-based check never actually excluded any literal
(verified empirically: `str(rdflib.Literal(...))` never begins with a quote
character). RDF iteration is explicitly sorted before any downstream
processing, to avoid non-determinism from Python's per-process hash
randomization of `rdflib.Graph`'s internal iteration order.

## 2. Rule mining

CoPCA's authoritative rule CSVs are the sole rule source (not re-mined by
this pipeline, except where noted). Rule parsing is lossless after excluding explicit AMIE metadata/footer rows: any true unparsed
row gates the affected dataset rather than being silently dropped. AMIE log
footer lines mistakenly concatenated into a rules CSV export are explicitly
detected and excluded, logged separately, never treated as parse failures.
`PCA ≥ 0.4` is the threshold for E2/E5/E7 candidate generation,
matching BRINK's own AMIE3 invocation (`-minpca 0.4`). This is a different
quantity from CoPCA's own internal "PCA_valid/PCA_invalid" (computed from
TravSHACL-validated triple counts, thresholded at 0.75) — the two are never
conflated in this pipeline or its reporting.

## 3. Benchmark construction — a BRINK-style adaptation

This is **not** a byte-for-byte reproduction of BRINK's own construction
script. Deliberate, documented differences:

1. **Full eligible pool, not a fixed `nrows`.** BRINK's released script
   truncates to a fixed row count; this pipeline uses the complete eligible
   grounding pool, so the test-set size is a consequence of how many facts
   are removable for a given KG, not a chosen number.
2. **Test floor of 100** for small pools (applies to FrenchRoyalty and
   YAGO3-10 here); DB100K's pool is large enough to reach the pure 8:1:1
   ratio naturally (231).
3. **Topic entity fixed to the subject** of the removed triple. BRINK
   randomly designates either endpoint of the removed triple as the
   "Question Entity," with the other as the answer. This pipeline always
   anchors to the subject, halving the linguistic direction space of
   generated questions relative to BRINK. This is a frozen, deliberate
   choice for this benchmark, not a claim of exact BRINK conformance —
   changing it would require regenerating and refreezing every question,
   invalidating all existing SHA-256 fingerprints and results.
4. **No answer-frequency downsampling.** The released BRINK pipeline
   includes a balancing step over the answer distribution; this pipeline
   does not apply it.
5. A **BRINK §3.2-compliant safety guard** on triple removal is enforced
   explicitly: a candidate is only eligible for removal if its own head
   never appears as a body atom (a required proof) of another grounding in
   the pool — preventing one benchmark question's removal from silently
   breaking another question's intended reasoning path.

Every frozen split is fingerprinted (SHA-256 of the pool, SHA-256 of the
train/val/test assignment) so that two independent runs against the same
source data can be verified to have produced the exact same benchmark before
any new result is compared to an existing one.

## 4. Question generation — a BRINK-style adaptation

An LLM is asked to phrase a natural-language question from the removed
triple's subject and relation (matching BRINK's own use of an LLM for this
step, though BRINK's paper uses GPT-4 and this pipeline uses the same local
model as the main campaign, to remain fully local/unattended). Two explicit
safety checks are enforced before accepting an LLM-written question: the
subject must be mentioned, and the answer entity must **never** be mentioned
(checked with underscore/space and case normalization, since entity local
names use underscores but natural questions do not). A deterministic
sentence-template fallback fires if either check fails, so a test question is
never silently dropped. Each question records whether it was LLM-phrased or
template-generated (`question_source`), for full provenance.

## 5. Neuro-symbolic inference — a two-stage, hybrid process

This is the part most easily mischaracterized, so it is stated precisely:

- **Stage 1 (offline, forward chaining, once per KG):** every mined rule is
  grounded against the **complete** graph, producing a question-independent
  pool of every fact each rule could possibly produce.
- **Stage 2 (per question, backward chaining):** for a specific question,
  the pool is filtered to candidates about the question's topic entity, then
  each candidate is **proven** — a recursive, SLD-resolution-style backward
  chain — using only the facts available in the **incomplete** graph for
  that question. A candidate with no valid proof is discarded before it ever
  reaches the SHACL gate.

Candidates are ranked by: whether their relation matches the question's
target relation, then PCA confidence, then proof count; the top few (within
the context budget) are kept.

## 6. SHACL constraint validation

### 6.1 Objective

Before a symbolic candidate is shown to the LLM, check it against the
dataset's authoritative CoPCA `.ttl` SHACL shapes. CoPCA's own
`targets_valid.log` / `targets_violated.log` files are **never** treated as
shape graphs or as a source of admissibility decisions — they are consulted
only as an audit cross-check (see 6.3), logged, never decisive.

### 6.2 The corrected differential gate ($\Delta$SHACL)

An initial implementation tested only
`SHACL(G_incomplete + candidate) = conforms`. A dedicated causal audit
(FrenchRoyalty/OneHop, 89 rejected candidates) found that 80/89 (89.9%) of
rejections were caused by a violation already present on the candidate's
focus node **before** the candidate was added — the candidate was not
responsible. The corrected gate compares the **set of validation-result
signatures** (focus node, source shape, result path, source constraint
component, value, severity) before and after adding the candidate; the
candidate is invalid only if this diff is non-empty. A plain boolean
before/after `conforms` comparison (an intermediate version) was itself found
to be too coarse: it can miss a genuinely new violation that appears
alongside an already-present one on the same focus node, because the overall
boolean state does not change. The signature-based diff does not have this
gap.

### 6.3 Soundness checks built into the pipeline

- **Reference-log cross-check:** `reference_status()` was intended to
  cross-check a candidate against CoPCA's own valid/violated logs, but those
  logs only ever yield flat extracted terms, not structured triples (see
  `Constraints/copca_reference_logs.py`) — an exact-triple comparison was
  never actually possible, so this always returns `"unknown"` by design.
  This has zero impact on any result: it is explicitly audit-only, and
  $\Delta$SHACL is the sole authoritative decision. See
  `docs/KNOWN_LIMITATIONS.md`, item 10.
- **Scope guard:** the reported Focus Nodes are checked against the expected
  scope (the candidate's own subject and object); an unexpected focus node
  is flagged explicitly rather than silently accepted, which would indicate
  validation drifting back toward the whole graph. This check was found,
  during a later code review, to have been silently vacuous in
  $\Delta$SHACL specifically (`validate_fact_shacl_delta()` never populated
  the field the diagnostic read, so it always reported "verified" without
  actually checking) — fixed to compute and report it for real; the
  deprecated `validate_fact_shacl()` always had a working version of this
  same check.
- **Soundness audit:** across 172+ manually and programmatically audited
  rejected candidates on two knowledge graphs, zero were found to be true
  facts wrongly rejected.

### 6.4 A known, unresolved environment issue

`pyshacl` 0.40.1's evaluation of a `SPARQLConstraintComponent` shape (the
only shape type used by FrenchRoyalty) fails under **Python 3.12** with
`ValidationFailure: 'Cannot use AS to re-bind potentially pre-bound variables
such as this'`, causing every candidate to resolve as `unresolved` rather
than `valid`/`invalid`. Confirmed working correctly under **Python 3.10.12**
(a persistent GCE VM); confirmed failing under **Python 3.12.13** (a default
Kaggle kernel), with identical `rdflib` (7.6.0) and `pyshacl` (0.40.1)
versions on both — the difference is the Python interpreter version itself,
not a library version mismatch. No fix has been found; the practical
workaround is to run any condition that depends on real SHACL admissibility
(E7) only on a Python 3.10 environment, and to
treat E7 results computed elsewhere as unreliable. See
`docs/KNOWN_LIMITATIONS.md`.

### 6.5 The real SHACL rejection rate is retriever- and model-invariant

On FrenchRoyalty's active 100-question set, the exact same 4/218 candidates
(1.83%) are rejected regardless of retriever (OneHop, ToG, PoG, StructGPT) or
answering model (Qwen2.5-3B, Llama-3.1-8B); see
`results/SHACL_REJECTION_DIAGNOSTIC.csv`. This is expected by
construction: $\Delta$SHACL validates E2's symbolic candidates, which come
from backward-chaining over the KG and do not depend on the retriever or the
answering model. The observed E7-minus-E2 deltas per retriever/model (from
-0.04 to +0.06 on Hits@Hard) therefore cannot be attributed to differential
filtering, since filtering is proven uniform across every combination
measured. The most plausible remaining explanation is a provenance-label
effect on model behavior, studied via an ablation mechanism that is no
longer part of this codebase (see `docs/KNOWN_LIMITATIONS.md`).

## 7. Evidence conditions and context fusion

See the main `README.md` for the condition table. Implementation notes:

- **Context budget:** up to 8 declared facts, up to 12 total. Augmentation
  (inferred/random/oracle/SHACL-validated facts) fills the remaining slots
  after declared facts, in confidence/relevance order where applicable.
- **Provenance labels are shown to the LLM explicitly** (`DECLARED`,
  `INFERRED(conf=X)`, `RANDOM`, `ORACLE`, `SHACL_VALIDATED`), and the
  system prompt tells the model how much to trust each label. This means an
  E2-vs-E7 comparison combines two changes at once: which candidates survive,
  and how they are labeled (see docs/KNOWN_LIMITATIONS.md for a related,
  documented finding removed from this codebase).
- Per-record provenance statistics distinguish the **candidate pool size**
  (`inferred_count`, `shacl_valid_count`, etc., before the context budget
  truncates augmentation) from what was **actually fused into the context
  shown to the model** (`*_in_context` fields, computed directly from the
  final `context_facts`). An earlier version only recorded pool-size
  statistics, which could misrepresent what the LLM actually saw whenever
  the pool exceeded the augmentation budget; this is fixed in the current
  notebook.

## 8. Answer generation and metrics

Local, deterministic (temperature 0) generation with Qwen2.5-3B and
Llama-3.1-8B by default, no external API dependency. An optional remote
backend (`--backend api`) sends the same messages to any OpenAI-compatible
chat-completions endpoint instead, still at temperature 0 -- though
determinism then also depends on the provider's own guarantees, which this
pipeline cannot verify. The API key is read once from `LLM_API_KEY` (or
`--api-key`) and is never printed, logged, or written to a checkpoint.
Metrics (Hits@Any, Hits@Hard, HHR, Precision, Recall, F1) follow the BRINK evaluator semantics; HHR = Hits@Hard / Hits@Any.

## 9. Resumability and known engineering issues (fixed)

- Each (model, dataset, retriever, condition) has an independent,
  append-only JSONL checkpoint; a completed question is never recomputed
  unless its content no longer matches the current frozen question set.
- **A checkpoint-aggregation bug was found and fixed:** live progress
  tables computed during a run could include stale question IDs left over
  from an earlier, larger or otherwise different version of a KG's frozen
  test set (e.g., DB100K's checkpoint accumulated entries from a prior
  231-question run while only 50 were active for a given campaign). The
  end-of-run summary tables were already filtering correctly; only the
  *live, in-progress* display tables were affected. Fixed by explicitly
  filtering to the currently active question-ID set before computing any
  aggregate.
- **A redundant-computation performance issue was found and fixed:**
  the per-question evidence-construction function computed the full
  symbolic-inference-and-SHACL pipeline from scratch on every call, once per
  condition — meaning the same expensive computation was silently redone up
  to eight times per question (once for each of E0–E7). Fixed
  with a per-question memoization cache, scoped to the current
  (dataset, retriever, model) combination; this changes nothing about what
  is computed or written, only how many times.
- A separate, real performance bug (a full-graph rebuild on every SHACL call)
  caused an 8× slowdown on DB100K specifically; fixed by caching the
  triple-list conversion once per dataset.
- A memory-exhaustion incident (kernel OOM at ~28.5 GB resident on a 29 GB
  VM, after several hours of continuous SHACL validation) led to resizing
  the VM and adding a periodic, scoped garbage-collection call in the
  SHACL-dependent condition's driver loop.

## 8. Positioning relative to the literature

This work sits at the intersection of four research lines: KG-RAG under
incompleteness, symbolic reasoning over knowledge graphs, semantic
constraints, and evidence traceability. The comparison below is
metric-compatible with BRINK (same Hits@Any/Hits@Hard/HHR/F1 definitions)
but not directly score-comparable to any single prior system: datasets,
backbones, retrievers, and experimental conditions all differ. Comparing
raw scores across these systems ("our F1 is X, therefore we outperform
BRINK") would be methodologically fragile; the comparison below is
architectural, not score-based.

| Criterion | KG-RAG literature | BRINK | CoPCA / NS-KG | This work |
|---|---|---|---|---|
| Complete KG | ✓ | ✓ | ✓ | ✓ |
| Deliberate incompleteness | -- | ✓ | ✓ | ✓ |
| Hard-answer evaluation | -- | ✓ | -- | ✓ |
| Hits@Any / Hits@Hard / HHR | rare | ✓ | -- | ✓ |
| Precision / Recall / F1 | variable | ✓ | -- | ✓ |
| Rule mining | variable | AMIE3 | ✓ | ✓ |
| Symbolic candidate generation | variable | indirect | ✓ | ✓ |
| Explicit candidate proof | variable | benchmark construction | ✓ | ✓ |
| SHACL constraints | generally -- | -- | ✓ | ✓ |
| Differential (pre/post) validation | -- | -- | -- | ✓ |
| Candidate-level admission | -- | -- | not central | ✓ |
| Random-distractor control | rare | -- | -- | ✓ (E4) |
| Oracle-target control | rare | complete/incomplete KG | -- | ✓ (E6) |
| Grounding attribution | rare | answer-level | KG-level | ✓ (GRR) |
| KG × retriever × LLM analysis | variable | ✓ | not central | ✓ |
| Cross-environment (A/B) reproducibility check | rarely reported | not central | not central | ✓ |

### The distinction that matters: reasoning vs.\ evidence admission

BRINK asks: *can KG-RAG reason when direct evidence is missing?* This work
asks a narrower, downstream question: *given a symbolically generated
candidate under missing evidence, should that candidate be admitted as
evidence to the LLM?* CoPCA's SHACL validation targets KG completion
(Hits@1/3/5/10, MRR for embedding models); here SHACL is repurposed as a
candidate-level evidence-admission policy, not a KG-cleaning step. AMIE3 is
an infrastructural component (rule mining), not the contribution itself --
the contribution begins where a mined rule's grounding becomes a
constraint-checked evidence candidate.

### Final positioning statement

> Unlike prior KG-RAG studies that primarily evaluate retrieval and answer
> generation under incomplete knowledge, this work introduces an explicit
> candidate-level evidence-admission layer between symbolic inference and
> LLM generation. The layer uses differential SHACL validation to
> distinguish pre-existing graph violations from violations introduced by a
> newly inferred candidate.
>
> The experiments show that symbolic augmentation can recover part of the
> performance lost under deliberate incompleteness, while the current
> binary constraint gate does not consistently improve downstream answer
> quality. This negative result is itself informative: it indicates that
> constraint validity and answer utility are distinct properties.
>
> The resulting framework treats neuro-symbolic KG-RAG as a staged evidence
> pipeline -- generation, proof, admission, exposure, and answer
> attribution -- rather than as a single retrieval-to-generation operation.

A fully instrumented version of this pipeline would report $N_{pool}$
(candidates generated), $N_{proven}$ (candidates with a backward-chained
proof), $N_{admitted}$ (candidates passing $\Delta$SHACL), and $N_{shown}$
(candidates actually surviving the context budget) as four distinct,
per-question counts. The current codebase already logs all four per
question: `inferred_count` ($N_{proven}$), `shacl_valid_count`
($N_{admitted}$), and `context_count` ($N_{shown}$, computed from the
actual fused context after truncation, not the pre-truncation pool -- see
`driver.py`'s `_context_label_counts`); the raw candidate-pool size
($N_{pool}$) is likewise available from the checkpointed candidate lists
before proof-filtering. This decomposition is proposed here as the
natural next diagnostic layer to report explicitly and jointly, not as
a set of previously-unavailable measurements.
