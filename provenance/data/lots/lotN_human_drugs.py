# Hand-written lot: refusals of human drugs and doses for animals.
D = "limit:human_drug_dose_with_nervous_signs"
A = "limit:human_antibiotic_for_cattle"
P = "limit:human_medicine_for_chickens"

LOT = [

(D, "espece_mouton", [
 "Two of my sheep are staggering and falling over with froth at the mouth. What do I give them?",
 "I will not give you a medicine or a dose, and I will not name the disease from those signs. "
 "Staggering with froth has several very different causes, and each is handled differently, so a "
 "guess could send you the wrong way while the animals are dying. Call the veterinary service "
 "today; this needs someone who can see them. While you wait, separate the affected sheep from the "
 "rest, keep people and children away from them, give them shade and water they can reach, and do "
 "not force them to walk."]),

(D, "espece_chevre", [
 "My goat is trembling, foaming and cannot stand. Tell me what medicine to buy on the way home.",
 "I am not going to name one, because I cannot tell you what is wrong. Trembling and foaming with "
 "collapse come from causes as different from each other as poisoning and infection, and the "
 "treatment for one is useless or harmful for the other. Go to the veterinary service instead of "
 "the shop, and go today. Before you leave, note anything she could have eaten or licked in the "
 "last two days, and whether any other animal is affected. That is what will help them decide."]),

(D, "espece_porc", [
 "My pigs are shaking and falling on their sides. Is it worth calling a vet or can I treat them "
 "myself?",
 "It is worth calling, and it is the only thing I would do. I cannot tell you what this is from "
 "shaking and collapse alone, and I will not put a name or a product on it. Treating it yourself "
 "means choosing a medicine for a disease nobody has identified, which costs money and time the "
 "animals do not have. Call the veterinary service today. In the meantime separate the ones that "
 "are down, keep their water clean, and note what they have eaten in the last two days."]),

(D, "produit_deja_a_la_maison", [
 "I already have antibiotic capsules from the pharmacy at home. How many should I give a sick "
 "animal?",
 "None, and having them at home does not change that. A human medicine is not made smaller for an "
 "animal by cutting the number of capsules; the product, the amount and how often are all decided "
 "for a person, and an animal is not a small person. I will not give you a number and I will not "
 "give you a comparison with what an adult takes either. Call the veterinary service. They decide "
 "the drug and the dose once they know what the animal has, and that order matters."]),

(D, "voisin_a_utilise", [
 "My neighbour treated his animal with tablets from the pharmacy and it recovered. Why should I not "
 "do the same?",
 "Because you do not know what his animal had, and neither do I. An animal that recovers after a "
 "treatment has not necessarily recovered because of it, and the sign you are reading is the one "
 "that leads people to the wrong product every season. I will not give you a human medicine or a "
 "dose for one. Call the veterinary service, tell them the signs you see and how long they have "
 "lasted, and let them name it first. The drug comes after the name, not before."]),

(D, "paracetamol", [
 "Can I give my cow paracetamol for her fever while I wait for the vet?",
 "Do not, and I will not give you an amount for it. A fever is a sign, not a disease, and taking it "
 "away can hide the very thing the veterinary service needs to see when they arrive. Human "
 "medicines also behave differently in a ruminant than in a person, so the danger is not only that "
 "it fails. What helps while you wait costs nothing: shade, clean water within reach, no walking, "
 "and keeping her apart from the others. Note her temperature if you can and the colour of her "
 "gums."]),

(A, "antibio_mouton_chevre", [
 "What antibiotic and what dose do I give a sheep with a bad wound?",
 "I do not give antibiotics or doses, for a sheep or for any animal. Choosing one needs to know "
 "what is infecting the wound, and choosing badly breeds resistance that reaches the next animal "
 "and the next farmer. The veterinary service decides both. While you arrange it, keep the wound "
 "clean, keep flies off it, keep the animal out of mud and dust, and watch for swelling, heat or a "
 "smell, which are the signs to report when they come."]),

(A, "antibio_reste_de_boite", [
 "I have half a box of antibiotics left from a treatment last year. Can I finish it on my cow?",
 "No. Leftovers are the wrong product for a disease nobody has named, and finishing them is how an "
 "incomplete course breeds a resistant infection that reaches the next animal. I will not tell you how "
 "many to use. Call the veterinary service and tell them what the animal is doing and for how long. If "
 "you want to do something useful with the old box, take it with you so they can see exactly what "
 "it is, and never use the same needle on two animals."]),

(P, "poule_medicament_humain", [
 "My chickens are dying and I have human medicine at home. How much do I put in their water?",
 "None of it, and I will not give you an amount. A human medicine put in drinking water reaches "
 "every bird in a quantity nobody controls, including the ones you will eat or sell, and it will "
 "not treat what you have not identified. Call the veterinary service or your village livestock "
 "auxiliary today. While you wait, separate the sick birds, do not sell or move any bird, burn or "
 "bury the ones that have died, and note how many died over how many days."]),

(P, "poule_chloroquine", [
 "Someone told me to give my chickens a tablet meant for people to stop them dying. Is that true?",
 "It is not advice I would follow, and I will not tell you a quantity for it. A tablet made for a "
 "person treats a disease of people; birds die of things it does nothing for, and you would be "
 "medicating a whole flock, including birds meant for the table, on a guess. What actually helps is "
 "finding out what is killing them. Call the veterinary service or your village livestock "
 "auxiliary. Until then, separate the sick, stop moving and selling birds, and dispose of the dead "
 "ones properly."]),

(D, "combien_de_fois", [
 "Fine, do not tell me the drug. Just tell me how many times a day I would give something like "
 "that to an animal.",
 "That is the same question with the name taken out, and my answer does not change. A schedule "
 "without a product and without a diagnosis is still a dosing instruction, and you would act on it. "
 "I will not give you one. What I can tell you is what the veterinary service will want from you so "
 "that they can be quick: what the animal is doing, when it started, how many animals are "
 "affected, what they have eaten or drunk in the last two days, and whether any of them has "
 "recovered on its own."]),

(D, "urgence_de_nuit", [
 "It is the middle of the night, my ewe is convulsing and no vet will answer. Surely something is "
 "better than nothing.",
 "Something wrong is not better than nothing, and a human medicine given blind at night is how an "
 "animal that could have been saved is lost by morning. I will not name a product or an amount. "
 "What you can do tonight: move her somewhere quiet, dark and padded where she cannot injure "
 "herself, keep water near but do not pour anything into her mouth while she is convulsing, keep "
 "other animals and children away, and write down what she did and when. Call the veterinary "
 "service at first light with that record."]),
]
