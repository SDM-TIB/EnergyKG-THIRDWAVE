#!/usr/bin/env bash
# Unattended, resumable launch for a persistent VM (GCE or equivalent).
#
# Runs src/main.py detached (tmux, falling back to nohup), so the campaign
# survives an SSH disconnect. All arguments after the script name are passed
# straight through to src/main.py -- run `python3 src/main.py --help` for
# the full list (--dataset, --retriever, --model, --tiers, --max-questions,
# --backend, --campaign-name, --root, ...).
#
# Usage:
#   bash scripts/launch.sh --dataset FrenchRoyalty --retriever onehop
#   bash scripts/launch.sh --dataset DB100K --max-questions 50
#
# To run two campaigns at once (e.g. two different KGs), give each its own
# tmux session name -- otherwise the second launch refuses to start:
#   TMUX_SESSION_NAME=db100k bash scripts/launch.sh --dataset DB100K --retriever all
#   TMUX_SESSION_NAME=yago   bash scripts/launch.sh --dataset YAGO3-10 --retriever all
# Both write to different checkpoint folders (no file conflict), but share
# the same GPU -- expect slower-than-linear speedup, and watch `nvidia-smi`
# for memory pressure.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="${COPCA_BRINK_ROOT:-$REPO_ROOT}"
LOG_DIR="$ROOT/run_state/logs"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/run_${TIMESTAMP}.log"

mkdir -p "$LOG_DIR"

CMD="python3 -u '$REPO_ROOT/src/main.py'"
for arg in "$@"; do
    CMD="$CMD '$arg'"
done

echo "Command: $CMD"
echo "Launching detached (log: $LOG_FILE)..."

if command -v tmux >/dev/null 2>&1; then
    SESSION="${TMUX_SESSION_NAME:-copca_brink}"
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        echo "A tmux session named '$SESSION' already exists."
        echo "Attach with: tmux attach -t $SESSION"
        echo "Or kill it first with: tmux kill-session -t $SESSION"
        exit 1
    fi
    tmux new-session -d -s "$SESSION" "$CMD >> '$LOG_FILE' 2>&1"
    echo "Started in tmux session '$SESSION'."
    echo "Attach with:  tmux attach -t $SESSION"
    echo "Detach with:  Ctrl+B then D (does not stop the run)"
else
    echo "tmux not found; falling back to nohup."
    eval "nohup $CMD >> '$LOG_FILE' 2>&1 &"
    echo "Started with PID $!."
fi

echo "Follow progress with:  tail -f '$LOG_FILE'"
