"""4. SHACL loading + DeltaSHACL validation gate."""

# PropertyShape links == 0 does not mean "unconstrained": NodeShapes may
# constrain directly via targetClass/targetNode/etc. E7's source of truth is
# the CoPCA .ttl shape graph; the target logs are audit references only.

SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
RDF_NS = rdflib.RDF

def load_shacl(path):
    if path is None or not path.exists():
        return None
    g = rdflib.Graph()
    g.parse(str(path), format="turtle")
    return g

for name in ACTIVE_DATASETS:
    DATA[name]["shacl_graph"] = load_shacl(DATA[name]["cfg"]["shacl"])
    sg = DATA[name]["shacl_graph"]
    print(name, "| SHACL triples:", len(sg) if sg is not None else 0)

def shacl_deep_inventory(name):
    sg = DATA[name]["shacl_graph"]
    if sg is None:
        return {"dataset":name,"available":False}
    node_shapes=set(sg.subjects(RDF_NS.type,SH.NodeShape))
    property_shapes=set(sg.subjects(RDF_NS.type,SH.PropertyShape))
    prop_links=list(sg.triples((None,SH.property,None)))
    target_preds=[SH.targetClass,SH.targetNode,SH.targetSubjectsOf,SH.targetObjectsOf]
    constraint_preds=[
        SH.minCount,SH.maxCount,SH.datatype,SH.pattern,SH.minLength,SH.maxLength,
        SH.languageIn,SH.uniqueLang,SH.in_,SH.hasValue,SH.equals,SH.disjoint,
        SH.lessThan,SH.lessThanOrEquals,SH.nodeKind,SH["class"],SH.node,
        SH.or_,SH.and_,SH.xone,SH.not_,SH.closed,SH.ignoredProperties
    ]
    target_counts={local_name(p):len(list(sg.triples((None,p,None)))) for p in target_preds}
    constraint_count=sum(len(list(sg.triples((None,p,None)))) for p in constraint_preds)
    return {
        "dataset":name,"available":True,"triples":len(sg),
        "NodeShapes":len(node_shapes),"PropertyShapes":len(property_shapes),
        "PropertyShape_links":len(prop_links),
        "target_mechanisms":sum(target_counts.values()),
        "direct_constraint_triples":constraint_count,
        "path_declarations":len(list(sg.triples((None,SH.path,None)))),
        "closed_shapes":len(list(sg.triples((None,SH.closed,None)))),
        **target_counts
    }

SHACL_DEEP_AUDIT = pd.DataFrame([shacl_deep_inventory(n) for n in ACTIVE_DATASETS])

# Alias for the preflight cell; same inventory, not a second source.
SHACL_AUDIT = SHACL_DEEP_AUDIT.copy()

display(SHACL_AUDIT)
SHACL_AUDIT.to_csv(ARTIFACTS/"SHACL_DEEP_AUDIT.csv", index=False)

# Counts all constraint predicates present, including NodeShape-level ones.
SHACL_CONSTRAINT_PREDICATES = [
    SH.minCount, SH.maxCount, SH.datatype, SH.pattern, SH.minLength,
    SH.maxLength, SH.languageIn, SH.uniqueLang, SH.in_, SH.hasValue,
    SH.equals, SH.disjoint, SH.lessThan, SH.lessThanOrEquals, SH.nodeKind,
    SH["class"], SH.node, SH.or_, SH.and_, SH.xone, SH.not_, SH.closed,
    SH.ignoredProperties, SH.property, SH.path, SH.targetClass, SH.targetNode,
    SH.targetSubjectsOf, SH.targetObjectsOf
]

_constraint_rows = []
for name in ACTIVE_DATASETS:
    sg = DATA[name]["shacl_graph"]
    if sg is None:
        continue
    for pred in SHACL_CONSTRAINT_PREDICATES:
        n = len(list(sg.triples((None, pred, None))))
        if n:
            _constraint_rows.append({
                "dataset": name,
                "predicate": local_name(pred),
                "triples": n,
            })

SHACL_CONSTRAINT_AUDIT = pd.DataFrame(
    _constraint_rows, columns=["dataset", "predicate", "triples"]
)
SHACL_CONSTRAINT_AUDIT.to_csv(
    ARTIFACTS/"SHACL_CONSTRAINT_PREDICATE_AUDIT.csv", index=False
)
display(SHACL_CONSTRAINT_AUDIT)

print("SHACL audit ready; E7 source: dataset-specific CoPCA TTL.")

print("SHACL inventory: PropertyShape links are structural only; targetClass/other constraints may still apply.")

# DeltaSHACL diffs validation-result signatures before/after, not a
# conforms boolean (which missed pre-existing-violation false rejects, 89.9% of them).
_GQ_TRIPLES_LIST_CACHE = {}
_SHACL_SHAPE_TRIPLES_CACHE = {}
_SHACL_BASELINE_CACHE = {}

