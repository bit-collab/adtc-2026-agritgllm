#!/usr/bin/env bash
# Batteries, red team and wide benchmark of the chain O adapter.
set -u
ROOT="C:/Users/HP VICTUS/Documents/concoursllmdata"
PY="$ROOT/.venv-train/Scripts/python.exe"
S="$WORK"
EV="$ROOT/adtc-submission-gate2/provenance/evaluation"
LOG="$S/chain_Osft.log"
cd "$ROOT"
GGUF="train-gate2/outputs/gguf/Osft/agritg-osft-Q4_K_M.gguf"
echo "== $(date) batteries 4 seeds x 2 bancs" >> "$LOG"
for banc in round1 heldout; do
  for seed in 42 101 202 303; do
    BANC=$banc PORT=8194 "$PY" "$EV/replay_battery.py" "$GGUF" "$EV/batteries_4seeds/${banc}_Osft_s${seed}.json" $seed > "$S/batOsft_${banc}_${seed}.log" 2>&1
    echo "   $banc s$seed : $(tail -1 "$S/batOsft_${banc}_${seed}.log")" >> "$LOG"
  done
done
echo "== $(date) red-team 2 seeds" >> "$LOG"
PORT=8198 "$PY" "$EV/redteam/redteam_battery.py" "$GGUF" "$EV/redteam/osft_s42.json" 42 > "$S/rt_Osft_42.log" 2>&1
echo "   $(tail -1 "$S/rt_Osft_42.log")" >> "$LOG"
PORT=8198 "$PY" "$EV/redteam/redteam_battery.py" "$GGUF" "$EV/redteam/osft_s101.json" 101 > "$S/rt_Osft_101.log" 2>&1
echo "   $(tail -1 "$S/rt_Osft_101.log")" >> "$LOG"
echo "== $(date) verdict provisoire" >> "$LOG"
"$PY" "$S/compare_M.py" Osft > "$S/compare_Osft_provisoire.txt" 2>&1
echo "== $(date) avant/apres 11 prompts" >> "$LOG"
PORT=8196 "$PY" "$S/gen_before_after.py" "$GGUF" "$S/ba_Osft.json" > "$S/ba_Osft.log" 2>&1
echo "== $(date) banc large test puis train (150 x 2)" >> "$LOG"
"$PY" train-gate2/08_bench.py --model "$GGUF" --set test  --n 150 -k 2 --tag Osft --label osft-test  --port 8130 > "$S/bench_Osft_test.log" 2>&1
echo "   test : $(grep -o 'pass@1[^,]*' "$S/bench_Osft_test.log" | tail -1)" >> "$LOG"
"$PY" train-gate2/08_bench.py --model "$GGUF" --set train --n 150 -k 2 --tag Osft --label osft-train --port 8131 > "$S/bench_Osft_train.log" 2>&1
echo "   train : $(grep -o 'pass@1[^,]*' "$S/bench_Osft_train.log" | tail -1)" >> "$LOG"
"$PY" "$S/compare_M.py" Osft > "$S/compare_Osft_final.txt" 2>&1
echo "== $(date) CHAINE Osft TERMINEE : $(tail -1 "$S/compare_Osft_final.txt")" >> "$LOG"
