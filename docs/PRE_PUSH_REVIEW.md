# Pre-push review

## Status
Pre-push review completed. The repository compiles and the automated test suite passes.
Repository identity and dataset-distribution references have also been normalized
to the canonical THIRDWAVE repository and project Figshare archive.

**Verification:** `python -m compileall -q src tests scripts` → PASS; `pytest -q` → **19 passed**.
Static secret scan found no embedded API-key patterns. A third-party lint run was not possible in the offline review environment, so CI remains the final lint/quality gate.

## Scientific contract
- BRINK metric semantics are centralized in `src/Evaluation/brink_metrics.py`.
- The benchmark is explicitly described as a **BRINK-style adaptation**, not an exact reproduction of BRINK's released construction script.
- CoPCA rule CSVs are authoritative; explicit AMIE footer/summary rows are metadata and are excluded from the lossless rule count.
- CoPCA SHACL `.ttl` files remain the authoritative shape graphs; validation-output logs are audit references only.
- Question IDs are derived from frozen split position, so re-runs do not renumber later questions after a dropped row.
- The small-pool 100-item test floor remains part of the frozen project protocol and is documented as such.
- Authoritative inputs resolve from the canonical `data/KG`, `data/Constraints`, and `data/Rules` tree; legacy CoPCA package paths are no longer required.
- The canonical repository is `SDM-TIB/EnergyKG-THIRDWAVE`, branch `constraint-gated-kg-rag`.
- DB100K and YAGO3-10 are distributed through the project Figshare archive rather than vendored as large Git files.

## Engineering contract
- Successful checkpoints are the only scientific answer records.
- Partial runs remain auditable and never masquerade as completed campaigns.
- Empty DataFrames are schema-safe in forensic and comparison utilities.
- No secrets are written to source files, caches, checkpoints, or manifests.
- CI compiles `src`, `tests`, and `scripts`, then runs pytest.

## Remaining declared limitation
SHACL behaviour on the project's tested Python/pySHACL environment remains a documented environment constraint; E7 results should only be reported from the validated runtime configuration described in `docs/KNOWN_LIMITATIONS.md`.