def _validation_signature(report_graph):
    """A hashable set of (predicate, value) tuples per SHACL ValidationResult,
    built only from focusNode/sourceShape/resultPath/sourceConstraintComponent/
    value/resultSeverity -- never from the ValidationResult node's own
    (possibly blank-node) identity. Shape and data terms are reused from
    cached triple lists across calls, so a blank-node-valued sourceShape or
    resultPath stays stable between the "before" and "after" validation runs,
    making the diff meaningful rather than an artifact of object identity."""
    signature = set()
    for result in report_graph.subjects(RDF_NS.type, SH.ValidationResult):
        values = []
        for predicate in (SH.focusNode, SH.sourceShape, SH.resultPath,
                           SH.sourceConstraintComponent, SH.value, SH.resultSeverity):
            for value in sorted(str(x) for x in report_graph.objects(result, predicate)):
                values.append((str(predicate), value))
        signature.add(tuple(values))
    return frozenset(signature)

def _shacl_validate_signature(name, triples, focus_nodes):
    if name not in _SHACL_SHAPE_TRIPLES_CACHE:
        _SHACL_SHAPE_TRIPLES_CACHE[name] = list(DATA[name]["shacl_graph"])

    data_graph = rdflib.Graph()
    for t in triples:
        data_graph.add(t)
    shape_graph = rdflib.Graph()
    for t in _SHACL_SHAPE_TRIPLES_CACHE[name]:
        shape_graph.add(t)

    try:
        conforms, report_graph, report_text = pyshacl.validate(
            data_graph=data_graph, shacl_graph=shape_graph, inference="none",
            abort_on_first=False, advanced=True, focus_nodes=focus_nodes
        )
        if not isinstance(report_graph, rdflib.Graph):
            # Keep the real ValidationFailure message, not a downstream exception.
            failure_message = getattr(report_graph, "message", None)
            return {"status": "error",
                    "error": f"ValidationFailure: {failure_message!r} conforms={conforms!r} report_text={str(report_text)[:500]!r}",
                    "signature": frozenset(), "scope_ok": None}
        signature = _validation_signature(report_graph)
        # Scope guard: an unexpected Focus Node means validation drifted to the whole graph.
        expected_focus = {str(n) for n in focus_nodes}
        actual_focus = {str(n) for n in report_graph.objects(None, SH.focusNode)}
        scope_ok = actual_focus.issubset(expected_focus)
        return {"status": "valid" if bool(conforms) else "invalid",
                "signature": signature, "error": None, "scope_ok": scope_ok,
                "unexpected_focus_nodes": sorted(actual_focus - expected_focus)[:20]}
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}", "signature": frozenset(), "scope_ok": None}

def _baseline_shacl_signature(name, focus_nodes):
    # Cached per focus-node pair: many candidates share the same (subject, object).
    key = (name, tuple(sorted(str(n) for n in focus_nodes)))
    if key not in _SHACL_BASELINE_CACHE:
        if name not in _GQ_TRIPLES_LIST_CACHE:
            _GQ_TRIPLES_LIST_CACHE[name] = list(incomplete_rdf_graph(name))
        _SHACL_BASELINE_CACHE[key] = _shacl_validate_signature(name, _GQ_TRIPLES_LIST_CACHE[name], focus_nodes)
    return _SHACL_BASELINE_CACHE[key]

def validate_fact_shacl_delta(name, fact):
    # The triple-list conversion is cached once per dataset (was rebuilt per
    # candidate before, an 8x slowdown on DB100K). The rdflib Graph itself is
    # still rebuilt fresh per call, to avoid a shared/degraded-object bug.
    if name not in _GQ_TRIPLES_LIST_CACHE:
        _GQ_TRIPLES_LIST_CACHE[name] = list(incomplete_rdf_graph(name))

    candidate_triple = fact_uri_triple(name, fact)
    focus_nodes = _focus_nodes_for_fact(name, fact)

    before = _baseline_shacl_signature(name, focus_nodes)
    if before["status"] == "error":
        return {"status": "error", "reason": "pyshacl_error",
                "error_before": before["error"], "error_after": None}

    candidate_triples = list(_GQ_TRIPLES_LIST_CACHE[name])
    candidate_triples.append(candidate_triple)
    after = _shacl_validate_signature(name, candidate_triples, focus_nodes)
    if after["status"] == "error":
        return {"status": "error", "reason": "pyshacl_error",
                "error_before": None, "error_after": after["error"]}

    new_violations = after["signature"] - before["signature"]
    if new_violations:
        return {"status": "invalid", "reason": "candidate_induced",
                "new_violation_count": len(new_violations), "scope_ok": after.get("scope_ok"),
                "unexpected_focus_nodes": after.get("unexpected_focus_nodes", [])}
    else:
        return {"status": "valid", "reason": "no_new_violation",
                "new_violation_count": 0, "scope_ok": after.get("scope_ok"),
                "unexpected_focus_nodes": after.get("unexpected_focus_nodes", [])}

