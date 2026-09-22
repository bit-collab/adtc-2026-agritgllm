#!/usr/bin/env bash
# Chain M, SFT step only: export and batteries of the adapter before DPO.
set -u
ROOT="C:/Users/HP VICTUS/Documents/concoursllmdata"
PY="$ROOT/.venv-train/Scripts/python.exe"
S="$WORK"
EV="$ROOT/adtc-submission-gate2/provenance/evaluation"
LOG="$S/chain_Msft.log"
cd "$ROOT"
echo "== $(date) export Q4_K_M avec imatrix du SFT M" >> "$LOG"
"$PY" train-gate2/03_export.py --tag Msft --adapter train-gate2/outputs/sft/M/best_lora --quants Q4_K_M >> "$S/export_Msft_imatrix.log" 2>&1
echo "   export exit=$?" >> "$LOG"
GGUF="train-gate2/outputs/gguf/Msft/agritg-msft-Q4_K_M.gguf"
sha256sum "$GGUF" >> "$LOG"
echo "== $(date) batteries 4 seeds x 2 bancs" >> "$LOG"
for banc in round1 heldout; do
  for seed in 42 101 202 303; do
    BANC=$banc PORT=8194 "$PY" "$EV/replay_battery.py" "$GGUF" "$EV/batteries_4seeds/${banc}_Msft_s${seed}.json" $seed > "$S/batMsft_${banc}_${seed}.log" 2>&1
    echo "   $banc s$seed : $(tail -1 "$S/batMsft_${banc}_${seed}.log")" >> "$LOG"
  done
done
echo "== $(date) red-team 2 seeds" >> "$LOG"
PORT=8198 "$PY" "$EV/redteam/redteam_battery.py" "$GGUF" "$EV/redteam/msft_s42.json" 42 > "$S/rt_Msft_42.log" 2>&1
echo "   $(tail -1 "$S/rt_Msft_42.log")" >> "$LOG"
PORT=8198 "$PY" "$EV/redteam/redteam_battery.py" "$GGUF" "$EV/redteam/msft_s101.json" 101 > "$S/rt_Msft_101.log" 2>&1
echo "   $(tail -1 "$S/rt_Msft_101.log")" >> "$LOG"
echo "== $(date) verdict provisoire" >> "$LOG"
"$PY" "$S/compare_M.py" Msft > "$S/compare_Msft_provisoire.txt" 2>&1
echo "== $(date) avant/apres 11 prompts" >> "$LOG"
PORT=8196 "$PY" "$S/gen_before_after.py" "$GGUF" "$S/ba_Msft.json" > "$S/ba_Msft.log" 2>&1
echo "== $(date) banc large test puis train (150 x 2)" >> "$LOG"
"$PY" train-gate2/08_bench.py --model "$GGUF" --set test  --n 150 -k 2 --tag Msft --label msft-test  --port 8130 > "$S/bench_Msft_test.log" 2>&1
echo "   test : $(grep -o 'pass@1[^,]*' "$S/bench_Msft_test.log" | tail -1)" >> "$LOG"
"$PY" train-gate2/08_bench.py --model "$GGUF" --set train --n 150 -k 2 --tag Msft --label msft-train --port 8131 > "$S/bench_Msft_train.log" 2>&1
echo "   train : $(grep -o 'pass@1[^,]*' "$S/bench_Msft_train.log" | tail -1)" >> "$LOG"
"$PY" "$S/compare_M.py" Msft > "$S/compare_Msft_final.txt" 2>&1
echo "== $(date) CHAINE Msft TERMINEE : $(tail -1 "$S/compare_Msft_final.txt")" >> "$LOG"
