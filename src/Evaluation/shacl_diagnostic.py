"""17c. SHACL diagnostic."""


SHACL_DIAG_ROWS = []
for mid, traces in ALL_TRACES_BY_MODEL.items():
    for (name, ret, cond), df in traces.items():
        if cond != "E7_incomplete_NS_SHACL" or df is None or len(df) == 0:
            continue
        n = len(df)
        valid = int(df["shacl_valid_count"].sum())
        invalid = int(df["shacl_invalid_count"].sum())
        unresolved = int(df["shacl_unresolved_count"].sum())
        candidates = valid + invalid + unresolved
        SHACL_DIAG_ROWS.append({
            "model_id": mid, "dataset": name, "retriever": ret,
            "n_questions": n, "ns_candidates_total": candidates,
            "shacl_valid": valid, "shacl_invalid": invalid, "shacl_unresolved": unresolved,
            "valid_share": round(valid / candidates, 4) if candidates else float("nan"),
            "unresolved_share": round(unresolved / candidates, 4) if candidates else float("nan"),
        })
SHACL_DIAG = pd.DataFrame(SHACL_DIAG_ROWS)
SHACL_DIAG.to_csv(ARTIFACTS / "SHACL_REJECTION_DIAGNOSTIC.csv", index=False)
display(SHACL_DIAG)

# Distinguishes real rejections (invalid>0) from mechanical failures (unresolved).
if len(SHACL_DIAG):
    if (SHACL_DIAG["ns_candidates_total"] == 0).any():
        print("ALERT: no NS candidate generated for at least one row (ns_candidates_total=0) "
              "-> the problem is upstream of SHACL, in ns_retrieve()/RULES_PCA "
              "(check MIN_PCA_E2 and grounding for this entity/KG).")
    elif (SHACL_DIAG["unresolved_share"].fillna(0) > 0.3).any() and (SHACL_DIAG["shacl_invalid"] == 0).all():
        print("ALERT: a large share of SHACL statuses are 'unresolved/error', AND no real "
              "'invalid' verdict appears anywhere -> likely a mechanical blockage (e.g. an "
              "engine ValidationFailure), not a genuine rejection of noisy rules. Inspect the "
              "'report' field of the examples below before concluding anything.")
    elif (SHACL_DIAG["valid_share"].fillna(0) == 0).any() and (SHACL_DIAG["shacl_invalid"] > 0).any():
        print("NOTE: valid_share=0 but real 'invalid' rejections do exist -> the validation "
              "mechanism is working (SHACL reaches a real verdict), but no candidate has been "
              "judged conformant yet in this sample. Worth monitoring as more data accumulates; "
              "not necessarily a bug.")
    elif (SHACL_DIAG["valid_share"].fillna(0) == 0).any():
        print("ALERT: valid_share=0 for at least one model/KG/retriever despite NS candidates "
              "being generated, and no real 'invalid' rejection either -> SHACL is failing "
              "mechanically on 100% of candidates. Inspect a few individual examples "
              "(shacl_status below) before concluding anything.")
    else:
        print("SHACL is working: a non-zero share of candidates is validated, and rejections "
              "remain mostly 'invalid' (not 'unresolved').")

# Scope guard: a Focus Node outside subject+object means validation drifted.
_scope_violations = 0
for mid, traces in ALL_TRACES_BY_MODEL.items():
    for (name, ret, cond), df in traces.items():
        if cond != "E7_incomplete_NS_SHACL" or df is None or len(df) == 0:
            continue
        for _, row in df.iterrows():
            for s in (row.get("shacl_status") or []):
                if s.get("scope_ok") is False:
                    _scope_violations += 1
if _scope_violations:
    print(f"\nSHACL SCOPE ALERT: {_scope_violations} candidate(s) with a Focus Node outside the "
          f"expected scope -> the 'invalid' counts above include violations unrelated to the "
          f"candidate actually being tested. See 'unexpected_focus_nodes' in shacl_status to "
          f"identify the offending nodes.")
else:
    print("\nSHACL scope verified: no out-of-scope Focus Node detected.")

# Up to 5 concrete examples for human review.
shown = 0
for mid, traces in ALL_TRACES_BY_MODEL.items():
    for (name, ret, cond), df in traces.items():
        if cond != "E7_incomplete_NS_SHACL" or df is None or len(df) == 0:
            continue
        for _, row in df.iterrows():
            for s in (row.get("shacl_status") or []):
                # Field names match validate_fact_shacl_delta()'s output, not
                # the deprecated function's (a past mismatch here always
                # printed "None" for the real error message).
                print(f"[{mid}/{name}/{ret}] fact={s.get('fact')} reference={s.get('reference')} "
                      f"status={s.get('status')} reason={s.get('reason')} "
                      f"new_violations={s.get('new_violation_count')}")
                if s.get("status") == "error":
                    print(f"    -> error_before: {str(s.get('error_before'))[:400]}")
                    print(f"    -> error_after:  {str(s.get('error_after'))[:400]}")
                shown += 1
                if shown >= 5:
                    break
            if shown >= 5:
                break
        if shown >= 5:
            break
    if shown >= 5:
        break
if shown == 0:
    print("No shacl_status record found (E7 not yet run for this model/KG).")
