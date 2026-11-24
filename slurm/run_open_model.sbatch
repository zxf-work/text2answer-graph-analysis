#!/bin/bash
#SBATCH -J t2a-open
#SBATCH -p bigTiger
#SBATCH -c 8
#SBATCH --mem=64G
#SBATCH --gres=gpu:1
#SBATCH -t 12:00:00
#SBATCH -o logs/%x-%j.out
# The session experiments with an open model served on the job's own GPU behind an OpenAI-compatible endpoint:
# Ollama (default; 4-bit quantised builds) or vLLM (SERVER=vllm; the published weights).
# Nothing is kept: the server release, caches and model weights go to node-local /tmp and are removed at the end.
# Usage: sbatch --export=ALL,MODEL=qwen3:14b,VARIANT=full[,WORKLOAD=stale|large][,REP=1][,ONLY=...][,CTX=32768] slurm/run_open_model.sbatch
#        sbatch --gres=gpu:h100_80gb:1 --export=ALL,SERVER=vllm,HF_MODEL=Qwen/Qwen3-14B,MODEL=qwen3-14b,VARIANT=full[,T2R_JSON_MODE=1] slurm/run_open_model.sbatch
set -euo pipefail
source "$SLURM_SUBMIT_DIR/slurm/env.sh"
unset ANTHROPIC_API_KEY
: "${MODEL:?set MODEL}" "${VARIANT:?set VARIANT}"
WORKLOAD="${WORKLOAD:-stale}"
WORK="$(mktemp -d /tmp/t2a-open-XXXXXX)"
trap 'kill $SERVER_PID 2>/dev/null || true; rm -rf "$WORK"' EXIT
PORT=$((20000 + SLURM_JOB_ID % 20000))
SRV="${SERVER:-ollama}"
if [ "$SRV" = vllm ]; then
  # vLLM: the published weights (HF_MODEL, e.g. Qwen/Qwen3-14B), served under the name MODEL. Environment from slurm/setup_vllm.sbatch.
  : "${HF_MODEL:?set HF_MODEL}"
  VENV="$(readlink -f "$T2A_ROOT")/envs/vllm"
  export HF_HOME="$WORK/hf" VLLM_CACHE_ROOT="$WORK/vllm-cache" XDG_CACHE_HOME="$WORK/xdg" HF_HUB_DISABLE_TELEMETRY=1 VLLM_NO_USAGE_STATS=1 DO_NOT_TRACK=1
  "$VENV/bin/vllm" serve "$HF_MODEL" --host 127.0.0.1 --port "$PORT" --served-model-name "$MODEL" --max-model-len "${CTX:-32768}" \
      --gpu-memory-utilization "${GPU_FRACTION:-0.92}" ${VLLM_ARGS:-} > "$WORK/server.log" 2>&1 &
  SERVER_PID=$!
  for i in $(seq 360); do
    curl -s "http://127.0.0.1:$PORT/v1/models" 2>/dev/null | grep -q "\"$MODEL\"" && break
    kill -0 $SERVER_PID 2>/dev/null || { echo "vLLM exited"; grep -i -e "error" -e "memory" "$WORK/server.log" | grep -v "File \"" | cut -c1-400 | head -30; tail -15 "$WORK/server.log"; exit 3; }
    sleep 10
  done
  curl -s "http://127.0.0.1:$PORT/v1/models" | grep -q "\"$MODEL\"" || { echo "vLLM not ready"; tail -40 "$WORK/server.log"; exit 3; }
  SERVED="vllm $("$VENV/bin/python" -c 'import vllm; print(vllm.__version__)') $HF_MODEL"
  BASE="http://127.0.0.1:$PORT"
else
  cd "$WORK"
  REL="${OLLAMA_RELEASE:-v0.40.17}"
  curl -sSL -o ollama.tar.zst "https://github.com/ollama/ollama/releases/download/$REL/ollama-linux-amd64.tar.zst"
  "$PY" -c "import zstandard,sys; zstandard.ZstdDecompressor().copy_stream(open('ollama.tar.zst','rb'), open('ollama.tar','wb'))"
  mkdir ollama && tar -xf ollama.tar -C ollama && rm ollama.tar ollama.tar.zst
  export OLLAMA_HOST="127.0.0.1:$PORT" OLLAMA_MODELS="$WORK/models" OLLAMA_CONTEXT_LENGTH="${CTX:-32768}" OLLAMA_KEEP_ALIVE=24h OLLAMA_NUM_PARALLEL=1 HOME="$WORK/home"
  mkdir -p "$HOME"
  "$WORK/ollama/bin/ollama" serve > "$WORK/server.log" 2>&1 &
  SERVER_PID=$!
  for i in $(seq 60); do curl -s "http://$OLLAMA_HOST/api/version" >/dev/null && break; sleep 2; done
  "$WORK/ollama/bin/ollama" pull "$MODEL" 2>&1 | tail -1
  SERVED="ollama $REL"
  BASE="http://$OLLAMA_HOST"
fi
nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader
export T2R_BASE_URL="$BASE" TMPDIR="$WORK" T2R_SCRIPT_MEM_MB=120000
cd "$T2A_REPO/prototype"
M="${MODEL//[:\/]/-}"
[ "$SRV" = vllm ] && M="$M-vllm"
OUT="runs/$WORKLOAD/$M/$VARIANT/rep${REP:-1}${ONLY:+-${ONLY//\//_}}"
[ "$WORKLOAD" = large ] && OUT="runs/large/$M/$VARIANT/rep${REP:-1}${ONLY:+-$ONLY}"
mkdir -p "$OUT"
echo "model=$MODEL variant=$VARIANT workload=$WORKLOAD ctx=${CTX:-32768} server=$SERVED json_mode=${T2R_JSON_MODE:-0} temperature=${T2R_TEMPERATURE:-0} seed=${T2R_SEED:-} job=$SLURM_JOB_ID node=$(hostname) started=$(date -u +%FT%TZ)" > "$OUT/run_meta.txt"
if [ "$WORKLOAD" = large ]; then
  "$PY" bench/sessions/run_stale.py "$OUT" --model "$MODEL" --variant "$VARIANT" --large "$T2A_DATA/snap" --work "$WORK/work" --timeout 3600 ${ONLY:+--only "$ONLY"}
else
  "$PY" bench/sessions/run_stale.py "$OUT" --model "$MODEL" --variant "$VARIANT" --work "$WORK/work" ${ONLY:+--only "$ONLY"} "$T2A_DATA"/sessions/pokec_*.txt
fi
grep -i -e "truncat" -e "context" "$WORK/server.log" | tail -5 || true
