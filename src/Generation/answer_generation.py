"""15. Shared answer generation."""

# INFERRED facts carry their PCA confidence in the label; the LLM is told what it means.
SYSTEM_PROMPT = (
    "You answer a knowledge-graph question using ONLY the supplied facts.\n"
    "DECLARED facts are explicit KG facts.\n"
    "INFERRED(conf=X) facts are derived by a symbolic rule with confidence X in [0,1]; "
    "treat values below 0.8 with caution, they may be wrong.\n"
    "RANDOM facts are distractors.\n"
    "ORACLE facts are privileged evidence.\n"
    "SHACL_VALIDATED facts passed the configured SHACL validation.\n"
    "Return only a comma-separated list of entity names.\n"
    "Do not explain your reasoning.\n"
    "If the facts are insufficient, return UNKNOWN."
)

def format_context(ctx):
    lines = []
    for fact, label in ctx:
        s, r, o = fact[:3]
        lines.append(f"{label} | {local_name(s)} | {local_name(r)} | {local_name(o)}")
    return "\n".join(lines) if lines else "(none)"

def answer_question(question, ctx, track_key, model_id):
    messages = [{
        "role": "user",
        "content": (
            f"{SYSTEM_PROMPT}\n\n"
            f"QUESTION:\n{question}\n\n"
            f"CONTEXT:\n{format_context(ctx)}"
        )
    }]
    return cached_chat(
        messages,
        model_id=model_id,
        max_tokens=MAX_NEW_TOKENS,
        temperature=TEMPERATURE,
        purpose="answer",
        track_key=track_key,
    )
