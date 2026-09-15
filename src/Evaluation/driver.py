"""Resumable, tiered, dataset-first driver: a KG is fully completed, per
model, before the next KG starts."""

import time, json, os, shutil

def atomic_json_write(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)

def durable_append_jsonl(path, rec):
    # flush+fsync: survive an interruption mid-write.
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        f.flush(); os.fsync(f.fileno())

def failure_path(mid, name, ret, cond): return FAILURES/mid/name/ret/f"{cond}.failures.jsonl"
def checkpoint_meta_path(mid, name, ret, cond): return CHECKPOINTS/mid/name/ret/f"{cond}.meta.json"
def condition_path(mid, name, ret, cond): return CHECKPOINTS/mid/name/ret/f"{cond}.jsonl"
def dataset_marker(mid, name): return STATE/f"{mid}__{name}__DATASET_COMPLETE.json"
def tier_marker(mid, name, tier): return STATE/f"{mid}__{name}__TIER_{tier}_COMPLETE.json"
def full_question_fingerprint(name): return fingerprint_questions(QUESTIONS[name])

def tier_df(name, tier):
    q = QUESTIONS[name].copy().reset_index(drop=True)
    return q.iloc[:min(int(tier), len(q))].copy().reset_index(drop=True)

def available_tiers(name):
    # Always include the true test-set size, so no question is ever skipped.
    n = len(QUESTIONS.get(name, []))
    tiers = [t for t in QUESTION_TIERS if t <= n]
    if n and (not tiers or tiers[-1] != n):
        tiers.append(n)
    return tiers

def unavailable_tiers(name):
    n = len(QUESTIONS.get(name, []))
    return [t for t in QUESTION_TIERS if t > n]

def _question_row_matches(name, qid, rec):
    # Per-question content match, not a global fingerprint.
    cur = QUESTIONS[name]
    match = cur[cur["question_id"].astype(str) == str(qid)]
    if match.empty:
        return False
    m = match.iloc[0]
    return (str(rec.get("question")) == str(m["question"]) and
            str(rec.get("topic_entity")) == str(m["topic_entity"]) and
            str(rec.get("relation")) == str(m["relation"]) and
            str(rec.get("hard_answer")) == str(m["hard_answer"]))

def condition_complete(mid, name, ret, cond, qdf):
    rows = load_checkpoint(condition_path(mid, name, ret, cond)); qids = set(map(str, qdf.question_id))
    if not qids.issubset(rows): return False
    # NS-dependent conditions also need a matching pipeline version.
    return all(_question_row_matches(name, qid, rows[qid]) and rows[qid].get("llm_status") == "OK"
               and (cond not in NS_DEPENDENT_CONDITIONS or rows[qid].get("evidence_pipeline_version") in {None, EVIDENCE_PIPELINE_VERSION})
               for qid in qids)

def tier_complete(mid, name, tier):
    qdf = tier_df(name, tier)
    if len(qdf) < tier: return False
    return all(condition_complete(mid, name, r, c, qdf) for r in ACTIVE_RETRIEVERS for c in CONDITION_ORDER)

def dataset_complete(mid, name):
    tiers = available_tiers(name)
    if not tiers: return False
    return all(tier_complete(mid, name, t) for t in tiers)

def _context_label_counts(context_facts):
    """Counts from the actual fused context, not the pre-truncation pool."""
    counts = {"declared_in_context": 0, "inferred_in_context": 0, "random_in_context": 0,
              "oracle_in_context": 0, "shacl_validated_in_context": 0, "other_in_context": 0}
    for _fact, label in context_facts:
        if label in ("DECLARED", "DECLARED_BACKFILL"):
            counts["declared_in_context"] += 1
        elif label.startswith("INFERRED"):
            counts["inferred_in_context"] += 1
        elif label == "RANDOM":
            counts["random_in_context"] += 1
        elif label == "ORACLE":
            counts["oracle_in_context"] += 1
        elif label == "SHACL_VALIDATED":
            counts["shacl_validated_in_context"] += 1
        else:
            counts["other_in_context"] += 1
    return counts

def build_record(name, ret, cond, mid, qrow, ev, qdf):
    raw = answer_question(qrow["question"], ev["context"], f"{mid}:{name}:{ret}:{cond}:{qrow['question_id']}", mid)
    context_label_counts = _context_label_counts(ev["context"])
    return {"model_id": mid, "model_name": MODEL_CONFIGS[mid]["model_name"], "dataset": name, "retriever": ret, "condition": cond,
      "question_id": str(qrow["question_id"]), "question": qrow["question"], "topic_entity": qrow["topic_entity"], "relation": qrow["relation"],
      "hard_answer": qrow["hard_answer"], "gold_answers": qrow["gold_answers"], "head": qrow["head"], "prediction_raw": raw, "llm_status": "OK",
      "context_facts": ev["context"], "context_count": len(ev["context"]),
      "declared_count": len(ev["declared"]), "inferred_count": len(ev["inferred"]),
      "random_count": len(ev["random"]), "oracle_count": len(ev["oracle"]), "shacl_valid_count": len(ev["shacl_valid"]), "shacl_invalid_count": len(ev["shacl_invalid"]),
      "shacl_unresolved_count": len(ev.get("shacl_unresolved", [])), **context_label_counts, "evidence_declared": ev["declared"], "evidence_inferred": ev["inferred"],
      "evidence_random": ev["random"], "evidence_oracle": ev["oracle"], "evidence_shacl_valid": ev["shacl_valid"], "evidence_shacl_invalid": ev["shacl_invalid"],
      "evidence_shacl_unresolved": ev.get("shacl_unresolved", []), "shacl_status": ev["shacl_status"], "inference_records": ev.get("inference_records", []),
      "retrieval_trace": ev.get("retrieval_trace", {}), "question_fingerprint_full": full_question_fingerprint(name), "tier_last_seen": len(qdf),
      "evidence_pipeline_version": EVIDENCE_PIPELINE_VERSION,
      "universe_fingerprint": fingerprint_universe(COMMON_UNIVERSE[name]), "completed_at": time.time()}

