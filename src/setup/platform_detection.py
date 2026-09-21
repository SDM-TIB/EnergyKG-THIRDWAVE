"""0a. Platform detection and persistent storage paths."""

# On GCE, the attached disk plays Drive's role: survives a VM stop/start.
import time, os, sys, subprocess, warnings, ast, shutil
from collections import defaultdict, Counter
from pathlib import Path as _Path

# pyshacl needs Python 3.10 (see KNOWN_LIMITATIONS #3); re-exec into the
# 3.10 venv if found, guarded against re-exec loops.
if sys.version_info[:2] != (3, 10) and not os.environ.get("_PY310_REEXEC_DONE"):
    _py310_venv = os.environ.get("PY310_VENV_DIR", "/kaggle/working/venv310")
    _py310_bin = _Path(_py310_venv) / "bin" / "python"
    if _py310_bin.exists():
        print(f"Python {sys.version.split()[0]} detected; re-executing under "
              f"{_py310_bin} (SHACL requires 3.10, see docs/KNOWN_LIMITATIONS.md).")
        os.environ["_PY310_REEXEC_DONE"] = "1"
        os.execv(str(_py310_bin), [str(_py310_bin)] + sys.argv)
    else:
        print(f"\n{'!' * 70}\n"
              f"WARNING: Python {sys.version.split()[0]} detected, not 3.10.\n"
              f"pyshacl is known to fail SHACL validation under 3.12 (every candidate\n"
              f"resolves as 'unresolved', silently collapsing E7 to E1).\n"
              f"Run scripts/setup_kaggle_py310.sh first for a reliable E7.\n"
              f"See docs/KNOWN_LIMITATIONS.md, item 3.\n"
              f"{'!' * 70}\n")

IN_GCE = os.path.exists("/etc/google_compute_engine") or "GCE_METADATA_HOST" in os.environ

# Both checks avoid a false negative on Kaggle.
IN_KAGGLE = os.path.exists("/kaggle/input") or "KAGGLE_KERNEL_RUN_TYPE" in os.environ

# google.colab's presence is the most reliable Colab signal.
try:
    import google.colab  # noqa: F401
    IN_COLAB = True
except ImportError:
    IN_COLAB = os.path.exists("/content") and "COLAB_GPU" in os.environ

# CAMPAIGN_NAME isolates runs so a smoke test never collides with a full campaign.
CAMPAIGN_NAME = os.environ.get("CAMPAIGN_NAME", "").strip()

# /kaggle/working is the only writable Kaggle path; on Colab, only Drive
# survives a runtime recycle. Mounting Drive needs a manual OAuth prompt once
# per session -- cannot be automated.
if IN_COLAB:
    try:
        from google.colab import drive as _colab_drive
        if not os.path.exists("/content/drive/MyDrive"):
            _colab_drive.mount("/content/drive")
    except Exception as _exc:
        print(f"[Colab Drive] Mount failed or already mounted: {_exc}")

_default_persist_base = (
    str(REPO_ROOT) if not IN_KAGGLE  # self-contained: data/ and run_state/ live under the repo
    else "/kaggle/working/CoPCA_BRINK_GraphRAG"  # /kaggle/input is read-only, state must go elsewhere
)
_persist_base = os.environ.get("COPCA_BRINK_ROOT", _default_persist_base)
PERSIST_ROOT = f"{_persist_base}/campaigns/{CAMPAIGN_NAME}" if CAMPAIGN_NAME else _persist_base
os.makedirs(PERSIST_ROOT, exist_ok=True)
PERSIST_LABEL = ("this repository (self-contained)" if not IN_KAGGLE and not os.environ.get("COPCA_BRINK_ROOT")
                  else "Kaggle session (/kaggle/working)" if IN_KAGGLE
                  else "custom root (COPCA_BRINK_ROOT)")

# Canonical repository data layout: <repo>/data/{KG,Constraints,Rules}.
# global_config.py resolves the authoritative DATA_ROOT (respecting
# DATA_ROOT_OVERRIDE/COPCA_BRINK_ROOT); nothing here is read downstream.

print(f"Platform: Kaggle={IN_KAGGLE} Colab={IN_COLAB} GCE={IN_GCE}")
if IN_COLAB and not os.path.exists("/content/drive/MyDrive"):
    print("[WARNING] Drive does not appear to be mounted -- data/checkpoints would "
          "go under /content (wiped at every runtime recycle). Run `from "
          "google.colab import drive; drive.mount('/content/drive')` manually, "
          "confirm the authentication prompt, then re-run this cell.")
