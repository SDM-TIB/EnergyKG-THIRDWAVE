"""29. Two-LLM forensic audit."""

# An unprocessed KG gives an empty trace, not None; len(df) is checked explicitly.
def forensic_two_llm(name, retriever, n=10, seed=42):
    q = QUESTIONS[name].sample(n=min(n, len(QUESTIONS[name])), random_state=seed)
    rows = []
    for qid in q.question_id:
        for mid, traces in ALL_TRACES_BY_MODEL.items():
            df = traces.get((name, retriever, "E2_incomplete_NS"))
            if df is None or len(df) == 0:
                continue
            # Forced to string comparison to avoid a dtype-related false negative.
            if "question_id" not in df.columns:
                print(f"[FORENSIC SCHEMA ERROR] {mid}/{name}/{retriever}/E2: colonnes={df.columns.tolist()}")
                continue
            r = df[df["question_id"].astype(str) == str(qid)]
            if r.empty:
                continue
            r = r.iloc[0]
            rows.append({"model_id": mid, "dataset": name, "retriever": retriever,
                "question_id": qid, "question": r["question"], "hard_gold": r["hard_answer"],
                "declared": r.evidence_declared, "inferred": r.evidence_inferred,
                "shacl_valid": r.evidence_shacl_valid,
                "shacl_invalid": r.evidence_shacl_invalid,
                "fused_context": r.context_facts, "prediction": r.prediction_raw})
    out = pd.DataFrame(rows)
    out.to_csv(ARTIFACTS/name/f"FORENSIC_TWO_LLM_{retriever}.csv", index=False)
    display(out)
    return out

FORENSIC_TWO_LLM = {}
for name in RUN_DATASETS:
    (ARTIFACTS/name).mkdir(parents=True, exist_ok=True)
    for ret in ACTIVE_RETRIEVERS:
        FORENSIC_TWO_LLM[(name, ret)] = forensic_two_llm(name, ret, 10, SEED)
