#!/usr/bin/env bash
# Constate la configuration de la machine de mesure et la confronte a ce que le reglement
# ADTC 2026 exige. Ne mesure rien, ne telecharge rien, ne modifie rien.
#
# A lancer sur la REPLIQUE de la machine cible, pas sur le poste de developpement :
#   bash check_target_env.sh /chemin/vers/le-depot-de-soumission
#
# Profil vise, section 2.2 du reglement : 8 Go de RAM, 4 vCPU Intel i5 10e a 12e generation,
# graphique integre seulement, aucune dependance reseau pendant l'evaluation.

set -uo pipefail
DEPOT="${1:-.}"
ok=0; ko=0
dire()  { printf '%-46s %s\n' "$1" "$2"; }
vert()  { dire "$1" "OK    $2"; ok=$((ok+1)); }
rouge() { dire "$1" "A VOIR  $2"; ko=$((ko+1)); }

echo "================ MACHINE ================"
if [ -r /proc/cpuinfo ]; then
  dire "processeur" "$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ *//')"
  NPROC=$(nproc)
  dire "vCPU" "$NPROC"
  [ "$NPROC" -le 4 ] && vert "vCPU <= 4" "$NPROC" || rouge "vCPU <= 4" "$NPROC, la cible en a 4"
  MEMKB=$(awk '/MemTotal/{print $2}' /proc/meminfo)
  MEMGB=$(awk -v k="$MEMKB" 'BEGIN{printf "%.1f", k/1048576}')
  dire "memoire totale" "${MEMGB} Go"
  awk -v g="$MEMGB" 'BEGIN{exit !(g<=8.5)}' && vert "RAM <= 8 Go" "${MEMGB}" || rouge "RAM <= 8 Go" "${MEMGB}"
else
  rouge "/proc/cpuinfo" "illisible, ce script vise Linux"
fi
dire "systeme" "$(uname -srm)"

echo
echo "============ JEU D'INSTRUCTIONS ============"
# La build d'audit des organisateurs desactive AVX/AVX2/FMA/F16C. Si la build locale les
# active, le debit mesure ici sera plus haut que le leur, et l'ecart tombera sous la regle 3.4.
for f in avx avx2 fma f16c avx512f; do
  if grep -qm1 " $f" /proc/cpuinfo 2>/dev/null; then
    dire "  $f present sur le processeur" "oui"
  fi
done

echo
echo "============== OUTILS REQUIS =============="
if command -v llama-bench >/dev/null 2>&1; then
  vert "llama-bench sur le PATH" "$(command -v llama-bench)"
  llama-bench --version 2>&1 | head -2 | sed 's/^/    /'
else
  rouge "llama-bench sur le PATH" "absent, le profileur en depend"
fi
if command -v adtc-profiler >/dev/null 2>&1; then
  vert "adtc-profiler installe" "$(command -v adtc-profiler)"
  adtc-profiler --version 2>&1 | head -1 | sed 's/^/    /'
else
  rouge "adtc-profiler installe" "pip install git+https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler.git"
fi
command -v python3 >/dev/null 2>&1 && dire "python3" "$(python3 -V 2>&1)"

echo
echo "========== DOSSIER DE SOUMISSION =========="
for f in metadata.json download_model.sh REPORT.md .gitignore; do
  [ -f "$DEPOT/$f" ] && vert "$f present" "" || rouge "$f present" "manquant"
done
[ -d "$DEPOT/model" ] && vert "model/ present" "" || rouge "model/ present" "manquant"

if [ -f "$DEPOT/.gitignore" ]; then
  grep -qE '\*\.gguf|model/' "$DEPOT/.gitignore" \
    && vert ".gitignore exclut les poids" "" \
    || rouge ".gitignore exclut les poids" "ajouter *.gguf"
fi

if [ -f "$DEPOT/download_model.sh" ]; then
  URL=$(grep -m1 '^MODEL_URL=' "$DEPOT/download_model.sh" | cut -d'"' -f2)
  dire "MODEL_URL" "${URL:0:78}"
  case "$URL" in
    *'$'*|*'`'*|*'${'*) rouge "URL statique" "elle contient une substitution, interdit par 3.2" ;;
    *) vert "URL statique" "lisible sans executer" ;;
  esac
  case "$URL" in
    */resolve/main/*|*/main/*|*latest*) rouge "URL epinglee" "elle pointe sur une branche mouvante" ;;
    *) vert "URL epinglee" "commit fige" ;;
  esac
  PATH_META=$(python3 -c "import json;print(json.load(open('$DEPOT/metadata.json'))['_runtime']['model_path'])" 2>/dev/null)
  FILE_SH=$(grep -m1 '^MODEL_FILE=' "$DEPOT/download_model.sh" | sed 's/.*\///; s/"$//')
  if [ -n "$PATH_META" ] && [ "model/$FILE_SH" = "$PATH_META" ]; then
    vert "chemin du script = _runtime.model_path" "$PATH_META"
  else
    rouge "chemin du script = _runtime.model_path" "script:model/$FILE_SH  metadata:$PATH_META"
  fi
fi

if [ -f "$DEPOT/metadata.json" ] && command -v python3 >/dev/null 2>&1; then
  python3 - "$DEPOT/metadata.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
n = len(d.get("test_prompts", []))
print("%-46s %s" % ("test_prompts", "OK    exactement 2" if n == 2 else "A VOIR  %d au lieu de 2" % n))
for k in ("team_id", "domain", "budget_laptop_claim"):
    print("%-46s %s" % (k, d.get(k)))
print("%-46s %s" % ("model.runtime", d.get("model", {}).get("runtime")))
print("%-46s %s" % ("model.quantization", d.get("model", {}).get("quantization")))
print("%-46s %s" % ("model.parameters_estimate", d.get("model", {}).get("parameters_estimate")))
sha = d.get("reproducibility", {}).get("git_commit_sha", "")
print("%-46s %s" % ("git_commit_sha", "OK    " + sha[:12] if sha and "REMPLIR" not in sha else "A VOIR  non rempli"))
restants = [k for k, v in d.items() if isinstance(v, str) and ("your-" in v or "YOUR_" in v)]
print("%-46s %s" % ("marqueurs du modele restants", restants or "aucun"))
PY
fi

echo
echo "================ THERMIQUE ================"
if ls /sys/class/thermal/thermal_zone*/temp >/dev/null 2>&1; then
  for z in /sys/class/thermal/thermal_zone*/temp; do
    t=$(awk -v v="$(cat "$z")" 'BEGIN{printf "%.1f", v/1000}')
    dire "  $(dirname "$z" | xargs basename)" "${t} C"
  done
  echo "    Penalite de 10 points au-dela de 85 C ou en cas de bridage."
else
  dire "capteurs thermiques" "aucun lisible"
fi

echo
echo "=================== BILAN ==================="
echo "points conformes : $ok   points a verifier : $ko"
[ "$ko" -eq 0 ] || echo "Regler les points ci-dessus avant de lancer le profileur."
