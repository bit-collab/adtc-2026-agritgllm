#!/bin/sh

set -eu

MODELE="${1:?donner le chemin du .gguf}"
SORTIE="${2:-thermal_sweep.csv}"
FILS="${FILS:-8 6 4 3 2}"
REPOS="${REPOS:-120}"   # secondes de refroidissement entre deux essais

BENCH="$(command -v llama-bench || echo /usr/local/bin/llama-bench)"
[ -x "$BENCH" ] || { echo "llama-bench introuvable, donner son chemin dans \$BENCH"; exit 1; }

ZONE=""
for z in /sys/class/thermal/thermal_zone*; do
    [ -r "$z/type" ] || continue
    case "$(cat "$z/type")" in
        x86_pkg_temp|coretemp*) ZONE="$z/temp"; break ;;
    esac
    [ -n "$ZONE" ] || ZONE="$z/temp"
done
[ -r "$ZONE" ] || { echo "aucune zone thermique lisible sous /sys/class/thermal"; exit 1; }
echo "capteur : $ZONE"

echo "fils,tok_par_s,temp_pic_c,temp_moy_c,mhz_moy" > "$SORTIE"

for t in $FILS; do
    echo "--- refroidissement ${REPOS}s avant l'essai a $t fils ---"
    sleep "$REPOS"

    TMP="$(mktemp)"
    ( while :; do
        printf '%s %s\n' "$(cat "$ZONE")" \
          "$(awk '/cpu MHz/ {s+=$4; n++} END {if (n) printf "%.0f", s/n; else print 0}' /proc/cpuinfo)"
        sleep 1
      done ) > "$TMP" &
    ECH=$!

    TPS="$("$BENCH" -m "$MODELE" -t "$t" -ngl 0 -p 0 -n 128 -r 3 -o csv 2>/dev/null \
           | awk -F, '$0 ~ /tg/ {gsub(/"/,"",$NF); v=$NF} END {printf "%.2f", v}')"

    kill "$ECH" 2>/dev/null || true
    wait "$ECH" 2>/dev/null || true

    PIC="$(awk '{if ($1 > m) m = $1} END {printf "%.1f", m/1000}' "$TMP")"
    MOY="$(awk '{s += $1; n++} END {if (n) printf "%.1f", s/n/1000; else print 0}' "$TMP")"
    MHZ="$(awk '{s += $2; n++} END {if (n) printf "%.0f", s/n; else print 0}' "$TMP")"
    rm -f "$TMP"

    printf '%s,%s,%s,%s,%s\n' "$t" "$TPS" "$PIC" "$MOY" "$MHZ" | tee -a "$SORTIE"
done

echo
echo "resultats dans $SORTIE"
echo
awk -F, 'NR > 1 {
    verdict = ($3 < 85.0) ? "SOUS 85 C" : "encore trop chaud"
    score   = ($2 >= 15.0) ? "debit plein" : sprintf("debit a %.0f %% du plein", $2 / 15.0 * 100)
    printf "  %s fils : %s tok/s, pic %s C  ->  %s, %s\n", $1, $2, $3, verdict, score
}' "$SORTIE"
echo
echo "Si une ligne passe sous 85 C en restant au-dessus de 10 tok/s, c'est celle-la qu'il faut,"
echo "et il faut ensuite relancer adtc-profiler dans cette configuration pour verifier que le"
echo "champ throttled passe a false. C'est ce champ qui est lu, pas la temperature seule."
