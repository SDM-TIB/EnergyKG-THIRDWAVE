"""12b. PoG + StructGPT -- BRINK-aligned local adaptations."""

def _rel_mentions(raw, allowed):
    return [r for r in sorted(set(allowed)) if re.search(rf"(?<![A-Za-z0-9_]){re.escape(r)}(?![A-Za-z0-9_])", str(raw))]

def _neighbors(idx, entity, rel):
    return [(entity,rel,o) for o in idx["out"].get(entity,{}).get(rel,set())] + [(s,rel,entity) for s in idx["in"].get(entity,{}).get(rel,set())]

def pog_retrieve(question, q_entity, idx, track_key, model_id, width=3, depth=3):
    # PoG in BRINK: sub-goal decomposition + iterative exploration + guidance/memory/reflection.
    rels=sorted(idx["rels"].get(local_name(q_entity),set()))
    subgoals=cached_chat([{"role":"user","content":
        f"Question: {question}\nTopic entity: {q_entity}\nRelations: {'; '.join(rels[:60])}\n"
        "Decompose into at most three KG reasoning subgoals. Return one short subgoal per line."}],
        model_id=model_id,max_tokens=120,purpose="pog_subgoals",track_key=track_key+":subgoals")
    frontier=[local_name(q_entity)]; memory=[]
    for step in range(depth):
        candidates=[]
        for entity in frontier[:width]:
            rel_pool=sorted(idx["rels"].get(entity,set()))
            if not rel_pool: continue
            raw=cached_chat([{"role":"user","content":
                f"Question: {question}\nSubgoals:\n{subgoals}\nCurrent entity: {entity}\nRelations: {'; '.join(rel_pool[:60])}\n"
                f"Select at most {width} relations for the next path step; names only."}],
                model_id=model_id,max_tokens=80,purpose="pog_guidance",track_key=track_key+f":g{step}:{entity}")
            chosen=_rel_mentions(raw,rel_pool)[:width] or rel_pool[:width]
            for rel in chosen: candidates.extend(_neighbors(idx,entity,rel))
        candidates=list(dict.fromkeys(candidates))
        if not candidates: break
        edge_text="\n".join(" | ".join(e) for e in candidates[:30])
        raw=cached_chat([{"role":"user","content":
            f"Question: {question}\nSubgoals:\n{subgoals}\nMemory:\n{memory[-8:]}\nCandidate paths:\n{edge_text}\n"
            "Reflect and select the most useful edges for answering. Return exact edge lines only."}],
            model_id=model_id,max_tokens=160,purpose="pog_reflection",track_key=track_key+f":r{step}")
        selected=[e for e in candidates if " | ".join(e) in str(raw)] or candidates[:width]
        memory.extend(selected[:width])
        frontier=[e[2] for e in selected[:width]]
    return list(dict.fromkeys(memory))[:MAX_DECLARED_FACTS]

def structgpt_retrieve(question, q_entity, idx, track_key, model_id, iters=3):
    # StructGPT: invoking -> linearization -> generation, iterated over KG interfaces.
    entity=local_name(q_entity); collected=[]
    for i in range(iters):
        rels=sorted(idx["rels"].get(entity,set()))
        if not rels: break
        raw=cached_chat([{"role":"user","content":
            f"Question: {question}\nCurrent entity: {entity}\nAvailable relation interfaces: {'; '.join(rels[:60])}\n"
            "Choose one interface to invoke. Return RELATION=<name> only."}],
            model_id=model_id,max_tokens=60,purpose="structgpt_invoke",track_key=track_key+f":i{i}")
        chosen=_rel_mentions(raw,rels)[:1] or rels[:1]; edges=_neighbors(idx,entity,chosen[0])
        if not edges: break
        linear="\n".join(" | ".join(e) for e in edges[:30])
        raw2=cached_chat([{"role":"user","content":
            f"Question: {question}\nInterface output:\n{linear}\nSelect the useful evidence edges. Return exact edge lines only."}],
            model_id=model_id,max_tokens=140,purpose="structgpt_linearize",track_key=track_key+f":l{i}")
        selected=[e for e in edges if " | ".join(e) in str(raw2)] or edges[:3]
        collected.extend(selected[:3]); entity=selected[0][2] if selected[0][0]==entity else selected[0][0]
    return list(dict.fromkeys(collected))[:MAX_DECLARED_FACTS]

# Dispatcher is replaced to ensure every method receives the active local model id.
def retrieve_declared(name,retriever,qrow,kg_kind,model_id):
    idx=RETRIEVAL_INDEXES[name][kg_kind]; q=qrow["question"]; entity=qrow["topic_entity"]
    key=f"{name}:{qrow['question_id']}:{kg_kind}:{retriever}:{model_id}"
    if retriever=="onehop": facts=onehop_retrieve(q,entity,idx)
    elif retriever=="tog": facts=tog_retrieve(q,entity,idx,key,model_id)
    elif retriever=="pog": facts=pog_retrieve(q,entity,idx,key,model_id)
    elif retriever=="structgpt": facts=structgpt_retrieve(q,entity,idx,key,model_id)
    else: raise ValueError(retriever)
    return {"facts":dedup_triples(facts)[:MAX_DECLARED_FACTS],"method":retriever,
            "trace":{"question_id":qrow["question_id"],"entity":entity,"candidate_count":len(facts),"model_id":model_id}}
