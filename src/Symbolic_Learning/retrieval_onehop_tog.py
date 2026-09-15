"""10. Retrieval indexes -- OneHop and ToG."""

def build_tog_index(df):
    out_rel = defaultdict(lambda: defaultdict(set))
    in_rel = defaultdict(lambda: defaultdict(set))
    rels = defaultdict(set)

    for s, r, o in df.itertuples(index=False, name=None):
        s, r, o = local_name(s), local_name(r), local_name(o)
        out_rel[s][r].add(o)
        in_rel[o][r].add(s)
        rels[s].add(r)
        rels[o].add(r)

    return {"out": out_rel, "in": in_rel, "rels": rels}

def onehop_retrieve(question, entity, idx):
    entity = local_name(entity)
    facts = []
    for rel, objs in idx["out"].get(entity, {}).items():
        for o in objs:
            facts.append((entity, rel, o))
    for rel, subs in idx["in"].get(entity, {}).items():
        for s in subs:
            facts.append((s, rel, entity))
    return sorted(set(facts), key=lambda x: (x[1], x[0], x[2]))

def select_relations(question, entity, allowed, track_key, model_id, k=TOG_WIDTH):
    allowed = sorted(set(allowed))
    if not allowed:
        return []

    prompt = (
        f"Question: {question}\n"
        f"Entity: {entity}\n"
        f"Relations: {'; '.join(allowed[:TOG_MAX_RELATIONS])}\n"
        f"List the top {k} most relevant relation names, comma-separated, nothing else."
    )
    raw = cached_chat(
        [{"role": "user", "content": prompt}],
        max_tokens=100,
        purpose="tog_rel",
        track_key=track_key,
        model_id=model_id,
    )
    found = [
        r for r in allowed
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(r)}(?![A-Za-z0-9_])", raw)
    ]
    return found[:k] if found else allowed[:k]

def score_candidates(question, relation, candidates, track_key, model_id):
    candidates = list(dict.fromkeys(candidates))
    if len(candidates) <= 1:
        return candidates

    cand = candidates[:TOG_MAX_CANDIDATES]
    prompt = (
        f"Question: {question}\n"
        f"Relation: {relation}\n"
        f"Candidates: {'; '.join(cand)}\n"
        f"Which {TOG_WIDTH} candidates are most relevant? "
        f"Reply with candidate names, comma-separated."
    )
    raw = cached_chat(
        [{"role": "user", "content": prompt}],
        max_tokens=100,
        purpose="tog_ent",
        track_key=track_key,
        model_id=model_id,
    )
    found = [
        c for c in cand
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(c)}(?![A-Za-z0-9_])", raw)
    ]
    return (found if found else cand[:TOG_WIDTH])[:TOG_WIDTH]

def tog_retrieve(question, q_entity, idx, track_key, model_id, width=TOG_WIDTH, depth=TOG_DEPTH):
    frontier = [(local_name(q_entity), [])]
    seen_paths = set()
    records = []

    for hop in range(depth):
        nxt = []
        for entity, path in frontier:
            relations = sorted(idx["rels"].get(entity, set()))
            chosen = select_relations(question, entity, relations, track_key, model_id)

            for rel in chosen:
                candidates = []
                for o in idx["out"].get(entity, {}).get(rel, set()):
                    candidates.append((o, (entity, rel, o)))
                for s in idx["in"].get(entity, {}).get(rel, set()):
                    candidates.append((s, (s, rel, entity)))

                names = [x[0] for x in candidates]
                for cand in score_candidates(question, rel, names, track_key, model_id):
                    edge = next((edge for c, edge in candidates if c == cand), None)
                    if edge is None:
                        continue
                    new_path = path + [edge]
                    key = tuple(new_path)
                    if key in seen_paths:
                        continue
                    seen_paths.add(key)
                    records.append({"triples": new_path, "depth": hop + 1})
                    nxt.append((cand, new_path))

        frontier = nxt[:width]
        if not frontier:
            break

    # Keep the existing ToG-style path evidence contract.
    triples = []
    for rec in records:
        triples.extend(rec["triples"])
    return list(dict.fromkeys(triples))[:MAX_DECLARED_FACTS]

RETRIEVAL_INDEXES = {
    name: {
        "complete": build_tog_index(BENCH[name]["complete"]),
        "incomplete": build_tog_index(BENCH[name]["incomplete"]),
    }
    for name in EVALUABLE_DATASETS
}
