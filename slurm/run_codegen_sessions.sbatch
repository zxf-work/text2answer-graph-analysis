#!/bin/bash
#SBATCH -J t2a-e2cg
#SBATCH -p bigTiger
#SBATCH -c 8
#SBATCH --mem=64G
#SBATCH -t 08:00:00
#SBATCH -o logs/%x-%j.out
# E2 baselines: code-generation agents on the session workload.
# Usage: sbatch --export=ALL,MODEL=claude-haiku-5-5,VARIANT=codegen_stateful[,REP=1][,ONLY=trust] slurm/run_codegen_sessions.sbatch
#   VARIANT: codegen_stateful | codegen_independent
set -euo pipefail
source "$SLURM_SUBMIT_DIR/slurm/env.sh"
: "${MODEL:?set MODEL}" "${VARIANT:?set VARIANT}"
[ -n "${ANTHROPIC_API_KEY:-}" ] || { echo "no API key"; exit 2; }
cd "$T2A_REPO/prototype"
OUT="runs/sessions/$MODEL/$VARIANT/rep${REP:-1}${ONLY:+-$ONLY}"
mkdir -p "$OUT"
if command -v git >/dev/null; then C=$(git rev-parse HEAD); else C=$(cat ../.git/$(cut -d' ' -f2 ../.git/HEAD) 2>/dev/null || echo unknown); fi
echo "commit=$C model=$MODEL variant=$VARIANT job=$SLURM_JOB_ID started=$(date -u +%FT%TZ) tree=working-copy" > "$OUT/run_meta.txt"
"$PY" bench/sessions/run_codegen_sessions.py "$OUT" --model "$MODEL" --variant "$VARIANT" ${ONLY:+--only "$ONLY"} "$T2A_DATA"/sessions/pokec_*.txt
