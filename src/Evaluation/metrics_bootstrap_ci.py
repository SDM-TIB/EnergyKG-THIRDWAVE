"""18. Metrics + question-level audit + bootstrap 95% CIs."""

# Rebuilt for every model (not just the first); norm_answer/parse_answer reused.

def metric_row(df):
    vals = []
    for _, row in df.iterrows():
        pred = process_prediction(row["prediction_raw"])
        gold = {normalize_answer(x) for x in row["gold_answers"] if normalize_answer(x)}
        hard = normalize_answer(row["hard_answer"])
        inter = pred & gold
        p = len(inter) / len(pred) if pred else 0.0
        r = len(inter) / len(gold) if gold else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        vals.append({"hit_any": bool(inter), "hit_hard": hard in pred, "precision": p, "recall": r, "f1": f1})

    v = pd.DataFrame(vals)
    return {
        "n": len(df),
        "hits_any": float(v["hit_any"].mean()) if len(v) else np.nan,
        "hits_hard": float(v["hit_hard"].mean()) if len(v) else np.nan,
        "hhr": float(v["hit_hard"].sum() / v["hit_any"].sum()) if len(v) and v["hit_any"].sum() else np.nan,
        "precision": float(v["precision"].mean()) if len(v) else np.nan,
        "recall": float(v["recall"].mean()) if len(v) else np.nan,
        "f1": float(v["f1"].mean()) if len(v) else np.nan,
        "avg_context_facts": float(df["context_count"].mean()) if len(df) else np.nan,
        "avg_declared": float(df["declared_count"].mean()) if len(df) else np.nan,
        "avg_inferred": float(df["inferred_count"].mean()) if len(df) else np.nan,
        "avg_random": float(df["random_count"].mean()) if len(df) else np.nan,
        "avg_oracle": float(df["oracle_count"].mean()) if len(df) else np.nan,
        "avg_shacl_validated": float(df["shacl_valid_count"].mean()) if len(df) else np.nan,
        "avg_shacl_invalid": float(df["shacl_invalid_count"].mean()) if len(df) else np.nan,
        "avg_shacl_unresolved": float(df["shacl_unresolved_count"].mean()) if len(df) else np.nan,
    }

RESULT_ROWS = []
for mid, traces in ALL_TRACES_BY_MODEL.items():
    for (name, retriever, condition), df in traces.items():
        if df is None or len(df) == 0:
            continue
        RESULT_ROWS.append({"model_id": mid, "dataset": name, "retriever": retriever, "condition": condition, **metric_row(df)})

RESULTS = pd.DataFrame(RESULT_ROWS)
RESULTS.to_csv(ARTIFACTS/"FINAL_RESULTS_E0_E7_ALL_DATASETS_ALL_RETRIEVERS_ALL_MODELS.csv", index=False)
display(RESULTS.round(4))

def bootstrap_metric(df, B=1000, seed=42):
    if len(df) == 0:
        return {}
    rng = np.random.default_rng(seed)
    arr = df.reset_index(drop=True)
    store = defaultdict(list)
    for _ in range(B):
        idx = rng.integers(0, len(arr), len(arr))
        m = metric_row(arr.iloc[idx])
        for k in ["hits_any", "hits_hard", "f1"]:
            store[k].append(m[k])
    return {**{k+"_lo": float(np.nanpercentile(store[k], 2.5)) for k in store},
            **{k+"_hi": float(np.nanpercentile(store[k], 97.5)) for k in store}}

CI_ROWS = []
for mid, traces in ALL_TRACES_BY_MODEL.items():
    for (name, retriever, condition), df in traces.items():
        if df is None or len(df) == 0:
            continue
        base = {"model_id": mid, "dataset": name, "retriever": retriever, "condition": condition, **metric_row(df)}
        base.update(bootstrap_metric(df))
        CI_ROWS.append(base)

RESULTS_CI = pd.DataFrame(CI_ROWS)
RESULTS_CI.to_csv(ARTIFACTS/"FINAL_RESULTS_WITH_CI_ALL_MODELS.csv", index=False)
display(RESULTS_CI.round(4))