def run_condition_model_tier(name, ret, cond, mid, qdf):
    path = condition_path(mid, name, ret, cond); existing = load_checkpoint(path)
    # Drop only entries whose content no longer matches; never truncate the file.
    bad_qids = [qid for qid, r in existing.items()
                if not (_question_row_matches(name, qid, r) and r.get("llm_status") == "OK")
                or (cond in NS_DEPENDENT_CONDITIONS and r.get("evidence_pipeline_version") not in {None, EVIDENCE_PIPELINE_VERSION})]
    if bad_qids:
        for qid in bad_qids:
            existing.pop(qid, None)
        print(f"[REBASE] {mid}/{name}/{ret}/{cond}: {len(bad_qids)} stale entrie(s), recomputing only these.")
    if mid in LLM_RUNTIME_STATE.get("blocked_models", {}): return False
    for _question_index, (_, qrow) in enumerate(tqdm(qdf.iterrows(), total=len(qdf), desc=f"{mid}/{name}/tier{len(qdf)}/{ret}/{cond}")):
        qid = str(qrow["question_id"])
        if qid in existing and existing[qid].get("llm_status") == "OK": continue
        try:
            # Cache full per-question evidence (name, ret, mid)-scoped: avoids
            # redoing e2/e3/e5 + SHACL for every condition on the same question.
            scope_key = (name, ret, mid)
            if _EVIDENCE_CACHE.get("_scope") != scope_key:
                _EVIDENCE_CACHE.clear()
                _EVIDENCE_CACHE["_scope"] = scope_key
            if qid not in _EVIDENCE_CACHE:
                _EVIDENCE_CACHE[qid] = build_evidence_for_question(name, ret, qrow, mid)
            ev = _EVIDENCE_CACHE[qid][cond]
            rec = build_record(name, ret, cond, mid, qrow, ev, qdf)
            durable_append_jsonl(path, rec); existing[qid] = rec
            # Periodic GC, E7 only: bounds memory growth from repeated SHACL graph copies.
            if cond == "E7_incomplete_NS_SHACL" and _question_index % 10 == 0:
                gc.collect()
        except LLMCallError as exc:
            durable_append_jsonl(failure_path(mid, name, ret, cond), {"model_id": mid, "dataset": name, "retriever": ret, "condition": cond, "question_id": qid,
              "error": str(exc), "auth_error": exc.auth, "quota_error": exc.quota, "status_code": exc.status_code, "retryable": exc.retryable, "timestamp": time.time()})
            print(f"[SAFE STOP / RESUME] {mid}/{name}/tier{len(qdf)}/{ret}/{cond}/{qid}: {exc}")
            if exc.auth or exc.quota: return False
        except Exception as exc:
            durable_append_jsonl(failure_path(mid, name, ret, cond), {"model_id": mid, "dataset": name, "retriever": ret, "condition": cond, "question_id": qid,
              "error": f"UNEXPECTED: {type(exc).__name__}: {exc}", "auth_error": False, "quota_error": False, "status_code": None, "retryable": False, "timestamp": time.time()})
            print(f"[QUESTION ERROR -- RESUME] {mid}/{name}/tier{len(qdf)}/{ret}/{cond}/{qid}: {type(exc).__name__}: {exc}")
    if condition_complete(mid, name, ret, cond, qdf):
        atomic_json_write(checkpoint_meta_path(mid, name, ret, cond), {"status": "COMPLETE", "model_id": mid, "dataset": name, "retriever": ret, "condition": cond,
          "tier": len(qdf), "questions": len(qdf), "question_fingerprint_full": full_question_fingerprint(name),
          "universe_fingerprint": fingerprint_universe(COMMON_UNIVERSE[name]), "checkpoint": str(path), "completed_at": time.time()})
        return True
    return False

def load_all_condition_traces(mid):
    # Excludes entries whose tier hasn't been (re)processed yet.
    traces = {}
    for name in RUN_DATASETS:
        for ret in ACTIVE_RETRIEVERS:
            for cond in CONDITION_ORDER:
                rows = load_checkpoint(condition_path(mid, name, ret, cond))
                valid = {qid: r for qid, r in rows.items()
                         if r.get("llm_status") == "OK" and _question_row_matches(name, qid, r)}
                traces[(name, ret, cond)] = (pd.DataFrame(list(valid.values())).sort_values("question_id").reset_index(drop=True) if valid else pd.DataFrame())
    return traces

