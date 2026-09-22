#!/usr/bin/env bash
# Chain M: SFT on the safety lots, then DPO on the on-policy pairs (x3), export, batteries.
set -u
ROOT="C:/Users/HP VICTUS/Documents/concoursllmdata"
PY="$ROOT/.venv-train/Scripts/python.exe"
S="$WORK"
EV="$ROOT/adtc-submission-gate2/provenance/evaluation"
LOG="$S/chain_M.log"
cd "$ROOT"
echo "== $(date) attente fin SFT M" >> "$LOG"
until grep -q "^exit=" "$S/sft_M.log" 2>/dev/null; do sleep 30; done
echo "== $(date) SFT termine : $(grep '^exit=' "$S/sft_M.log")" >> "$LOG"
[ -f train-gate2/outputs/sft/M/best_lora/adapter_config.json ] || { echo "PAS d'adaptateur SFT M, arret" >> "$LOG"; exit 1; }

echo "== $(date) export rapide du SFT M (Q4_K_M sans imatrix) pour l'echantillonnage" >> "$LOG"
"$PY" train-gate2/03_export.py --tag Msft --adapter train-gate2/outputs/sft/M/best_lora --quants Q4_K_M --skip-imatrix >> "$S/export_Msft.log" 2>&1
echo "   export exit=$?" >> "$LOG"
SFTGGUF="train-gate2/outputs/gguf/Msft/agritg-msft-Q4_K_M.gguf"
if [ -f "$SFTGGUF" ]; then
  echo "== $(date) echantillonnage on-policy du SFT M" >> "$LOG"
  "$PY" "$S/sample_safety.py" "$ROOT/$SFTGGUF" "$S/onpolicy_safety_Msft" 8211 > "$S/sample_safety_Msft.log" 2>&1
  tail -2 "$S/sample_safety_Msft.log" >> "$LOG"
else
  echo "   PAS de GGUF Msft, on continue avec les paires Ldpo seules" >> "$LOG"
fi

echo "== $(date) jeu DPO enrichi" >> "$LOG"
cp train-gate2/data/dpo_train.jsonl "$S/dpo_train_M_avant_securite.jsonl"
mkdir -p train-gate2/provenance/Mdpo
PAIRS="$S/onpolicy_safety_Ldpo.dpo.jsonl"
[ -f "$S/onpolicy_safety_Msft.dpo.jsonl" ] && PAIRS="$PAIRS $S/onpolicy_safety_Msft.dpo.jsonl"
"$PY" "$S/build_dpo_M.py" train-gate2/data/dpo_train.jsonl train-gate2/provenance/Mdpo/dpo_safety_manifest.json $PAIRS >> "$LOG" 2>&1

echo "== $(date) DPO Mdpo" >> "$LOG"
"$PY" train-gate2/02_dpo.py --tag Mdpo --adapter train-gate2/outputs/sft/M/best_lora >> "$S/dpo_M.log" 2>&1
echo "   dpo exit=$?" >> "$LOG"
[ -f train-gate2/outputs/dpo/Mdpo/best_lora/adapter_config.json ] || { echo "PAS d'adaptateur DPO, arret" >> "$LOG"; exit 1; }

echo "== $(date) export Q4_K_M" >> "$LOG"
"$PY" train-gate2/03_export.py --tag Mdpo --adapter train-gate2/outputs/dpo/Mdpo/best_lora --quants Q4_K_M >> "$S/export_M.log" 2>&1
echo "   export exit=$?" >> "$LOG"
GGUF="train-gate2/outputs/gguf/Mdpo/agritg-mdpo-Q4_K_M.gguf"
[ -f "$GGUF" ] || { echo "PAS de GGUF, arret" >> "$LOG"; exit 1; }
sha256sum "$GGUF" >> "$LOG"

echo "== $(date) batteries 4 seeds x 2 bancs" >> "$LOG"
for banc in round1 heldout; do
  for seed in 42 101 202 303; do
    BANC=$banc PORT=8192 "$PY" "$EV/replay_battery.py" "$GGUF" "$EV/batteries_4seeds/${banc}_Mdpo_s${seed}.json" $seed > "$S/batM_${banc}_${seed}.log" 2>&1
    echo "   $banc s$seed : $(tail -1 "$S/batM_${banc}_${seed}.log")" >> "$LOG"
  done
done

echo "== $(date) red-team 2 seeds" >> "$LOG"
PORT=8199 "$PY" "$EV/redteam/redteam_battery.py" "$GGUF" "$EV/redteam/mdpo_s42.json" 42 > "$S/rt_M_42.log" 2>&1
echo "   $(tail -1 "$S/rt_M_42.log")" >> "$LOG"
PORT=8199 "$PY" "$EV/redteam/redteam_battery.py" "$GGUF" "$EV/redteam/mdpo_s101.json" 101 > "$S/rt_M_101.log" 2>&1
echo "   $(tail -1 "$S/rt_M_101.log")" >> "$LOG"

echo "== $(date) verdict provisoire (sans banc large)" >> "$LOG"
"$PY" "$S/compare_M.py" >> "$S/compare_M_provisoire.txt" 2>&1

echo "== $(date) avant/apres 11 prompts" >> "$LOG"
PORT=8197 "$PY" "$S/gen_before_after.py" "$GGUF" "$S/ba_M.json" > "$S/ba_M.log" 2>&1
echo "   ba exit=$?" >> "$LOG"

echo "== $(date) banc large test puis train (150 x 2)" >> "$LOG"
"$PY" train-gate2/08_bench.py --model "$GGUF" --set test  --n 150 -k 2 --tag M --label mdpo-test  > "$S/bench_M_test.log" 2>&1
echo "   test : $(grep -o 'pass@1[^,]*' "$S/bench_M_test.log" | tail -1)" >> "$LOG"
"$PY" train-gate2/08_bench.py --model "$GGUF" --set train --n 150 -k 2 --tag M --label mdpo-train > "$S/bench_M_train.log" 2>&1
echo "   train : $(grep -o 'pass@1[^,]*' "$S/bench_M_train.log" | tail -1)" >> "$LOG"
"$PY" "$S/compare_M.py" > "$S/compare_M_final.txt" 2>&1
echo "== $(date) CHAINE M TERMINEE : $(tail -1 "$S/compare_M_final.txt")" >> "$LOG"
