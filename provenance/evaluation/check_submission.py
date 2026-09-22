import hashlib, io, json, os, re, sys

ok, ko = [], []


def v(cond, message):
    (ok if cond else ko).append(message)


def main():
    d = json.load(io.open("metadata.json", encoding="utf-8"))

    n = len(d.get("test_prompts", []))
    v(n == 2, "exactement 2 test_prompts (%d trouves)" % n)

    chemin = d["_runtime"]["model_path"]
    v(os.path.exists(chemin), "le fichier %s existe" % chemin)

    sh = io.open("download_model.sh", encoding="utf-8").read()
    m = re.search(r'MODEL_URL="([^"]+)"', sh)
    url = m.group(1) if m else ""
    v("/resolve/" in url, "l'URL utilise /resolve/")
    v("/resolve/main/" not in url, "l'URL n'est PAS epinglee sur main")
    m = re.search(r"/resolve/([0-9a-f]{40})/", url)
    v(bool(m), "l'URL porte un identifiant de commit complet")

    m = re.search(r'MODEL_FILE="[^"]*/([^/"]+)"', sh)
    nom = m.group(1) if m else ""
    v(nom == os.path.basename(chemin),
      "le nom dans download_model.sh et _runtime.model_path concordent (%s)" % nom)
    v(url.endswith(nom), "l'URL se termine par ce meme nom de fichier")

    if os.path.exists(chemin):
        h = hashlib.sha256()
        with open(chemin, "rb") as f:
            while True:
                b = f.read(1 << 20)
                if not b:
                    break
                h.update(b)
        attendu = ""
        for l in io.open("provenance/checksums.txt", encoding="utf-8"):
            if l.strip().endswith(chemin):
                attendu = l.split()[0]
        v(attendu != "" and h.hexdigest() == attendu,
          "sha256 du fichier livre identique a la ligne de provenance/checksums.txt")
        taille = os.path.getsize(chemin) / 1e6
        v(True, "taille du fichier livre : %.1f Mo sur disque" % taille)

    mes = d["model"].get("measured_on_target_machine")
    if mes is None:
        v(True, "pas de bloc measured_on_target_machine dans metadata (les chiffres sont dans REPORT.md section 6)")
        rep = io.open("REPORT.md", encoding="utf-8").read()
        v("Which file these numbers come from" in rep,
          "REPORT.md section 6 dit explicitement sur quel fichier les chiffres ont ete mesures")
    else:
        for champ in ("tokens_per_second", "peak_rss_mb", "first_token_latency_ms"):
            v(isinstance(mes.get(champ), (int, float)),
              "%s renseigne depuis la machine cible" % champ)
        v(mes.get("model_measured", "").startswith(os.path.splitext(nom)[0][:20]) or nom in mes.get("model_measured", ""),
          "les chiffres de la machine cible portent bien sur le fichier livre")
    RACINE_OK = {"team_id", "domain", "language_scope", "african_alpha_claim", "budget_laptop_claim", "provenance",
                 "submitter", "cross_disciplinary_pairing", "test_prompts", "model"}
    MODELE_OK = {"name", "runtime", "quantization", "parameters_estimate", "packaging"}
    hors = sorted(k for k in d if not k.startswith("_") and k not in RACINE_OK)
    v(not hors, "aucune cle hors schema a la racine de metadata.json%s" % (" (%s)" % ", ".join(hors) if hors else ""))
    hors_m = sorted(k for k in d["model"] if k not in MODELE_OK)
    v(not hors_m, "aucune cle hors schema dans metadata.model%s" % (" (%s)" % ", ".join(hors_m) if hors_m else ""))
    v(RACINE_OK <= set(d), "toutes les cles obligatoires du schema sont presentes")

    prov = d.get("provenance", {})
    bsha = prov.get("base_model_commit_sha", "")
    v(re.fullmatch(r"[a-f0-9]{7,40}", bsha) is not None, "provenance.base_model_commit_sha rempli")
    tc = json.load(io.open("provenance/train_config.json", encoding="utf-8"))
    v(bsha == tc.get("revision"), "provenance.base_model_commit_sha identique a la revision de provenance/train_config.json")
    v(prov.get("fine_tuning_method") in {"none", "prompt_engineering", "lora", "qlora", "full_fine_tune"},
      "provenance.fine_tuning_method dans la liste du schema")
    v(prov.get("base_model_source", "").startswith("huggingface:"), "provenance.base_model_source renseigne")
    v(isinstance(prov.get("training_datasets"), list) and prov["training_datasets"] and all(isinstance(x, str) and x for x in prov["training_datasets"]),
      "provenance.training_datasets : liste de chaines non vides")

    texte = json.dumps(d, ensure_ascii=False)
    for marqueur in ("A_REMPLIR", "A REMPLIR", "TODO", "XXX", "[YOUR_", "your-team-id"):
        v(marqueur not in texte, "aucun marqueur %r dans metadata.json" % marqueur)

    for ligne in ok:
        print("  ok    " + ligne)
    for ligne in ko:
        print("  FAUX  " + ligne)
    print("\n%d controles passes, %d echoues" % (len(ok), len(ko)))
    return 1 if ko else 0


if __name__ == "__main__":
    sys.exit(main())
