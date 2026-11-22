#!/bin/bash
#SBATCH --job-name=t2a-session
#SBATCH --partition=bigTiger
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=01:00:00
#SBATCH --output=logs/session-%j.out
# Live session on Pokec. Usage: sbatch --export=ALL,MODEL=claude-haiku-5-5 slurm/session_live.sbatch
set -euo pipefail
source "${SLURM_SUBMIT_DIR:-.}/slurm/env.sh"
MODEL=${MODEL:-claude-haiku-5-5}
cd "$T2A_REPO/prototype"
"$PY" bench/big/session_live.py "$T2A_DATA/snap/soc-pokec-relationships.txt" region --model "$MODEL" \
  --description "Pokec social network: each row is a directed friendship from the first user to the second." \
  --out "runs/session_live/$MODEL/job$SLURM_JOB_ID"
