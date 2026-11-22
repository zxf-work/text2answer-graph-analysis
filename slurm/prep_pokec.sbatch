#!/bin/bash
#SBATCH -J t2a-pokec
#SBATCH -p bigTiger
#SBATCH -c 8
#SBATCH --mem=48G
#SBATCH -t 02:00:00
#SBATCH -o logs/%x-%j.out
# Downloads Pokec's profile table, builds the node table next to the edge file, then runs the session reuse check.
# No model calls.
set -euo pipefail
source "$SLURM_SUBMIT_DIR/slurm/env.sh"
cd "$T2A_DATA/snap"
if [ ! -s soc-pokec-profiles.txt ]; then
  curl -fsSL --retry 3 -o soc-pokec-profiles.txt.gz https://snap.stanford.edu/data/soc-pokec-profiles.txt.gz
  gunzip -f soc-pokec-profiles.txt.gz
fi
ls -lh soc-pokec-profiles.txt
"$PY" "$T2A_REPO/prototype/bench/big/prep_pokec.py" soc-pokec-profiles.txt soc-pokec-relationships.txt
cd "$T2A_REPO/prototype"
"$PY" bench/big/session_check.py "$T2A_DATA/snap/soc-pokec-relationships.txt" region
