#!/usr/bin/env bash
# Installs Python 3.10 in a dedicated virtualenv on Kaggle (whose default
# kernel runs Python 3.12), matching the GCE VM's confirmed-working
# environment. Required because pyshacl 0.40.1's SPARQLConstraintComponent
# evaluation (used by FrenchRoyalty's shape) fails under Python 3.12 with
# "Cannot use AS to re-bind potentially pre-bound variables such as this",
# resolving every candidate as SHACL-unresolved instead of valid/invalid --
# silently collapsing E7 to E1 and L4 to L1. Confirmed working under 3.10.12.
#
# Usage (in a Kaggle notebook cell):
#   !bash scripts/setup_kaggle_py310.sh
# Then run the pipeline through the venv's own interpreter, not the kernel's:
#   !/kaggle/working/venv310/bin/python src/main.py --dataset FrenchRoyalty
#
# main.py also auto-detects and re-execs into this venv if it exists and the
# current interpreter is not 3.10.x (see src/setup/platform_detection.py),
# so once this script has run once, the kernel's own `!python3 src/main.py`
# also transparently uses 3.10 from then on.
set -euo pipefail

VENV_DIR="${PY310_VENV_DIR:-/kaggle/working/venv310}"

if [ -x "$VENV_DIR/bin/python3.10" ] || [ -x "$VENV_DIR/bin/python" ]; then
    echo "Already set up at $VENV_DIR -- skipping install."
else
    echo "Installing Python 3.10..."
    if command -v apt-get >/dev/null 2>&1; then
        (apt-get install -y python3.10 python3.10-venv python3.10-distutils 2>/dev/null) || {
            echo "python3.10 not in default repos; adding deadsnakes PPA..."
            apt-get update -qq
            apt-get install -y software-properties-common
            add-apt-repository -y ppa:deadsnakes/ppa
            apt-get update -qq
            apt-get install -y python3.10 python3.10-venv python3.10-distutils
        }
    else
        echo "ERROR: apt-get not found -- this script assumes a Debian/Ubuntu-based Kaggle image." >&2
        exit 1
    fi

    echo "Creating venv at $VENV_DIR..."
    python3.10 -m venv "$VENV_DIR"
fi

echo "Installing requirements into the 3.10 venv..."
"$VENV_DIR/bin/python" -m pip install -q --upgrade pip
"$VENV_DIR/bin/python" -m pip install -q -r requirements.txt

echo ""
"$VENV_DIR/bin/python" -c "import sys; print('Venv Python version:', sys.version)"
echo "Done. Run the pipeline with: $VENV_DIR/bin/python src/main.py ..."
