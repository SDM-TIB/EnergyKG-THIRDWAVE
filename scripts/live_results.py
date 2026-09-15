"""Live results, computed from whatever is already written in the checkpoints
-- safe to run anytime, even mid-campaign, without disturbing the running
process (read-only). Usage:
    python3 live_results.py --dataset FrenchRoyalty
    python3 live_results.py --dataset DB100K --model Qwen2.5-3B --retriever onehop
"""
import argparse, json, os, re
from pathlib import Path

CONDITIONS = ["E0_complete_baseline", "E1_incomplete_baseline", "E2_incomplete_NS",
              "E3_incomplete_noPCA", "E4_incomplete_random", "E5_complete_NS",
              "E6_incomplete_oracle", "E7_incomplete_NS_SHACL"]

# Frozen active test-set sizes (see results/<KG>/fingerprints.txt). A
# checkpoint file can still hold MORE distinct question_ids than this if an
# older, larger benchmark version was run earlier -- those extra, stale ids
# must be excluded, not just deduplicated, or aggregates silently mix two
# different question sets (a real bug found in this exact script once
# already; --expected-count overrides this for a capped/custom run).
KNOWN_ACTIVE_COUNTS = {"FrenchRoyalty": 100, "DB100K": 231, "YAGO3-10": 100}


def norm(x):
    return re.sub(r"\s+", " ", str(x).strip().lower())


def parse_answer(raw):
    text = re.sub(r"^answer\s*:\s*", "", str(raw).strip(), flags=re.I)
    text = re.sub(r"[\[\]{}\"']", "", text)
    return {norm(x) for x in re.split(r",|;|\n", text) if norm(x) and norm(x) != "unknown"}


def active_ids(checkpoints_dir, model, dataset, retriever, expected_count):
    """Active question set = ids in E0 whose numeric suffix is below the
    known frozen test-set size (or --expected-count override) -- excludes
    stale ids left over from an earlier, larger benchmark version."""
    p = checkpoints_dir / model / dataset / retriever / "E0_complete_baseline.jsonl"
    if not p.exists():
        return None
    ids = set()
    with open(p) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            qid = r["question_id"]
            m = re.search(r"_(\d+)$", qid)
            if m is None or int(m.group(1)) < expected_count:
                ids.add(qid)
    return ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None, help="Persistent root (default: this repository, or $COPCA_BRINK_ROOT)")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--model", default=None, help="Restrict to one model (default: both found)")
    ap.add_argument("--retriever", default=None, help="Restrict to one retriever (default: all found)")
    ap.add_argument("--expected-count", type=int, default=None,
                     help="Override the known frozen test-set size (needed for a --max-questions-capped run).")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    root = Path(args.root) if args.root else Path(os.environ.get("COPCA_BRINK_ROOT", repo_root))
    checkpoints_dir = root / "run_state" / "checkpoints"
    if not checkpoints_dir.exists():
        raise SystemExit(f"No checkpoints found under {checkpoints_dir} -- run src/main.py first.")
    expected_count = args.expected_count or KNOWN_ACTIVE_COUNTS.get(args.dataset)
    if expected_count is None:
        raise SystemExit(f"Unknown dataset {args.dataset!r}: pass --expected-count explicitly.")

    models = [args.model] if args.model else sorted(p.name for p in checkpoints_dir.iterdir() if p.is_dir())

    print(f"{'Model':<15}{'Retriever':<12}{'Condition':<28}{'n':>5}{'Hits@Hard':>12}{'HHR':>10}{'F1':>10}")
    for model in models:
        ds_dir = checkpoints_dir / model / args.dataset
        if not ds_dir.exists():
            continue
        retrievers = [args.retriever] if args.retriever else sorted(p.name for p in ds_dir.iterdir() if p.is_dir())
        for ret in retrievers:
            ids = active_ids(checkpoints_dir, model, args.dataset, ret, expected_count)
            if not ids:
                continue
            for cond in CONDITIONS:
                p = ds_dir / ret / f"{cond}.jsonl"
                if not p.exists():
                    continue
                latest = {}
                with open(p) as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        r = json.loads(line)
                        qid = r.get("question_id")
                        if qid in ids and r.get("llm_status") == "OK":
                            latest[qid] = r
                if not latest:
                    continue
                hit_any = hit_hard = 0
                f1_sum = 0.0
                for r in latest.values():
                    pred = parse_answer(r["prediction_raw"])
                    gold = {norm(x) for x in r["gold_answers"]}
                    hard = norm(r["hard_answer"])
                    inter = pred & gold
                    p_ = len(inter) / len(pred) if pred else 0.0
                    rc = len(inter) / len(gold) if gold else 0.0
                    f1 = 2 * p_ * rc / (p_ + rc) if p_ + rc else 0.0
                    f1_sum += f1
                    if inter:
                        hit_any += 1
                    if hard in pred:
                        hit_hard += 1
                n = len(latest)
                hhr = hit_hard / hit_any if hit_any else float("nan")
                complete = f" ({n}/{len(ids)})" if n < len(ids) else ""
                print(f"{model:<15}{ret:<12}{cond+complete:<28}{n:>5}{hit_hard/n:>12.4f}{hhr:>10.4f}{f1_sum/n:>10.4f}")


if __name__ == "__main__":
    main()

