"""8. LLM-generated questions (BRINK protocol) + template fallback."""

# BRINK-style question generation with deterministic validation and fallback.
QUESTION_GEN_MODEL = MODEL_ORDER[0]

GENERIC_RELATION_TEMPLATES = [
    "What is the {relation} of {s}?",
    "Which entity is related to {s} by {relation}?",
]
REL_TEMPLATES_BY_DATASET = {
    "FrenchRoyalty": {
        "parent":["What is the parent of {s}?","Which person is a parent of {s}?"],
        "mother":["Who is the mother of {s}?"], "father":["Who is the father of {s}?"],
        "spouse":["Who is the spouse of {s}?"], "hasSpouse":["Who is the spouse of {s}?"],
        "child":["Who is a child of {s}?"], "successor":["Who is the successor of {s}?"],
        "predecessor":["Who is the predecessor of {s}?"], "gender":["What is the gender of {s}?"],
        "name":["What is the name associated with {s}?"],
    },
    "DB100K": {},
    "YAGO3-10": {},
}

def _normalize_for_entity_match(x):
    """A question's validity is checked by comparing the entity's LOCAL name
    (e.g. "Louis_XI", underscore inherited from the URI) against the question
    text written by the LLM, which naturally expresses it with a space
    ("Louis XI"), never an underscore. Without normalization: (a) the "the
    question must mention the subject" check would fail almost systematically
    whenever a name contains an underscore (far more common on FrenchRoyalty,
    with its compound royal names, than on DB100K/YAGO3-10); (b) more
    seriously, the symmetric "the question must not leak the answer" check
    could fail to trigger for the same reason, letting through a question that
    does reveal the answer whenever that answer contains an underscore and the
    LLM paraphrased it with a space -- a scientific-integrity risk, not merely
    a yield problem. This normalization (underscore -> space, case-insensitive)
    applies ONLY to the validity comparison; the question text and identifiers
    themselves are left unchanged."""
    return x.replace("_", " ").lower()

def make_question_template(name, fact):
    """Deterministic fallback -- used only when LLM generation fails validation."""
    s, r, o = map(local_name, fact); rel = r
    templates = REL_TEMPLATES_BY_DATASET.get(name, {}).get(rel)
    if not templates:
        templates = [x.format(relation=rel.replace("_", " "), s=s) for x in GENERIC_RELATION_TEMPLATES]
    for t in templates:
        q = t.format(s=s, relation=rel.replace("_", " "))
        # Same underscore/space normalization as make_question_llm, for consistency.
        if _normalize_for_entity_match(o) not in _normalize_for_entity_match(q):
            return q
    return templates[0].format(s=s, relation=rel.replace("_", " "))

QUESTION_GEN_SYSTEM_PROMPT = (
    "You write a single short natural-language question that asks for the "
    "{relation} of {s}, following the BRINK benchmark protocol. "
    "Rules: (1) the question must mention the subject entity exactly as given; "
    "(2) the question must NOT mention or hint at the answer entity; "
    "(3) output ONLY the question text, no explanation, no quotes."
)

def make_question_llm(name, fact):
    """BRINK-style LLM question generation. Returns (question, source) where
    source in {'llm', 'template_fallback'}; validity checks mirror BRINK's own
    requirement that the removed answer must not leak into the question text."""
    s, r, o = map(local_name, fact)
    rel_readable = r.replace("_", " ")
    prompt = QUESTION_GEN_SYSTEM_PROMPT.format(relation=rel_readable, s=s)
    try:
        raw = cached_chat(
            [{"role": "user", "content": prompt}],
            model_id=QUESTION_GEN_MODEL, max_tokens=48, temperature=0.0,
            purpose="question_generation",
            track_key=f"{name}:qgen:{fact_id((s, r, o))}",
        )
        q = raw.strip().strip('"').strip()
        q_norm = _normalize_for_entity_match(q)
        s_norm = _normalize_for_entity_match(s)
        o_norm = _normalize_for_entity_match(o)
        valid = bool(q) and (o_norm not in q_norm) and (s_norm in q_norm)
        if valid:
            return q, "llm"
    except LLMCallError as e:
        print(f"[question-gen] LLM unavailable for {name}/{fact_id((s,r,o))} ({e}); falling back to template.")
    return make_question_template(name, fact), "template_fallback"

def build_questions(name):
    b=BENCH[name]; complete=b["complete"]
    complete_idx=defaultdict(set)
    for s,r,o in complete.itertuples(index=False,name=None): complete_idx[(local_name(s),local_name(r))].add(local_name(o))
    rows=[]; qgen_stats=Counter()
    for split_pos,(_,row) in enumerate(b["splits"]["test"].iterrows()):
        s,r,o=map(local_name,row["head_canon"])
        q, source = make_question_llm(name, (s, r, o))
        qgen_stats[source] += 1
        # May legitimately drop a question (e.g. answer name appears by coincidence).
        if _normalize_for_entity_match(o) in _normalize_for_entity_match(q): continue  # belt-and-braces: never accept an answer-leaking question
        rows.append({"question_id":f"{name}_TEST_{split_pos:06d}","fact_id":fact_id((s,r,o)),"question":q,
                     "question_source":source,
                     "topic_entity":s,"relation":r,"hard_answer":o,"gold_answers":sorted(complete_idx[(s,r)]),
                     "head":(s,r,o),"rule_id":str(row["rule_id"]),"pca_confidence":float(row["pca_confidence"])})
    qdf=pd.DataFrame(rows)
    (ARTIFACTS/name).mkdir(parents=True,exist_ok=True)
    if MAX_TEST_QUESTIONS is not None: qdf=qdf.head(int(MAX_TEST_QUESTIONS)).copy()
    qdf.to_json(ARTIFACTS/name/"test_questions.json",orient="records",force_ascii=False,indent=2)
    # question_source records LLM vs. template fallback per question.
    qdf.to_csv(ARTIFACTS/name/"test_questions.csv",index=False)
    print(f"{name}: questions={len(qdf)}; provenance={dict(qgen_stats)}")
    return qdf

QUESTIONS={}
# MAX_QUESTIONS_OVERRIDE truncates to the first N questions (frozen,
# deterministic order); per-question resume reuses earlier checkpoints.
_MAX_Q_OVERRIDE = os.environ.get("MAX_QUESTIONS_OVERRIDE", "").strip()
for name in EVALUABLE_DATASETS:
    QUESTIONS[name]=build_questions(name)
    if _MAX_Q_OVERRIDE:
        _n = int(_MAX_Q_OVERRIDE)
        if len(QUESTIONS[name]) > _n:
            QUESTIONS[name] = QUESTIONS[name].iloc[:_n].copy().reset_index(drop=True)
            print(f"[MAX_QUESTIONS_OVERRIDE] {name} truncated to {_n} questions (from the already-frozen deterministic prefix)")
    print(name,"| test:",len(QUESTIONS[name]),"| split_test:",len(BENCH[name]["splits"]["test"]))
    print("relations:",QUESTIONS[name]["relation"].value_counts().to_dict() if len(QUESTIONS[name]) else {})
