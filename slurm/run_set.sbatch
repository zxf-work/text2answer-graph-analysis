#!/bin/bash
#SBATCH -J t2a-run
#SBATCH -p bigTiger
#SBATCH -c 8
#SBATCH --mem=8G
#SBATCH -t 12:00:00
#SBATCH -o logs/%x-%A_%a.out
# One benchmark set with one model and one seed index. Calls a model: needs the API key file (see env.sh).
#   sbatch --export=ALL,SET=hard,MODEL=claude-haiku-5-5 --array=1-3 slurm/run_set.sbatch
#   SET: base | hard | scale       (scale: add --mem=64G -t 2-00:00:00)
#   SYSTEMS (optional): comma list passed to run_experiment.py --systems
set -euo pipefail
source "$SLURM_SUBMIT_DIR/slurm/env.sh"
: "${SET:?set SET=base|hard|scale}" "${MODEL:?set MODEL=<model id>}"
[ -n "${ANTHROPIC_API_KEY:-}" ] || { echo "no API key at $T2A_KEY_FILE"; exit 2; }
SEED="${SLURM_ARRAY_TASK_ID:-1}"
case "$SET" in
  base)  Q=questions.json;       D=datasets.json ;;
  hard)  Q=questions_hard.json;  D=datasets_hard.json ;;
  scale) Q=questions_scale.json; D=datasets_scale.json ;;
  *) echo "unknown SET=$SET"; exit 2 ;;
esac
cd "$T2A_REPO/prototype"
export T2R_MODEL="$MODEL" T2R_QUESTIONS="$Q" T2R_DATASETS="$D"
export T2R_RESULTS="runs/$SET/$MODEL/seed$SEED"
mkdir -p "$T2R_RESULTS"
{ echo "commit=$(git -C "$T2A_REPO" rev-parse HEAD)"; echo "model=$MODEL set=$SET seed=$SEED job=${SLURM_JOB_ID:-}"; date -u +started=%FT%TZ; } > "$T2R_RESULTS/run_meta.txt"
"$PY" run_experiment.py --workers "${WORKERS:-3}" --qids all ${SYSTEMS:+--systems "$SYSTEMS"}
date -u +finished=%FT%TZ >> "$T2R_RESULTS/run_meta.txt"
