#!/bin/bash
#SBATCH -J t2a-fetch
#SBATCH -p bigTiger
#SBATCH -c 4
#SBATCH --mem=16G
#SBATCH -t 04:00:00
#SBATCH -o logs/%x-%j.out
# Downloads the three real graphs for the scale tier from SNAP and unpacks them. No model calls.
set -euo pipefail
source "$SLURM_SUBMIT_DIR/slurm/env.sh"
mkdir -p "$T2A_DATA/snap" && cd "$T2A_DATA/snap"
fetch() {  # url
  f="$(basename "$1")"; out="${f%.gz}"
  if [ -s "$out" ]; then echo "have $out"; return; fi
  curl -fsSL --retry 3 -o "$f" "$1"
  gunzip -f "$f"
  echo "$out  rows(non-comment)=$(grep -vc '^#' "$out")  size=$(du -h "$out" | cut -f1)  sha256=$(sha256sum "$out" | cut -c1-16)"
}
fetch https://snap.stanford.edu/data/soc-pokec-relationships.txt.gz
fetch https://snap.stanford.edu/data/soc-LiveJournal1.txt.gz
fetch https://snap.stanford.edu/data/bigdata/communities/com-orkut.ungraph.txt.gz
ls -lh
