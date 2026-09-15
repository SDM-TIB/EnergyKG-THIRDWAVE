"""5b. Data-integrity preflight -- rules + SHACL."""


print("=" * 80)
print("CoPCA x BRINK scientific source preflight")
print("=" * 80)

display(RULE_AUDIT if "RULE_AUDIT" in globals() else pd.DataFrame())
display(SHACL_AUDIT if "SHACL_AUDIT" in globals() else pd.DataFrame())
display(SHACL_CONSTRAINT_AUDIT if "SHACL_CONSTRAINT_AUDIT" in globals() else pd.DataFrame())
display(LOG_AUDIT if "LOG_AUDIT" in globals() else pd.DataFrame())

SHACL_AUDIT_DEFINED = "SHACL_AUDIT" in globals()
RULES_LOSSLESS_BY_DATASET = {
    n: bool(
        len(RULE_AUDIT[RULE_AUDIT["dataset"] == n]) == 1
        and bool(RULE_AUDIT.loc[RULE_AUDIT["dataset"] == n, "lossless"].iloc[0])
    )
    for n in ACTIVE_DATASETS
}
SHACL_AVAILABLE_BY_DATASET = {
    n: DATA[n]["shacl_graph"] is not None for n in ACTIVE_DATASETS
}
DATASET_READY = {
    n: bool(SHACL_AUDIT_DEFINED and RULES_LOSSLESS_BY_DATASET[n] and SHACL_AVAILABLE_BY_DATASET[n])
    for n in ACTIVE_DATASETS
}
# Summary only; does not gate clean datasets.
RULES_LOSSLESS = all(RULES_LOSSLESS_BY_DATASET.values())
# Dataset-local readiness controls evaluation.
EXPERIMENT_READY = bool(DATASET_READY) and all(DATASET_READY.values())
EVALUABLE_DATASETS = [n for n in ACTIVE_DATASETS if DATASET_READY[n]]
GATED_DATASETS = [n for n in ACTIVE_DATASETS if not DATASET_READY[n]]

print("\nSHACL_AUDIT_DEFINED =", SHACL_AUDIT_DEFINED)
print("RULES_LOSSLESS_BY_DATASET =", RULES_LOSSLESS_BY_DATASET)
print("SHACL_AVAILABLE_BY_DATASET =", SHACL_AVAILABLE_BY_DATASET)
print("DATASET_READY =", DATASET_READY)
print("EVALUABLE_DATASETS =", EVALUABLE_DATASETS)
print("GATED_DATASETS =", GATED_DATASETS)

if not RULES_LOSSLESS:
    display(RULE_AUDIT[RULE_AUDIT["parse_failures"] > 0][
        ["dataset","csv_rows","parsed_rules","parse_failures"]
    ])
    print(
        "DATASET-LOCAL GATE: only datasets with lossless authoritative rules "
        "remain eligible; other datasets are excluded from evaluation."
    )

if not all(SHACL_AVAILABLE_BY_DATASET.values()):
    print("DATASET-LOCAL GATE: datasets without authoritative SHACL are excluded.")

print(
    "\nE7 provenance: the dataset-specific CoPCA .ttl file is passed to "
    "pySHACL. targets_valid.log / targets_violated.log are independent "
    "validation-output artifacts and are NOT SHACL shape graphs."
)

# Prints the exact cause for each gated dataset, not just a failure count.
for _name in GATED_DATASETS:
    print(f"\n{'=' * 80}\nDETAILED DIAGNOSTIC -- {_name} (gated)\n{'=' * 80}")
    _shacl_path = DATA[_name]["cfg"]["shacl"]
    _shacl_ok = SHACL_AVAILABLE_BY_DATASET.get(_name, False)
    print(f"SHACL: resolved path = {_shacl_path}")
    print(f"       exists on disk = {Path(_shacl_path).exists()} | loaded successfully = {_shacl_ok}")
    if not _shacl_ok:
        print("       -> the .ttl file is missing or empty at this exact path. Check that the "
              "attached Kaggle Dataset contains Constraints/<KG>/<KG>.ttl with EXACTLY this "
              "capitalization (YAGO3-10 vs Yago3-10 vs yago3-10 are three different paths on a "
              "case-sensitive filesystem).")
    if not RULES_LOSSLESS_BY_DATASET.get(_name, True):
        _fail_path = ARTIFACTS / _name / "rule_parse_failures.csv"
        print(f"\nRules: {int(RULE_AUDIT.loc[RULE_AUDIT['dataset']==_name,'parse_failures'].iloc[0])} "
              f"unparsed line(s) out of {int(RULE_AUDIT.loc[RULE_AUDIT['dataset']==_name,'csv_rows'].iloc[0])} "
              f"(full detail: {_fail_path})")
        try:
            _fdf = pd.read_csv(_fail_path)
            print("Sample of the first 5 unparsed lines (raw content + exact error):")
            for _, _r in _fdf.head(5).iterrows():
                print(f"  - body_raw={_r['body_raw']!r} head_raw={_r['head_raw']!r} -> {_r['error']}")
            print("\n=> If this failure mode is not already covered by parse_rule_row()/"
                  "_parse_atom_group(), extend the parser for this exact format based on the "
                  "raw lines above, rather than guessing a fix without having seen the real file.")
        except Exception as _e:
            print(f"(could not re-read {_fail_path}: {_e})")
