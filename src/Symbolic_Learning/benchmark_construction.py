"""7. Unique removable facts + frozen test set (BRINK-style split)."""

# Policy: dataset-local source gating, frozen BRINK-style split, documented
# small-pool test floor, and no fabricated test facts.

def build_benchmark(name):
    if not DATASET_READY.get(name, False):
        reasons=[]
        if not SHACL_AUDIT_DEFINED: reasons.append("SHACL_AUDIT undefined")
        if not RULES_LOSSLESS_BY_DATASET.get(name, False): reasons.append("authoritative CoPCA rule parsing is not lossless")
        if not SHACL_AVAILABLE_BY_DATASET.get(name, False): reasons.append("authoritative CoPCA SHACL file unavailable")
        reason="; ".join(reasons) or "source preflight not ready"
        print(f"{name}: benchmark gated ({reason}).")
        return make_gated_benchmark(name, reason)

    complete=DATA[name]["semantic"].copy()
    complete_facts={canonical_fact(t) for t in complete.itertuples(index=False,name=None)}
    g2=GROUNDINGS[name]["E2"].copy()
    if len(g2)==0:
        return make_gated_benchmark(name,"E2 grounding pool is empty")

    g2["head_canon"]=g2["head"].map(canonical_fact)
    g2["body_canon"]=g2["body"].map(lambda x:[canonical_fact(a) for a in (ast.literal_eval(x) if isinstance(x,str) else x)])

    # Safety guard: do not remove a fact that is itself used as another proof premise.
    all_body_atoms = {a for body in g2["body_canon"] for a in body}
    eligible=(g2[g2["head_canon"].isin(complete_facts) & ~g2["head_canon"].isin(all_body_atoms)]
              .sort_values(["pca_confidence","rule_id","head_canon"],ascending=[False,True,True],kind="stable")
              .drop_duplicates("head_canon").reset_index(drop=True))
    _n_excluded_as_body = int(g2["head_canon"].isin(complete_facts).sum()) - len(eligible)
    if _n_excluded_as_body > 0:
        print(f"{name}: excluded {_n_excluded_as_body} unsafe removal candidate(s).")
    pool=(eligible.iloc[:int(BRINK_SPLIT_NROWS)].copy().reset_index(drop=True)
          if BRINK_SPLIT_NROWS is not None else eligible.copy().reset_index(drop=True))

    if len(pool)==0:
        return make_gated_benchmark(name,"no removable facts available")

    # Base split is BRINK-style 8:1:1; small pools use the documented test floor.
    n=len(pool)
    train_frac,val_frac,test_frac=BRINK_SPLIT_RATIOS
    natural_test=int(round(n*test_frac))
    # TEST_FLOOR: a pure 10% share on a small pool gives too few test
    # questions for a defensible margin of error, so test is raised to a
    # floor of 100 when the pool is too small to reach it naturally.
    TEST_FLOOR=100
    if n<=TEST_FLOOR:
        # Pool smaller than the floor: everything goes to test, no train/val.
        train_n=0; val_n=0; desired_test=n
        split_policy=f"all_available_as_test_pool_leq_floor_{TEST_FLOOR}"
    elif natural_test>=TEST_FLOOR:
        train_n=int(round(n*train_frac))
        val_n=n-train_n-natural_test
        desired_test=natural_test
        split_policy=f"brink_proportional_{BRINK_SPLIT_RATIOS[0]:.0%}_{BRINK_SPLIT_RATIOS[1]:.0%}_{BRINK_SPLIT_RATIOS[2]:.0%}_of_full_grounding_pool"
    else:
        desired_test=TEST_FLOOR
        remaining=n-desired_test
        val_n=int(round(remaining*(val_frac/(train_frac+val_frac))))
        train_n=remaining-val_n
        split_policy=f"brink_811_with_test_floor_{TEST_FLOOR}_train_val_share_remainder_8to1"

    shuffled=pool.sample(frac=1.0,random_state=SPLIT_SEED).reset_index(drop=True)
    splits={
        "train":shuffled.iloc[:train_n].copy(),
        "validation":shuffled.iloc[train_n:train_n+val_n].copy(),
        "test":shuffled.iloc[train_n+val_n:train_n+val_n+desired_test].copy(),
    }
    kg_artifacts=ARTIFACTS/name; kg_artifacts.mkdir(parents=True,exist_ok=True)
    for split_name,df in splits.items(): df.to_csv(kg_artifacts/f"{split_name}_facts.csv",index=False)

    ids={k:set(v["head_canon"].map(tuple)) for k,v in splits.items()}
    assert not ids["train"] & ids["validation"]
    assert not ids["train"] & ids["test"]
    assert not ids["validation"] & ids["test"]
    removed=ids["test"]
    incomplete=complete.loc[~complete.apply(lambda r: canonical_fact((r["subject"],r["relation"],r["object"])),axis=1).isin(removed)].reset_index(drop=True)
    incomplete_facts={canonical_fact(t) for t in incomplete.itertuples(index=False,name=None)}
    assert removed.issubset(complete_facts) and not removed & incomplete_facts

    # SHA-256 over sorted canonical content (not just row counts), so two
    # runs can be verified to have produced the exact same benchmark.
    import hashlib
    def _sha256_of_facts(facts_iterable):
        canon = sorted(str(f) for f in facts_iterable)
        return hashlib.sha256("\n".join(canon).encode("utf-8")).hexdigest()
    pool_sha256 = _sha256_of_facts(pool["head_canon"].map(str))
    split_sha256 = _sha256_of_facts(
        f"{split_name}:{fact}" for split_name, df in splits.items() for fact in df["head_canon"].map(str)
    )

    return {"ready":True,"status":"READY","reason":"","complete":complete,"incomplete":incomplete,
            "pool":pool,"splits":splits,"removed_test":removed,
            "split_policy":split_policy,"requested_test_questions":len(splits["test"]),
            "actual_test_questions":len(splits["test"]),
            "pool_sha256":pool_sha256,"split_sha256":split_sha256}

