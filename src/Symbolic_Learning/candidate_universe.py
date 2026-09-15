"""9. Frozen common candidate universe."""

def build_common_universe(name):
    complete = BENCH[name]["complete"]
    entities = sorted(
        set(complete["subject"].map(local_name)) |
        set(complete["object"].map(local_name))
    )
    relations = sorted({
        local_name(r) for r in complete["relation"]
        if local_name(r).lower() not in {"type", "rdf:type"}
    })
    return {"entities": entities, "relations": relations}

COMMON_UNIVERSE = {name: build_common_universe(name) for name in EVALUABLE_DATASETS}

def fingerprint_questions(qdf):
    cols = ["question_id","fact_id","question","topic_entity","relation","hard_answer"]
    return sha_key(qdf[cols].to_dict("records"))

def fingerprint_universe(u):
    return sha_key({"entities": u["entities"], "relations": u["relations"]})

for name in EVALUABLE_DATASETS:
    q = QUESTIONS[name]
    u = COMMON_UNIVERSE[name]
    missing_topics = set(q["topic_entity"].astype(str)) - set(u["entities"]) if len(q) else set()
    missing_answers = set(q["hard_answer"].astype(str)) - set(u["entities"]) if len(q) else set()
    assert not missing_topics and not missing_answers
    print(name, "| universe entities:", len(u["entities"]), "| relations:", len(u["relations"]))
