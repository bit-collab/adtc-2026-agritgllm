#!/usr/bin/env bash
# usage: ./eval/gen.sh Q4_K_M | Q5_K_M | Q6_K
set -euo pipefail
cd ~/adtc-2026
Q="${1:?usage: $0 Q4_K_M|Q5_K_M|Q6_K}"
G="/home/exau/Téléchargements/Telegram Desktop/candidature_agl/gguf"
echo "==> generation v2-$Q : 27 questions de acceptance.jsonl"
python3 eval/ask.py "models/adtc-agritgllm-adviser-v2-$Q.gguf" "$G/acceptance.jsonl" "eval/answers_v2-$Q.jsonl"
echo "==> termine : eval/answers_v2-$Q.jsonl"