print("PERSIST_ROOT:", PERSIST_ROOT, "(runtime state: checkpoints/artifacts/cache)")
if CAMPAIGN_NAME:
    print("CAMPAIGN_NAME:", CAMPAIGN_NAME)
print(f"\nAuthoritative source data resolved relative to persistent root; see data/README.md.")
if os.environ.get("COPCA_BRINK_ROOT"):
    print("COPCA_BRINK_ROOT is set; external runtime state is preserved, but data resolution remains canonical unless overridden below.")
print("Expected layout: data/KG, data/Constraints, data/Rules (see data/README.md).")

# Unattended run: Kaggle credentials must be provided in advance
# (~/.kaggle/kaggle.json or KAGGLE_USERNAME/KAGGLE_KEY), never via a prompt.
# Missing credentials disable the affected model only, never block the run.
def ensure_package(pip_name, import_name=None, extra_args=None):
    import importlib.util
    name = import_name or pip_name
    if importlib.util.find_spec(name) is None:
        cmd = [sys.executable, "-m", "pip", "install", "-q", pip_name] + (extra_args or [])
        subprocess.check_call(cmd)

for pkg, imp in [
    ("pandas", "pandas"), ("numpy", "numpy"), ("tqdm", "tqdm"),
    ("matplotlib", "matplotlib"), ("rdflib", "rdflib"),
    ("pyshacl", "pyshacl"),
    ("transformers", "transformers"),
    ("accelerate", "accelerate"), ("bitsandbytes", "bitsandbytes"),
    ("sentencepiece", "sentencepiece"), ("requests", "requests"),
    ("kagglehub", "kagglehub"), ("psutil", "psutil"),
]:
    try:
        ensure_package(pkg, imp)
    except Exception as e:
        print(f"[install warning] {pkg}: {e} -- continuing (may fall back to CPU / no quantization).")

import numpy as np
import pandas as pd
# Force a headless backend: a parent Jupyter kernel's MPLBACKEND may not
# resolve in an isolated venv, and figures are only ever saved, not shown.
os.environ["MPLBACKEND"] = "Agg"
import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import rdflib
import pyshacl
import torch
from tqdm.auto import tqdm
import random
import kagglehub

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)

# kagglehub cache is on persistent disk, shared across campaigns, never re-downloaded.
os.environ.setdefault("KAGGLEHUB_CACHE", f"{_persist_base}/run_state/kagglehub_cache")
os.makedirs(os.environ["KAGGLEHUB_CACHE"], exist_ok=True)

_kaggle_json = _Path(os.environ.get("KAGGLE_CONFIG_DIR", os.path.expanduser("~/.kaggle"))) / "kaggle.json"
_kaggle_ready = _kaggle_json.exists() or bool(os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY")) or IN_KAGGLE
if IN_COLAB and not _kaggle_ready:
    # Colab has no built-in Kaggle auth; kaggle.json must be provided manually.
    for _candidate in [_Path("/content/drive/MyDrive/kaggle.json"), _Path("/content/kaggle.json")]:
        if _candidate.exists():
            os.makedirs(os.path.expanduser("~/.kaggle"), exist_ok=True)
            shutil.copy(_candidate, os.path.expanduser("~/.kaggle/kaggle.json"))
            os.chmod(os.path.expanduser("~/.kaggle/kaggle.json"), 0o600)
            _kaggle_json = _Path(os.path.expanduser("~/.kaggle/kaggle.json"))
            _kaggle_ready = True
            print(f"[Colab] kaggle.json found and copied from {_candidate}")
            break
print("Kaggle credentials detected:", _kaggle_ready,
      "(no interactive prompt is used in this notebook -- see the local LLM "
      "runtime section for what happens if this is False)")
if IN_KAGGLE and not (_kaggle_json.exists() or os.environ.get("KAGGLE_USERNAME")):
    print("Note: native Kaggle kernel detected -- kagglehub normally uses the "
          "platform's built-in authentication without needing kaggle.json. "
          "If model download fails anyway, check that Internet access is "
          "enabled in the notebook settings (Settings -> Internet).")

# display() is an IPython global, not available when run as a plain script
# (how every unattended campaign runs) -- shimmed explicitly to avoid a NameError.
try:
    from IPython.display import display  # noqa: F401
except ImportError:
    def display(*args, **kwargs):
        for a in args:
            print(a)

print("Python:", sys.version.split()[0])
print("Torch:", torch.__version__)
print("CUDA:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
else:
    print("No GPU detected -- local inference will run on CPU (slower, but still "
          "possible, and still fully self-contained: no dependency on a remote API).")
print("KAGGLEHUB_CACHE (model weights, persisted on disk):", os.environ["KAGGLEHUB_CACHE"])
