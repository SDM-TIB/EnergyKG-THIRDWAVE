"""30. Final two-LLM manifest / invariants."""

FINAL_TWO_LLM_MANIFEST={"benchmark":"CoPCA × BRINK",
    "datasets_configured":ACTIVE_DATASETS,"datasets_executed":RUN_DATASETS,
    "datasets_gated":sorted(set(ACTIVE_DATASETS)-set(RUN_DATASETS)),"models":MODEL_CONFIGS,"retrievers":ACTIVE_RETRIEVERS,
    "conditions":CONDITION_ORDER,"tiers_requested":QUESTION_TIERS,"HHR":"Hits@Hard / Hits@Any",
    "rules":"authoritative CoPCA CSV; lossless parse required","SHACL":"authoritative CoPCA TTL + pySHACL",
    "target_logs":"audit references only; not fact triples",
    "split":{"nrows":BRINK_SPLIT_NROWS,"seed":SPLIT_SEED,"split_ratios_train_val_test":BRINK_SPLIT_RATIOS,
             "policy":"BRINK-style 80/10/10 with a documented 100-item test floor for small pools"},
    "question_generation": "BRINK-style adaptation: topic_entity is fixed to the SUBJECT of the "
             "removed triple, not randomly chosen between both endpoints as in BRINK's own "
             "question_generation.py -- documented deviation, not exact BRINK conformance.",
    "strict_dataset_gate":"complete all AVAILABLE tiers before next KG; unavailable nominal tiers never block execution"}
write_json(ARTIFACTS/"FINAL_TWO_LLM_MANIFEST.json",FINAL_TWO_LLM_MANIFEST)
for mid,traces in ALL_TRACES_BY_MODEL.items():
    for (name,ret,cond),df in traces.items():
        if len(df)==0 or name not in QUESTIONS: continue
        assert df.question_id.is_unique
        assert set(df.question_id.astype(str)).issubset(set(QUESTIONS[name].question_id.astype(str)))
print("FINAL TWO-LLM INVARIANTS: PASS")
