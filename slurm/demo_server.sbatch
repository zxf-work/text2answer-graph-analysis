#!/bin/bash
#SBATCH --job-name=t2a-demo
#SBATCH --partition=bigTiger
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=01:30:00
#SBATCH --output=logs/demo-%j.out
# The demo server with the signature session's graph offered live.
# Usage: sbatch --export=ALL,MODEL=claude-haiku-5-5,PORT=8765 slurm/demo_server.sbatch
# The server listens on the node's loopback only; reach it through an SSH tunnel (the log prints the node name):
#   ssh -N -L 8772:localhost:8765 -J <user>@<login node> <user>@<node>
# Sessions on the scripted graph run on a copy of the Pokec files in node-local /tmp, removed when the job ends.
set -euo pipefail
source "$SLURM_SUBMIT_DIR/slurm/env.sh"
cd "$T2A_REPO/prototype"
WORK="$(mktemp -d /tmp/t2a-live-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
export TMPDIR="$WORK" T2R_PROMPT_CACHE=1
echo "node $(hostname) port ${PORT:-8765}"
"$PY" demo/server.py --port "${PORT:-8765}" --model "${MODEL:-claude-haiku-5-5}" \
  --live "$T2A_DATA/snap/soc-pokec-relationships.txt" --script demo/signature.json --work "$WORK/work"
