"""1b. Authoritative source + resume preflight."""

for name,cfg in DATASETS_CONFIG.items():
    missing=[k for k,fp in cfg.items() if not fp.exists()]
    print(f"{name}: {'OK' if not missing else 'MISSING '+','.join(missing)}")
rows = []
for mid in MODEL_ORDER:
    for name in ACTIVE_DATASETS:
        for ret in ACTIVE_RETRIEVERS:
            for cond in CONDITION_ORDER:
                fp = CHECKPOINTS/mid/name/ret/f"{cond}.jsonl"
                rows.append((mid, name, ret, cond, checkpoint_count(fp)))
resume_df = pd.DataFrame(rows, columns=["model", "dataset", "retriever", "condition", "checkpointed"])
display(resume_df.groupby(["model", "dataset"], as_index=False)["checkpointed"].sum())
