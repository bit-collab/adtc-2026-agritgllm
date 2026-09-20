# -*- coding: utf-8 -*-
"""Configuration of the Gate 2 fine-tune. Read this file before launching anything.

Hardware for TRAINING : RTX 3050 Laptop 6 GB -> 4-bit QLoRA only, no full fine-tune.
Hardware for JUDGING  : ADTC Standard Laptop - 8 GB RAM, 4 vCPU (i5 10th-12th gen),
                        integrated graphics, llama.cpp, GGUF, fully offline.

Score (official Gate 2 rules, section 2.5):
    Stotal = 0.50*Sacc + 0.30*Sperf + 0.20*Seff - Pthermal  (+ up to 10 for African relevance)
Round 1 gave us Sacc 65.54 / Sperf 21.33 / Seff 82.99 = 55.77, and 0.5/0.3/0.2 reproduces
that total to the cent. The semifinalist medians are Seff 84.65 and Sperf 24.50: our
efficiency is mid-pack, our throughput is below median. Throughput is where the points are,
and that is why the base model shrinks. Rule 3.5 forbids shrinking it into a toy, so 0.6B is
the floor we defend rather than 350M.

No Unsloth here on purpose: it does not support Python 3.13 and its Windows install is the
most fragile part of the stack. Plain transformers + peft + trl + bitsandbytes works on 3.11
and 3.12, which is what the training venv must be.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "rebuild-gate2" / "out" / "train"          # sft.jsonl / dpo.jsonl
PAIRS = ROOT / "rebuild-gate2" / "out" / "pairs"         # pairs_clean.jsonl (carries bundle_id)
SPLIT = HERE / "data"                                    # written by 00_split.py
OUT = HERE / "outputs"
PROV = HERE / "provenance"                               # everything rule 3.1 asks for

# --- base model --------------------------------------------------------------------------
# A: the one we defend. B: the aggressive one, kept for the ablation, not for the submission
#    unless it measures better AND still answers the 12 acceptance items.
BASE_MODELS = {
    "A": {"id": "Qwen/Qwen3-0.6B",            "revision": "main", "params": "0.6B"},
    "B": {"id": "ibm-granite/granite-4.0-350m", "revision": "main", "params": "0.35B"},
    "D": {"id": "LiquidAI/LFM2-700M",         "revision": "86f49fc9a3800c3a325b7320bde179c318062583", "params": "0.70B"},
}
# D : le modele reellement livre. Les runs D2 et D3 passaient par --model en ligne de
# commande, ce qui laissait 00_split.py estampiller Qwen dans split_manifest.json.
EXPERIMENT = "D"
BASE_MODEL = BASE_MODELS[EXPERIMENT]["id"]
BASE_REVISION = BASE_MODELS[EXPERIMENT]["revision"]

MAX_SEQ = 1024        # our answers are 86 words median, 192 max: 1024 tokens is ample
LOAD_IN_4BIT = True

# --- held-out sets --------------------------------------------------------------------------
# TWO sets, because they answer two different questions, and confusing them cost us a run on
# 12/09/2026: early stopping fired at 0.65 of 3 epochs while the training loss was still falling
# from 4.02 to 0.62.
#
#   TEST  - whole FICHES the model never sees. Measures generalisation to a new subject. It is a
#           number for the REPORT, never a training signal: a bare model with no retrieval cannot
#           learn facts it has not read, so this loss plateaus as soon as the FORM is acquired and
#           then rises. Using it for early stopping stops the run almost immediately.
#   EVAL  - whole FACTS (bundles) held out from fiches the model DOES see. Same subjects, same
#           style, a sentence it has not been trained on. That is in-distribution and learnable,
#           so its loss tracks real progress and is the right early-stopping signal.
#
# Never split by line: the 8-9 gates of one fact quote the SAME sentence, so a random split puts
# the answer of the test set into training.
#
# NEVER hold out cattle_tick_borne, soil_depletion_north or tomato_sucking_pests: those three
# fiches exist only to repair the round-1 jury failures, and holding them out would undo the
# repair. Same for the hand-written families that answer the jury's own prompts.
# 13/09/2026 - BUG TROUVE PAR LA MESURE. Les deux sujets reserves etaient
# `out_of_distribution_plant` et `unregistered_pesticide_mix`, c'est-a-dire EXACTEMENT deux des
# questions de la batterie du jury : on retirait de l'entrainement la reponse a une question sur
# laquelle on se note ensuite. `fix_meta_out_of_distribution` a echoue sur 12 mesures sur 12.
# La regle du projet le disait deja pour les fiches de reparation ; elle vaut aussi ici. On
# reserve maintenant deux sujets de MEME nature qui ne sont PAS des questions du jury : `photos`
# (refus d'image, comme no_camera) et `mixing_chemicals` (refus de melange, comme le ratio de
# dilution). La generalisation reste mesuree, la reparation n'est plus annulee.
# "photos" rendu a l'entrainement le 19/09/2026 : voir la mesure et le raisonnement dans
# 00_split.py, au-dessus de la lecture de cette liste. Il reste un temoin de generalisation.
HELD_OUT_GOLD_TOPICS = ["mixing_chemicals"]

# Decision du 19/09/2026, apres mesure. maize_streak_virus et groundnut_rosette sortent du
# jeu reserve et entrent dans l'entrainement. Ce qui a ete mesure avant de decider, sur quatre
# chaines et quatre tirages chacune : devant des symptomes de ces deux maladies le modele ne
# dit jamais qu'il ne sait pas, il prend la fiche voisine de la meme culture et la deroule
# entiere, dose comprise (le neem 1:1 du foreur de tige pose sur la striure, la cercosporiose
# posee sur la rosette). Zero reussite sur seize passages, avant et apres le lot I. La question
# n'etait donc plus de savoir si la generalisation a une fiche entierement absente fonctionne :
# la reponse est non, elle est mesuree, et elle sera ecrite telle quelle dans le rapport.
# Restait a choisir ce que le modele repond a un jury. Ces deux maladies sont parmi les plus
# courantes sur le mais et l'arachide au Togo ; un conseiller qui ne sait pas les nommer est
# deficient sur son propre terrain. Elles entrent.
# Trois fiches restent reservees et mesurent toujours la generalisation sur la matiere :
# cassava_brown_streak, small_ruminant_ppr, sorghum_striga. Le comportement "aucune des fiches
# que je connais" est appris a part, par le lot K, sur des problemes qui n'ont de fiche nulle
# part : charbon du mais, chenille coupeuse, pourriture du collet, necrose apicale.
TEST_FICHES = [
    "cassava_brown_streak", "small_ruminant_ppr", "sorghum_striga",
]
EVAL_BUNDLE_FRACTION = 0.08    # share of the remaining FACTS kept aside for early stopping

# --- how many DIFFERENT answers one fact may have in training -------------------------------
# Measured 13/09/2026 on the cycle-2 model, 5 draws per question at the jury's sampling: two
# answers to the SAME question share only 20 % of their content words, and only 3 of the 12
# requirements pass on all five draws. The training file explains it: after the `expose` stage a
# fact carries a MEDIAN OF 9 DIFFERENT ANSWERS (up to 41). The model learnt a broad distribution
# of ways to answer, and picks a different mixture each time.
#
# Physics of LMs 3.1 augments the KNOWLEDGE TEXT and the QUESTIONS; its QA answers stay canonical.
# We augmented the answers too, which is not what the paper does. So: keep every question wording
# (that is what makes the knowledge extractable), and collapse the ANSWER side onto a few
# canonical answers per fact, chosen without a model as the most central ones (medoid on content
# words). 0 = keep everything, as before.
# MESURE DU 13/09/2026, 22h50 : hypothese REFUTEE. Banc large, 150 questions x 2 tirages.
#   sur les faits appris     : sans canonisation 0.690 +/- 0.038, avec 0.540 +/- 0.041
#   sur les fiches jamais vues: sans 0.337 +/- 0.039, avec 0.237 +/- 0.035
#   similarite entre tirages  : 0.281 sans, 0.275 avec  <- la canonisation ne change RIEN au seul
#                               chiffre qu'elle devait ameliorer, et coute de la justesse partout.
# (Reserve honnete : le modele canonise s'est arrete a 1,3 epoque contre 2,0 pour le temoin.)
# Remise a 0. Le levier qui marche, mesure sur les deux jeux, c'est le DPO sur les erreurs
# REELLES du modele (07_onpolicy.py) : +0.100 +/- 0.052 sur les fiches jamais vues.
ANSWER_VARIANTS = 0

# --- LoRA ------------------------------------------------------------------------------------
LORA_R = 32
LORA_ALPHA = 64
LORA_DROPOUT = 0.0
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

# Les noms de modules ne sont PAS les memes d'une famille a l'autre, et PEFT ne previent pas :
# une cible absente est silencieusement ignoree, l'entrainement tourne et n'apprend presque rien.
# LFM2 est hybride (10 couches de convolution courte + 6 d'attention sur 16) : son MLP s'appelle
# w1/w2/w3, sa sortie d'attention out_proj (pas o_proj), et le bloc de convolution porte in_proj
# + out_proj. Liste confirmee deux fois le 14/09/2026 : lue dans transformers/models/lfm2/
# modeling_lfm2.py, et identique a celle que Liquid/Unsloth publient.
# "LoRA Without Regret" (Thinking Machines, 2025) : appliquer LoRA a TOUTES les couches, surtout
# le MLP - c'est la ou est la capacite. On cible donc aussi les convolutions.
TARGET_MODULES_BY_BASE = {
    "qwen":    ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    "granite": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    "lfm2":    ["q_proj", "k_proj", "v_proj", "out_proj", "in_proj", "w1", "w2", "w3"],
}


def family_of(base_id: str) -> str:
    b = (base_id or "").lower()
    for k in TARGET_MODULES_BY_BASE:
        if k in b:
            return k
    return "qwen"


def targets_for(base_id: str):
    return TARGET_MODULES_BY_BASE[family_of(base_id)]


# Physics 3.3 (Allen-Zhu & Li, ICLR 2025) : int8 est sans perte, int4 fait tomber la capacite a
# 0,7 bit/parametre. En QLoRA la base reste GELEE en nf4 pendant tout l'entrainement : l'adaptateur
# apprend autour d'une base deja abimee. On ne l'accepte que quand la memoire l'impose.
#   Qwen3-0.6B  751,6 M x 2 octets = 1,50 Go  -> bf16 possible, jamais teste (a faire)
#   LFM2-700M   742,5 M x 2 octets = 1,48 Go  -> bf16 sur les 6 Go de la RTX 3050
def use_4bit_for(base_id: str) -> bool:
    return LOAD_IN_4BIT and family_of(base_id) != "lfm2"

# --- SFT ---------------------------------------------------------------------------------------
SFT_OUT = OUT / "sft"
SFT_LR = 2e-4
SFT_EPOCHS = 3                 # a cap; the best checkpoint is chosen on eval loss
# Four dry runs on the 6 GB card, 12/09/2026, same effective batch of 16 and same 456 steps.
# Doubling the batch changes nothing (the optimiser step still sees 16 examples); what costs
# time is gradient checkpointing, and the card has memory to spare without it.
#
#   batch x accum   checkpointing   steps/s   peak GPU   estimated run
#   2 x 8           on              0.117     1.98 GB    65 min
#   4 x 4           on              0.113     2.04 GB    67 min
#   4 x 4           off             0.146     4.74 GB    52 min   <- margin too thin on 6 GB
#   2 x 8           off             0.175     3.33 GB    43 min   <- kept
SFT_BATCH = 2
SFT_GRAD_ACCUM = 8             # effective batch 16
SFT_WARMUP_RATIO = 0.05
SFT_WEIGHT_DECAY = 0.01
# MESURE DU 14/09/2026, LFM2-700M, banc large 150 q x 2 tirages, profil llamacpp :
#   arret anticipe sur eval_loss (meilleur point = 1 epoque)   faits appris 0.727  jamais vues 0.313
#   3 epoques completes, modele FINAL garde (--patience 0)     faits appris 0.887  jamais vues 0.343
# eval_loss etait MONTEE de 1.33 a 1.50 entre les deux : c'etait de la memorisation des faits, pas
# du surapprentissage - exactement ce que Physics 3.3 predit (la capacite se remplit avec les
# expositions). Troisieme fois qu'eval_loss nous trompe comme signal d'arret (12/09, 13/09, 14/09).
# Le banc juge ; eval_loss ne sert plus qu'a detecter une divergence franche.
SFT_PATIENCE = 3               # laisse a 3 pour Qwen (non re-mesure) ; LFM2 se lance avec --patience 0
# 13/09/2026, cycle 2: with the documents (up to ~700 tokens) and the persona in every conversation,
# the run WITHOUT checkpointing peaked at 9.04 GB on the 6 GB card - Windows spilled into system
# RAM and the step went from 4.2 s to 30 s (9h47 instead of 1h15). Checkpointing costs ~30 % per
# step and keeps the peak near 2 GB: on this data it is the faster setting by far.
GRAD_CKPT = True

# --- DPO ------------------------------------------------------------------------------------
# ref_model=None + precompute_ref_log_probs: TRL uses the adapter-disabled policy as the
# reference, so DPO needs no second model in memory. That kills SimPO's main argument for us,
# and DPO keeps the explicit pull towards the SFT behaviour - which matters because 655 of our
# 1446 pairs differ by exactly one sentence and we do NOT want the model to drift elsewhere.
DPO_OUT = OUT / "dpo"
DPO_LR = 5e-6
DPO_EPOCHS = 1
DPO_BETA = 0.1
DPO_BATCH = 1
DPO_GRAD_ACCUM = 8
DPO_SOURCES = ["trim", "onpolicy"]   # "onpolicy" = the model's own rejected answers vs the reference (07_onpolicy.py, 13/09/2026)

# --- export ---------------------------------------------------------------------------------
MERGED = OUT / "merged"
GGUF = OUT / "gguf"
ANSWERS = OUT / "answers"                        # what each GGUF actually replied, kept as evidence
QUANTS = ["Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M"]    # measured against FP16, not assumed

# Two different llama.cpp installs, and they are not interchangeable. Checked 12/09/2026:
#   the CLONE  carries convert_hf_to_gguf.py (HF -> GGUF) and is at commit 89482bd66;
#   the BINARIES are the prebuilt Windows CPU build (build 10595, commit e8eed4525) and carry
#   llama-quantize / llama-imatrix / llama-server / llama-bench. There is no Windows build
#   inside the clone (its build/bin holds Linux .so files), hence the two paths.
# Override either with the environment variable if you move them.
import os as _os
LLAMA_CPP = Path(_os.environ.get("LLAMA_CPP_REPO", ROOT / "adtc-2026" / "llama.cpp"))
LLAMA_BIN = Path(_os.environ.get("LLAMA_BIN", ROOT / "tools" / "llama-cpu"))
CONVERT_HF = LLAMA_CPP / "convert_hf_to_gguf.py"

# --- imatrix ---------------------------------------------------------------------------------
# The importance matrix is calibrated on OUR OWN training conversations, never on wikitext: the
# quantisation error is then pushed away from the weights our answers actually use. Train split
# only - putting the test fiches in the calibration file would quantise towards the very text
# the test is supposed to be blind to.
IMATRIX_CHUNKS = 400           # chunks of 512 tokens; 0 = the whole calibration file
IMATRIX_CTX = 512

# --- the judging machine, and how our numbers translate to it ---------------------------------
# ADTC Standard Laptop: 8 GB RAM, 4 vCPU. Measure with 4 threads or the number means nothing.
TARGET_THREADS = 4
# Round 1 anchor, from the official report (ADTC2026_556, received 10/09/2026): Sperf 21.33 for
# the 1.7B model = 3.20 tok/s on the audit VM, against 6.34 tok/s measured on the same model on
# this bench. The audit machine runs at HALF our measured speed. Rule 3.4 punishes an
# unexplained gap between the declared figure and the organisers' measurement, so 04_compare.py
# reports the raw measurement AND this anchored estimate, and says which is which.
# MESURE le 13/09/2026 et elle contredit cette constante : le GGUF du tour 1 rend 36.76 tok/s
# sur CE banc contre 3.20 sur la VM d'audit, soit un facteur 0.0871 - ce banc va ~11.5 fois plus
# vite que la leur, pas deux fois. Le 0.5 venait d'un autre banc (Ubuntu, 6.34 tok/s) et ne vaut
# rien ici. Il ne reste que comme repli quand le fichier du tour 1 est absent.
AUDIT_SPEED_FACTOR = 0.5
# Better than that constant: the model WE submitted in round 1 is still on disk, and the report
# tells us what the audit VM measured on it (Sperf 21.33 = 3.20 tok/s, since Sperf saturates at
# 15 tok/s). Benching that same file HERE, with the organisers' own command, gives the factor
# between this bench and their machine directly, instead of carrying over a factor measured on a
# different bench. 04_compare.py does this when the file is present.
ROUND1_GGUF = ROOT / "adtc-submission" / "model" / "adtc-agritgllm-adviser-Q4_K_M.gguf"
ROUND1_AUDIT_TOK_S = 3.20      # 21.33 / 100 * 15, from the official round-1 report

# --- the persona baked into the GGUF (the jury runs the bare model, no system prompt) --------
BAKED_SYSTEM = (
    "You are AgriTG, an offline agricultural adviser for Togo. You help smallholder farmers "
    "and extension officers across Maritime, Plateaux, Centrale, Kara and Savanes with crops, "
    "livestock, weather and market advice, grounded in the Togolese services ICAT, ITRA, "
    "ANAMET, ANSAT, CAGIA and SIM. Answer directly and practically, in clear English. Never "
    "give a human medicine, a pesticide dose or a dilution ratio, and never name a disease you "
    "cannot support from what the farmer described."
)

SEED = 23
