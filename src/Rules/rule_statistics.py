"""5d. BRINK-style rule statistics, each KG."""

def classify_rule(rule):
    b=[tuple(a) for a in rule["body"]]; h=tuple(rule["head"])
    if len(b)==1:
        x,r,y=b[0]
        if r==h[1] and x==h[2] and y==h[0]: return "Symmetry"
        if x==h[2] and y==h[0] and r!=h[1]: return "Inversion"
        if x==h[0] and y==h[2] and r!=h[1]: return "Hierarchy"
    if len(b)==2 and b[0][2]==b[1][0] and h[0]==b[0][0] and h[2]==b[1][2]: return "Composition"
    return "Other"
RULE_TYPE_ORDER=["Symmetry","Inversion","Hierarchy","Composition","Other"]
rr=[]
for name in ACTIVE_DATASETS:
    c=Counter(classify_rule(r) for r in RULES.get(name,[]))
    rr.append({"dataset":name,**{k:int(c.get(k,0)) for k in RULE_TYPE_ORDER},"Total":int(sum(c.values())),"PCA>=0.4":int(len(RULES_PCA.get(name,[])))})
RULE_STATS=pd.DataFrame(rr,columns=["dataset"]+RULE_TYPE_ORDER+["Total","PCA>=0.4"])
RULE_STATS.to_csv(ARTIFACTS/"BRINK_RULE_STATISTICS_BY_KG.csv",index=False)
display(RULE_STATS)
# Rule mining is KG-level; repeat for each retrieval/LLM combination for complete experiment bookkeeping.
rep=[]
for _,r in RULE_STATS.iterrows():
    for ret in ACTIVE_RETRIEVERS:
        for mid in MODEL_ORDER:
            cfg = MODEL_CONFIGS[mid]
            rep.append({**r.to_dict(), "retriever": ret, "model_id": mid, "model_name": cfg["model_name"]})
RULE_STATS_BY_METHOD=pd.DataFrame(rep)
RULE_STATS_BY_METHOD.to_csv(ARTIFACTS/"BRINK_RULE_STATISTICS_KG_RETRIEVER_LLM.csv",index=False)
