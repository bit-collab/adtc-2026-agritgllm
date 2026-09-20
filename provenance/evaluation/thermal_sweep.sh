#!/bin/sh
# Cherche une configuration qui garde le pic de temperature sous 85 C sans perdre le score
# de debit. A lancer SUR LA REPLIQUE, pas sur la machine de developpement.
#
# Pourquoi ce balayage.
#   Trois passages d'adtc-profiler sur la replique, le 19/09/2026, avec le meme fichier :
#   15,64 tok/s a froid, puis 15,27 et 14,91 une fois la machine chaude. Les trois ecrivent
#   "throttled": true et un pic de coeur entre 98 et 100 C. Le debit n'est donc pas le
#   probleme : 15,0 tok/s suffisent deja pour le plein score de performance, et nous sommes
#   au-dessus. Le probleme est la chaleur, et elle coute dix points.
#
#   Le releve thermique du 19/09 (thermo-20260919-160921.csv, 365 points sur 1834 s) montre
#   autre chose d'utile : pendant les phases chaudes le processeur tient 3700 a 3900 MHz. Il
#   ne s'effondre pas, il travaille a sa limite de puissance. Il y a donc de la frequence a
#   rendre, et c'est exactement ce qu'on veut echanger.
#
#   Le calcul de l'echange, avec la ponderation du concours : la penalite thermique vaut dix
#   points pleins, la performance ne pese que 0,30. Perdre du debit ne coute 10 points qu'en
#   tombant vers 10 tok/s. Toute configuration qui reste au-dessus de 10 tok/s en effacant le
#   drapeau est gagnante, et au-dessus de 15,0 elle est gratuite.
#
# Ce que le script fait : pour chaque nombre de fils, un llama-bench de generation, avec la
# temperature echantillonnee en parallele. Il n'ecrit que son propre fichier de resultats.
#
# Usage : sh thermal_sweep.sh /chemin/vers/le/modele.gguf [fichier_de_sortie.csv]

set -eu

MODELE="${1:?donner le chemin du .gguf}"
SORTIE="${2:-thermal_sweep.csv}"
FILS="${FILS:-8 6 4 3 2}"
REPOS="${REPOS:-120}"   # secondes de refroidissement entre deux essais

BENCH="$(command -v llama-bench || echo /usr/local/bin/llama-bench)"
[ -x "$BENCH" ] || { echo "llama-bench introuvable, donner son chemin dans \$BENCH"; exit 1; }

# capteur : on prefere la temperature de paquet, sinon la premiere zone disponible
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

    # -n 128 jetons generes, -p 0 : on mesure la generation, pas la lecture du prompt
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
