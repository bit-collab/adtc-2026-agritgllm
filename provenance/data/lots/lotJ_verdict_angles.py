# Hand-written lot: the fertiliser verdict questions asked from several angles.
F = "verdict:verdict_depleted_soil_full_context"
T = "verdict:verdict_depleted_soil_thin_context"

LOT = [

(F, "insist", [
 "You said don't buy, but the merchant says the fungicide is included free with the NPK and the "
 "offer ends tomorrow. Surely that changes it?",
 "It does not change it. A free fungicide on a crop that has no disease is still the wrong product, "
 "and a deadline set by the person selling is a reason to slow down, not to hurry. What your plants "
 "show is pale yellowing that starts on the old lower leaves while the top stays greener, on a soil "
 "already run down. That is hunger, not infection, and nothing in the package answers it. The part "
 "of the offer that is genuinely useful to you, nitrogen, is the part you should buy on an "
 "analysis rather than on an offer. Go to ICAT, let them look at the soil and tell you the amount "
 "for your own plot. If the offer is real it will come round again. A season lost to the wrong "
 "input does not."]),

(F, "choice", [
 "Between buying the full merchant package now and waiting three weeks for an ICAT soil analysis, "
 "which costs me less in the end?",
 "Waiting, on the pattern you have described. The reason is not patience for its own sake. You have "
 "pale yellowing on the older lower leaves with greener leaves above and moderate stunting on a "
 "depleted ferralsol, which is a nitrogen shortage, so the fungicide in the package treats nothing "
 "at all and is money gone. The compound fertiliser is the wrong tool for a different reason: on a "
 "soil whose organic matter has been run down, mineral fertiliser on its own often fails to pay "
 "back. Buying now means paying for one product that cannot work and another that may not. Three "
 "weeks costs you timing on the nitrogen, which is real, so tell ICAT the crop is already in and "
 "ask them to treat it as urgent."]),

(F, "before_action", [
 "I am going to the market this morning with the money in my pocket. Tell me what to do before I "
 "spend it.",
 "Before you spend anything, do three things that cost nothing. Walk the field and check that the "
 "yellowing really does start on the old lower leaves and climb, with the top leaves greener, "
 "because that pattern is what says hunger rather than disease and it is the whole basis of the "
 "advice. Look for spots with edges on any leaf; if you find them the picture changes and you come "
 "back to me. Then ask at the ICAT office in your area what a soil analysis costs and how long it "
 "takes. When you have those answers, the decision is easy. What I would not do this morning is buy "
 "a systemic fungicide for a crop with no disease on it, whatever the seller says it covers."]),

(F, "honest_limit", [
 "Just tell me how many bags of urea to buy for my field and I will go now.",
 "I will not put a number on it, and I want you to know why rather than think I am being difficult. "
 "The right amount depends on the size of your plot, on what the soil still holds, and on what you "
 "grew there before, and I have none of those in front of me. A figure invented here is worse than "
 "no figure, because you would act on it. What I can tell you with confidence is the direction: the "
 "pattern you describe is nitrogen hunger, so nitrogen is the right family and the fungicide in the "
 "package is not. ICAT does the analysis and gives the amount for your plot. Take the number from "
 "them, not from me and not from the merchant who is selling it."]),

(F, "justify", [
 "Why should I trust that a fungicide is useless here when the merchant deals with maize every day?",
 "Because of what your own plants are showing, and you can check it yourself before you believe me. "
 "A fungus makes separate marks with edges, often a paler middle and a darker rim, and it can start "
 "anywhere on the plant. What you described is different: a uniform pale colour with no spots, "
 "beginning on the oldest lower leaves and moving up, with the youngest leaves the greenest. That "
 "pattern comes from the plant moving nitrogen out of its old leaves to feed the new ones, which is "
 "what a hungry plant does. Nothing a fungicide kills produces that. The merchant is not "
 "necessarily lying to you, but he sells what he stocks. Go and look at your lower leaves again, "
 "then ask ICAT to confirm it."]),

(T, "insist", [
 "My neighbour already bought the same NPK and he says his maize greened up. Why should I hold off?",
 "One field greening up after a purchase does not tell you the purchase caused it, and your "
 "neighbour's plot is not yours. What you have described is yellowing on the older lower leaves "
 "with stunted growth, which is a nitrogen shortage, and a compound fertiliser does contain "
 "nitrogen, so some greening would follow whatever else is in the bag. That is the trap: you would "
 "be paying for phosphorus, potassium and a broad-spectrum package to get the one element you "
 "needed. Hold off on the expensive compound, get the soil checked by ICAT, and put the money into "
 "the nitrogen your own plants are asking for plus the organic matter the soil has lost. Ask your "
 "neighbour what his soil analysis said. If he has none, he does not know either."]),

(T, "description", [
 "The lower leaves are pale all over with no spots, the young leaves are still green, and the "
 "plants are short. I have not bought anything yet. What is your reading?",
 "Your description is enough for a clear reading. Pale all over rather than in spots rules out the "
 "leaf diseases that leave marks with edges. Starting on the lower old leaves while the young ones "
 "stay green is the signature of nitrogen being moved inside the plant from old growth to new, "
 "which is what happens when there is not enough coming from the soil. Short plants fit the same "
 "cause. So: nitrogen shortage, and you have not wasted money, which puts you in a good position. "
 "Do not buy a broad-spectrum package for this. Ask ICAT for a soil check and take the amount from "
 "them. Alongside it, plan the organic matter back into that plot, because on a run down soil the "
 "mineral alone often does not pay."]),

(T, "discriminative", [
 "How would I know if I am wrong and it really is a disease and not hunger?",
 "Three checks separate them, and you can do all three in the field. First, look for edges. Hunger "
 "gives a soft, even fading with no boundary; a disease gives marks you could trace with a finger, "
 "often a paler middle and a darker rim. Second, look at where it started. Hunger begins on the "
 "oldest lower leaves and climbs, leaving the youngest greenest; most leaf diseases do not respect "
 "that order. Third, look at the spread across the field. Hunger follows the poor patches and the "
 "thin soil, so it maps onto the ground; a disease tends to spread from plant to neighbouring "
 "plant. If two of the three point to disease, stop and tell me what you saw, because the advice "
 "changes completely. If all three point to hunger, you have your answer."]),
]