def to_original_uri(name, value, kind):
    value = str(value)
    if value.startswith("http://") or value.startswith("https://"):
        return value
    d = DATA[name]
    mp = d["relation_uri_map"] if kind == "relation" else d["entity_uri_map"]
    return mp.get(local_name(value), value)

def incomplete_rdf_graph(name):
    if "incomplete_rdf_graph" in DATA[name]:
        return DATA[name]["incomplete_rdf_graph"]
    g = rdflib.Graph()
    removed = BENCH[name]["removed_test"] if "BENCH" in globals() else set()
    for s,p,o in DATA[name]["rdf_graph"]:
        t = canonical_fact((s,p,o))
        if t in removed:
            continue
        g.add((s,p,o))
    DATA[name]["incomplete_rdf_graph"] = g
    return g

def fact_uri_triple(name, fact):
    s,r,o = fact
    return (
        rdflib.URIRef(to_original_uri(name,s,"entity")),
        rdflib.URIRef(to_original_uri(name,r,"relation")),
        rdflib.URIRef(to_original_uri(name,o,"entity")),
    )

SHACL_CACHE={}

def _focus_nodes_for_fact(name,fact):
    s,r,o=fact
    return [
        rdflib.URIRef(to_original_uri(name,s,"entity")),
        rdflib.URIRef(to_original_uri(name,o,"entity"))
    ]

# CoPCA validates with TravSHACL against a SPARQL endpoint; this pipeline
# uses in-memory pySHACL instead (same .ttl shapes, different tool), since a
# SPARQL endpoint would be far too slow for per-candidate, ad-hoc validation.
def validate_fact_shacl(name,fact):
    # DEPRECATED, kept only so the historical flaw (89.9% of rejections were
    # pre-existing, not candidate-induced) stays reproducible. Never called;
    # validate_fact_shacl_delta() is the only active gate.
    shapes_persistent=DATA[name]["shacl_graph"]
    if shapes_persistent is None:
        return {"status":"unavailable","conforms":None,"source":"none"}
    key=(name,tuple(map(str,fact)))
    if key in SHACL_CACHE:
        return SHACL_CACHE[key]

    # Fresh shapes graph per call, not reused: a reused object degraded
    # across thousands of calls (later retrievers got worse verdicts); shapes
    # are tiny (4-24 triples) so rebuilding costs little.
    shapes=rdflib.Graph()
    for t in shapes_persistent: shapes.add(t)

    candidate_triple=fact_uri_triple(name,fact)

    def _run_pyshacl(data_graph):
        # focus_nodes is required: without it, every person in the graph is
        # targeted, surfacing unrelated pre-existing violations instead of
        # the candidate's own subject/object.
        conforms, report_graph, report_text=pyshacl.validate(
            data_graph=data_graph, shacl_graph=shapes, inference="none",
            abort_on_first=False, advanced=True,
            focus_nodes=_focus_nodes_for_fact(name,fact)
        )
        if not isinstance(report_graph, rdflib.Graph):
            failure_message = getattr(report_graph, "message", None)
            raise RuntimeError(
                f"pySHACL ValidationFailure (formal SHACL-spec failure, not a library bug): "
                f"message={failure_message!r}, conforms={conforms!r}, "
                f"report_text={str(report_text)[:1000]!r}"
            )
        nvr=len(list(report_graph.subjects(RDF_NS.type,SH.ValidationResult)))
        # Scope guard: flag (not crash on) any focus node outside the
        # candidate's own subject/object -- would mean validation drifted
        # back to the whole graph.
        expected_focus = {str(n) for n in _focus_nodes_for_fact(name, fact)}
        actual_focus = {str(n) for n in report_graph.objects(None, SH.focusNode)}
        unexpected_focus = sorted(actual_focus - expected_focus)
        return {
            "status":"valid" if bool(conforms) else "invalid",
            "conforms":bool(conforms),
            "source":"pyshacl+CoPCA_TTL",
            "violation_count":nvr,
            "report":str(report_text)[:20000],
            "scope_ok": len(unexpected_focus) == 0,
            "unexpected_focus_nodes": unexpected_focus[:20],
        }

    # Fresh, isolated graph per call, not a reused mutable object: reuse
    # caused progressive degradation across a campaign (see gate note above).
    g_isolated=rdflib.Graph()
    for t in incomplete_rdf_graph(name): g_isolated.add(t)
    g_isolated.add(candidate_triple)
    try:
        result=_run_pyshacl(g_isolated)
    except Exception as exc:
        result={"status":"error","conforms":None,
                "source":"pyshacl+CoPCA_TTL","violation_count":None,
                "report":repr(exc)}

    SHACL_CACHE[key]=result
    return result

for name in ACTIVE_DATASETS:
    assert DATA[name]["shacl_graph"] is not None, f"{name}: missing CoPCA SHACL TTL"

print("E7 source: CoPCA TTL; target logs are audit-only.")
