# Ce que chaque banc mesure, et ce qu'il ne mesure pas

Ecrit le 19 septembre 2026, avant la remise du tour 2. Ce document existe parce qu'une mesure
sans son domaine de validite est une decoration. Trois choses y sont dites, dont deux sont a
notre desavantage.

## 1. Le banc des 27 questions recouvre largement l'entrainement

Le fichier `acceptance_27_round1.jsonl` a ete bati a partir du rapport de jugement du tour 1 :
un item par defaut signale par les juges, avec la reponse d'alors et le critere de reussite.
C'est un bon instrument de reparation. Ce n'en est pas un de generalisation, et le chiffre le
montre.

Chacune des 27 questions a ete comparee aux 7 587 questions du jeu d'entrainement, par
similarite de Jaccard sur les mots de trois lettres et plus, en gardant le maximum. Resultat
dans `battery_overlap_with_training.json` :

| | items |
|---|---|
| identiques a une question d'entrainement (similarite superieure a 0,95) | 19 |
| inedites | 8 |

Les huit inedites sont `keep_whitefly_not_aphid_discriminative`, `meta_architecture_hybrid`,
`dom_newcastle_sudden_deaths`, `dom_cassava_mosaic`, `dom_maize_streak`,
`dom_groundnut_rosette`, `limit_market_price_live`, `limit_weather_forecast`.

Consequence chiffree, mesuree sur quatre modeles et quatre tirages chacun : le score global
tourne autour de 21 sur 27, soit environ 78 %, et le score restreint aux huit inedites tombe
entre 19 et 22 sur 32, soit environ 65 %. C'est ce second chiffre qui decrit ce qu'un jury
rencontrera, puisqu'un jury ne pose pas les questions du corpus.

Le recouvrement n'est pas un artifice monte apres coup : les paquets d'entrainement ont ete
ecrits pour reparer ce que les juges avaient trouve, et le banc a ete ecrit a partir de la
meme source. Mais noter la reparation sur la question qui a servi a l'ecrire est circulaire,
et il vaut mieux le dire que le laisser trouver.

## 2. Un second banc, tenu hors de l'entrainement

`acceptance_27_heldout.jsonl` reprend les 27 memes defauts avec d'autres situations et un autre
vocabulaire. La meme mesure de similarite donnait un maximum de 0,55 contre l'entrainement au moment
ou le banc a ete construit, c'est-a-dire aucune question identique ni proche.

Correction du 20/09/2026, mesuree et non supposee : les lots L et M, ecrits le 19/09 apres la
construction du banc, ont introduit dans l'entrainement quatre questions identiques mot pour
mot a quatre items de ce banc (keep_off_topic_refusal_v2, greet_bonjour_french_v2,
fix_meta_no_camera_v2, dom_newcastle_sudden_deaths_v2). Le fichier livre v3 les a lues. Sur
ces quatre items il ne reussissait que 2 passages sur 16, donc la contamination n'a presque
rien gonfle ; mais le chiffre honnete de v3 sur ce banc est 15,75 sur les 23 items propres, et
16,25 sur 27. Les quatre lignes ont ete retirees de l'entrainement pour la chaine suivante, et
le controle de similarite est desormais passe sur les 78 prompts de mesure avant chaque split.

Les questions de ce fichier ont ete ecrites le 19/09/2026 pour ce banc, pas reprises du
rapport des juges, et cela est inscrit dans chaque ligne. Les criteres de reussite sont ceux du fichier d'origine, a trois
exceptions signalees dans l'en-tete de `make_heldout_battery.py` : les deux items de striure et
de rosette, dont la reponse attendue a change avec l'arbitrage decrit plus bas, et les items de
verdict, ou la tournure a la premiere personne a ete ajoutee a la liste acceptee.

Cette derniere correction vient d'une lecture ligne a ligne. Sur douze passages de
`keep_kara_verdict_full_context`, sept echouaient parce que le bareme attend la chaine
`do not buy` et que le modele ecrit `I will not buy the merchant's package`. C'est le meme
verdict. Le bareme d'origine n'a pas ete modifie, il est livre tel qu'il a ete recu ; la
correction ne vit que dans le second banc, et elle est signalee ici.

## 3. La troisieme mesure, la seule qui n'ait jamais rien vu

`sft_test` tient des fiches entieres, jamais presentes dans l'entrainement sous aucune forme.
Au 19 septembre 2026 il en reste trois : `cassava_brown_streak`, `small_ruminant_ppr`,
`sorghum_striga`. S'y ajoute un sujet de comportement reserve, `mixing_chemicals`.

Elles etaient cinq jusqu'a ce jour. `maize_streak_virus` et `groundnut_rosette` ont ete rendues
a l'entrainement, et voici pourquoi, parce que la decision est discutable et doit etre lisible.

Ce qui a ete mesure d'abord. Devant les symptomes de ces deux maladies, quatre chaines de
modeles et seize passages au total n'ont jamais produit un aveu d'ignorance. Le modele prend la
fiche voisine de la meme culture et la deroule entiere, gestion et dose comprises : la recette
de neem du foreur de tige posee sur la striure, la cercosporiose posee sur la rosette. Zero
reussite sur seize, avant et apres l'ajout de douze paires d'abstention sur des cultures
inconnues.

La question n'etait donc plus de savoir si le comportement se generalise jusqu'a une fiche
entierement absente. La reponse est non, elle est mesuree, et elle est ecrite ici. Restait a
choisir ce que le modele repond a un jury. La striure du mais et la rosette de l'arachide
comptent parmi les maladies les plus repandues sur ces deux cultures au Togo ; un conseiller
agricole qui ne sait pas les nommer est deficient sur son propre terrain. Elles entrent.

Le comportement de non-reconnaissance continue d'etre appris, mais sur des cas qui n'ont de
fiche nulle part : charbon du mais, chenille coupant les plantules a ras, moisissure sur la
panicule, pourriture du collet de l'arachide, necrose apicale de la tomate, pourriture molle du
piment, pourriture seche de l'igname, pustules sur le soja, et une adventice inconnue. Vingt et
une paires au total, ecrites a la main.

## Ce qu'il faut lire dans le rapport

Trois chiffres, jamais un seul :

1. le banc du tour 1, qui dit si les defauts signales par les juges sont corriges ;
2. le banc hors entrainement, qui dit si la correction tient sur d'autres mots ;
3. `sft_test`, qui dit ce que le modele fait d'une matiere qu'il n'a jamais lue.

Le premier est le plus flatteur des trois. C'est la raison pour laquelle il ne sera jamais cite
seul.
