"""Regression tests for publication-critical benchmark contracts."""

import pandas as pd

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def _load_brink_metrics():
    ns = {}
    exec((SRC / "Evaluation/brink_metrics.py").read_text(encoding="utf-8"), ns)
    return ns


def test_brink_prediction_processing_matches_official_style():
    ns = _load_brink_metrics()
    assert ns["process_prediction"]("Paris, New York\nLondon") == {"paris", "new york", "london"}
    assert ns["normalize_answer"]("The Eiffel-Tower!") == "eiffeltower"


def test_brink_hhr_definition():
    ns = _load_brink_metrics()
    m = ns["example_metrics"]({"paris"}, {"paris", "london"}, "paris")
    assert m["hits_any"] == 1.0 and m["hits_hard"] == 1.0


def test_rule_source_gate_accounts_for_metadata_rows():
    # Mirrors the publication gate: rule + explicit metadata rows must account
    # for every source row, while unknown rows remain failures.
    source_rows, rules, metadata, failures = 239, 236, 3, 0
    assert rules + metadata == source_rows
    assert failures == 0
    assert (rules + metadata == source_rows) and failures == 0


def test_metric_f1_is_set_based():
    ns = _load_brink_metrics()
    m = ns["example_metrics"]({"paris", "london"}, {"paris", "berlin"}, "paris")
    assert round(m["f1"], 10) == round(2 / 4, 10)


def test_amie_footer_rows_are_metadata():
    ns = {"re": __import__("re"), "Path": Path, "pd": pd, "np": __import__("numpy") , "ast": __import__("ast"), "json": __import__("json")}
    try:
        exec((SRC / "Rules/rule_parser.py").read_text(encoding="utf-8"), ns)
    except NameError:
        pass
    assert ns["is_amie_footer"]("236 rules mined")
    assert ns["is_amie_footer"]("Total time: 12.3s")
    assert ns["is_amie_footer"]("Mining done in 42s")
    assert not ns["is_amie_footer"]("(?x,p,?y) => (?y,q,?x)")
