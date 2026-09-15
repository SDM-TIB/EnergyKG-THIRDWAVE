"""25. Scientific decision report and reproducibility manifest."""

def dataset_manifest(name):
    d = DATA[name]
    b = BENCH.get(name) or make_gated_benchmark(name, "benchmark record unavailable")
    return {
        "dataset": name, "paths": {k: str(v) for k, v in d["cfg"].items()},
        "raw_rdf_triples": len(d["raw"]), "rdf_type_artifacts": int(d["type_mask"].sum()),
        "semantic_triples": len(d["semantic"]),
        "semantic_entities": len(set(d["semantic"].subject) | set(d["semantic"].object)),
        "semantic_relations": d["semantic"].relation.map(local_name).nunique(),
        "rules_total": len(RULES[name]), "rules_pca_ge_0_4": len(RULES_PCA[name]),
        "groundings_E2": len(GROUNDINGS[name]["E2"]), "groundings_E3": len(GROUNDINGS[name]["E3"]),
        "benchmark_status": b.get("status", "UNKNOWN"), "benchmark_reason": b.get("reason", ""),
        "eligible_pool_after_nrows": len(b.get("pool", [])),
        "split_train": len(b.get("splits", {}).get("train", [])),
        "split_validation": len(b.get("splits", {}).get("validation", [])),
        "split_test_facts": len(b.get("splits", {}).get("test", [])),
        # SHA-256 fingerprints of the pool and the split -- comparing these two
        # strings across two independent runs is enough to confirm an identical
        # benchmark down to its exact content, not merely its row counts.
        "pool_sha256": b.get("pool_sha256"), "split_sha256": b.get("split_sha256"),
        "test_questions": len(QUESTIONS.get(name, pd.DataFrame())),
        "incomplete_triples": len(b.get("incomplete", [])) if b.get("incomplete") is not None else None,
        "shacl_available": d["shacl_graph"] is not None,
    }

MANIFEST = {
    "created_by": f"CoPCA × BRINK × Zhou harmonized benchmark ({PERSIST_LABEL})",
    "seed": SEED, "datasets": ACTIVE_DATASETS, "evaluable_datasets": EVALUABLE_DATASETS,
    "gated_datasets": GATED_DATASETS, "dataset_readiness": DATASET_READY, "retrievers": ACTIVE_RETRIEVERS,
    "models": MODEL_CONFIGS, "model_order": MODEL_ORDER, "conditions": CONDITION_ORDER,
    "brink_split": {"nrows": BRINK_SPLIT_NROWS, "shuffle_seed": SPLIT_SEED,
        "ratios": "BRINK-style 80/10/10 with a documented 100-item test floor for small pools", "unit": "unique removable facts"},
    "retrieval": {"onehop": "deterministic one-hop adjacency retrieval", "tog": {"width": TOG_WIDTH, "depth": TOG_DEPTH},
        "pog": {"width": 3, "depth": 3, "subgoals_guidance_reflection": True},
        "structgpt": {"iterations": 3, "interface_linearization": True}},
    "context_max_facts": CONTEXT_MAX_FACTS, "max_declared_facts": MAX_DECLARED_FACTS, "min_pca_e2": MIN_PCA_E2,
    "max_groundings_per_rule": MAX_GROUNDINGS_PER_RULE, "token_log": MODEL_TOKEN_LOG,
    "datasets_detail": {name: dataset_manifest(name) for name in ACTIVE_DATASETS},
    "artifacts_root": str(ARTIFACTS), "checkpoints_root": str(CHECKPOINTS), "drive_root": str(ROOT),
}
write_json(ARTIFACTS/"FINAL_MANIFEST.json", MANIFEST)

# The scientific decision report (deltas E2-E1 / E2-E4 / E7-E2) loops over
# each model separately (RESULTS includes model_id).
decision_rows = []
for mid in MODEL_ORDER:
    for name in ACTIVE_DATASETS:
        for retriever in ACTIVE_RETRIEVERS:
            sub = RESULTS[(RESULTS["model_id"] == mid) & (RESULTS["dataset"] == name) & (RESULTS["retriever"] == retriever)].set_index("condition")

            delta_e2_e1 = (sub.loc["E2_incomplete_NS", "hits_hard"] - sub.loc["E1_incomplete_baseline", "hits_hard"]
                           if {"E2_incomplete_NS", "E1_incomplete_baseline"}.issubset(sub.index) else np.nan)
            delta_e2_e4 = (sub.loc["E2_incomplete_NS", "hits_hard"] - sub.loc["E4_incomplete_random", "hits_hard"]
                           if {"E2_incomplete_NS", "E4_incomplete_random"}.issubset(sub.index) else np.nan)
            delta_e7_e2 = (sub.loc["E7_incomplete_NS_SHACL", "hits_hard"] - sub.loc["E2_incomplete_NS", "hits_hard"]
                           if {"E7_incomplete_NS_SHACL", "E2_incomplete_NS"}.issubset(sub.index) else np.nan)

            decision_rows.append({"model_id": mid, "dataset": name, "retriever": retriever,
                "delta_HitsHard_E2_minus_E1": delta_e2_e1, "delta_HitsHard_E2_minus_E4": delta_e2_e4,
                "delta_HitsHard_E7_minus_E2": delta_e7_e2})

DECISION = pd.DataFrame(decision_rows)
DECISION.to_csv(ARTIFACTS/"SCIENTIFIC_DECISION_REPORT.csv", index=False)

display(DECISION.round(4))
print("Scientific decision report:", ARTIFACTS / "SCIENTIFIC_DECISION_REPORT.csv")
