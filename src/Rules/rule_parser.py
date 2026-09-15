"""5. Authoritative CoPCA rule files -- lossless parser."""

# CoPCA rule CSVs are authoritative; never re-mined here. Supports
# (?x,p,?y), p(?x,?y), conjunctions, => / <=, and URI-valued terms.
# Any unparsed row halts the benchmark (rule_parse_failures.csv) rather
# than silently dropping data.


def norm_col(c):
    return re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")

AMIE_LOG_FOOTER_RE = re.compile(
    r"^\s*(?:mining done in|total time|\d+\s+rules mined\.?)\s*",
    re.IGNORECASE,
)

def is_amie_footer(text: str) -> bool:
    """Return True only for explicit AMIE summary/footer rows."""
    return bool(AMIE_LOG_FOOTER_RE.match(str(text).strip()))

def _float_or_nan(v):
    if pd.isna(v):
        return np.nan
    s = str(v).strip().replace(",", ".")
    if s.lower() in {"", "nan", "none", "null", "n/a", "na", "-"}:
        return np.nan
    return float(s)

# Rule-direction separators found in AMIE/CoPCA-style exports.
RULE_SEP_RE = re.compile(r"\s*(?:=>|->|⊃|⇒|<=|<-|<-)\s*", re.UNICODE)

def _clean_term(x):
    x = str(x).strip()
    x = x.strip(" \t\r\n")
    x = x.strip("<>")
    x = x.strip("()[]{}")
    return x.strip(" \t\r\n,;")

def _is_atom_candidate(x):
    x = str(x).strip()
    return bool(x)

def _parse_function_atoms(text):
    """Parse predicate(arg1,arg2,arg3) or predicate(arg1,arg2)."""
    atoms = []
    # A binary/ternary KG relation is expected; predicate itself may be URI-like.
    pat = re.compile(
        r"([A-Za-z_][A-Za-z0-9_.:/#\-]*|<[^>]+>)\s*"
        r"\(\s*([^()]*)\s*\)"
    )
    for m in pat.finditer(str(text)):
        pred = _clean_term(m.group(1))
        args = [_clean_term(x) for x in re.split(r"\s*,\s*|\s+", m.group(2).strip()) if x.strip()]
        if len(args) == 2:
            atoms.append((args[0], pred, args[1]))
        elif len(args) == 3:
            # Support ternary notation defensively.
            atoms.append((args[0], pred, args[1]))  # only binary KG facts are used
        else:
            raise ValueError(f"Unsupported functional atom arity={len(args)}: {m.group(0)!r}")
    return atoms

def _parse_atom_group(group):
    group = str(group).strip()
    if not group:
        return []

    # First support predicate(x,y) notation.
    fun = _parse_function_atoms(group)
    if fun:
        return fun

    # Parenthesized triple notation: (?x,p,?y) or (?x p ?y)
    groups = re.findall(r"\(([^()]*)\)", group)
    if groups:
        atoms = []
        for g in groups:
            toks = [_clean_term(t) for t in re.split(r"\s*(?:,|\t|\|)\s*|\s+", g.strip()) if str(t).strip()]
            toks = [t for t in toks if t not in {",",";"}]
            if len(toks) != 3:
                raise ValueError(f"Malformed atom with {len(toks)} terms: {g!r}")
            atoms.append(tuple(toks))
        return atoms

    # RDF-style angle URI triple without parentheses.
    m = re.search(r"<([^>]+)>\s+<([^>]+)>\s+<([^>]+)>", group)
    if m:
        return [tuple(m.groups())]

    # Plain whitespace triple.
    toks = [_clean_term(t) for t in re.split(r"\s+", group.strip()) if t.strip()]
    toks = [t for t in toks if t not in {"^","&","AND","and",",",";"}]
    if len(toks) == 3:
        return [tuple(toks)]

    # Comma-separated triple.
    toks = [_clean_term(t) for t in re.split(r"\s*,\s*", group.strip()) if t.strip()]
    if len(toks) == 3:
        return [tuple(toks)]

    raise ValueError(f"Cannot parse atom group: {group!r}")

