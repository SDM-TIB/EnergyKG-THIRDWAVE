"""24. Final global analytical tables."""

# RESULTS_CI includes model_id.
GLOBAL_TABLE = RESULTS_CI.sort_values(["model_id", "dataset", "retriever", "condition"]).copy()

PAPER_TABLE = GLOBAL_TABLE[
    ["model_id", "dataset", "retriever", "condition", "n", "hits_any", "hits_hard", "hhr", "precision", "recall", "f1"]
].copy()

GLOBAL_TABLE.to_csv(ARTIFACTS/"FINAL_GLOBAL_ANALYTICAL_TABLE.csv", index=False)
PAPER_TABLE.to_csv(ARTIFACTS/"PAPER_READY_RESULTS_TABLE.csv", index=False)

display(GLOBAL_TABLE.round(4))
