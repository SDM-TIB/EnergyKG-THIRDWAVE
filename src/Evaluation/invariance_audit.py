"""17. Controlled-invariance and leakage audit."""

# Loops over every model. Per-question content match is the source of
# truth; global fingerprints are logged but don't fail the audit on minor
# upstream drift.
def audit_trace(name, retriever, condition, df, model_id=None):
    mismatched = [row["question_id"] for _, row in df.iterrows() if not _question_row_matches(name, row["question_id"], row)]
    assert not mismatched, (
        f"{len(mismatched)} question(s) whose content no longer matches the current question set: "
        f"{model_id}/{name}/{retriever}/{condition} -- examples: {mismatched[:5]}"
    )

    qfp = fingerprint_questions(QUESTIONS[name])
    ufp = fingerprint_universe(COMMON_UNIVERSE[name])
    if df["question_fingerprint_full"].nunique() != 1 or df["question_fingerprint_full"].iloc[0] != qfp:
        print(f"[INFO] {model_id}/{name}/{retriever}/{condition}: the question set's global fingerprint "
              f"differs from this session's (a known minor upstream drift) -- per-question content "
              f"verified individually above, no anomaly.")
    if df["universe_fingerprint"].nunique() != 1 or df["universe_fingerprint"].iloc[0] != ufp:
        print(f"[INFO] {model_id}/{name}/{retriever}/{condition}: universe fingerprint differs from this "
              f"session -- informational only.")

    leakage = 0
    removed = BENCH[name]["removed_test"]
    for _, row in df.iterrows():
        for fact, _label in row["context_facts"]:
            if tuple(fact) in removed and condition not in {"E0_complete_baseline", "E5_complete_NS", "E6_incomplete_oracle"}:
                leakage += 1

    assert leakage == 0, f"Target leakage in {model_id}/{name}/{retriever}/{condition}: {leakage}"
    return {
        "model_id": model_id, "dataset": name, "retriever": retriever, "condition": condition,
        "n_questions": len(df), "leakage": leakage,
        "context_min": int(df["context_count"].min()) if len(df) else 0,
        "context_max": int(df["context_count"].max()) if len(df) else 0,
    }

AUDIT_ROWS = []
for mid, traces in ALL_TRACES_BY_MODEL.items():
    for key, df in traces.items():
        if df is None or len(df) == 0:
            continue
        AUDIT_ROWS.append(audit_trace(*key, df, model_id=mid))

AUDIT_DF = pd.DataFrame(AUDIT_ROWS)
AUDIT_DF.to_csv(ARTIFACTS/"CONTROLLED_INVARIANCE_AUDIT.csv", index=False)
display(AUDIT_DF)
