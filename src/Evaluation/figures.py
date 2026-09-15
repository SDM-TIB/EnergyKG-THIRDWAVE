"""23. Figures."""

# One figure per model x KG x retriever.
def savefig(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path.with_suffix(".png"), bbox_inches="tight")
    plt.savefig(path.with_suffix(".pdf"), bbox_inches="tight")
    plt.show()

for mid in MODEL_ORDER:
    for name in EVALUABLE_DATASETS:
        for retriever in ACTIVE_RETRIEVERS:
            sub = RESULTS[
                (RESULTS["model_id"] == mid) & (RESULTS["dataset"] == name) & (RESULTS["retriever"] == retriever)
            ].set_index("condition")

            if len(sub):
                ax = sub[["hits_any", "hits_hard", "f1"]].plot(kind="bar", figsize=(12, 5))
                ax.set_ylabel("Score")
                ax.set_title(f"{mid} — {name} — {retriever}: E0–E7")
                savefig(ARTIFACTS/name/f"{mid}_{retriever}_results")

                ctx = sub[["avg_declared", "avg_inferred", "avg_random", "avg_oracle", "avg_shacl_validated"]]
                ax = ctx.plot(kind="bar", stacked=True, figsize=(12, 5))
                ax.set_ylabel("Average facts")
                ax.set_title(f"{mid} — {name} — {retriever}: evidence provenance")
                savefig(ARTIFACTS/name/f"{mid}_{retriever}_context_provenance")

if len(GRR):
    for mid in MODEL_ORDER:
        sub = GRR[GRR["model_id"] == mid]
        if len(sub):
            ax = sub.pivot(index="dataset", columns="retriever", values="GRR").plot(kind="bar", figsize=(9, 5))
            ax.set_ylabel("GRR")
            ax.set_title(f"{mid}: E7 Grounded Recovery Rate")
            savefig(ARTIFACTS/f"GRR_E7_{mid}")
