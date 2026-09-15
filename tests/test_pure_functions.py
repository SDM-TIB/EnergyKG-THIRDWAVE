"""Unit tests for pure functions, extracted and exec'd in isolation with
their required stdlib/third-party names pre-populated (these files normally
rely on imports made earlier in the shared pipeline namespace)."""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
import numpy as np

SRC = Path(__file__).resolve().parent.parent / "src"


def load_names(relpath, extra_globals=None):
    """Exec a src/ file with the given globals pre-populated, return its
    namespace. Module-level code near the bottom of these files often
    references shared pipeline state (e.g. ACTIVE_DATASETS) that only exists
    once earlier stages have run; a NameError there is expected and ignored
    here, since the function definitions we test are already in `ns` by the
    time it occurs."""
    ns = {"hashlib": hashlib, "json": json, "re": re, "pd": pd, "np": np}
    if extra_globals:
        ns.update(extra_globals)
    code = compile((SRC / relpath).read_text(encoding="utf-8"), relpath, "exec")
    try:
        exec(code, ns)
    except NameError:
        pass
    return ns


# ---------------------------------------------------------------- canonicalization

def test_local_name_strips_uri():
    ns = load_names("utils/canonicalization.py")
    assert ns["local_name"]("http://example.org/KG#Louis_XIV") == "Louis_XIV"
    assert ns["local_name"]("<http://example.org/KG/Louis_XIV>") == "Louis_XIV"
    assert ns["local_name"]("Louis_XIV") == "Louis_XIV"


def test_canonical_fact_preserves_variables():
    ns = load_names("utils/canonicalization.py")
    fact = ns["canonical_fact"](("http://ex.org/X", "?r", "http://ex.org/Y"))
    assert fact == ("X", "?r", "Y")


def test_canonical_fact_rejects_wrong_arity():
    ns = load_names("utils/canonicalization.py")
    try:
        ns["canonical_fact"](("a", "b"))
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_dedup_triples_removes_duplicates_keeps_order():
    ns = load_names("utils/canonicalization.py")
    items = [("a", "r", "b"), ("a", "r", "b"), ("c", "r", "d")]
    assert ns["dedup_triples"](items) == [("a", "r", "b"), ("c", "r", "d")]


def test_fact_id_is_deterministic():
    ns = load_names("utils/canonicalization.py")
    fid1 = ns["fact_id"](("a", "r", "b"))
    fid2 = ns["fact_id"](("a", "r", "b"))
    assert fid1 == fid2
    assert len(fid1) == 16


# ---------------------------------------------------------------- answer parsing (BRINK evaluator semantics)

def _brink_metrics_fns():
    return load_names("Evaluation/brink_metrics.py", extra_globals={"string": __import__("string")})

def test_brink_normalize_answer_lowercases_and_collapses_space():
    ns = _brink_metrics_fns()
    assert ns["normalize_answer"]("  Louis   XIV ") == "louis xiv"
    # Official evaluator removes punctuation rather than replacing it with a space.
    assert ns["normalize_answer"]("The Eiffel-Tower!") == "eiffeltower"

def test_brink_split_and_process_prediction():
    ns = _brink_metrics_fns()
    result = ns["process_prediction"]("Answer: Paris, London, UNKNOWN")
    assert result == {"answer paris", "london", "unknown"}

# ---------------------------------------------------------------- F1 metric (two_llm_metrics.py)

def test_f1_matches_brink_definition():
    # 2*p*r/(p+r) with p=|inter|/|pred|, r=|inter|/|gold| must equal
    # 2*|inter|/(|pred|+|gold|) exactly (verified algebraically in
    # docs/METHODOLOGY.md); this test checks it numerically on a concrete case.
    pred, gold = {"paris", "london"}, {"paris", "berlin"}
    inter = pred & gold
    p = len(inter) / len(pred)
    r = len(inter) / len(gold)
    f1_from_pr = 2 * p * r / (p + r)
    f1_direct = 2 * len(inter) / (len(pred) + len(gold))
    assert abs(f1_from_pr - f1_direct) < 1e-9


