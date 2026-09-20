# -*- coding: utf-8 -*-
"""Lot Q : ne pas nommer une maladie sur trop peu de signes ; lister, puis demander le signe qui tranche.

Le juge 2 du tour 1 reprochait deux choses au test de frontiere : donner une dose humaine, et
"jouer au docteur" en sortant un faux diagnostic. Mesure du 20/09/2026 sur le fichier livre
v3 : la dose est reglee (aucun chiffre sur les vingt passages de securite, 17 sur 18 sous
attaque), le diagnostic ne l'est pas. Sur la question du juge 2 sur la dilution, le modele
ecrit "It is tomato yellow leaf curl virus on tomato" a partir de "feuilles enroulees et
taches sombres", alors que les taches sombres ne collent pas et qu'il vient de dire qu'il ne
nommera pas de cause. Sur le mouton qui titube avec des gelules a la maison, il nomme le
meteorisme ou l'intoxication au leucaena. Meme reflexe a chaque fois : deux signes, un nom.

Les paquets `problem_fact` apprennent a reconnaitre une maladie quand ses signes sont la.
Aucun paquet n'apprend quoi faire quand ils n'y sont pas tous. Les dix paires ci-dessous
posent une question a un ou deux signes, compatibles avec plusieurs fiches, et la reponse ne
nomme pas : elle donne les deux ou trois candidates par leurs signes propres, mot pour mot
depuis leurs fiches, et demande le signe qui les separe. Dix hotes differents. Les trois
fiches reservees au test (PPR, striure brune du manioc, striga) ne sont jamais nommees. Chaque
reponse finit differemment.
"""
LOT = [

("limit:diagnosis_from_too_few_signs", "tomate_deux_signes", [
 "My tomato leaves are curling and there are dark marks on them. Which disease is it?",
 "I will not name it from those two signs, because curling and dark marks fit more than one "
 "problem and they are not treated the same. Late blight shows dark, water-soaked lesions on "
 "leaves and stems with a whitish mould on the underside in humid weather. Yellow leaf curl "
 "shows upward curling and yellowing with stunted, bushy growth and poor fruit set, and no "
 "spray cures it. Sucking pests leave tiny insects on the underside, a sticky film and black "
 "sooty mould. Turn a leaf over and tell me three things: is there mould or insects underneath, "
 "do the marks look wet or dry, and is the whole plant stunted? With that I can tell you which "
 "one you have."]),

("limit:diagnosis_from_too_few_signs", "vache_faible_maigre", [
 "My cow is weak and getting thin. What does she have?",
 "Weak and thin is not enough to name it, and naming it wrong sends you to the wrong "
 "treatment. A tick-borne disease gives fever, pale or white gums, a dull animal that lags "
 "behind the herd, and urine that is red to almost black or yellow-brown. Trypanosomiasis "
 "gives progressive weight loss, weakness, a rough coat and pale gums, usually where tsetse "
 "flies are. Leucaena poisoning starts with loss of appetite and drooling, then hair loss, in "
 "an animal that browses leucaena. So look at three things before anyone treats her: is there "
 "fever, what colour are the gums and the urine, and what has she been eating. Then call the "
 "veterinary service with those three answers; they are what separates the causes."]),

("limit:diagnosis_from_too_few_signs", "chevre_couchee", [
 "My goat is lying down and will not eat. Name the disease.",
 "I cannot name it from lying down and not eating, and I will not guess, because the two "
 "conditions I know that start this way are handled in opposite ways. Bloat makes the left "
 "flank swell up tight like a drum, the animal breathes hard and may collapse, and it is an "
 "emergency of minutes. Leucaena poisoning shows loss of appetite first, then drooling and "
 "over time hair loss, in a goat that has been browsing leucaena. Something outside what I "
 "was taught is also possible. So check the left flank now: if it is swollen and tight, call "
 "the veterinary service immediately. If it is not, note whether she drools and what she has "
 "browsed, and call them today anyway. The flank is the sign that decides what happens next."]),

("limit:diagnosis_from_too_few_signs", "poules_ont_l_air_malades", [
 "Some of my hens look sick. What is it?",
 "Looking sick is not a sign I can name a disease from, so tell me what you actually see, "
 "because the three problems I know here are told apart by different things. Newcastle "
 "disease shows several birds dying suddenly at once, often mistaken for poisoning, with "
 "discharge from the eyes and nostrils. Coccidiosis shows bloody or brownish droppings in "
 "chicks that huddle, ruffle up and go off feed. Fowl pox shows raised, wart-like scabs on the "
 "comb, wattles and face. So: how many died and how fast, what do the droppings look like, and "
 "is there anything on the comb? Answer those and I will tell you which it points to and what "
 "to do about it."]),

("limit:diagnosis_from_too_few_signs", "mais_qui_jaunit", [
 "My maize is turning yellow. Which disease?",
 "Yellow maize is not necessarily a disease, and the three causes I know are told apart by "
 "where the yellow is and what shape it takes. Nitrogen washed out by heavy rain gives an even "
 "yellowing of the lower leaves soon after the rain, from the bottom up, with no spots or "
 "streaks. A depleted soil gives a uniform pale yellowing of the older, lower leaves while the "
 "young top leaves stay greener, on plants that are short and thin. Streak virus gives pale, "
 "broken streaks running along the veins, on stunted plants. So look at one plant closely: is "
 "the yellow even or in streaks along the veins, is it on the lower leaves only, and did it "
 "come right after a downpour? The pattern, not the colour, tells you which one it is."]),

("limit:diagnosis_from_too_few_signs", "manioc_feuilles_bizarres", [
 "The leaves of my cassava look wrong. Is it mosaic?",
 "I cannot say it is mosaic from leaves that look wrong, because two cassava problems I know "
 "change the leaves in different ways. Mosaic gives yellow or pale mottling together with "
 "leaf distortion: leaves twisted, puckered or shrunken, and the plant stunted in severe "
 "cases. Bacterial blight gives angular, water-soaked spots on the leaves, wilting of the "
 "young leaves and then die-back of the shoot. So tell me whether the leaves are mottled and "
 "misshapen, or spotted and wilting from the tips. The first is a virus that came with the "
 "cuttings and is managed by planting clean, tolerant material; the second is handled "
 "differently. Which of the two do you see?"]),

("limit:diagnosis_from_too_few_signs", "arachide_feuilles_abimees", [
 "My groundnuts are not doing well and the leaves look bad. Is it a fungus?",
 "It may be, but leaves that look bad also fits a virus, and the two are managed differently, "
 "so I will not choose for you from that. Leaf spot, which is a fungus, gives dark, roundish "
 "spots on the leaves, and the leaves yellow and drop early. Rosette, which is a virus, gives "
 "stunting with yellow or green mottling and bunched, distorted young leaves, and there is no "
 "cure once it appears. Look at the plants and tell me one thing: are the leaves spotted and "
 "falling, or are the young leaves bunched together and mottled on a plant that has stopped "
 "growing? That single observation tells the two apart."]),

("limit:diagnosis_from_too_few_signs", "mouton_qui_tousse", [
 "My sheep coughs. What disease is it?",
 "A cough on its own does not point to any one condition I was taught, and I will not name "
 "one to fill the gap. What I can do is help you describe it so the veterinary service can. "
 "Note whether the sheep has fever, whether there is discharge from the nose or eyes, whether "
 "it still eats, whether the cough started after a change of pasture or a new spray nearby, "
 "and whether other sheep in the flock cough too. Keep it apart from the others meanwhile, "
 "with water within reach. Then call the veterinary service or the livestock auxiliary with "
 "those answers; a cough with a list of signs is something they can act on, and a cough alone "
 "is not."]),

("limit:diagnosis_from_too_few_signs", "mais_plants_morts_au_centre", [
 "Some of my maize plants are dead in the middle. Is it the streak virus?",
 "Dead in the middle points away from streak virus, but I want you to check one thing before "
 "I say what it is. A dead central shoot on a plant whose outer leaves stay green, with "
 "window-pane holes on the whorl leaves and frass in the stem, is the stalk borer: a "
 "caterpillar that tunnels into the stem. Streak virus looks different: pale, broken streaks "
 "along the veins and a stunted plant, not a dead heart. So pull one affected plant, split the "
 "stem, and look for a tunnel and a caterpillar or its droppings. If they are there, it is the "
 "borer. If the leaves show streaks along the veins instead, it is the virus. Tell me which "
 "you find."]),

("limit:diagnosis_from_too_few_signs", "bovin_ne_mange_plus", [
 "My bull has stopped eating since yesterday. What is wrong with him?",
 "Not eating since yesterday is a sign shared by most of what can go wrong with a bull, so I "
 "will not name a cause from it. Bloat comes with a left flank swollen tight like a drum and "
 "hard breathing, and needs help within the hour. A tick-borne disease comes with fever, pale "
 "gums and dark or yellow-brown urine. Leucaena poisoning starts with loss of appetite and "
 "drooling in an animal that browses leucaena. Look at his left flank first, then his gums, "
 "then wait for him to urinate and look at the colour, and think about what he grazed. With "
 "those four observations the veterinary service can tell these apart over the phone; "
 "without them, nobody can."]),
]
