"""BRINK evaluator-compatible answer parsing and metrics."""

from __future__ import annotations

import re
import string
from typing import Iterable

ARTICLES = {"a", "an", "the"}

def normalize_answer(text: str) -> str:
    text = str(text).lower().replace("\u2014", " ")
    text = "".join(ch for ch in text if ch not in string.punctuation)
    return " ".join(tok for tok in text.split() if tok not in ARTICLES)

def split_raw_output(raw_output: str, *, split_on_spaces: bool = False) -> list[str]:
    if raw_output is None:
        return []
    text = str(raw_output).strip()
    if not text:
        return []
    pattern = r"[,\n\r\t ]+" if split_on_spaces else r"[,\n\r]+"
    return [part.strip() for part in re.split(pattern, text) if part.strip()]

def process_prediction(raw_output: str, *, split_on_spaces: bool = False) -> set[str]:
    seen = set()
    result = []
    for candidate in split_raw_output(raw_output, split_on_spaces=split_on_spaces):
        normalized = normalize_answer(candidate)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return set(result)

def example_metrics(pred_set: set[str], gold_set: set[str], hard_answer: str) -> dict[str, float]:
    overlap = pred_set & gold_set
    return {
        "hits_any": float(bool(overlap)),
        "precision": len(overlap) / len(pred_set) if pred_set else 0.0,
        "recall": len(overlap) / len(gold_set) if gold_set else 0.0,
        "f1": (2.0 * len(overlap) / (len(pred_set) + len(gold_set)))
              if (len(pred_set) + len(gold_set)) else 0.0,
        "hits_hard": float(normalize_answer(hard_answer) in pred_set),
    }

def aggregate_metrics(rows: Iterable[tuple[str, Iterable[str], str]]) -> dict[str, float]:
    values = []
    for raw_output, gold_answers, hard_answer in rows:
        pred = process_prediction(raw_output)
        gold = {normalize_answer(x) for x in gold_answers if normalize_answer(x)}
        values.append(example_metrics(pred, gold, hard_answer))
    if not values:
        return {"n": 0, "hits_any": float("nan"), "hits_hard": float("nan"),
                "hhr": float("nan"), "precision": float("nan"),
                "recall": float("nan"), "f1": float("nan")}
    n = len(values)
    hits_any = sum(v["hits_any"] for v in values) / n
    hits_hard = sum(v["hits_hard"] for v in values) / n
    return {
        "n": n,
        "hits_any": hits_any,
        "hits_hard": hits_hard,
        "hhr": hits_hard / hits_any if hits_any > 0 else float("nan"),
        "precision": sum(v["precision"] for v in values) / n,
        "recall": sum(v["recall"] for v in values) / n,
        "f1": sum(v["f1"] for v in values) / n,
    }
