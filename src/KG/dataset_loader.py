"""3. Authoritative dataset loader."""

def parse_rdf(path):
    g = rdflib.Graph()
    suffix = Path(path).suffix.lower()
    fmt = {".nt": "nt", ".ttl": "turtle"}.get(suffix)
    if fmt is None:
        raise ValueError(f"Unsupported KG format for {path}; expected .nt or .ttl")
    g.parse(str(path), format=fmt)
    # rdflib.Graph iteration order depends on Python's per-process hash
    # randomization, which propagated to which groundings got truncated by
    # MAX_GROUNDINGS_PER_RULE. Explicit sort fixes a canonical, deterministic order.
    triples = sorted(g, key=lambda t: tuple(map(str, t)))
    rows = [(str(s), str(p), str(o)) for s, p, o in triples]
    raw_full = pd.DataFrame(rows, columns=["subject", "relation", "object"])
    # Literal detection uses the RDF term type, not string prefix: a
    # startswith('"') check never matches rdflib.Literal's str() output.
    literal_mask_full = pd.Series([isinstance(o, rdflib.Literal) for _, _, o in triples], dtype=bool)

    # drop_duplicates() keeps each surviving row's original label, so .loc
    # selects exactly the matching literal flags -- a positional slice here
    # would silently misalign as soon as any duplicate raw triple exists.
    raw = raw_full.drop_duplicates()
    literal_mask = literal_mask_full.loc[raw.index].reset_index(drop=True)
    raw = raw.reset_index(drop=True)

    type_mask = raw["relation"].map(local_name).str.lower().isin({"type", "rdf:type"})
    semantic = raw.loc[~type_mask & ~literal_mask].copy().reset_index(drop=True)

    return g, raw, semantic, type_mask

def load_dataset(name):
    cfg = DATASETS_CONFIG[name]
    missing = [str(p) for p in cfg.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(f"{name}: missing authoritative files:\n" + "\n".join(missing))

    graph, raw, semantic, type_mask = parse_rdf(cfg["kg"])

    # Auxiliary maps only; raw RDF is untouched.
    entity_uri_map = {}
    relation_uri_map = {}
    # Same hashing non-determinism as parse_rdf; sorted for rigor here too.
    for s, r, o in sorted((str(a), str(b), str(c)) for a, b, c in graph):
        entity_uri_map.setdefault(local_name(s), s)
        entity_uri_map.setdefault(local_name(o), o)
        relation_uri_map.setdefault(local_name(r), r)

    return {
        "name": name,
        "cfg": cfg,
        "rdf_graph": graph,
        "raw": raw,
        "semantic": semantic,
        "type_mask": type_mask,
        "entity_uri_map": entity_uri_map,
        "relation_uri_map": relation_uri_map,
    }

DATA = {}
for name in ACTIVE_DATASETS:
    DATA[name] = load_dataset(name)
    d = DATA[name]
    print("=" * 72)
    print(name)
    print("Raw RDF triples      :", len(d["raw"]))
    print("rdf:type artefacts   :", int(d["type_mask"].sum()))
    print("Semantic QA triples  :", len(d["semantic"]))
    print("Semantic entities    :", len(set(d["semantic"].subject) | set(d["semantic"].object)))
    print("Semantic relations   :", d["semantic"].relation.map(local_name).nunique())
