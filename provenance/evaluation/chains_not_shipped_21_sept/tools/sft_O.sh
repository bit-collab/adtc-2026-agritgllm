#!/usr/bin/env bash
# SFT run of chain O.
ROOT="C:/Users/HP VICTUS/Documents/concoursllmdata"
S="$WORK"
cd "$ROOT"
"$ROOT/.venv-train/Scripts/python.exe" train-gate2/01_sft.py --tag O --no-4bit --patience 0 > "$S/sft_O.log" 2>&1
echo "exit=$?" >> "$S/sft_O.log"
