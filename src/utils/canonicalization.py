"""2. Canonicalization + hashing + serialization utilities."""

def local_name(x):
    s = str(x).strip()
    if s.startswith("<") and s.endswith(">"):
        s = s[1:-1]
    if s.startswith("http://") or s.startswith("https://"):
        s = s.rstrip("/")
        s = s.rsplit("#", 1)[-1]
        s = s.rsplit("/", 1)[-1]
    return s

def is_var(x):
    return str(x).startswith("?")

def canonical_entity(x):
    return local_name(x)

def canonical_relation(x):
    return local_name(x)

def canonical_fact(fact):
    if len(fact) != 3:
        raise ValueError(f"Expected triple of length 3: {fact}")
    return tuple(local_name(x) if not is_var(x) else str(x) for x in fact)

def sha_key(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()

def fact_id(fact):
    return hashlib.sha1(repr(tuple(fact)).encode("utf-8")).hexdigest()[:16]

def dedup_triples(items):
    out, seen = [], set()
    for x in items or []:
        t = tuple(x[:3]) if len(x) >= 3 else tuple(x)
        if len(t) != 3 or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
