# Les reparations ecrites a la main, et la mesure qui a decide chacune

Regle 3.1 et regle 3.3. Ce document existe pour qu'on puisse verifier que chaque paire ajoutee
au corpus repond a un defaut mesure, et non a une intuition ou au desir de faire monter un
score. Chaque lot porte en tete, dans son propre fichier, la mesure qui l'a declenche, avec la
reponse fautive citee mot pour mot.

## Le compte

| | paires |
|---|---:|
| ecrites a la main sur fiche, verifiees par le lint du pipeline contre leur fiche | 1 303 |
| ecrites a la main dans les familles de comportement, sans fiche a verifier | 197 |
| **total ecrit a la main** | **1 500** |

Les 197 paires de comportement sont celles qui demandent le plus d'attention, parce que le
Checker du pipeline ne peut presque rien y verifier : elles n'ont pas de fiche contre laquelle
confronter un chiffre ou un nom propre. Le garde-fou pour celles-la est dans `append_gold.py`,
et il est plus severe sur un point : une reponse de la famille `limit:` ne doit porter aucun
chiffre de dose, de ratio ni de concentration, meme sous forme derivee. Il a refuse des lots
entiers, y compris des phrases ecrites par l'assistant : le lot N a ete rejete sur
`half box is the wrong product, in the wrong amount`, un faux positif. La phrase a ete
reformulee, la regle n'a pas ete touchee. Affaiblir un controle de securite pour laisser passer
son propre texte est la facon dont une fuite finit par passer.

## Ce que chaque lot repare, et ce qui l'a declenche

| lot | paires | defaut mesure | ou la mesure est consignee |
|---|---:|---|---|
| A | 15 | le refus de ratio de dilution suivi d'une consigne de dosage derivee | rapport des juges, tour 1 |
| B | 13 | la posologie humaine et le diagnostic invente sur signes nerveux | rapport des juges, tour 1 |
| C | 16 | l'institution inventee, CATREF, dans un refus hors sujet | rapport des juges, tour 1 |
| D | 12 | le calendrier du sud donne pour celui du nord | banc du tour 1 |
| E | 24 | le verdict qui se derobe quand le contexte est long | banc du tour 1 |
| F | 29 | le poste de depense pris pour le total, la taille du noyau pour un ratio | banc du tour 1 |
| G | 16 | les etapes du compost dans le desordre | banc du tour 1 |
| H | 16 | l'architecture recitee puis deraillee, et les signes nerveux nommes | banc du tour 1 |
| I | 12 | dire je ne sais pas en theorie, jamais en situation | banc du tour 1, 16 passages a zero |
| J | 8 | le verdict long qui lache une dose apres avoir dit de ne pas la prendre | banc du tour 1, 12 passages relus un par un |
| K | 9 | culture connue, probleme absent de toute fiche : la fiche voisine deroulee | banc du tour 1, 16 passages a zero |
| L | 17 | une regle de football inventee, le francais qui ne repart pas en anglais | banc hors entrainement |
| M | 10 | le meteorisme plaque sur une maladie a tiques, avec la conduite inverse | banc hors entrainement, 2 passages sur 2 |
| N | 12 | la dose d'amoxicilline humaine donnee a un mouton | banc hors entrainement, 4 passages sur 4 |

## La regle que ces lots ont fini par etablir

Les lots I a N ont tous ete ecrits le meme jour, apres une serie de mesures qui pointaient dans
la meme direction. Elle vaut d'etre enoncee, parce qu'elle contredit ce que la construction du
corpus supposait.

Le corpus multiplie chaque fait par seize portes : direct, telegraphique, situation,
discriminative, vrai ou faux, choix, justification, scientifique, multitour, limite honnete,
echelle, exposition, avant l'action, description, symptome alternatif, insistance. Ces seize
portes font varier la FORME de la question. Aucune ne fait varier son SUJET.

Mesures qui l'etablissent :

- `limit:off_topic_general_knowledge` porte 35 lignes et vingt angles, la couverture la plus
  complete du corpus. Ses 35 questions portent sur deux sujets, la capitale de la France et
  l'ecriture d'un poeme. Devant une question de football le modele invente une regle de football.
- `limit:human_drug_dose_with_nervous_signs`, `limit:human_antibiotic_for_cattle` et
  `limit:human_medicine_for_chickens` portent 51 lignes ensemble, bien angulees. Toutes leurs
  questions parlent de bovins, sauf le troisieme qui parle de poulets. A un mouton, le modele
  donne la dose d'un adulte humain.
- `verdict:tick_borne_cattle_decisive` porte 19 lignes et la serie complete des seize portes.
  Sa formulation d'entrainement passe quatre fois sur quatre. Une presentation qui met
  "ne se leve pas" en tete au lieu de "faible et fievreux" echoue deux fois sur deux, et le
  modele repond alors la conduite du meteorisme, qui est l'inverse de ce qu'il faut faire.
- `identity:no_camera_no_image` porte 22 lignes qui posent toutes la meme question technique sur
  une lecture spectrale depuis un telephone. A "can I send you a photo", le modele repond "Yes".
- `greeting:bonjour_french` porte 8 lignes dont cinq sont en anglais. Le comportement francais
  repose sur trois lignes, ce que la loi d'exposition situe a 0,25 de reussite. C'est ce qu'on
  mesure.

La profondeur d'un paquet achete la question. La largeur de sujet achete le comportement. Les
lots I a N ajoutent de la largeur de sujet et presque aucun angle nouveau.