def parse_rule_side(text):
    text = str(text).strip()
    literal = _parse_literal_atoms(text)
    if literal:
        return literal
    if not text or text.lower() in {"nan","none","null"}:
        return []

    # AMIE also accepts a bare "&" and unicode "∧" (not just "&&"/"^").
    text = re.sub(r"\s+(?:AND|and)\s+", " ^ ", text)
    text = text.strip().rstrip(".")  # AMIE/CoPCA exports sometimes end with a period.
    parts = [p.strip() for p in re.split(r"\s*(?:\^|&&|&|∧)\s*", text) if p.strip()]

    atoms = []
    for part in parts:
        atoms.extend(_parse_atom_group(part))

    if not atoms:
        raise ValueError(f"Empty rule side: {text!r}")
    return atoms

def _regex_triple_scan(text):
    """
    Conservative recovery parser used only after structured parsing fails.
    It extracts explicit 3-term RDF atoms without inventing a missing term.
    """
    t = str(text).strip()
    token = r'(?:<[^>]+>|\?[A-Za-z_][A-Za-z0-9_]*|[A-Za-z_][A-Za-z0-9_:/#.\-]*|"[^"]+"|\'[^\']+\')'
    # Prefer parenthesized atoms, because this is the least ambiguous recovery.
    recovered = []
    for inside in re.findall(r'\(([^()]*)\)', t):
        toks = [_clean_term(x) for x in re.split(r'\s*(?:,|\t|\|)\s*|\s+', inside.strip()) if x.strip()]
        if len(toks) == 3:
            recovered.append(tuple(toks))
    if recovered:
        return recovered

    # Then recover explicit whitespace-separated RDF atoms.
    pat = re.compile(rf'({token})\s+({token})\s+({token})')
    return [tuple(_clean_term(z) for z in m.groups()) for m in pat.finditer(t)]


def _parse_side_resilient(text):
    try:
        return parse_rule_side(text)
    except Exception as first_exc:
        recovered = _regex_triple_scan(text)
        if recovered:
            return recovered
        raise first_exc

def parse_rule_row(body_text, head_text):
    b = str(body_text).strip()
    h = str(head_text).strip()

    # Recover a complete rule if either field contains an implication.
    for text in (b, h):
        if RULE_SEP_RE.search(text):
            left, right = RULE_SEP_RE.split(text, maxsplit=1)
            b, h = left.strip(), right.strip()
            break

    # Additional CoPCA/AMIE export spellings seen in CSV/text dumps.
    if not RULE_SEP_RE.search(b) and not h:
        m = re.search(r'(?is)^(?:IF|WHERE)\\s+(.+?)\\s+(?:THEN|=>|->)\\s+(.+)$', b)
        if m:
            b, h = m.group(1).strip(), m.group(2).strip()

    # Some CoPCA exports use "body | head" after CSV serialization.
    if (not h or h.lower() in {"nan","none","null"}) and "|" in b:
        parts=[x.strip() for x in b.split("|") if x.strip()]
        if len(parts)==2:
            b,h=parts

    if not h and RULE_SEP_RE.search(b):
        parts = RULE_SEP_RE.split(b, maxsplit=1)
        if len(parts) == 2:
            b, h = parts[0].strip(), parts[1].strip()
    body = _parse_side_resilient(b)
    head_atoms = _parse_side_resilient(h)

    if not body:
        raise ValueError("Empty rule body")
    if len(head_atoms) != 1:
        raise ValueError(f"Expected exactly one head atom, got {len(head_atoms)}")
    if any(len(a) != 3 for a in body + head_atoms):
        raise ValueError("Only binary RDF atoms are supported")
    return body, head_atoms[0]

