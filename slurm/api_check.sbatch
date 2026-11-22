#!/bin/bash
#SBATCH -J t2a-api
#SBATCH -p bigTiger
#SBATCH -c 16
#SBATCH --mem=64G
#SBATCH -t 00:30:00
#SBATCH -o logs/%x-%j.out
# Starts the demo server on the compute node and drives the session endpoints end to end (Haiku).
set -euo pipefail
source "$SLURM_SUBMIT_DIR/slurm/env.sh"
cd "$T2A_REPO/prototype"
PORT=$((20000 + SLURM_JOB_ID % 10000))
"$PY" demo/server.py --port "$PORT" > "$T2A_REPO/logs/server-$SLURM_JOB_ID.log" 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null || true' EXIT
"$PY" demo/api_check.py "$PORT" "$T2A_DATA/snap/soc-pokec-relationships.txt"
