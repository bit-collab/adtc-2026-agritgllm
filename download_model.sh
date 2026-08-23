#!/usr/bin/env bash
# Downloads the GGUF model weight file into model/. Idempotent, no credentials.
# The file must be publicly hosted; edit MODEL_URL if you host elsewhere.
set -euo pipefail

MODEL_DIR="model"
MODEL_FILE="${MODEL_DIR}/adtc-agritgllm-adviser-Q4_K_M.gguf"

# Public Hugging Face download URL. No credentials needed.
MODEL_URL="https://huggingface.co/exau/adtc-agritgllm-adviser/resolve/main/adtc-agritgllm-adviser-Q4_K_M.gguf?download=true"

mkdir -p "${MODEL_DIR}"

if [ -f "${MODEL_FILE}" ]; then
  echo "Model already present at ${MODEL_FILE}, skipping download."
  exit 0
fi

echo "Downloading model to ${MODEL_FILE} ..."
if command -v curl >/dev/null 2>&1; then
  curl -L --fail -o "${MODEL_FILE}" "${MODEL_URL}"
elif command -v wget >/dev/null 2>&1; then
  wget -O "${MODEL_FILE}" "${MODEL_URL}"
else
  echo "ERROR: need curl or wget to download the model." >&2
  exit 1
fi

echo "Done: ${MODEL_FILE}"
