"""6. Efficient relation-aware grounding engine."""

def build_fact_indexes(df):
    by_rel=defaultdict(list); by_sr=defaultdict(list); by_or=defaultdict(list); facts=set()
    for s,r,o in df.itertuples(index=False,name=None):
        t=canonical_fact((s,r,o)); facts.add(t)
        by_rel[t[1]].append(t); by_sr[(t[0],t[1])].append(t); by_or[(t[2],t[1])].append(t)
    return {"rel":by_rel,"sr":by_sr,"or":by_or,"facts":facts}

def bind_term(pattern,value,env):
    if is_var(pattern):
        if pattern in env and env[pattern]!=value: return None
        e=dict(env); e[pattern]=value; return e
    return dict(env) if local_name(pattern)==local_name(value) else None

def unify_atom(pattern,fact,env):
    e=dict(env)
    for p,v in zip(pattern,fact):
        e=bind_term(p,v,e)
        if e is None: return None
    return e

def substitute_atom(atom,env):
    return tuple(env.get(x,x) for x in atom)

def candidate_facts(atom,idx):
    s,r,o=atom; sb=None if is_var(s) else local_name(s); ob=None if is_var(o) else local_name(o); rb=None if is_var(r) else local_name(r)
    if rb is None: return []  # AMIE3 relations are constants in this benchmark
    if sb is not None: pool=idx["sr"].get((sb,rb),[])
    elif ob is not None: pool=idx["or"].get((ob,rb),[])
    else: pool=idx["rel"].get(rb,[])
    if ob is not None and sb is not None: pool=[t for t in pool if t[2]==ob]
    return pool

def ground_rule_forward(rule,idx,max_groundings=MAX_GROUNDINGS_PER_RULE):
    envs=[{}]
    for atom in rule["body"]:
        nxt=[]
        for env in envs:
            for fact in candidate_facts(substitute_atom(atom,env),idx):
                e=unify_atom(atom,fact,env)
                if e is not None:
                    nxt.append(e)
                    if len(nxt)>=max_groundings: break
            if len(nxt)>=max_groundings: break
        envs=nxt
        if not envs: break
    out=[]
    for env in envs:
        head=tuple(env.get(x,x) for x in rule["head"])
        if any(is_var(x) for x in head): continue
        body=[substitute_atom(a,env) for a in rule["body"]]
        out.append({"rule_id":rule["rule_id"],"rule_text":rule["text"],"pca_confidence":rule["pca_confidence"],"body":body,"head":head})
    return out

def ground_rule_pool(name,rules):
    idx=build_fact_indexes(DATA[name]["semantic"]); all_rows=[]
    for rule in tqdm(rules,desc=f"Grounding {name}",leave=False):
        all_rows.extend(ground_rule_forward(rule,idx,MAX_GROUNDINGS_PER_RULE))
    # BRINK samples up to 30 groundings per rule; duplicates are removed at fact level later.
    by_rule=defaultdict(list)
    for row in all_rows: by_rule[row["rule_id"]].append(row)
    sampled=[]
    for rule in rules:
        sampled.extend(by_rule.get(rule["rule_id"],[])[:MAX_GROUNDINGS_PER_RULE])
    return pd.DataFrame(sampled,columns=["rule_id","rule_text","pca_confidence","body","head"])

GROUNDINGS={}
for name in ACTIVE_DATASETS:
    GROUNDINGS[name]={"E2":ground_rule_pool(name,RULES_PCA[name]),"E3":ground_rule_pool(name,RULES[name])}
    for label,df in GROUNDINGS[name].items():
        df.to_json(ARTIFACTS/name/f"groundings_{label}.json",orient="records",force_ascii=False,indent=2)
        print(name,label,"groundings:",len(df))
