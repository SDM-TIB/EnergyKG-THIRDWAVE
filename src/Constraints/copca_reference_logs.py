"""4b. CoPCA validation reference logs (audit only)."""

# targets_valid.log / targets_violated.log are CoPCA validation-output logs,
# not RDF triples ("0 parsed" != "0 valid"). Used only as an independent
# audit reference; SHACL itself validates BRINK candidates.

def _extract_rdf_terms(text):
    """Extract RDF/URI-like terms conservatively for target-level auditing."""
    text = str(text)
    terms = []
    # <URI>
    terms.extend(re.findall(r"<([^<>]+)>", text))
    # bare http(s)/urn URIs
    terms.extend(re.findall(r"(?:https?://|urn:)[^\s,;|)\]}>\"']+", text))
    # remove punctuation
    return [str(x).strip().strip(".,;:|") for x in terms if str(x).strip()]

def parse_copca_target_log(path):
    path = Path(path)
    if not path.exists():
        return {
            "exists": False, "file_lines": 0, "nonempty_lines": 0,
            "target_lines": [], "extracted_terms": set(),
            "term_lines": 0, "unmatched_nonempty_lines": []
        }

    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    target_lines, extracted_terms, unmatched = [], set(), []

    for lineno, raw in enumerate(lines, start=1):
        line = str(raw).strip()
        if not line:
            continue
        terms = _extract_rdf_terms(line)
        if terms:
            extracted_terms.update(terms)
            target_lines.append({"line": lineno, "text": line[:2000], "terms": terms})
        else:
            unmatched.append({"line": lineno, "text": line[:2000]})

    return {
        "exists": True,
        "file_lines": len(lines),
        "nonempty_lines": sum(bool(str(x).strip()) for x in lines),
        "target_lines": target_lines,
        "extracted_terms": extracted_terms,
        "term_lines": len(target_lines),
        "unmatched_nonempty_lines": unmatched,
    }

COPCA_REFERENCE = {}
LOG_AUDIT = []

for name in ACTIVE_DATASETS:
    valid = parse_copca_target_log(DATA[name]["cfg"]["valid_log"])
    violated = parse_copca_target_log(DATA[name]["cfg"]["violated_log"])

    COPCA_REFERENCE[name] = {
        "valid_target_lines": valid["target_lines"],
        "violated_target_lines": violated["target_lines"],
        "valid_terms": valid["extracted_terms"],
        "violated_terms": violated["extracted_terms"],
    }

    LOG_AUDIT.append({
        "dataset": name,
        "valid_file_lines": valid["file_lines"],
        "violated_file_lines": violated["file_lines"],
        "valid_nonempty_lines": valid["nonempty_lines"],
        "violated_nonempty_lines": violated["nonempty_lines"],
        "valid_target_lines_with_rdf_terms": valid["term_lines"],
        "violated_target_lines_with_rdf_terms": violated["term_lines"],
        "valid_unique_terms_extracted": len(valid["extracted_terms"]),
        "violated_unique_terms_extracted": len(violated["extracted_terms"]),
        "valid_unmatched_nonempty_lines": len(valid["unmatched_nonempty_lines"]),
        "violated_unmatched_nonempty_lines": len(violated["unmatched_nonempty_lines"]),
        "valid_log_exists": int(valid["exists"]),
        "violated_log_exists": int(violated["exists"]),
    })

    out = ARTIFACTS / name
    out.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(valid["target_lines"]).to_json(
        out / "copca_valid_target_log_extracted.jsonl",
        orient="records", lines=True, force_ascii=False
    )
    pd.DataFrame(violated["target_lines"]).to_json(
        out / "copca_violated_target_log_extracted.jsonl",
        orient="records", lines=True, force_ascii=False
    )
    pd.DataFrame(valid["unmatched_nonempty_lines"]).to_csv(
        out / "copca_valid_unmatched_lines.csv", index=False
    )
    pd.DataFrame(violated["unmatched_nonempty_lines"]).to_csv(
        out / "copca_violated_unmatched_lines.csv", index=False
    )

LOG_AUDIT = pd.DataFrame(LOG_AUDIT)
LOG_AUDIT.to_csv(ARTIFACTS / "COPCA_TARGET_LOG_AUDIT.csv", index=False)
display(LOG_AUDIT)

print("CoPCA target logs: audit references only; never converted to fact triples.")
