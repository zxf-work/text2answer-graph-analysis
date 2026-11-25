#!/bin/bash
#SBATCH -J t2a-written
#SBATCH -p bigTiger
#SBATCH -c 16
#SBATCH --mem=96G
#SBATCH -t 24:00:00
#SBATCH -o logs/%x-%j.out
# Model-written sessions (bench/sessions/write_sessions.py) run through one system; answers are stored, not scored.
# Usage: sbatch --export=ALL,WRITER=claude-opus-5-5,GRAPH=pokec,MODEL=claude-haiku-5-5,VARIANT=full[,T2R_PROMPT_CACHE=1][,REP=1][,ONLY=s03] slurm/run_written.sbatch
#   WRITER: directory under prototype/runs/written; GRAPH: pokec | livejournal | twitch; VARIANT as in run_stale.py
# Per-session copies of the graph files and their binary caches go to node-local /tmp and are removed at the end.
set -euo pipefail
source "$SLURM_SUBMIT_DIR/slurm/env.sh"
: "${MODEL:?set MODEL}" "${VARIANT:?set VARIANT}" "${WRITER:?set WRITER}" "${GRAPH:?set GRAPH}"
[ -n "${ANTHROPIC_API_KEY:-}" ] || [ -n "${T2R_BASE_URL:-}" ] || { echo "no API key"; exit 2; }
cd "$T2A_REPO/prototype"
OUT="runs/written-runs/$WRITER/$GRAPH/$MODEL/$VARIANT${T2R_PROMPT_CACHE:+-cache}/rep${REP:-1}${ONLY:+-$ONLY}"
mkdir -p "$OUT"
WORK="$(mktemp -d /tmp/t2a-wr-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
export TMPDIR="$WORK" T2R_SCRIPT_MEM_MB=120000
if command -v git >/dev/null; then C=$(git rev-parse HEAD); else C=$(cat ../.git/$(cut -d' ' -f2 ../.git/HEAD) 2>/dev/null || echo unknown); fi
echo "commit=$C writer=$WRITER graph=$GRAPH model=$MODEL variant=$VARIANT job=$SLURM_JOB_ID node=$(hostname) started=$(date -u +%FT%TZ) tree=working-copy" >> "$OUT/run_meta.txt"
"$PY" bench/sessions/run_written.py "$OUT" --written "runs/written/$WRITER" --snap "$T2A_DATA/snap" --graph "$GRAPH" --model "$MODEL" --variant "$VARIANT" --work "$WORK/work" ${ONLY:+--only "$ONLY"}