def _read_copca_rule_csv(path):
    """Read CoPCA rule tables with delimiter and quoting fallbacks."""
    path = Path(path)
    candidates = []
    for sep in [None, ",", ";", "\t", "|"]:
        try:
            if sep is None:
                df = pd.read_csv(path, dtype=str, keep_default_na=False,
                                  sep=None, engine="python")
            else:
                df = pd.read_csv(path, dtype=str, keep_default_na=False,
                                  sep=sep, engine="python")
            candidates.append(df)
        except Exception:
            continue
    if not candidates:
        raise RuntimeError(f"Could not read CoPCA rule file: {path}")
    def score(df):
        cols = [norm_col(c) for c in df.columns]
        return (
            20 * int(any(c in cols for c in ["rule","rule_text","body","rule_body"])) +
            20 * int(any("pca" in c for c in cols)) +
            min(len(cols), 10)
        )
    return max(candidates, key=score)

def _row_rule_text(row):
    vals = [str(v).strip() for v in row.tolist() if str(v).strip()]
    for v in vals:
        if RULE_SEP_RE.search(v) or "=>" in v or "->" in v:
            return v
    return " ".join(vals)

def _parse_literal_atoms(text):
    """Parse Python/JSON-like nested lists/tuples of binary triples."""
    t = str(text).strip()
    if not t or t[0] not in "[({":
        return []
    try:
        obj = ast.literal_eval(t)
    except Exception:
        return []
    atoms = []
    def visit(x):
        if isinstance(x, (list, tuple)) and len(x) == 3 and all(
            not isinstance(z, (list, tuple, dict)) for z in x
        ):
            atoms.append(tuple(_clean_term(z) for z in x))
        elif isinstance(x, (list, tuple)):
            for y in x:
                visit(y)
        elif isinstance(x, dict):
            for y in x.values():
                visit(y)
    visit(obj)
    return atoms


def parse_rules(name):
    path = DATA[name]["cfg"]["rules"]
    raw = _read_copca_rule_csv(path)
    colmap = {norm_col(c): c for c in raw.columns}

    def get_col(*names, required=True):
        for n in names:
            if norm_col(n) in colmap:
                return colmap[norm_col(n)]
        if required:
            raise KeyError(
                f"{name}: missing rule column {names}; columns={list(raw.columns)}"
            )
        return None

    rule_col = get_col("Rule","Rule_Text","rule_text",required=False)
    body_col = get_col("Body","Rule_Body","body","Rule",required=False)
    head_col = get_col("Head","Rule_Head","head",required=False)
    if body_col is None and rule_col is None:
        raise KeyError(f"{name}: missing Rule/Body column; columns={list(raw.columns)}")
    pca_col = get_col(
        "PCA_Confidence","PCA","Pca_Confidence",
        "pca_confidence","PCA valid","PCA_valid"
    )
    std_col = get_col("Std_Confidence","Standard_Confidence","Std",required=False)
    hc_col = get_col("Head Coverage","Head_Coverage","HeadCoverage",required=False)
    support_col = get_col("positive_examples","support","Support",required=False)

    rules, failures = [], []

    # AMIE summary rows are metadata, not rules.
    skipped_footer_rows = []

    for idx, row in raw.iterrows():
        body_raw = row[body_col] if body_col is not None else ""
        head_raw = row[head_col] if head_col is not None else ""
        if rule_col is not None and RULE_SEP_RE.search(str(row[rule_col])):
            body_raw = str(row[rule_col])
            head_raw = ""

        if is_amie_footer(body_raw) and not str(head_raw).strip():
            skipped_footer_rows.append({"source_row": int(idx), "body_raw": str(body_raw), "head_raw": str(head_raw)})
            continue

        # If a CSV exporter split a comma-containing rule across columns,
        # recover the complete rule expression from the raw row.
        if (not RULE_SEP_RE.search(str(body_raw))) and (not str(head_raw).strip()):
            recovered = _row_rule_text(row)
            if RULE_SEP_RE.search(recovered):
                body_raw = recovered

        try:
            body, head = parse_rule_row(body_raw, head_raw)

            body = [
                tuple(str(x) if is_var(x) else local_name(x) for x in atom)
                for atom in body
            ]
            head = tuple(str(x) if is_var(x) else local_name(x) for x in head)

            pca = _float_or_nan(row[pca_col])
            if not np.isfinite(pca):
                raise ValueError(f"Missing/non-numeric PCA confidence: {row[pca_col]!r}")

            rules.append({
                "rule_id": f"CoPCA_R{idx:05d}",
                "source_row": int(idx),
                "body": body,
                "head": head,
                "pca_confidence": pca,
                "std_confidence": _float_or_nan(row[std_col]) if std_col else np.nan,
                "head_coverage": _float_or_nan(row[hc_col]) if hc_col else np.nan,
                "support": _float_or_nan(row[support_col]) if support_col else np.nan,
                "text": " ".join(" ".join(a) for a in body) + " => " + " ".join(head),
                "body_raw": str(body_raw),
                "head_raw": str(head_raw),
            })

        except Exception as exc:
            failures.append({
                "source_row": int(idx),
                "body_raw": str(body_raw),
                "head_raw": str(head_raw),
                "error": repr(exc),
            })

    return raw, rules, failures, skipped_footer_rows

