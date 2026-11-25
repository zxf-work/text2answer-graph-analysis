#!/bin/bash
#SBATCH -J t2a-rec
#SBATCH -p bigTiger
#SBATCH -c 16
#SBATCH --mem=64G
#SBATCH -t 01:00:00
#SBATCH -o logs/%x-%j.out
# Record the signature session for the interface (demo/signature.json -> demo/sessions/pokec.json).
# Usage: sbatch --export=ALL,MODEL=claude-haiku-5-5 slurm/make_session.sbatch
# The session runs on a copy of the Pokec files in node-local /tmp (the script appends rows to it), removed at the end.
set -euo pipefail
source "$SLURM_SUBMIT_DIR/slurm/env.sh"
cd "$T2A_REPO/prototype"
WORK="$(mktemp -d /tmp/t2a-rec-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
export TMPDIR="$WORK" T2R_PROMPT_CACHE=1
"$PY" demo/make_session.py "$T2A_DATA/snap/soc-pokec-relationships.txt" --script demo/signature.json --model "${MODEL:-claude-haiku-5-5}" --work "$WORK/work"