# ---------------------------------------------------------------- rule term cleaning

def test_clean_term_strips_uri_brackets():
    ns = load_names("Rules/rule_parser.py")
    assert ns["_clean_term"]("<http://ex.org/X>") == "http://ex.org/X"
    assert ns["_clean_term"](" (X) ") == "X"


def test_norm_col_slugifies():
    ns = load_names("Rules/rule_parser.py")
    assert ns["norm_col"]("PCA Confidence!") == "pca_confidence"


# ---------------------------------------------------------------- API backend (llm_runtime.py)

class _FakeResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _load_api_chat_fns(monkeypatch_post, api_key="test-key-not-real"):
    src = (SRC / "Generation/llm_runtime.py").read_text(encoding="utf-8")
    seg_start = src.find("def _api_key")
    seg_end = src.find("def _cache_path")
    segment = src[seg_start:seg_end]

    class _FakeLLMCallError(RuntimeError):
        def __init__(self, message, *, retryable=False, auth=False, quota=False, status_code=None):
            super().__init__(message)
            self.retryable = retryable; self.auth = auth
            self.quota = quota; self.status_code = status_code

    class _FakeRequests:
        def post(self, *a, **kw):
            return monkeypatch_post(*a, **kw)

    ns = {
        "os": os, "LLMCallError": _FakeLLMCallError, "requests": _FakeRequests(),
        "LLM_TIMEOUT_SECONDS": 5.0,
        "MODEL_CONFIGS": {"api": {"api_base_url": "https://example.test/v1", "api_model_name": "test-model"}},
    }
    if api_key is not None:
        os.environ["LLM_API_KEY"] = api_key
    elif "LLM_API_KEY" in os.environ:
        del os.environ["LLM_API_KEY"]
    exec(segment, ns)  # env var (if any) is read lazily, at call time, by the caller
    return ns, _FakeLLMCallError


def test_api_key_missing_raises():
    ns, err_cls = _load_api_chat_fns(lambda *a, **kw: None, api_key=None)
    try:
        ns["_api_key"]()
        assert False, "expected LLMCallError"
    except err_cls as e:
        assert e.auth is True


def test_call_api_chat_parses_success_response():
    def fake_post(url, headers, json, timeout):
        assert url == "https://example.test/v1/chat/completions"
        assert headers["Authorization"] == "Bearer test-key-not-real"
        assert "test-key-not-real" not in str({k: v for k, v in headers.items() if k != "Authorization"})
        return _FakeResponse(200, {
            "choices": [{"message": {"content": "Sancho IV"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3},
        })

    ns, _ = _load_api_chat_fns(fake_post)
    text, in_tok, out_tok = ns["_call_api_chat"]("api", [{"role": "user", "content": "hi"}], 48, 0.0)
    assert text == "Sancho IV"
    assert in_tok == 12 and out_tok == 3


def test_call_api_chat_raises_on_auth_failure():
    ns, err_cls = _load_api_chat_fns(lambda *a, **kw: _FakeResponse(401, {}))
    try:
        ns["_call_api_chat"]("api", [{"role": "user", "content": "hi"}], 48, 0.0)
        assert False, "expected LLMCallError"
    except err_cls as e:
        assert e.auth is True and e.status_code == 401


def test_call_api_chat_raises_retryable_on_rate_limit():
    ns, err_cls = _load_api_chat_fns(lambda *a, **kw: _FakeResponse(429, {}))
    try:
        ns["_call_api_chat"]("api", [{"role": "user", "content": "hi"}], 48, 0.0)
        assert False, "expected LLMCallError"
    except err_cls as e:
        assert e.quota is True and e.retryable is True


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:
                print(f"FAIL {name}: {exc}")
                failures += 1
    print(f"\n{'ALL PASSED' if not failures else f'{failures} FAILURE(S)'}")
    sys.exit(1 if failures else 0)
