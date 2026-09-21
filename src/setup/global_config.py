"""1. Global configuration (resumable, local LLM)."""

from pathlib import Path
import os, time, json, hashlib, shutil, gc, re, math, random

# Canonical, repository-local data layout.  An explicit DATA_ROOT_OVERRIDE may
# point to another directory with the same KG/Constraints/Rules structure.
_DATA_BASE = Path(os.environ.get("DATA_ROOT_OVERRIDE", str(Path(_persist_base) / "data"))).resolve()

def _candidate_dataset_config(root):
    return {
        "FrenchRoyalty": {
            "kg": root / "KG" / "FrenchRoyalty" / "french_royalty.nt",
            "rules": root / "Rules" / "french_royalty.csv",
            "shacl": root / "Constraints" / "FrenchRoyalty" / "FrenchRoyalty.ttl",
            "valid_log": root / "Constraints" / "FrenchRoyalty" / "result_FrenchRoyalty" / "targets_valid.log",
            "violated_log": root / "Constraints" / "FrenchRoyalty" / "result_FrenchRoyalty" / "targets_violated.log",
        },
        "DB100K": {
            "kg": root / "KG" / "DB100K" / "DB100K.nt",
            "kg_tsv": root / "KG" / "DB100K" / "DB100K.tsv",
            "rules": root / "Rules" / "DB100K.csv",
            "shacl": root / "Constraints" / "DB100K" / "db100k.ttl",
            "valid_log": root / "Constraints" / "DB100K" / "result_DB100K" / "targets_valid.log",
            "violated_log": root / "Constraints" / "DB100K" / "result_DB100K" / "targets_violated.log",
        },
        "YAGO3-10": {
            "kg": root / "KG" / "YAGO3-10" / "YAGO3-10.nt",
            "kg_tsv": root / "KG" / "YAGO3-10" / "YAGO3-10.tsv",
            "rules": root / "Rules" / "YAGO3-10.csv",
            "shacl": root / "Constraints" / "YAGO3-10" / "YAGO3-10.ttl",
            "valid_log": root / "Constraints" / "YAGO3-10" / "result_YAGO3-10" / "targets_valid.log",
            "violated_log": root / "Constraints" / "YAGO3-10" / "result_YAGO3-10" / "targets_violated.log",
        },
    }

DATA_ROOT = _DATA_BASE
DATASETS_CONFIG = _candidate_dataset_config(DATA_ROOT)
DATA_SOURCE_NAMESPACE = str(DATA_ROOT)

_CORE_KEYS = ("kg", "rules", "shacl")
_missing = [str(DATASETS_CONFIG[name][key])
            for name in DATASETS_CONFIG for key in _CORE_KEYS
            if not DATASETS_CONFIG[name][key].exists() or DATASETS_CONFIG[name][key].stat().st_size == 0]
if _missing:
    raise FileNotFoundError(
        "Canonical authoritative data layout is incomplete or contains empty placeholder files:\n"
        + "\n".join(_missing)
        + "\nSee data/README.md. Set DATA_ROOT_OVERRIDE to use another root with the same layout."
    )

DATASET_TO_RUN = os.environ.get("DATASET_TO_RUN", "YAGO3-10").strip()
RETRIEVER_TO_RUN = os.environ.get("RETRIEVER_TO_RUN", "onehop").strip()
# Read from environment; lets the active KG/retriever change between launches.
print(f"DATASET_TO_RUN={DATASET_TO_RUN!r}  RETRIEVER_TO_RUN={RETRIEVER_TO_RUN!r}")

MIN_PCA_E2 = 0.4; MAX_GROUNDINGS_PER_RULE = 30; MAX_PROOF_DEPTH = 3; MAX_PROOFS_PER_GOAL = 20
# MIN_PCA_E2 matches BRINK's AMIE3 "-minpca 0.4". Distinct from CoPCA's own
# PCA_valid/PCA_invalid (TravSHACL-based, threshold 0.75) -- never conflate the two.
EVIDENCE_PIPELINE_VERSION = "v18_e7_delta_signature_corrected"
NS_DEPENDENT_CONDITIONS = {"E2_incomplete_NS", "E3_incomplete_noPCA", "E5_complete_NS", "E7_incomplete_NS_SHACL"}
# Base benchmark split is BRINK-style 8:1:1; small pools use the documented test floor.
SPLIT_SEED = 42; BRINK_SPLIT_NROWS = None; MAX_TEST_QUESTIONS = None
BRINK_SPLIT_RATIOS = (0.8, 0.1, 0.1)  # train, validation, test -- BRINK's proportions, never an absolute count
# Tiers are opt-in staged checkpoints (e.g. 10,50,100): QUESTION_TIERS=[]
# (default) runs a single pass over the full frozen BRINK split, uncapped.
QUESTION_TIERS = [int(t) for t in os.environ.get("QUESTION_TIERS_OVERRIDE", "").split(",") if t.strip()]
TOG_WIDTH, TOG_DEPTH = 3, 3; MAX_DECLARED_FACTS = 8; CONTEXT_MAX_FACTS = 12; MAX_NS_FACTS = 8; MAX_RANDOM_FACTS = 4
TOG_MAX_RELATIONS = 60; TOG_MAX_CANDIDATES = 30

