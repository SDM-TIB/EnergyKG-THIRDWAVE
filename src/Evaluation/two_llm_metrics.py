"""28. Two-LLM metrics and paired model effects."""

def norm_answer(x):
    return normalize_answer(x)

def parse_answer(raw):
    return process_prediction(raw)

def _two_llm_metric_row(df):
    # Matches BRINK's metric definitions exactly (Zhou et al. 2025, Sec. 4.3):
    # Hits@Any, Precision, Recall, F1, Hits@Hard, HHR = Hits@Hard/Hits@Any.
    if df is None or len(df)==0:
        return {"n":0,"hits_any":np.nan,"hits_hard":np.nan,"hhr":np.nan,
                "precision":np.nan,"recall":np.nan,"f1":np.nan}

    required={"prediction_raw","gold_answers","hard_answer"}
    missing=required-set(df.columns)
    if missing:
        raise ValueError(f"Cannot compute metrics: missing columns {sorted(missing)}")

    vals=[]
    for _,row in df.iterrows():
        pred=parse_answer(row["prediction_raw"])
        gold={norm_answer(x) for x in row["gold_answers"]}
        hard=norm_answer(row["hard_answer"])
        inter=pred & gold
        p=len(inter)/len(pred) if pred else 0.0
        r=len(inter)/len(gold) if gold else 0.0
        f1=2*p*r/(p+r) if p+r else 0.0
        vals.append({"hit_any":bool(inter),"hit_hard":hard in pred,"precision":p,"recall":r,"f1":f1})

    v=pd.DataFrame.from_records(vals,columns=["hit_any","hit_hard","precision","recall","f1"])
    any_sum=int(v["hit_any"].sum())
    hard_sum=int(v["hit_hard"].sum())
    return {"n":len(v),
            "hits_any":float(v["hit_any"].mean()),
            "hits_hard":float(v["hit_hard"].mean()),
            "hhr":float(hard_sum/any_sum) if any_sum else np.nan,
            "precision":float(v["precision"].mean()),
            "recall":float(v["recall"].mean()),
            "f1":float(v["f1"].mean())}

rows=[]
for mid,traces in ALL_TRACES_BY_MODEL.items():
    for (name,ret,cond),df in traces.items():
        # Partial checkpoints are reported as partial, never as complete.
        if df is None or len(df)==0: continue
        rows.append({"model_id":mid,"model_name":MODEL_CONFIGS[mid]["model_name"],"dataset":name,
                     "retriever":ret,"condition":cond,**_two_llm_metric_row(df)})
MODEL_RESULTS=pd.DataFrame(rows)
if len(MODEL_RESULTS):
    MODEL_RESULTS.to_csv(ARTIFACTS/"FINAL_RESULTS_TWO_LLM.csv",index=False)
else:
    MODEL_RESULTS=pd.DataFrame(columns=["model_id","model_name","dataset","retriever","condition","n","hits_any","hits_hard","hhr","f1"])
    MODEL_RESULTS.to_csv(ARTIFACTS/"FINAL_RESULTS_TWO_LLM.csv",index=False)
display(MODEL_RESULTS.round(4))

ids = list(MODEL_ORDER); effects = []
if len(ids)>=2 and len(MODEL_RESULTS):
    a,b=ids[:2]
    z=MODEL_RESULTS.set_index(["model_id","dataset","retriever","condition"])
    for name in RUN_DATASETS:
        for ret in ACTIVE_RETRIEVERS:
            for cond in CONDITION_ORDER:
                if (a,name,ret,cond) in z.index and (b,name,ret,cond) in z.index:
                    ra,rb=z.loc[(a,name,ret,cond)],z.loc[(b,name,ret,cond)]
                    effects.append({"model_A":a,"model_B":b,"dataset":name,"retriever":ret,"condition":cond,
                        "delta_hits_any_B_minus_A":rb["hits_any"]-ra["hits_any"],"delta_hits_hard_B_minus_A":rb["hits_hard"]-ra["hits_hard"],
                        "delta_hhr_B_minus_A":rb["hhr"]-ra["hhr"],"delta_f1_B_minus_A":rb["f1"]-ra["f1"]})
MODEL_EFFECTS=pd.DataFrame(effects)
MODEL_EFFECTS.to_csv(ARTIFACTS/"TWO_LLM_PAIRED_EFFECTS.csv",index=False)
display(MODEL_EFFECTS.round(4))
