"""7. Benchmark object contract."""

# A benchmark is always a dict, never None; NOT_READY objects hold no test set.

def make_gated_benchmark(name, reason):
    return {
        "ready": False,
        "status": "NOT_READY",
        "reason": str(reason),
        "complete": DATA[name]["semantic"].copy(),
        "incomplete": None,
        "pool": pd.DataFrame(),
        "splits": {"train": pd.DataFrame(), "validation": pd.DataFrame(), "test": pd.DataFrame()},
        "removed_test": set(),
    }

def benchmark_is_evaluable(name):
    return bool(name in BENCH and BENCH[name].get("ready") is True and BENCH[name].get("status") == "READY")
