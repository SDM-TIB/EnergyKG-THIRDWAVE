"""20. Retriever comparison diagnostics."""

# Loops over each model separately.
def compare_retrievers(name, condition, mid):
    if "onehop" not in ACTIVE_RETRIEVERS or "tog" not in ACTIVE_RETRIEVERS:
        return pd.DataFrame()

    traces = ALL_TRACES_BY_MODEL.get(mid, {})
    raw_a = traces.get((name, "onehop", condition))
    raw_b = traces.get((name, "tog", condition))
    # Guards an empty, columnless trace (unprocessed KG) against a KeyError.
    if raw_a is None or raw_b is None or len(raw_a) == 0 or len(raw_b) == 0:
        return pd.DataFrame()
    if not isinstance(raw_a, pd.DataFrame) or "question_id" not in raw_a.columns:
        raw_a = pd.DataFrame(columns=["question_id"])
    if not isinstance(raw_b, pd.DataFrame) or "question_id" not in raw_b.columns:
        raw_b = pd.DataFrame(columns=["question_id"])
    a = raw_a.set_index("question_id")
    b = raw_b.set_index("question_id")
    rows = []

    for qid in sorted(set(a.index) & set(b.index)):
        ra, rb = a.loc[qid], b.loc[qid]
        ca = {tuple(x[0]) for x in ra["context_facts"]}
        cb = {tuple(x[0]) for x in rb["context_facts"]}
        rows.append({
            "model_id": mid, "dataset": name, "condition": condition, "question_id": qid,
            "context_same": ca == cb,
            "context_jaccard": len(ca & cb) / len(ca | cb) if ca | cb else 1.0,
            "answer_same": process_prediction(ra["prediction_raw"]) == process_prediction(rb["prediction_raw"]),
            "onehop_context": len(ca), "tog_context": len(cb),
            "onehop_inferred": ra["inferred_count"], "tog_inferred": rb["inferred_count"],
        })
    return pd.DataFrame(rows)

RETRIEVER_DIAGNOSTICS = []
for mid in MODEL_ORDER:
    for name in EVALUABLE_DATASETS:
        (ARTIFACTS/name).mkdir(parents=True, exist_ok=True)
        for condition in CONDITION_ORDER:
            d = compare_retrievers(name, condition, mid)
            if len(d):
                RETRIEVER_DIAGNOSTICS.append({
                    "model_id": mid, "dataset": name, "condition": condition, "n": len(d),
                    "context_same_rate": d["context_same"].mean(),
                    "context_jaccard_mean": d["context_jaccard"].mean(),
                    "answer_same_rate": d["answer_same"].mean(),
                    "mean_onehop_context": d["onehop_context"].mean(),
                    "mean_tog_context": d["tog_context"].mean(),
                })
                d.to_csv(ARTIFACTS/name/f"diagnostic_onehop_vs_tog_{mid}_{condition}.csv", index=False)

RETRIEVER_DIAGNOSTICS = pd.DataFrame(RETRIEVER_DIAGNOSTICS)
RETRIEVER_DIAGNOSTICS.to_csv(ARTIFACTS/"RETRIEVER_ONEHOP_VS_TOG_DIAGNOSTICS.csv", index=False)
display(RETRIEVER_DIAGNOSTICS.round(4))
