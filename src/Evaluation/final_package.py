"""Final persistent package (zip/csv/jsonl), strict KG sequential."""


# Final dataset-local gate summary.
for _name in ACTIVE_DATASETS:
    _ready=bool(DATASET_READY.get(_name,False))
    _reason=""
    if not _ready:
        _parts=[]
        if not RULES_LOSSLESS_BY_DATASET.get(_name,False): _parts.append("non-lossless authoritative rule parsing")
        if not SHACL_AVAILABLE_BY_DATASET.get(_name,False): _parts.append("authoritative SHACL unavailable")
        if not _parts and not SHACL_AUDIT_DEFINED: _parts.append("SHACL audit unavailable")
        _reason="; ".join(_parts) or "source preflight not ready"
    elif _name in QUESTIONS:
        _reason=f"test={len(QUESTIONS[_name])}; available_tiers={available_tiers(_name)}; unavailable_tiers={unavailable_tiers(_name)}"
    print(f"{_name}: {'READY' if _ready else 'NOT_READY'}" + (f" — {_reason}" if _reason else ""))
print("No dataset-local source gate is allowed to terminate notebook execution.")
print("Only an incomplete CURRENT KG blocks transition to the NEXT KG.")


# Final execution invariant.
assert "BENCH" in globals()
for _name in ACTIVE_DATASETS:
    _b=BENCH[_name]
    assert isinstance(_b,dict)
    assert _b.get("status") in {"READY","NOT_READY"}
    assert isinstance(_b.get("pool",[]),pd.DataFrame)
    assert isinstance(_b.get("splits",{}),dict)
    assert all(isinstance(_b["splits"].get(k,pd.DataFrame()),pd.DataFrame) for k in ("train","validation","test"))
    if _b.get("ready") and _name in QUESTIONS:
        # A dropped answer-leaking question is intended; check <=, not ==.
        assert len(QUESTIONS[_name])<=len(_b["splits"]["test"])
        assert len(QUESTIONS[_name])<=len(_b["pool"])  # no fixed target anymore; only the pool bounds the test size
print("FINAL EXECUTION INVARIANT: PASS")
print("Ready:",EVALUABLE_DATASETS)
print("Gated:",GATED_DATASETS)
for _name in EVALUABLE_DATASETS:
    print(_name,"| test:",len(QUESTIONS[_name]),"| available tiers:",available_tiers(_name),"| unavailable:",unavailable_tiers(_name))


# Final method/model manifest.
MANIFEST_V16 = {"benchmark": f"CoPCA × BRINK × Zhou — resumable harmonized benchmark ({PERSIST_LABEL})",
    "datasets": ACTIVE_DATASETS, "datasets_executed": RUN_DATASETS, "retrievers": ACTIVE_RETRIEVERS,
    "models": MODEL_CONFIGS, "model_order": MODEL_ORDER, "sequential_models": True,
    "HHR": "Hits@Hard / Hits@Any", "rules": "authoritative CoPCA CSV",
    "shacl": "authoritative CoPCA TTL + explicit validator status", "target_logs": "audit references only; not fact triples",
    # Model weights are cached on persistent storage; API credentials are runtime-only.
    "llm": "local transformers inference from Kaggle Model weights fetched once via kagglehub "
           "(cached on the GCE persistent disk across VM stop/start cycles), "
           "4-bit (bitsandbytes) on GPU when available, fp32 CPU fallback; "
           "no interactive prompts; local Kaggle-model inference or a configured API backend, depending on MODEL_CONFIGS.",
    "credential_policy": "secrets are read at runtime and never persisted", "retry": {"max_retries": LLM_MAX_RETRIES, "timeout_seconds": LLM_TIMEOUT_SECONDS,
    "backoff_base": LLM_BACKOFF_BASE, "backoff_max": LLM_BACKOFF_MAX}, "cache": "successful responses only; token excluded from cache key",
    "failure_policy": "failed generations are not answer checkpoints; they are retried/resumed later",
    "split": {"pool_cap": BRINK_SPLIT_NROWS, "seed": SPLIT_SEED, "split_ratios_train_val_test": BRINK_SPLIT_RATIOS,
             "policy": "BRINK-style 80/10/10 split with a documented 100-item test floor for small pools; "
                       "this is a project adaptation, not an exact reproduction of the released BRINK construction script"},
    "question_generation": "BRINK-style adaptation, not an exact reproduction of BRINK's "
                       "question_generation.py: the Question Entity (topic_entity) is always "
                       "fixed to the SUBJECT of the removed (head, relation, tail) triple; "
                       "BRINK instead randomly designates either endpoint as the Question "
                       "Entity, with the other as the Answer Entity. This halves the linguistic "
                       "direction space of generated questions relative to BRINK. Kept as-is "
                       "for this frozen benchmark (changing it would require regenerating and "
                       "refreezing the question set, invalidating existing SHA-256 fingerprints "
                       "and all computed results); documented explicitly rather than claimed as "
                       "exact BRINK conformance.",
    "tier_policy": "Tiers 10/50/100/200 are nested prefixes of the same frozen "
                   "test set, kept ONLY as engineering tools (smoke testing, bug "
                   "detection, throughput profiling) -- they are NEVER a final "
                   "scientific result on their own. Only the state after the LAST "
                   "available tier (covering 100% of the BRINK-proportional test "
                   "set) is a reportable result; intermediate tiers are not.",
    "dataset_gate": "a KG must complete every available tier for every model/retriever/condition before the next KG starts",
    "persistence": f"all state (cache/checkpoints/artifacts/state/failures/model_cache) lives under {PERSIST_LABEL}; "
                    "survives runtime disconnects, internet outages and power loss"}