def display_kg_results(name):
    """Display only completed traces for the current KG."""
    rows = []
    for mid in MODEL_ORDER:
        for ret in ACTIVE_RETRIEVERS:
            for cond in CONDITION_ORDER:
                data = load_checkpoint(condition_path(mid, name, ret, cond))
                valid = [r for r in data.values() if r.get("llm_status") == "OK" and _question_row_matches(name, r.get("question_id"), r)]
                if not valid:
                    continue
                metrics = aggregate_metrics((r["prediction_raw"], r["gold_answers"], r["hard_answer"]) for r in valid)
                rows.append({"dataset": name, "model_id": mid, "retriever": ret, "condition": cond, **metrics})
    if not rows:
        print(f"{name}: no completed traces.")
        return
    table = pd.DataFrame(rows).sort_values(["model_id", "retriever", "condition"])
    table.to_csv(ARTIFACTS/name/"KG_RESULTS_ON_COMPLETION.csv", index=False)
    display(table.round(4))

_EVIDENCE_CACHE = {}
RUN_DATASETS = [n for n in ACTIVE_DATASETS if BENCH.get(n, {}).get("ready") is True]
ALL_TRACES_BY_MODEL = {}; MODEL_RUN_SUMMARY = []; KG_PROGRESS = []

# Model-first loop: each model progresses through KGs independently; a
# blocked model never stops the other model's progress.
for mid in MODEL_ORDER:
    print(f"\nMODEL {mid}")
    for name in RUN_DATASETS:
        print(f"KG {name} | model={mid}")
        avail = available_tiers(name); unavailable = unavailable_tiers(name)
        print(f"  questions={len(QUESTIONS[name])}; tiers={avail}")
        if not avail:
            KG_PROGRESS.append({"dataset": name, "model_id": mid, "status": "NOT_EVALUABLE", "reason": "no test questions"})
            print(f"  skipped: no test questions")
            continue

        t0 = time.time(); model_ok = True
        if mid in LLM_RUNTIME_STATE.get("blocked_models", {}):
            model_ok = False
            print(f"  blocked: {LLM_RUNTIME_STATE['blocked_models'][mid]}")
        for tier in avail:
            if not model_ok: break
            qdf = tier_df(name, tier)
            if tier_complete(mid, name, tier):
                print(f"  tier {tier}: resume")
                continue
            for ret in ACTIVE_RETRIEVERS:
                if not model_ok: break
                for cond in CONDITION_ORDER:
                    if not run_condition_model_tier(name, ret, cond, mid, qdf):
                        model_ok = False; break
                if not model_ok: break
                print(f"  {ret}: complete")
            if model_ok and tier_complete(mid, name, tier):
                atomic_json_write(tier_marker(mid, name, tier), {"status": "COMPLETE", "model_id": mid, "dataset": name, "tier": tier, "completed_at": time.time()})
                print(f"  tier {tier}: complete")
            else:
                print(f"  tier {tier}: incomplete")
                model_ok = False

        status = "COMPLETE" if model_ok and dataset_complete(mid, name) else "PARTIAL_OR_DEFERRED"
        KG_PROGRESS.append({"dataset": name, "model_id": mid, "status": status,
                            "available_tiers": ";".join(map(str, avail)), "unavailable_tiers": ";".join(map(str, unavailable)),
                            "elapsed_seconds": time.time()-t0})

        if status == "COMPLETE":
            atomic_json_write(dataset_marker(mid, name), {"status": "COMPLETE", "model_id": mid, "dataset": name, "tiers": avail, "unavailable_tiers": unavailable, "completed_at": time.time()})
            print(f"KG COMPLETE: {name} / {mid}")
            display_kg_results(name)
        else:
            print(f"KG PAUSED: {name} / {mid}")
            break

for mid in MODEL_ORDER: ALL_TRACES_BY_MODEL[mid] = load_all_condition_traces(mid)
ALL_TRACES = ALL_TRACES_BY_MODEL.get(MODEL_ORDER[0], {}) if MODEL_ORDER else {}
MODEL_RUN_SUMMARY = pd.DataFrame(KG_PROGRESS)
MODEL_RUN_SUMMARY.to_csv(ARTIFACTS/"KG_PROGRESS.csv", index=False)
write_json(ARTIFACTS/"RESUME_STATE.json", {"datasets": RUN_DATASETS, "retrievers": ACTIVE_RETRIEVERS, "conditions": CONDITION_ORDER, "tiers": QUESTION_TIERS,
  "available_tiers_by_dataset": {n: available_tiers(n) for n in RUN_DATASETS}, "strict_gate_scope": "per_model",
  "blocked_models": LLM_RUNTIME_STATE.get("blocked_models", {}), "kg_progress": KG_PROGRESS})
print("\nRun summary")
display(pd.DataFrame(KG_PROGRESS))
