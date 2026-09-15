"""Command-line entry point. Sets configuration then runs each pipeline
stage in order, in one process (stages share global state, like notebook
cells)."""

import argparse
import os
from pathlib import Path

STAGES = [
    "setup/platform_detection.py",
    "setup/global_config.py",
    "setup/source_preflight.py",
    "utils/canonicalization.py",
    "Generation/llm_runtime.py",
    "KG/dataset_loader.py",
    "Constraints/shacl_validation.py",
    "Constraints/copca_reference_logs.py",
    "Rules/rule_parser.py",
    "Rules/rule_statistics.py",
    "Rules/preflight_audit.py",
    "Symbolic_Learning/grounding_engine.py",
    "Symbolic_Learning/benchmark_contract.py",
    "Symbolic_Learning/benchmark_construction.py",
    "Symbolic_Learning/question_generation.py",
    "Symbolic_Learning/candidate_universe.py",
    "Symbolic_Learning/retrieval_onehop_tog.py",
    "Symbolic_Learning/retrieval_pog_structgpt.py",
    "Symbolic_Learning/neurosymbolic_inference.py",
    "Evaluation/proof_audit.py",
    "Evaluation/brink_metrics.py",
    "Evidence_Fusion/evidence_conditions.py",
    "Generation/answer_generation.py",
    "Evaluation/driver.py",
    "Evaluation/invariance_audit.py",
    "Evaluation/shacl_diagnostic.py",
    "Evaluation/brink_style_examples.py",
    "Evaluation/two_llm_metrics.py",
    "Evaluation/two_llm_forensic_audit.py",
    "Evaluation/two_llm_manifest.py",
    "Evaluation/metrics_bootstrap_ci.py",
    "Evaluation/retriever_comparison.py",
    "Evaluation/recovery_rate.py",
    "Evaluation/benchmark_adequacy.py",
    "Evaluation/figures.py",
    "Evaluation/final_tables.py",
    "Evaluation/final_manifest.py",
    "Evaluation/forensic_audit_10q.py",
    "Evaluation/hhr_check.py",
    "Evaluation/final_package.py",
]


VALID_DATASETS = ["FrenchRoyalty", "DB100K", "YAGO3-10"]
VALID_RETRIEVERS = ["onehop", "tog", "pog", "structgpt"]
VALID_MODELS = ["Qwen2.5-3B", "Llama-3.1-8B"]


def _validate_choices(values, valid, flag_name):
    for v in values:
        if v not in valid and v != "all":
            raise SystemExit(f"{flag_name}: {v!r} is not one of {valid + ['all']}")


API_PROVIDERS = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "deepinfra": "https://api.deepinfra.com/v1/openai",
}


