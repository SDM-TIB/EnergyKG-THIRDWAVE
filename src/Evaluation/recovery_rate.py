"""21. Grounded recovery rate (E7)."""

# Loops over every model.
GRR_ROWS = []
for mid, traces in ALL_TRACES_BY_MODEL.items():
    for key, df in traces.items():
        name, retriever, condition = key
        if condition != "E7_incomplete_NS_SHACL" or df is None or len(df) == 0:
            continue

        hits = grounded = 0
        for _, row in df.iterrows():
            pred = process_prediction(row["prediction_raw"])
            hard = normalize_answer(row["hard_answer"])
            if hard in pred:
                hits += 1
                valid_facts = [tuple(x) for x in row["evidence_shacl_valid"]]
                if any(hard in {norm_answer(f[0]), norm_answer(f[2])} for f in valid_facts):
                    grounded += 1

        GRR_ROWS.append({
            "model_id": mid, "dataset": name, "retriever": retriever,
            "E7_hard_hits": hits, "E7_grounded_hard_hits": grounded,
            "GRR": grounded / hits if hits else np.nan,
        })

GRR = pd.DataFrame(GRR_ROWS)
GRR.to_csv(ARTIFACTS/"GRR_E7_ALL_DATASETS.csv", index=False)
display(GRR.round(4))
