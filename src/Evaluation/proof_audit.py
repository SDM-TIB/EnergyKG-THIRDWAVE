"""13b. Target-level proof audit."""

TARGET_PROOF_AUDIT=[]
for name in EVALUABLE_DATASETS:
    kg=BENCH[name]["incomplete"]
    idx=build_fact_indexes(kg)
    for _,q in QUESTIONS[name].iterrows():
        target=canonical_fact(q["head"])
        for policy in ["E2","E3"]:
            proofs=prove_goal(target,idx,RULES_BY_HEAD_REL[name][policy],MAX_PROOF_DEPTH,MAX_PROOFS_PER_GOAL)
            TARGET_PROOF_AUDIT.append({"dataset":name,"question_id":q["question_id"],"policy":policy,"target":target,"proof_count":len(proofs),"provable":bool(proofs),"max_depth":max([p["depth"] for p in proofs],default=None),"proof_rule_ids":[x["rule_id"] for p in proofs for x in p["proof"]]})
TARGET_PROOF_AUDIT=pd.DataFrame(TARGET_PROOF_AUDIT)
TARGET_PROOF_AUDIT.to_json(ARTIFACTS/"TARGET_BACKWARD_CHAIN_AUDIT.json",orient="records",force_ascii=False,indent=2)
display(TARGET_PROOF_AUDIT.groupby(["dataset","policy"]).agg(n=("question_id","size"),provable=("provable","mean"),avg_proofs=("proof_count","mean"),avg_depth=("max_depth","mean")).round(4))