# Default: public Kaggle model weights, cached on persistent storage.
# API mode is opt-in via LLM_BACKEND=api.
MODEL_CONFIGS = {
    "Llama-3.1-8B": {"kagglehub_handle": "danbth/llama-3-1-8b-instruct/Transformers/default/1",
                      "model_name": "danbth/llama-3-1-8b-instruct/Transformers/default/1",  # display alias
                      "backend": "local"},
    "Qwen2.5-3B": {"kagglehub_handle": "pengzhengcurtis/qwen2.5-3b-instruct/PyTorch/default/1",
                   "model_name": "pengzhengcurtis/qwen2.5-3b-instruct/PyTorch/default/1",  # display alias
                   "backend": "local"},
}
# LLM_BACKEND=api switches from local Kaggle weights to a remote,
# OpenAI-compatible chat-completions API (OpenAI, Groq, Together, a local
# vLLM/Ollama server, etc.). Local remains the default; API mode requires an
# API key (LLM_API_KEY, never logged) and a model name (API_MODEL_NAME).
_llm_backend = os.environ.get("LLM_BACKEND", "local").strip().lower()
if _llm_backend == "api":
    _api_model_name = os.environ.get("API_MODEL_NAME", "").strip()
    if not _api_model_name:
        raise ValueError("LLM_BACKEND=api requires API_MODEL_NAME to be set.")
    if not os.environ.get("LLM_API_KEY", "").strip():
        raise ValueError("LLM_BACKEND=api requires LLM_API_KEY to be set.")
    MODEL_CONFIGS["api"] = {
        "api_model_name": _api_model_name,
        "api_base_url": os.environ.get("API_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        "model_name": _api_model_name, "backend": "api",
    }
    MODEL_ORDER = ["api"]
else:
    _model_override = os.environ.get("MODEL_TO_RUN", "").strip()
    MODEL_ORDER = [m.strip() for m in _model_override.split(",") if m.strip()] if _model_override else ["Qwen2.5-3B", "Llama-3.1-8B"]
MODEL_NAME = MODEL_CONFIGS[MODEL_ORDER[0]].get("kagglehub_handle", MODEL_CONFIGS[MODEL_ORDER[0]].get("model_name"))
LLM_TIMEOUT_SECONDS = 120.0; LLM_MAX_RETRIES = 6; LLM_BACKOFF_BASE = 2.0; LLM_BACKOFF_MAX = 45.0; LLM_RETRY_JITTER = 0.35
MAX_NEW_TOKENS = 48; TEMPERATURE = 0.0; TOP_P = None
CONDITION_ORDER = ["E0_complete_baseline", "E1_incomplete_baseline", "E2_incomplete_NS", "E3_incomplete_noPCA",
                    "E4_incomplete_random", "E5_complete_NS", "E6_incomplete_oracle", "E7_incomplete_NS_SHACL"]

# ROOT is on persistent storage; every checkpoint line is flush+fsync'd.
ROOT = Path(PERSIST_ROOT) / "run_state"
CACHE = ROOT/"cache"; CHECKPOINTS = ROOT/"checkpoints"; ARTIFACTS = ROOT/"artifacts"; STATE = ROOT/"state"; FAILURES = ROOT/"failures"
for p in (ROOT, CACHE, CHECKPOINTS, ARTIFACTS, STATE, FAILURES):
    p.mkdir(parents=True, exist_ok=True)
for _dataset_name in DATASETS_CONFIG:
    (ARTIFACTS/_dataset_name).mkdir(parents=True, exist_ok=True)

ACTIVE_DATASETS = (
    list(DATASETS_CONFIG) if DATASET_TO_RUN == "all"
    else [d.strip() for d in DATASET_TO_RUN.split(",") if d.strip()]
)
ALL_RETRIEVERS = ["onehop", "tog", "pog", "structgpt"]
# "all", a single name, or a comma-separated list ("onehop,tog").
ACTIVE_RETRIEVERS = (
    ALL_RETRIEVERS if RETRIEVER_TO_RUN == "all"
    else [r.strip() for r in RETRIEVER_TO_RUN.split(",") if r.strip()]
)

print("Authoritative source pair:", DATA_SOURCE_NAMESPACE)
print("Models (local, 4-bit when GPU available):", MODEL_ORDER)
print("Persistent root:", ROOT)


def load_checkpoint(path):
    rows = {}
    path = Path(path)
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                qid = r.get("question_id")
                if qid is not None and str(qid):
                    rows[str(qid)] = r
            except Exception:
                continue  # a partial final line must not destroy resume
    return rows

def checkpoint_count(path):
    return len(load_checkpoint(path)) if Path(path).exists() else 0
