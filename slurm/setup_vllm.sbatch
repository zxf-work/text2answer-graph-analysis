#!/bin/bash
#SBATCH -J t2a-vllm-setup
#SBATCH -p bigTiger
#SBATCH -c 8
#SBATCH --mem=32G
#SBATCH --gres=gpu:1
#SBATCH -t 01:00:00
#SBATCH -o logs/%x-%j.out
# One-time: a separate Python environment with vLLM under the project root (delete envs/vllm to remove it).
# The package cache goes to node-local /tmp so nothing lands in the home directory.
# itiger's GPU driver (560.35) supports CUDA 12 only; vLLM releases built against CUDA 13 do not start there, so pin
# a CUDA 12 release with VLLM_SPEC, e.g. sbatch --export=ALL,VLLM_SPEC="vllm==0.10.2" slurm/setup_vllm.sbatch
set -euo pipefail
source "$SLURM_SUBMIT_DIR/slurm/env.sh"
ENV="$(readlink -f "$T2A_ROOT")/envs/vllm"
WORK="$(mktemp -d /tmp/t2a-vllm-setup-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
export UV_CACHE_DIR="$WORK/uv-cache"
UV="$HOME/.local/bin/uv"
rm -rf "$ENV"; mkdir -p "$(dirname "$ENV")"
"$UV" venv --python 3.12 "$ENV"
"$UV" pip install --python "$ENV/bin/python" ${VLLM_SPEC:-vllm}
"$ENV/bin/python" -c "import vllm, torch; print('vllm', vllm.__version__, 'torch', torch.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0))"
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
"$ENV/bin/vllm" serve --help > /dev/null && echo "vllm command starts"
du -sh "$ENV" | cat
