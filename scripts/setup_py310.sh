#!/usr/bin/env bash
#
# Set up a dedicated Python 3.10 virtual environment for the project.
#
# Portable version:
#   - Linux / macOS
#   - local workstation, VM, GCE, cloud notebook, etc.
#   - does not assume Kaggle or apt-get
#
# Usage:
#   bash scripts/setup_py310.sh
#
# Optional:
#   PY310_VENV_DIR=/path/to/venv bash scripts/setup_py310.sh
#
# Then:
#   ./venv310/bin/python src/main.py --dataset FrenchRoyalty
#
# The script intentionally does NOT install Python itself.
# Python 3.10 must already be available on the host system.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

VENV_DIR="${PY310_VENV_DIR:-$REPO_ROOT/.venv310}"
REQUIREMENTS_FILE="${REQUIREMENTS_FILE:-$REPO_ROOT/requirements.txt}"

echo "============================================================"
echo " Python 3.10 environment setup"
echo "============================================================"
echo "Repository : $REPO_ROOT"
echo "Virtualenv  : $VENV_DIR"
echo "Requirements: $REQUIREMENTS_FILE"
echo ""

# ------------------------------------------------------------------
# Locate Python 3.10
# ------------------------------------------------------------------

PYTHON310="${PYTHON310_BIN:-}"

if [ -n "$PYTHON310" ]; then
    if [ ! -x "$PYTHON310" ]; then
        echo "ERROR: PYTHON310_BIN does not point to an executable:" >&2
        echo "       $PYTHON310" >&2
        exit 1
    fi
else
    for candidate in python3.10 python3.10m python310; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PYTHON310="$(command -v "$candidate")"
            break
        fi
    done
fi

if [ -z "$PYTHON310" ]; then
    echo "ERROR: Python 3.10 was not found." >&2
    echo "" >&2
    echo "Install Python 3.10 using your platform's package manager," >&2
    echo "then rerun this script." >&2
    echo "" >&2
    echo "Examples:" >&2
    echo "  Ubuntu/Debian : sudo apt install python3.10 python3.10-venv" >&2
    echo "  Conda         : conda create -n py310 python=3.10" >&2
    echo "  Homebrew/macOS: brew install python@3.10" >&2
    exit 1
fi

# ------------------------------------------------------------------
# Verify Python version
# ------------------------------------------------------------------

PYTHON_VERSION="$("$PYTHON310" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"

case "$PYTHON_VERSION" in
    3.10.*)
        ;;
    *)
        echo "ERROR: Expected Python 3.10.x, found $PYTHON_VERSION" >&2
        echo "Interpreter: $PYTHON310" >&2
        exit 1
        ;;
esac

echo "Python      : $PYTHON_VERSION"
echo "Interpreter : $PYTHON310"
echo ""

# ------------------------------------------------------------------
# Check requirements
# ------------------------------------------------------------------

if [ ! -f "$REQUIREMENTS_FILE" ]; then
    echo "ERROR: requirements.txt not found:" >&2
    echo "       $REQUIREMENTS_FILE" >&2
    exit 1
fi

# ------------------------------------------------------------------
# Create virtual environment
# ------------------------------------------------------------------

if [ -x "$VENV_DIR/bin/python" ]; then
    EXISTING_VERSION="$("$VENV_DIR/bin/python" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"

    case "$EXISTING_VERSION" in
        3.10.*)
            echo "Existing Python 3.10 virtualenv found; reusing it."
            ;;
        *)
            echo "ERROR: Existing virtualenv uses Python $EXISTING_VERSION." >&2
            echo "Remove it and rerun:" >&2
            echo "  rm -rf \"$VENV_DIR\"" >&2
            exit 1
            ;;
    esac
else
    echo "Creating virtual environment..."
    "$PYTHON310" -m venv "$VENV_DIR"
fi

VENV_PYTHON="$VENV_DIR/bin/python"

# ------------------------------------------------------------------
# Install dependencies
# ------------------------------------------------------------------

echo "Upgrading pip..."
"$VENV_PYTHON" -m pip install --upgrade pip

echo "Installing project requirements..."
"$VENV_PYTHON" -m pip install -r "$REQUIREMENTS_FILE"

# ------------------------------------------------------------------
# Final verification
# ------------------------------------------------------------------

echo ""
echo "============================================================"
echo " Environment ready"
echo "============================================================"

"$VENV_PYTHON" - <<'PY'
import sys

print("Python :", sys.version)

try:
    import pyshacl
    print("pySHACL:", getattr(pyshacl, "__version__", "installed"))
except Exception as exc:
    print("pySHACL: ERROR:", exc)
    raise SystemExit(1)
PY

echo ""
echo "Run the pipeline with:"
echo ""
echo "  \"$VENV_PYTHON\" src/main.py --dataset all --retriever all --max-questions 10 --campaign-name smoke-10q"
echo ""
echo "Or export the interpreter:"
echo ""
echo "  export PYTHON=\"$VENV_PYTHON\""
echo "  \$PYTHON src/main.py --dataset all --retriever all --max-questions 10"
echo ""