BENCH={name:build_benchmark(name) for name in ACTIVE_DATASETS}
for name,b in BENCH.items():
    print(name,"| status:",b["status"],"| eligible pool:",len(b["pool"]),
          "| train/val/test:",len(b["splits"]["train"]),len(b["splits"]["validation"]),len(b["splits"]["test"]),
          "| test:",len(b["splits"]["test"]),"| policy:",b.get("split_policy"))
    if b.get("pool_sha256"):
        print(f"  pool_sha256:  {b['pool_sha256']}")
        print(f"  split_sha256: {b['split_sha256']}")

# SPLIT_DRY_RUN=1: stop here (before any GPU work) to inspect split sizes.
# No effect on a normal run.
if os.environ.get("SPLIT_DRY_RUN", "").strip() == "1":
    print("\n" + "=" * 72)
    print("SPLIT_DRY_RUN=1: stopping here on purpose, before any GPU computation.")
    print("Test-set sizes by KG:")
    for _name, _b in BENCH.items():
        print(f"  {_name}: train={len(_b['splits']['train'])}  "
              f"val={len(_b['splits']['validation'])}  test={len(_b['splits']['test'])}")
    print("Re-run without SPLIT_DRY_RUN for the full campaign.")
    print("=" * 72)
    raise SystemExit(0)

# DATA[name]["rdf_graph"] (a full rdflib.Graph, memory-heavy) is only still
# needed to build incomplete_rdf_graph() once removed_test is known -- built
# here, then freed immediately, since nothing else reads it afterward.
EVALUABLE_DATASETS=[n for n in ACTIVE_DATASETS if BENCH[n]["ready"]]
GATED_DATASETS=[n for n in ACTIVE_DATASETS if not BENCH[n]["ready"]]
print("EVALUABLE_DATASETS:",EVALUABLE_DATASETS)
print("GATED_DATASETS:",GATED_DATASETS)

import gc
for _name in ACTIVE_DATASETS:
    if _name in EVALUABLE_DATASETS:
        incomplete_rdf_graph(_name)  # builds and caches DATA[_name]["incomplete_rdf_graph"]
    # Gated datasets are never used downstream either; freed the same way.
    _freed = DATA[_name]["rdf_graph"]
    DATA[_name]["rdf_graph"] = None
    del _freed
gc.collect()
print(f"RAM: rdf_graph (raw rdflib copy) freed for {ACTIVE_DATASETS} "
      f"after building their incomplete_rdf_graph (evaluable datasets) -- "
      f"'raw'/'semantic' (pandas, much lighter) remain available for "
      f"the rest of the notebook.")

# Reports resident memory after release, as a check and an early warning.
try:
    import psutil
    _rss_gb = psutil.Process(os.getpid()).memory_info().rss / (1024 ** 3)
    print(f"Process resident memory after release: {_rss_gb:.2f} GB")
except Exception:
    try:
        import resource
        _rss_gb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 ** 2)
        print(f"Peak resident memory (approximate): {_rss_gb:.2f} GB")
    except Exception as _e:
        print(f"(memory measurement unavailable: {_e})")