write_json(ARTIFACTS/"METHOD_MODEL_MANIFEST.json", MANIFEST_V16)
print("Method/model manifest written.")


# Local runtime status (loading, retries, failures); columns kept for compatibility.
quota_status = pd.DataFrame([
    {
        "model_id": mid,
        "model_name": MODEL_CONFIGS[mid]["model_name"],
        "status": LLM_RUNTIME_STATE.get("blocked_models", {}).get(mid, "AVAILABLE_OR_NOT_TESTED"),
        "calls_local": MODEL_TOKEN_LOG[mid]["calls"],
        "api_calls": MODEL_TOKEN_LOG[mid].get("api_calls", 0),
        "api_failures": MODEL_TOKEN_LOG[mid].get("api_failures", 0),
        "cache_hits": MODEL_TOKEN_LOG[mid]["cache_hits"],
        "failures": MODEL_TOKEN_LOG[mid]["failures"],
        "retries": MODEL_TOKEN_LOG[mid]["retries"],
        "auth_or_load_blocked": MODEL_TOKEN_LOG[mid]["auth_blocked"],
    }
    for mid in MODEL_ORDER
])
quota_status.to_csv(ARTIFACTS / "LLM_RUNTIME_STATUS.csv", index=False)
display(quota_status)
print("No loading/authentication condition is ever treated as a scientific success.")
print("Deferred questions stay absent from the answer checkpoints and remain eligible for a later resume.")


# Final zip/csv/jsonl package; ROOT is already persistent, this is a convenience copy.
from zipfile import ZipFile, ZIP_DEFLATED
completion_rows = []
ARTIFACTS.mkdir(parents=True, exist_ok=True)
for mid in MODEL_ORDER:
    for name in RUN_DATASETS:
        # Uses the KG's actual active tiers, not the (now empty) global QUESTION_TIERS.
        for tier in available_tiers(name):
            n_questions = len(QUESTIONS.get(name, [])) if name in QUESTIONS else 0
            available = tier <= n_questions
            qdf = tier_df(name, tier) if name in QUESTIONS else pd.DataFrame()
            qids = set(map(str, qdf.question_id)) if available else set()
            for ret in ACTIVE_RETRIEVERS:
                for cond in CONDITION_ORDER:
                    rows = load_checkpoint(condition_path(mid, name, ret, cond))
                    valid = sum(1 for qid in qids if qid in rows and rows[qid].get("llm_status") == "OK")
                    complete = int(available and valid == len(qids) and condition_complete(mid, name, ret, cond, qdf))
                    completion_rows.append({"model_id": mid, "dataset": name, "tier": tier, "available": available, "retriever": ret, "condition": cond,
                        "questions_expected": len(qids), "questions_valid_for_tier": valid, "complete": complete})
completion = pd.DataFrame(completion_rows)
completion.to_csv(ARTIFACTS/"CHECKPOINT_COMPLETION_INDEX.csv", index=False)
manifest = {"benchmark": f"CoPCA × BRINK × Zhou — strict dataset-first resumable benchmark ({PERSIST_LABEL})", "models": MODEL_CONFIGS, "model_order": MODEL_ORDER,
"datasets": RUN_DATASETS, "retrievers": ACTIVE_RETRIEVERS, "conditions": CONDITION_ORDER, "tiers_requested": QUESTION_TIERS,
"strict_dataset_gate": True, "policy": "A KG must complete every AVAILABLE tier (10/50/100/200) for every model/retriever/condition before the next KG starts; unavailable tiers do not block.",
"split": {"pool_cap": BRINK_SPLIT_NROWS, "seed": SPLIT_SEED, "split_ratios_train_val_test": BRINK_SPLIT_RATIOS,
         "policy": "BRINK-style 80/10/10 with a documented 100-item test floor for small pools"},
"question_generation": "BRINK-style adaptation: topic_entity is fixed to the SUBJECT of the "
         "removed triple, not randomly chosen between both endpoints as in BRINK's own "
         "question_generation.py -- documented deviation, not exact BRINK conformance.",
"checkpoint_policy": "successful records append+flush+fsync; nested tiers reuse validated question IDs; failures never count as scientific answers",
"persistent_root": str(ROOT), "artifacts_root": str(ARTIFACTS), "checkpoints_root": str(CHECKPOINTS), "created_at": time.time()}
write_json(ARTIFACTS/"FINAL_RESUMABLE_MANIFEST.json", manifest)
PACKAGE = ROOT/f"CoPCA_BRINK_Zhou_SEQUENTIAL_KG_COMPLETE_{time.strftime('%Y%m%d_%H%M%S')}.zip"
with ZipFile(PACKAGE, "w", ZIP_DEFLATED) as z:
    for base in [ARTIFACTS, CHECKPOINTS, STATE, FAILURES, CACHE]:
        if base.exists():
            for fp in base.rglob("*"):
                if fp.is_file():
                    z.write(fp, arcname=str(fp.relative_to(ROOT)))
print(f"FINAL PACKAGE (on {PERSIST_LABEL}):", PACKAGE)
print("Completed KG/model pairs:", sum(1 for x in KG_PROGRESS if x.get("status") == "COMPLETE"))
print(f"Persistent root ({PERSIST_LABEL}):", ROOT)


