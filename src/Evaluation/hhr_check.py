"""27. HHR definition check."""

assert "RESULTS" in globals()
if len(RESULTS) > 0:
    assert "hhr" in RESULTS.columns
    assert "model_id" in RESULTS.columns
for _, r in RESULTS.iterrows():
    if r["hits_any"] and not np.isnan(r["hhr"]):
        expected = r["hits_hard"] / r["hits_any"]
        assert abs(expected - r["hhr"]) < 1e-12
print("HHR check: PASS")
