#!/usr/bin/env bash
set -euo pipefail

echo '[1/5] Checking NVIDIA GPU inside WSL...'
nvidia-smi || { echo 'NVIDIA GPU is not visible in WSL. Update Windows NVIDIA driver and WSL2 first.'; exit 1; }

echo '[2/5] Installing Ubuntu prerequisites...'
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip git curl build-essential

echo '[3/5] Creating vLLM venv...'
python3 -m venv ~/venvs/vllm
source ~/venvs/vllm/bin/activate
python -m pip install -U pip wheel setuptools

echo '[4/5] Installing vLLM...'
pip install vllm

echo '[5/5] Verifying...'
python - <<'PY'
import vllm
print('vLLM:', vllm.__version__)
PY

echo 'vLLM SETUP COMPLETE'
echo 'Start with: bash wsl/start_vllm.sh'
