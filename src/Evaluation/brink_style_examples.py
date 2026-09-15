"""31. BRINK-style examples, every KG x retriever x LLM."""

def proof_path(rec):
    if not isinstance(rec,dict): return ""
    for p in rec.get("proofs",[]):
        atoms=["("+", ".join(map(local_name,s.get("body_atom",())))+")" for s in p.get("proof",[])]
        if atoms: return " ∧ ".join(atoms)
    return ""

def make_examples(name,ret,mid,n=3):
    df=ALL_TRACES_BY_MODEL[mid][(name,ret,"E2_incomplete_NS")].head(n)
    rows=[]
    for _,r in df.iterrows():
        recs=r.get("inference_records",[]) if isinstance(r.get("inference_records",[]),list) else []
        target=tuple(r["head"]); rec=next((x for x in recs if tuple(x.get("head",()))==target),None)
        rows.append({"dataset":name,"retriever":ret,"llm":mid,"question_id":r["question_id"],"question":r["question"],
          "topic_entity":r["topic_entity"],"answer":r["gold_answers"],"hard_answer":r["hard_answer"],
          "direct_evidence_removed":target,"alternative_path":proof_path(rec) or "(no retained target proof)",
          "declared_context":r["evidence_declared"],"inferred_context":r["evidence_inferred"],"fused_context":r["context_facts"],"llm_answer":r["prediction_raw"]})
    return pd.DataFrame(rows)
EXAMPLE_TABLES=[]
for name in RUN_DATASETS:
  (ARTIFACTS/name).mkdir(parents=True,exist_ok=True)
  for ret in ACTIVE_RETRIEVERS:
    for mid in MODEL_CONFIGS:
      if (name,ret,"E2_incomplete_NS") in ALL_TRACES_BY_MODEL.get(mid,{}):
        e=make_examples(name,ret,mid,3); EXAMPLE_TABLES.append(e); e.to_csv(ARTIFACTS/name/f"BRINK_EXAMPLES_{ret}_{mid}.csv",index=False)
BRINK_EXAMPLES=pd.concat(EXAMPLE_TABLES,ignore_index=True) if EXAMPLE_TABLES else pd.DataFrame()
BRINK_EXAMPLES.to_csv(ARTIFACTS/"BRINK_EXAMPLES_ALL_KG_RETRIEVER_LLM.csv",index=False)
display(BRINK_EXAMPLES)
