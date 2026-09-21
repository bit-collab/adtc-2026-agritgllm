#!/usr/bin/env bash
ROOT="C:/Users/HP VICTUS/Documents/concoursllmdata"
S="$WORK"
cd "$ROOT"
"$ROOT/.venv-train/Scripts/python.exe" train-gate2/01_sft.py --tag M --no-4bit --patience 0 > "$S/sft_M.log" 2>&1
echo "exit=$?" >> "$S/sft_M.log"