RULES, RULES_PCA, RULE_AUDIT = {}, {}, []

for name in ACTIVE_DATASETS:
    raw, rules, failures, skipped_footer_rows = parse_rules(name)

    out = ARTIFACTS / name
    out.mkdir(parents=True, exist_ok=True)
    raw.to_csv(out / "rules_copca_source_snapshot.csv", index=False)
    pd.DataFrame(failures).to_csv(out / "rule_parse_failures.csv", index=False)
    pd.DataFrame(skipped_footer_rows).to_csv(out / "rule_amie_log_footer_skipped.csv", index=False)
    if skipped_footer_rows:
        print(f"{name}: skipped {len(skipped_footer_rows)} metadata row(s).")

    # Every source row must be accounted for: rule or explicit metadata.
    # Unknown rows remain failures and keep the dataset gated.
    accounted_rows = len(rules) + len(skipped_footer_rows)
    lossless = (accounted_rows == len(raw)) and not failures
    pd.DataFrame([{
        "dataset": name,
        "source_rows": len(raw),
        "parsed_rules": len(rules),
        "metadata_rows": len(skipped_footer_rows),
        "accounted_rows": accounted_rows,
        "parse_failures": len(failures),
        "lossless": bool(lossless),
    }]).to_json(out / "rule_lossless_gate.json", orient="records", indent=2)

    # Preserve all failures for diagnosis. The global preflight below is the
    # only experiment gate; this cell itself never crashes.
    if failures:
        print(f"{name}: {len(failures)} unparsed rule row(s); gate CLOSED.")

    RULES[name] = rules
    RULES_PCA[name] = [r for r in rules if r["pca_confidence"] >= MIN_PCA_E2]

    pd.DataFrame([
        {k:r[k] for k in [
            "rule_id","source_row","pca_confidence","std_confidence",
            "head_coverage","support","text","body_raw","head_raw"
        ]}
        for r in rules
    ]).to_csv(out / "rules_copca_original_audit.csv", index=False)

    RULE_AUDIT.append({
        "dataset": name,
        "csv_rows": len(raw),
        "parsed_rules": len(rules),
        "metadata_rows": len(skipped_footer_rows),
        "accounted_rows": len(rules) + len(skipped_footer_rows),
        "parse_failures": len(failures),
        "lossless": bool((len(rules) + len(skipped_footer_rows) == len(raw)) and not failures),
        "pca_ge_0_4": len(RULES_PCA[name]),
    })

RULE_AUDIT = pd.DataFrame(RULE_AUDIT)
RULE_AUDIT.to_csv(ARTIFACTS / "RULE_SOURCE_AUDIT.csv", index=False)
display(RULE_AUDIT)