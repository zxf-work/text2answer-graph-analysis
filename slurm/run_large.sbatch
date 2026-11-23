#!/bin/bash
#SBATCH -J t2a-e4
#SBATCH -p bigTiger
#SBATCH -c 16
#SBATCH --mem=160G
#SBATCH -t 12:00:00
#SBATCH -o logs/%x-%j.out
# E4: sessions on the real large graphs (Pokec, LiveJournal, Orkut), with an unannounced change of the edge file.
# Usage: sbatch --export=ALL,MODEL=claude-opus-5-5,VARIANT=full[,REP=1][,ONLY=pokec][,DRY=1] slurm/run_large.sbatch
# Per-session copies of the graph files and their binary caches go to node-local /tmp and are removed at the end.
set -euo pipefail
source "$SLURM_SUBMIT_DIR/slurm/env.sh"
: "${MODEL:?set MODEL}" "${VARIANT:?set VARIANT}"
[ -n "${DRY:-}" ] || [ -n "${ANTHROPIC_API_KEY:-}" ] || { echo "no API key"; exit 2; }
cd "$T2A_REPO/prototype"
OUT="runs/large/$MODEL/${DRY:+dry-}$VARIANT/rep${REP:-1}${ONLY:+-$ONLY}"
mkdir -p "$OUT"
WORK="$(mktemp -d /tmp/t2a-e4-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
export TMPDIR="$WORK" T2R_SCRIPT_MEM_MB=120000
if command -v git >/dev/null; then C=$(git rev-parse HEAD); else C=$(cat ../.git/$(cut -d' ' -f2 ../.git/HEAD) 2>/dev/null || echo unknown); fi
echo "commit=$C model=$MODEL variant=$VARIANT job=$SLURM_JOB_ID node=$(hostname) started=$(date -u +%FT%TZ) tree=working-copy" > "$OUT/run_meta.txt"
"$PY" bench/sessions/run_stale.py "$OUT" --model "$MODEL" --variant "$VARIANT" --large "$T2A_DATA/snap" --work "$WORK/work" --timeout 3600 ${ONLY:+--only "$ONLY"} ${DRY:+--dry} ${RESCORE:+--rescore}
