"""14. Evidence conditions (E0-E7) + context fusion."""


CONDITIONS = {
    "E0_complete_baseline":   {"kg": "complete",   "kind": "declared"},
    "E1_incomplete_baseline": {"kg": "incomplete", "kind": "declared"},
    "E2_incomplete_NS":       {"kg": "incomplete", "kind": "ns_pca"},
    "E3_incomplete_noPCA":    {"kg": "incomplete", "kind": "ns_all"},
    "E4_incomplete_random":   {"kg": "incomplete", "kind": "random"},
    "E5_complete_NS":         {"kg": "complete",   "kind": "ns_pca"},
    "E6_incomplete_oracle":   {"kg": "incomplete", "kind": "oracle"},
    "E7_incomplete_NS_SHACL": {"kg": "incomplete", "kind": "ns_shacl"},
}

def fixed_context(declared, augmentation, default_label="AUGMENTED"):
    """`augmentation` accepts either a flat list of facts (backward-compatible,
    all labeled `default_label`), or a list of (fact, label) pairs -- which
    lets E2/E3/E5 attach each inferred fact's PCA confidence directly in its
    label (e.g. "INFERRED(conf=0.82)") instead of a generic "INFERRED" label
    indistinguishable across facts of very different reliability."""
    declared = dedup_triples(declared)
    seen_aug = set(); aug_pairs = []
    for item in augmentation:
        if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], str):
            f, lab = item
        else:
            f, lab = item, default_label
        if f in seen_aug:
            continue
        seen_aug.add(f); aug_pairs.append((f, lab))

    ctx = [(f, "DECLARED") for f in declared[:MAX_DECLARED_FACTS]]
    used = {f for f, _ in ctx}

    for f, lab in aug_pairs:
        if len(ctx) >= CONTEXT_MAX_FACTS:
            break
        if f not in used:
            ctx.append((f, lab))
            used.add(f)

    # Fixed context budget.
    for f in declared[MAX_DECLARED_FACTS:]:
        if len(ctx) >= CONTEXT_MAX_FACTS:
            break
        if f not in used:
            ctx.append((f, "DECLARED_BACKFILL"))
            used.add(f)

    return ctx[:CONTEXT_MAX_FACTS]

