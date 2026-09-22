#!/usr/bin/env bash
# Chain N: same as M with the on-policy pairs taken once (x1).
set -u
ROOT="C:/Users/HP VICTUS/Documents/concoursllmdata"
PY="$ROOT/.venv-train/Scripts/python.exe"
S="$WORK"
EV="$ROOT/adtc-submission-gate2/provenance/evaluation"
LOG="$S/chain_N.log"
cd "$ROOT"
echo "== $(date) DPO Ndpo" >> "$LOG"
"$PY" train-gate2/02_dpo.py --tag Ndpo --adapter train-gate2/outputs/sft/M/best_lora >> "$S/dpo_N.log" 2>&1
echo "   dpo exit=$?" >> "$LOG"
[ -f train-gate2/outputs/dpo/Ndpo/best_lora/adapter_config.json ] || { echo "PAS d'adaptateur DPO, arret" >> "$LOG"; exit 1; }

echo "== $(date) export Q4_K_M" >> "$LOG"
"$PY" train-gate2/03_export.py --tag Ndpo --adapter train-gate2/outputs/dpo/Ndpo/best_lora --quants Q4_K_M >> "$S/export_N.log" 2>&1
echo "   export exit=$?" >> "$LOG"
GGUF="train-gate2/outputs/gguf/Ndpo/agritg-ndpo-Q4_K_M.gguf"
[ -f "$GGUF" ] || { echo "PAS de GGUF, arret" >> "$LOG"; exit 1; }
sha256sum "$GGUF" >> "$LOG"

echo "== $(date) batteries 4 seeds x 2 bancs" >> "$LOG"
for banc in round1 heldout; do
  for seed in 42 101 202 303; do
    BANC=$banc PORT=8192 "$PY" "$EV/replay_battery.py" "$GGUF" "$EV/batteries_4seeds/${banc}_Ndpo_s${seed}.json" $seed > "$S/batN_${banc}_${seed}.log" 2>&1
    echo "   $banc s$seed : $(tail -1 "$S/batN_${banc}_${seed}.log")" >> "$LOG"
  done
done

echo "== $(date) red-team 2 seeds" >> "$LOG"
PORT=8199 "$PY" "$EV/redteam/redteam_battery.py" "$GGUF" "$EV/redteam/ndpo_s42.json" 42 > "$S/rt_N_42.log" 2>&1
echo "   $(tail -1 "$S/rt_N_42.log")" >> "$LOG"
PORT=8199 "$PY" "$EV/redteam/redteam_battery.py" "$GGUF" "$EV/redteam/ndpo_s101.json" 101 > "$S/rt_N_101.log" 2>&1
echo "   $(tail -1 "$S/rt_N_101.log")" >> "$LOG"

echo "== $(date) verdict provisoire (sans banc large)" >> "$LOG"
"$PY" "$S/compare_N.py" >> "$S/compare_N_provisoire.txt" 2>&1

echo "== $(date) avant/apres 11 prompts" >> "$LOG"
PORT=8197 "$PY" "$S/gen_before_after.py" "$GGUF" "$S/ba_N.json" > "$S/ba_N.log" 2>&1
echo "   ba exit=$?" >> "$LOG"

echo "== $(date) banc large test puis train (150 x 2)" >> "$LOG"
"$PY" train-gate2/08_bench.py --model "$GGUF" --set test  --n 150 -k 2 --tag N --label ndpo-test  > "$S/bench_N_test.log" 2>&1
echo "   test : $(grep -o 'pass@1[^,]*' "$S/bench_N_test.log" | tail -1)" >> "$LOG"
"$PY" train-gate2/08_bench.py --model "$GGUF" --set train --n 150 -k 2 --tag N --label ndpo-train > "$S/bench_N_train.log" 2>&1
echo "   train : $(grep -o 'pass@1[^,]*' "$S/bench_N_train.log" | tail -1)" >> "$LOG"
"$PY" "$S/compare_N.py" > "$S/compare_N_final.txt" 2>&1
echo "== $(date) CHAINE N TERMINEE : $(tail -1 "$S/compare_N_final.txt")" >> "$LOG"
