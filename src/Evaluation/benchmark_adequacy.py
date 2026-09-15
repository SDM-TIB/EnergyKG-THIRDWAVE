"""22. Benchmark adequacy."""

ADEQUACY_ROWS = []
for name in EVALUABLE_DATASETS:
    test = BENCH[name]["splits"]["test"]
    rel_counts = test["head_canon"].map(lambda x: x[1]).value_counts() if len(test) else pd.Series(dtype=int)
    ADEQUACY_ROWS.append({
        "dataset": name,
        "eligible_removable_facts": len(BENCH[name]["pool"]),
        "train": len(BENCH[name]["splits"]["train"]),
        "validation": len(BENCH[name]["splits"]["validation"]),
        "test_facts": len(test),
        "test_questions": len(QUESTIONS[name]),
        "test_relations": test["head_canon"].map(lambda x: x[1]).nunique() if len(test) else 0,
        "max_relation_share": rel_counts.max()/len(test) if len(test) else np.nan,
        "removed_rate_percent": len(test)/len(DATA[name]["semantic"])*100 if len(DATA[name]["semantic"]) else np.nan,
        "questions_per_test_fact": len(QUESTIONS[name])/len(test) if len(test) else np.nan,
    })

ADEQUACY = pd.DataFrame(ADEQUACY_ROWS)
ADEQUACY.to_csv(ARTIFACTS/"BENCHMARK_ADEQUACY.csv", index=False)
display(ADEQUACY.round(4))
