# Sourced by every job script. Paths are relative to the project root on the cluster.
export T2A_ROOT="${T2A_ROOT:-$HOME/text2answer-sigmod27}"
export T2A_REPO="$T2A_ROOT/text2answer-graph-analysis"
export T2A_DATA="$T2A_ROOT/data"
export PY="$T2A_REPO/.venv/bin/python"
export T2R_CACHE_DIR="$T2A_DATA/cache"
# The API key lives in a mode-600 file that is never committed; only jobs that call a model need it.
T2A_KEY_FILE="${T2A_KEY_FILE:-$HOME/.config/t2a/anthropic_key}"
if [ -r "$T2A_KEY_FILE" ]; then export ANTHROPIC_API_KEY="$(cat "$T2A_KEY_FILE")"; fi
