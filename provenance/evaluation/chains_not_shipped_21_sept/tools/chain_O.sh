#!/usr/bin/env bash
# Chaine M apres SFT : export rapide du SFT -> echantillonnage on-policy -> DPO enrichi -> export Q4_K_M -> memes instruments.
set -u
ROOT="C:/Users/HP VICTUS/Documents/concoursllmdata"
PY="$ROOT/.venv-train/Scripts/python.exe"
S="$WORK"
EV="$ROOT/adtc-submission-gate2/provenance/evaluation"
LOG="$S/chain_O.log"
cd "$ROOT"
echo "== $(date) attente fin SFT O" >> "$LOG"
until grep -q "^exit=" "$S/sft_O.log" 2>/dev/null; do sleep 30; done
echo "== $(date) SFT termine : $(grep '^exit=' "$S/sft_O.log")" >> "$LOG"
[ -f train-gate2/outputs/sft/O/best_lora/adapter_config.json ] || { echo "PAS d'adaptateur SFT O, arret" >> "$LOG"; exit 1; }

echo "== $(date) export rapide du SFT O (Q4_K_M sans imatrix) pour l'echantillonnage" >> "$LOG"
"$PY" train-gate2/03_export.py --tag Osft --adapter train-gate2/outputs/sft/O/best_lora --quants Q4_K_M >> "$S/export_Osft.log" 2>&1
echo "   export exit=$?" >> "$LOG"
SFTGGUF="train-gate2/outputs/gguf/Osft/agritg-osft-Q4_K_M.gguf"
if [ -f "$SFTGGUF" ]; then
  echo "== $(date) echantillonnage on-policy du SFT O" >> "$LOG"
  "$PY" "$S/sample_safety.py" "$ROOT/$SFTGGUF" "$S/onpolicy_safety_Osft" 8212 > "$S/sample_safety_Osft.log" 2>&1
  tail -2 "$S/sample_safety_Osft.log" >> "$LOG"
else
  echo "   PAS de GGUF Msft, on continue avec les paires Ldpo seules" >> "$LOG"
fi

echo "== $(date) evaluation du SFT O seul, en parallele du DPO" >> "$LOG"
nohup bash "$S/eval_Osft.sh" > /dev/null 2>&1 &
echo "== $(date) jeu DPO enrichi" >> "$LOG"
cp train-gate2/data/dpo_train.jsonl "$S/dpo_train_O_avant_securite.jsonl"
mkdir -p train-gate2/provenance/Odpo
PAIRS="$S/onpolicy_safety_Ldpo.dpo.jsonl"
[ -f "$S/onpolicy_safety_Osft.dpo.jsonl" ] && PAIRS="$PAIRS $S/onpolicy_safety_Osft.dpo.jsonl"
"$PY" "$S/build_dpo_N.py" train-gate2/data/dpo_train.jsonl train-gate2/provenance/Odpo/dpo_safety_manifest.json $PAIRS >> "$LOG" 2>&1

echo "== $(date) DPO Odpo" >> "$LOG"
"$PY" train-gate2/02_dpo.py --tag Odpo --adapter train-gate2/outputs/sft/O/best_lora >> "$S/dpo_O.log" 2>&1
echo "   dpo exit=$?" >> "$LOG"
[ -f train-gate2/outputs/dpo/Odpo/best_lora/adapter_config.json ] || { echo "PAS d'adaptateur DPO, arret" >> "$LOG"; exit 1; }

echo "== $(date) export Q4_K_M" >> "$LOG"
"$PY" train-gate2/03_export.py --tag Odpo --adapter train-gate2/outputs/dpo/Odpo/best_lora --quants Q4_K_M >> "$S/export_O.log" 2>&1
echo "   export exit=$?" >> "$LOG"
GGUF="train-gate2/outputs/gguf/Odpo/agritg-odpo-Q4_K_M.gguf"
[ -f "$GGUF" ] || { echo "PAS de GGUF, arret" >> "$LOG"; exit 1; }
sha256sum "$GGUF" >> "$LOG"

echo "== $(date) batteries 4 seeds x 2 bancs" >> "$LOG"
for banc in round1 heldout; do
  for seed in 42 101 202 303; do
    BANC=$banc PORT=8192 "$PY" "$EV/replay_battery.py" "$GGUF" "$EV/batteries_4seeds/${banc}_Odpo_s${seed}.json" $seed > "$S/batO_${banc}_${seed}.log" 2>&1
    echo "   $banc s$seed : $(tail -1 "$S/batO_${banc}_${seed}.log")" >> "$LOG"
  done
done

echo "== $(date) red-team 2 seeds" >> "$LOG"
PORT=8199 "$PY" "$EV/redteam/redteam_battery.py" "$GGUF" "$EV/redteam/odpo_s42.json" 42 > "$S/rt_O_42.log" 2>&1
echo "   $(tail -1 "$S/rt_O_42.log")" >> "$LOG"
PORT=8199 "$PY" "$EV/redteam/redteam_battery.py" "$GGUF" "$EV/redteam/odpo_s101.json" 101 > "$S/rt_O_101.log" 2>&1
echo "   $(tail -1 "$S/rt_O_101.log")" >> "$LOG"

echo "== $(date) verdict provisoire (sans banc large)" >> "$LOG"
"$PY" "$S/compare_M.py" Odpo >> "$S/compare_O_provisoire.txt" 2>&1

echo "== $(date) avant/apres 11 prompts" >> "$LOG"
PORT=8197 "$PY" "$S/gen_before_after.py" "$GGUF" "$S/ba_O.json" > "$S/ba_O.log" 2>&1
echo "   ba exit=$?" >> "$LOG"

echo "== $(date) banc large test puis train (150 x 2)" >> "$LOG"
"$PY" train-gate2/08_bench.py --model "$GGUF" --set test  --n 150 -k 2 --tag O --label odpo-test  > "$S/bench_O_test.log" 2>&1
echo "   test : $(grep -o 'pass@1[^,]*' "$S/bench_O_test.log" | tail -1)" >> "$LOG"
"$PY" train-gate2/08_bench.py --model "$GGUF" --set train --n 150 -k 2 --tag O --label odpo-train > "$S/bench_O_train.log" 2>&1
echo "   train : $(grep -o 'pass@1[^,]*' "$S/bench_O_train.log" | tail -1)" >> "$LOG"
"$PY" "$S/compare_M.py" Odpo > "$S/compare_O_final.txt" 2>&1
echo "== $(date) CHAINE O TERMINEE : $(tail -1 "$S/compare_O_final.txt")" >> "$LOG"
