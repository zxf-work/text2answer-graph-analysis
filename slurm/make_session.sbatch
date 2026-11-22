#!/bin/bash
#SBATCH -J t2a-rec
#SBATCH -p bigTiger
#SBATCH -c 16
#SBATCH --mem=64G
#SBATCH -t 01:00:00
#SBATCH -o logs/%x-%j.out
# Record the Pokec session for the interface. Usage: sbatch --export=ALL,MODEL=claude-opus-5-5 slurm/make_session.sbatch
set -euo pipefail
source "$SLURM_SUBMIT_DIR/slurm/env.sh"
cd "$T2A_REPO/prototype"
"$PY" demo/make_session.py "$T2A_DATA/snap/soc-pokec-relationships.txt" region --name pokec --model "${MODEL:-claude-opus-5-5}" \
  --title "Pokec: who is influential, and where" \
  --description "Pokec social network: each row is a directed friendship from the first user to the second."
