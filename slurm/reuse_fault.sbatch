#!/bin/bash
#SBATCH -J t2a-e1
#SBATCH -p bigTiger
#SBATCH -c 16
#SBATCH --mem=96G
#SBATCH -t 04:00:00
#SBATCH -o logs/%x-%j.out
# E1: reuse fault injection (no model calls). Builds the attributed Pokec subgraphs on first use.
set -euo pipefail
source "$SLURM_SUBMIT_DIR/slurm/env.sh"
cd "$T2A_REPO/prototype"
PARTS="$T2A_DATA/sessions"
if ! ls "$PARTS"/pokec_*.nodes.tsv >/dev/null 2>&1; then
  "$PY" bench/sessions/prep_pokec_parts.py "$T2A_DATA/snap/soc-pokec-relationships.txt" "$PARTS" 3
fi
OUT="runs/reuse_fault/job$SLURM_JOB_ID"
mkdir -p "$OUT"
if command -v git >/dev/null; then C=$(git rev-parse HEAD); else C=$(cat ../.git/$(cut -d' ' -f2 ../.git/HEAD) 2>/dev/null || echo unknown); fi
echo "commit=$C job=$SLURM_JOB_ID started=$(date -u +%FT%TZ) tree=working-copy" > "$OUT/run_meta.txt"
"$PY" bench/sessions/reuse_fault.py "$OUT" "$PARTS"/pokec_*.txt
