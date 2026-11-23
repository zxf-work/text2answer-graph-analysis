#!/bin/bash
#SBATCH -J t2a-lp
#SBATCH -p bigTiger
#SBATCH -c 16
#SBATCH --mem=160G
#SBATCH -t 03:00:00
#SBATCH -o logs/%x-%j.out
# Stage-by-stage timing of a cold load, and of off-the-shelf alternatives, on one SNAP graph. No model calls.
# Usage: sbatch --export=ALL,FILE=com-orkut.ungraph.txt slurm/load_profile.sbatch
set -euo pipefail
source "$SLURM_SUBMIT_DIR/slurm/env.sh"
: "${FILE:?set FILE}"
cd "$T2A_REPO/prototype"
WORK="$(mktemp -d /tmp/t2a-lp-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
export TMPDIR="$WORK" T2R_CACHE_DIR="$WORK/cache"
cp "$T2A_DATA/snap/$FILE" "$WORK/"
echo "node=$(hostname) file=$FILE"
"$PY" bench/load_profile.py "$WORK/$FILE" ${ARGS:-}