def random_distractors(name, qrow, declared_incomplete):
    facts = {
        canonical_fact(t)
        for t in BENCH[name]["incomplete"].itertuples(index=False, name=None)
    }
    excluded = set(map(tuple, declared_incomplete)) | {tuple(qrow["head"])}
    pool = sorted(facts - excluded)

    seed = int(hashlib.sha1(qrow["question_id"].encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    return rng.sample(pool, min(MAX_RANDOM_FACTS, len(pool)))


def reference_status(name, fact):
    """Audit-only cross-check against CoPCA's target logs; never decisive
    (validate_fact_shacl_delta is the only authoritative gate). CoPCA's logs
    only yield flat extracted terms (see copca_reference_logs.py), not
    structured triples, so no exact-triple comparison is actually possible --
    this always returns "unknown" by design, not by omission. Matching
    individual terms against a fact's subject/relation/object would require
    an unverified heuristic and risks a false "disagreement" signal, which
    would be worse than the honest, always-"unknown" audit this returns."""
    return "unknown"

def build_evidence_for_question(name,retriever,qrow,model_id):
    complete=BENCH[name]["complete"]; incomplete=BENCH[name]["incomplete"]
    removed=BENCH[name]["removed_test"]
    declared_complete=retrieve_declared(name,retriever,qrow,"complete",model_id)["facts"]
    declared_incomplete=[f for f in retrieve_declared(name,retriever,qrow,"incomplete",model_id)["facts"] if tuple(f) not in removed]
    complete_set={canonical_fact(t) for t in complete.itertuples(index=False,name=None)}
    incomplete_set={canonical_fact(t) for t in incomplete.itertuples(index=False,name=None)}

    # Target relation passed through to prioritize the on-topic candidate.
    e2=ns_retrieve(name,qrow["topic_entity"],incomplete_set,"E2",target_relation=qrow["relation"])
    e3=ns_retrieve(name,qrow["topic_entity"],incomplete_set,"E3",target_relation=qrow["relation"])
    e5=ns_retrieve(name,qrow["topic_entity"],complete_set,"E2",target_relation=qrow["relation"])
    e2=[x for x in e2 if x["head"] not in removed]; e3=[x for x in e3 if x["head"] not in removed]

    shacl_valid=[]; shacl_invalid=[]; shacl_unresolved=[]; shacl_status=[]
    # DeltaSHACL is the only decision path; reference_status (CoPCA logs) is
    # audit-only, any disagreement is logged explicitly.
    for item in e2:
        fact=item["head"]
        ref=reference_status(name,fact)  # audit only, never decides anything
        chk=validate_fact_shacl_delta(name,fact)
        copca_agrees = (
            (ref=="copca_valid" and chk["status"]=="valid") or
            (ref=="copca_violated" and chk["status"]=="invalid") or
            (ref=="unknown")
        )
        if not copca_agrees:
            print(f"[AUDIT reference_status] DISAGREEMENT detected -- {name} {fact}: "
                  f"CoPCA log={ref}, DeltaSHACL={chk['status']} (DeltaSHACL is authoritative)")
        shacl_status.append({"fact":fact,"reference":ref,"copca_agrees":copca_agrees,**chk})
        if chk["status"]=="valid": shacl_valid.append(fact)
        elif chk["status"]=="invalid": shacl_invalid.append(fact)
        else: shacl_unresolved.append(fact)

    random_facts=random_distractors(name,qrow,declared_incomplete)
    oracle=[tuple(qrow["head"])]
    raw={
      "E0_complete_baseline":{"declared":declared_complete,"inferred":[],"random":[],"oracle":[],"shacl_valid":[],"shacl_invalid":[],"shacl_unresolved":[],"shacl_status":[]},
      "E1_incomplete_baseline":{"declared":declared_incomplete,"inferred":[],"random":[],"oracle":[],"shacl_valid":[],"shacl_invalid":[],"shacl_unresolved":[],"shacl_status":[]},
      "E2_incomplete_NS":{"declared":declared_incomplete,"inferred":[x["head"] for x in e2],
        "inferred_labeled":[(x["head"], f"INFERRED(conf={x['pca_confidence']:.2f})") for x in e2],
        "random":[],"oracle":[],"shacl_valid":[],"shacl_invalid":[],"shacl_unresolved":[],"shacl_status":[],"inference_records":e2},
      "E3_incomplete_noPCA":{"declared":declared_incomplete,"inferred":[x["head"] for x in e3],
        "inferred_labeled":[(x["head"], f"INFERRED(conf={x['pca_confidence']:.2f})") for x in e3],
        "random":[],"oracle":[],"shacl_valid":[],"shacl_invalid":[],"shacl_unresolved":[],"shacl_status":[],"inference_records":e3},
      "E4_incomplete_random":{"declared":declared_incomplete,"inferred":[],"random":random_facts,"oracle":[],"shacl_valid":[],"shacl_invalid":[],"shacl_unresolved":[],"shacl_status":[]},
      "E5_complete_NS":{"declared":declared_complete,"inferred":[x["head"] for x in e5],
        "inferred_labeled":[(x["head"], f"INFERRED(conf={x['pca_confidence']:.2f})") for x in e5],
        "random":[],"oracle":[],"shacl_valid":[],"shacl_invalid":[],"shacl_unresolved":[],"shacl_status":[],"inference_records":e5},
      "E6_incomplete_oracle":{"declared":declared_incomplete,"inferred":[],"random":[],"oracle":oracle,"shacl_valid":[],"shacl_invalid":[],"shacl_unresolved":[],"shacl_status":[]},
      "E7_incomplete_NS_SHACL":{"declared":declared_incomplete,"inferred":shacl_valid,"random":[],"oracle":[],"shacl_valid":shacl_valid,"shacl_invalid":shacl_invalid,"shacl_unresolved":shacl_unresolved,"shacl_status":shacl_status,"inference_records":e2},
    }

    for label,ev in raw.items():
        if label in {"E0_complete_baseline","E1_incomplete_baseline"}: ev["context"]=fixed_context(ev["declared"],[],"DECLARED")
        elif label=="E4_incomplete_random": ev["context"]=fixed_context(ev["declared"],[(f,"RANDOM") for f in ev["random"]])
        elif label=="E6_incomplete_oracle": ev["context"]=fixed_context(ev["declared"],[(f,"ORACLE") for f in ev["oracle"]])
        elif label=="E7_incomplete_NS_SHACL": ev["context"]=fixed_context(ev["declared"],[(f,"SHACL_VALIDATED") for f in ev["shacl_valid"]])
        # E2/E3/E5 label each fact with its own PCA confidence, not a generic tag.
        else: ev["context"]=fixed_context(ev["declared"],ev["inferred_labeled"])
    return raw
