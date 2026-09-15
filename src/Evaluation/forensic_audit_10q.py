"""26. Ten-question forensic audit."""

def pretty_facts(xs):
    out = []
    for x in xs or []:
        if isinstance(x, (list, tuple)) and len(x) >= 3:
            out.append(f"({local_name(x[0])}, {local_name(x[1])}, {local_name(x[2])})")
        elif isinstance(x, dict) and "head" in x:
            out.append(f"({local_name(x['head'][0])}, {local_name(x['head'][1])}, {local_name(x['head'][2])})")
    return "\n".join(out) if out else "(none)"

def forensic_table(name, retriever, mid, n=10, seed=42):
    base = QUESTIONS[name].sample(n=min(n, len(QUESTIONS[name])), random_state=seed)
    traces_by_cond = ALL_TRACES_BY_MODEL.get(mid, {})
    # A KG not yet processed produces an empty trace with no "question_id"
    # column (same underlying case as compare_retrievers).
    raw = {c: traces_by_cond.get((name, retriever, c)) for c in CONDITION_ORDER}
    if any(r is None or len(r) == 0 for r in raw.values()):
        return pd.DataFrame()
    traces = {
        c: (r.set_index("question_id") if isinstance(r, pd.DataFrame) and "question_id" in r.columns and not r.empty
            else pd.DataFrame())
        for c, r in raw.items()
    }
    rows = []
    for qid in base["question_id"]:
        if any(qid not in traces[c].index for c in CONDITION_ORDER):
            continue
        r = {c: traces[c].loc[qid] for c in CONDITION_ORDER}
        e2 = r["E2_incomplete_NS"]; e6 = r["E6_incomplete_oracle"]; e7 = r["E7_incomplete_NS_SHACL"]
        rows.append({
            "model_id": mid, "question_id": qid, "question": r["E0_complete_baseline"]["question"],
            "hard_gold": r["E0_complete_baseline"]["hard_answer"], "gold_answers": r["E0_complete_baseline"]["gold_answers"],
            "declared_E0": pretty_facts(r["E0_complete_baseline"]["evidence_declared"]),
            "declared_E1": pretty_facts(r["E1_incomplete_baseline"]["evidence_declared"]),
            "inferred_E2": pretty_facts(e2["evidence_inferred"]),
            "inferred_E3": pretty_facts(r["E3_incomplete_noPCA"]["evidence_inferred"]),
            "random_E4": pretty_facts(r["E4_incomplete_random"]["evidence_random"]),
            "oracle_E6": pretty_facts(e6["evidence_oracle"]),
            "shacl_valid_E7": pretty_facts(e7["evidence_shacl_valid"]),
            "shacl_invalid_E7": pretty_facts(e7["evidence_shacl_invalid"]),
            "shacl_unresolved_E7": pretty_facts(e7.get("evidence_shacl_unresolved", [])),
            "final_E2": pretty_facts(e2["context_facts"]), "final_E7": pretty_facts(e7["context_facts"]),
            "answer_E2": e2["prediction_raw"], "answer_E6": e6["prediction_raw"], "answer_E7": e7["prediction_raw"],
            "pca_proof_count": e2.get("pca_target_proof_count", 0), "all_proof_count": e2.get("all_target_proof_count", 0),
        })
    return pd.DataFrame(rows)

FORENSIC = {}
for mid in MODEL_ORDER:
    for name in EVALUABLE_DATASETS:
        (ARTIFACTS/name).mkdir(parents=True, exist_ok=True)
        for retriever in ACTIVE_RETRIEVERS:
            tab = forensic_table(name, retriever, mid, 10, SEED); FORENSIC[(mid, name, retriever)] = tab
            tab.to_csv(ARTIFACTS/name/f"FORENSIC_10_{mid}_{retriever}.csv", index=False)
            print("\n====", mid, name, retriever, "====")
            display(tab)