def parse_args():
    p = argparse.ArgumentParser(
        description="Constraint-gated neuro-symbolic KG-RAG pipeline."
    )
    p.add_argument("--dataset", nargs="+", default=["FrenchRoyalty"],
                    help=f"One or more of {VALID_DATASETS}, or 'all'. "
                         f"Default: FrenchRoyalty. Example: --dataset FrenchRoyalty DB100K")
    p.add_argument("--retriever", nargs="+", default=["onehop"],
                    help=f"One or more of {VALID_RETRIEVERS}, or 'all'. Default: onehop.")
    p.add_argument("--model", nargs="+", default=None,
                    help=f"One or more of {VALID_MODELS} (default: both). Ignored with --backend api.")
    p.add_argument("--backend", default="local", choices=["local", "api"],
                    help="local (default): Qwen/Llama via kagglehub. api: a remote OpenAI-compatible endpoint.")
    p.add_argument("--api-key", default=None,
                    help="API key for --backend api. Prefer the LLM_API_KEY environment variable; "
                         "never printed or logged either way.")
    p.add_argument("--api-model-name", default=None,
                    help="Model name to request from the API (required with --backend api).")
    p.add_argument("--api-provider", default=None, choices=list(API_PROVIDERS),
                    help=f"Shortcut for --api-base-url, one of {list(API_PROVIDERS)}. "
                         "Use --api-base-url directly for any other OpenAI-compatible endpoint "
                         "(e.g. a local vLLM/Ollama server).")
    p.add_argument("--api-base-url", default=None,
                    help="OpenAI-compatible base URL (overrides --api-provider if both given).")
    p.add_argument("--max-questions", type=int, default=None,
                    help="Cap on test questions. Default: none -- runs BRINK's full frozen split, uncapped.")
    p.add_argument("--tiers", nargs="+", type=int, default=None,
                    help="Optional staged checkpoints, e.g. --tiers 10 50 100. "
                         "Default: none -- a single pass over the full frozen split.")
    p.add_argument("--campaign-name", default="",
                    help="Isolate this run's checkpoints under a named subfolder.")
    p.add_argument("--root", default=None,
                    help="Override the persistent storage root (default: auto-detected).")
    p.add_argument("--gpu", default=None,
                    help="Pin this run to one GPU (e.g. --gpu 0), or several (--gpu 0,1). "
                         "On a multi-GPU machine, this lets independent runs (different "
                         "KGs/retrievers) use separate GPUs with zero contention.")
    p.add_argument("--stop-after-split", action="store_true",
                    help="Build and print the frozen benchmark split, then exit (no GPU needed).")
    args = p.parse_args()

    _validate_choices(args.dataset, VALID_DATASETS, "--dataset")
    _validate_choices(args.retriever, VALID_RETRIEVERS, "--retriever")
    if args.model:
        _validate_choices(args.model, VALID_MODELS, "--model")
    return args


def main():
    args = parse_args()

    if args.gpu is not None:
        os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu
        print(f"Pinned to GPU(s): {args.gpu}")

    os.environ["DATASET_TO_RUN"] = "all" if "all" in args.dataset else ",".join(args.dataset)
    os.environ["RETRIEVER_TO_RUN"] = "all" if "all" in args.retriever else ",".join(args.retriever)
    if args.backend == "api":
        api_model = args.api_model_name or os.environ.get("API_MODEL_NAME", "").strip()
        if not api_model:
            raise SystemExit("--backend api requires --api-model-name (or set API_MODEL_NAME).")
        os.environ["API_MODEL_NAME"] = api_model
        key = args.api_key or os.environ.get("LLM_API_KEY", "").strip()
        if not key:
            raise SystemExit("--backend api requires an API key: pass --api-key or set LLM_API_KEY.")
        os.environ["LLM_API_KEY"] = key  # never printed; read lazily by llm_runtime.py
        base_url = args.api_base_url or (API_PROVIDERS[args.api_provider] if args.api_provider else None)
        if base_url:
            os.environ["API_BASE_URL"] = base_url
        os.environ["LLM_BACKEND"] = "api"
        print(f"Backend: api (model={api_model}, provider={args.api_provider or 'custom'}, key=set)")
    else:
        os.environ["LLM_BACKEND"] = "local"
        if args.model:
            os.environ["MODEL_TO_RUN"] = ",".join(args.model)
    if args.max_questions is not None:
        os.environ["MAX_QUESTIONS_OVERRIDE"] = str(args.max_questions)
    if args.tiers:
        os.environ["QUESTION_TIERS_OVERRIDE"] = ",".join(str(t) for t in sorted(args.tiers))
    if args.campaign_name:
        os.environ["CAMPAIGN_NAME"] = args.campaign_name
    if args.root:
        os.environ["COPCA_BRINK_ROOT"] = args.root
    if args.stop_after_split:
        os.environ["SPLIT_DRY_RUN"] = "1"

    src_root = Path(__file__).resolve().parent
    namespace = {"__name__": "__main__", "REPO_ROOT": src_root.parent}
    for relpath in STAGES:
        path = src_root / relpath
        print(f"\n== {relpath} ==")
        code = compile(path.read_text(encoding="utf-8"), str(path), "exec")
        try:
            exec(code, namespace)
        except SystemExit:
            if args.stop_after_split:
                return
            raise


if __name__ == "__main__":
    main()
