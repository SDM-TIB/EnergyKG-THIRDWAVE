"""13. Backward-chaining neuro-symbolic inference."""


def freeze_grounding_rows(df):
    rows=[]
    for _,row in df.iterrows():
        body=row["body"]; head=row["head"]
        if isinstance(body,str): body=ast.literal_eval(body)
        if isinstance(head,str): head=ast.literal_eval(head)
        rows.append({"rule_id":str(row["rule_id"]),"rule_text":str(row["rule_text"]),"pca_confidence":float(row["pca_confidence"]),"body":[canonical_fact(a) for a in body],"head":canonical_fact(head)})
    return rows

FROZEN_GROUNDINGS={name:{"E2":freeze_grounding_rows(GROUNDINGS[name]["E2"]),"E3":freeze_grounding_rows(GROUNDINGS[name]["E3"])} for name in ACTIVE_DATASETS}

RULES_BY_HEAD_REL={name:{"E2":defaultdict(list),"E3":defaultdict(list)} for name in ACTIVE_DATASETS}
for name in EVALUABLE_DATASETS:
    for policy,rs in [("E2",RULES_PCA[name]),("E3",RULES[name])]:
        for rule in rs: RULES_BY_HEAD_REL[name][policy][local_name(rule["head"][1])].append(rule)

def prove_goal(goal,idx,rules_by_rel,max_depth=MAX_PROOF_DEPTH,max_proofs=MAX_PROOFS_PER_GOAL):
    memo={}
    def prove(atom,env,depth,active_rules):
        atom=substitute_atom(atom,env)
        key=(tuple(atom),tuple(sorted(env.items())),depth,tuple(sorted(active_rules)))
        if key in memo: return memo[key]
        if depth>max_depth: return []
        results=[]
        # Direct facts support body atoms; a removed goal needs a rule-derived proof.
        for fact in candidate_facts(atom,idx):
            e=unify_atom(atom,fact,env)
            if e is not None:
                results.append({"env":e,"proof":[],"depth":depth})
                if len(results)>=max_proofs: break
        rel=local_name(atom[1]) if not is_var(atom[1]) else None
        rules=rules_by_rel.get(rel,[]) if rel is not None else [r for rs in rules_by_rel.values() for r in rs]
        if depth<max_depth and len(results)<max_proofs:
            for rule in rules:
                if rule["rule_id"] in active_rules: continue
                e0=unify_atom(rule["head"],atom,env)
                if e0 is None: continue
                partial=[{"env":e0,"proof":[],"depth":depth}]
                for body_atom in rule["body"]:
                    nxt=[]
                    for p0 in partial:
                        subproofs=prove(body_atom,p0["env"],depth+1,active_rules|{rule["rule_id"]})
                        for p1 in subproofs:
                            nxt.append({"env":p1["env"],"proof":p0["proof"]+[{"rule_id":rule["rule_id"],"rule_text":rule["text"],"pca_confidence":rule["pca_confidence"],"body_atom":substitute_atom(body_atom,p1["env"])}]+p1["proof"],"depth":max(p0["depth"],p1["depth"])})
                            if len(nxt)>=max_proofs: break
                        if len(nxt)>=max_proofs: break
                    partial=nxt
                    if not partial: break
                results.extend(partial[:max_proofs-len(results)])
                if len(results)>=max_proofs: break
        memo[key]=results[:max_proofs]
        return memo[key]
    raw=prove(tuple(goal),{},0,set())
    uniq=[]; seen=set()
    for p in raw:
        sig=(tuple(sorted(p["env"].items())),tuple(x["rule_id"] for x in p["proof"]))
        if sig not in seen: seen.add(sig); uniq.append(p)
        if len(uniq)>=max_proofs: break
    return uniq

def ns_retrieve(name,entity,kg_set,policy,max_facts=MAX_NS_FACTS,target_relation=None):
    entity=local_name(entity); idx=build_fact_indexes(pd.DataFrame(list(kg_set),columns=["subject","relation","object"]))
    rules_by_rel=RULES_BY_HEAD_REL[name][policy]
    # Candidates come from complete-KG groundings; proof runs backward on the incomplete KG.
    candidates=[]; seen=set()
    for gr in FROZEN_GROUNDINGS[name][policy]:
        head=canonical_fact(gr["head"])
        if head[0]!=entity or head in seen: continue
        if head in kg_set: continue
        proofs=prove_goal(head,idx,rules_by_rel,MAX_PROOF_DEPTH,MAX_PROOFS_PER_GOAL)
        if not proofs: continue
        seen.add(head)
        candidates.append({"fact":head,"head":head,"rule_id":gr["rule_id"],"rule_text":gr["rule_text"],"pca_confidence":gr["pca_confidence"],"proof_count":len(proofs),"proofs":proofs})
    # Target relation is prioritized first, then confidence/proof count, so
    # the on-topic candidate isn't crowded out under the context budget.
    target_rel_local = local_name(target_relation) if target_relation is not None else None
    candidates.sort(key=lambda x:(
        0 if (target_rel_local is not None and local_name(x["head"][1]) == target_rel_local) else 1,
        -x["pca_confidence"], -x["proof_count"], x["rule_id"], repr(x["fact"])))
    return candidates[:max_facts]
