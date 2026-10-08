#!/usr/bin/env bash
set -euo pipefail
VLLM_VENV="${VLLM_VENV:-$HOME/venvs/vllm129}"
if [[ ! -x "$VLLM_VENV/bin/python" ]]; then
  VLLM_VENV="$HOME/venvs/vllm"
fi
source "$VLLM_VENV/bin/activate"
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"
export VLLM_USE_FLASHINFER_SAMPLER="${VLLM_USE_FLASHINFER_SAMPLER:-0}"
# vLLM 0.30 can stall during the ZeroMQ EngineCore handshake on WSL2.
# In-process V1 avoids that transport while keeping the same inference engine.
export VLLM_ENABLE_V1_MULTIPROCESSING="${VLLM_ENABLE_V1_MULTIPROCESSING:-0}"
MODEL="${MODEL:-Qwen/Qwen3-4B-Instruct-2507}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-devpilot-qwen4b}"
echo "Starting vLLM model: $MODEL"
echo 'First run downloads several GB of model weights.'
vllm serve "$MODEL" \
  --served-model-name "$SERVED_MODEL_NAME" \
  --host 0.0.0.0 \
  --port 8000 \
  --dtype auto \
  --enforce-eager \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.72
