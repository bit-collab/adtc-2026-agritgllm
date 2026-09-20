# Procedure de la mesure finale sur la replique

A suivre dans cet ordre, sur la machine repliquant le profil d'evaluation, une fois le modele
definitif en place. Chaque etape existe parce qu'une mesure precedente a rate quelque chose.

## 1. Cloner le depot de soumission sur la replique, et travailler dedans

Les trois passages du 19 septembre 2026 ont tous ecrit :

    "git_commit_sha": "000000000000"

et leur journal porte la ligne `fatal: not a git repository (or any of the parent directories)`.
Le profileur cherche le commit dans le repertoire courant ; il n'en trouve pas parce qu'il a ete
lance depuis un dossier qui n'est pas un clone. Le champ n'est donc pas casse, il est vide parce
qu'on ne lui a rien donne a lire. Lancer le profileur depuis l'interieur du clone le remplit
tout seul, et c'est ce champ qui relie le chiffre publie au code publie.

    git clone https://github.com/bit-collab/adtc-2026-agritgllm
    cd adtc-2026-agritgllm
    git rev-parse HEAD        # a comparer ensuite avec le champ du JSON produit

## 2. Telecharger le modele par le script livre, pas a la main

    sh download_model.sh

C'est le chemin que l'evaluateur empruntera. S'il echoue chez nous, il echouera chez lui. Le
script verifie l'empreinte ; si elle ne correspond pas, ne pas continuer et reprendre l'envoi
sur Hugging Face.

## 3. Chercher la configuration qui efface le drapeau thermique

    sh provenance/evaluation/thermal_sweep.sh model/<le fichier>.gguf

Ce que la mesure du 19 septembre a etabli, et qui rend ce balayage interessant : sur les trois
passages, le debit va de 14,91 a 15,64 tok/s, donc le plein score de performance est deja
atteint, tandis que le pic de coeur monte a 98, 99 et 100 degres et que les trois JSON portent
`"throttled": true`. Le releve `thermo-20260919-160921.csv`, 365 points sur 1834 secondes,
montre que pendant les phases chaudes le processeur tient 3700 a 3900 MHz : il ne s'effondre
pas, il travaille a sa limite de puissance. Il reste donc de la frequence a rendre.

L'echange est tres favorable. La penalite thermique retire dix points pleins ; la performance ne
pese que 0,30 dans le total et elle est deja au maximum a 15,0 tok/s. Une configuration qui
descend a 12 tok/s en effacant le drapeau gagne environ six points nets. Le point mort se situe
vers 10 tok/s.

## 4. Relancer le profileur dans la configuration retenue

C'est le champ `throttled` qui est lu, pas la temperature seule. Un pic sous 85 degres qui
laisserait quand meme `throttled: true` ne servirait a rien, et l'inverse non plus. Il faut donc
verifier sur la sortie du profileur lui-meme, pas sur le balayage.

Faire au moins deux passages : un a froid, machine au repos depuis plusieurs minutes, et un
enchaine juste apres. Les deux vont dans `provenance/evaluation/target_machine/`. Le rapport
cite le passage a froid et donne l'ecart, parce que c'est la condition dans laquelle un audit
commence et que cacher l'ecart serait malhonnete.

## 5. Reporter les chiffres et verifier le dossier

Copier le JSON du profileur dans `provenance/evaluation/target_machine/` et reporter ses valeurs
dans la section 6 de `REPORT.md`, en remplacant le paragraphe qui dit que les chiffres viennent
du fichier precedent. Rien dans `metadata.json` : le schema officiel n'a pas de bloc pour ces
mesures, et le `submission.json` lui-meme est exclu par le `.gitignore` du gabarit, donc il ne se
commite pas. Puis, depuis la racine du dossier :

    python provenance/evaluation/check_submission.py

Tous les controles doivent etre verts. Le commit du depot n'est ecrit nulle part a la main :
le schema du profileur l'interdit et le capture lui-meme depuis `git rev-parse HEAD` quand il
tourne dans le clone. Le seul commit dans `metadata.json` est `model.base_model_commit_sha`,
celui du modele de base.

## Question restee ouverte, a poser aux organisateurs

La penalite thermique est-elle lue dans le `submission.json` que nous fournissons, ou dans leur
propre passage d'audit sur leur machine ? La reponse change tout. Si c'est le notre, brider la
replique suffit. Si c'est le leur, le bridage doit voyager avec le modele, donc figurer dans la
commande de lancement documentee et pas seulement dans nos reglages locaux.
