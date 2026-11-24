#!/bin/bash
#SBATCH -J t2a-practice
#SBATCH -p bigTiger
#SBATCH -c 16
#SBATCH --mem=96G
#SBATCH -t 12:00:00
#SBATCH -o logs/%x-%j.out
# Practice sessions on full Pokec (workload_practice.py): what a realistic session costs with and without reuse and prompt caching.
# Usage: sbatch --export=ALL,MODEL=claude-haiku-5-5,VARIANT=full[,T2R_PROMPT_CACHE=1][,T2R_PLAN_REPLAY=1][,REP=1][,ONLY=campaign][,DRY=1] slurm/run_practice.sbatch
#   VARIANT: full | full_noreuse | codegen_stateful | codegen_stateful_warned | codegen_independent
# Per-session copies of the graph files and their binary caches go to node-local /tmp and are removed at the end.
set -euo pipefail
source "$SLURM_SUBMIT_DIR/slurm/env.sh"
: "${MODEL:?set MODEL}" "${VARIANT:?set VARIANT}"
[ -n "${DRY:-}" ] || [ -n "${ANTHROPIC_API_KEY:-}" ] || { echo "no API key"; exit 2; }
cd "$T2A_REPO/prototype"
OUT="runs/practice/$MODEL/${DRY:+dry-}$VARIANT${T2R_PROMPT_CACHE:+-cache}${T2R_PLAN_REPLAY:+-replay}/rep${REP:-1}${ONLY:+-$ONLY}"
mkdir -p "$OUT"
WORK="$(mktemp -d /tmp/t2a-pr-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
export TMPDIR="$WORK" T2R_SCRIPT_MEM_MB=120000
if command -v git >/dev/null; then C=$(git rev-parse HEAD); else C=$(cat ../.git/$(cut -d' ' -f2 ../.git/HEAD) 2>/dev/null || echo unknown); fi
echo "commit=$C model=$MODEL variant=$VARIANT job=$SLURM_JOB_ID node=$(hostname) started=$(date -u +%FT%TZ) tree=working-copy" > "$OUT/run_meta.txt"
"$PY" bench/sessions/run_stale.py "$OUT" --model "$MODEL" --variant "$VARIANT" --practice "$T2A_DATA/snap" --work "$WORK/work" --timeout 3600 ${ONLY:+--only "$ONLY"} ${DRY:+--dry} ${RESCORE:+--rescore}
