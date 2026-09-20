# -*- coding: utf-8 -*-
"""STEP 9 - GRPO on a VERIFIABLE reward: optimise directly what the bench measures.

Why this and not another round of DPO (measured 14/09/2026, banc large):
  SFT seul            faits appris 0.690, jamais vus 0.337 (DPO 1849) -> 0.357 (DPO 2231)
  Each DPO round now buys about +0.02, inside the error bar. DPO moves the model AWAY from one
  bad answer at a time; it never optimises the probability that a DRAW is clean. That probability
  is exactly pass@1, and a policy-gradient method maximises it by construction.

CME 295 lecture 6 (DeepSeek-R1 recipe) : run RL on rewards a RULE can verify, no reward model.
Ours is already written and costs nothing:
    reward = 1.0  if no blocking lint fault, grounded in the reference, well-formed
           + partial credit otherwise, so the gradient is not flat on the bad half
The lint is `check.Checker` - the round-1 jury's own complaints written as rules (invented
figure, wrong crop, unknown name, service absent from the material, bare referral, "the fiche").

Goodhart (L8 p168): a measure that becomes a target stops being a measure. Two guards:
  1. GRPO trains on TRAIN bundles only. The bench on sft_test stays untouched by this training.
  2. --holdout keeps a share of the TRAIN bundles out of GRPO as well, so 08_bench can be run
     on questions this stage never optimised and the two numbers compared.
LoRA rank: "LoRA Without Regret" (Thinking Machines, 2025) measures that rank 1 already matches
full fine-tuning for policy gradient, because an episode carries about one bit. We keep the SFT
rank so the adapter stays mergeable with the same shape.

Usage (TRAINING venv), from concoursllmdata/ :
    .venv-train\\Scripts\\python train-gate2\\09_grpo.py --dry-run
    .venv-train\\Scripts\\python train-gate2\\09_grpo.py --adapter train-gate2\\outputs\\dpo\\A\\best_lora --prompts 400
Output: outputs/grpo/<tag>/best_lora/ , provenance/<tag>/grpo_log.json
"""
from __future__ import annotations
import argparse, json, os, random, re, sys, time
from pathlib import Path

os.environ.setdefault("WANDB_DISABLED", "true")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
from importlib import import_module
CHATML_GEN = import_module("01_sft").CHATML_GEN
sys.path.insert(0, str(C.ROOT / "rebuild-gate2" / "pipeline"))
import g4_generate as G4
import check as CHK

GROUND_MIN = 0.25
WORDS = (40, 200)
# Au-dela de SOFT_WORDS la note de forme decroit au lieu de rester pleine. Le RL allonge les
# reponses, c'est son biais connu, et la longueur frappe deux fois : Seff pese 20 % du score
# ADTC et Sperf 30 %, tous deux mesures sur un portable CPU sans reseau. Nos references tiennent
# en 85 mots de mediane, donc 160 laisse toute la place utile sans payer la derive.
SOFT_WORDS = 160
NO_MATERIAL = {"doc", "unknown"}


def read_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()] if Path(p).is_file() else []


def content(t):
    return set(re.findall(r"[a-z]{4,}", (t or "").lower()))


def looping(answer, n=4, times=4):
    w = answer.lower().split()
    if len(w) < n * times:
        return False
    from collections import Counter
    c = Counter(tuple(w[i:i + n]) for i in range(len(w) - n + 1))
    return max(c.values()) >= times


def human(sec):
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


class Reward:
    """Deterministic, no model. Returns 0..1 and keeps the counts for the log."""

    def __init__(self):
        self.checker = CHK.Checker()
        self.stats = {}

    def bump(self, k):
        self.stats[k] = self.stats.get(k, 0) + 1

    def __call__(self, completions, **kw):
        bundles = kw["bundle"]
        refs = kw["reference"]
        users = kw["farmer"]
        out = []
        for comp, b, ref, farmer in zip(completions, bundles, refs, users):
            text = comp[0]["content"] if isinstance(comp, list) else str(comp)
            text = " ".join(text.split())
            words = len(text.split())
            faults = [x for x in self.checker.check(text, b, final=True, user_text=farmer)
                      if x.split(":")[0] in CHK.BLOCKING]
            ref_words = content(ref)
            ground = len(ref_words & content(text)) / max(1, len(ref_words))
            loop = looping(text)
            form = WORDS[0] <= words <= WORDS[1] and not loop
            if not form:
                form_score = 0.0
            elif words <= SOFT_WORDS:
                form_score = 1.0
            else:
                form_score = (WORDS[1] - words) / (WORDS[1] - SOFT_WORDS)
            if faults:
                for f in faults:
                    self.bump(f.split(":")[0])
            # 0.5 for a clean answer, 0.3 for the grounding, 0.2 for the form: a wrong but
            # well-shaped answer still beats a shapeless one, so the gradient is informative
            # everywhere instead of being flat on the whole bad half.
            r = 0.0
            r += 0.5 * (0.0 if faults else 1.0)
            r += 0.3 * min(1.0, ground / GROUND_MIN)
            r += 0.2 * form_score
            if not faults and ground >= GROUND_MIN and form:
                self.bump("clean")
            self.bump("n")
            out.append(float(r))
        return out


def build_rows(tok, holdout, seed, max_prompts, max_prompt_tokens, only=None):
    """Ne jamais optimiser une question dont la RECOMPENSE CONDAMNE DEJA LA REFERENCE.

    Trouve le 18/09/2026 en mesurant la recompense sur les references elles-memes, avant
    d'entrainer. Resultat : 1,000 de moyenne sur la matiere du pipeline, 0,959 sur la matiere
    ecrite a la main, et tout l'ecart venait de 88 reponses d'arithmetique. Le Checker ne sait
    pas calculer : quand une reponse ecrit correctement que 33 poules a 8-10 par m2 demandent
    3,3 a 4,1 m2, il ne retrouve ni 3,3 ni 4,1 dans la fiche et retire 0,5. Le RL aurait donc
    appris au modele a NE PAS calculer, c'est-a-dire exactement l'inverse de l'angle `scale`
    que le SFT venait de lui enseigner.

    Deux assouplissements du Checker ont ete mesures et REFUSES tous les deux, sur les 484
    reponses ou le modele a reellement invente un chiffre (onpolicy_dpo.jsonl) :
      - tolerer tout chiffre derivable en une operation : 66 % des vraies inventions passent ;
      - exiger que la reponse montre son calcul dans la phrase : 12 % passent encore, et
        seulement 19 % de l'arithmetique legitime est recuperee.
    Aucune des deux ne separe les deux classes, donc le Checker reste strict. C'est le RL qui
    s'abstient la ou sa recompense est fausse, et non la mesure qui s'assouplit.
    """
    bundles = {b["bundle_id"]: b for b in read_jsonl(G4.BUNDLES)}
    juge = Reward()
    rows, ecartees = [], 0
    for r in read_jsonl(C.SPLIT / "sft_train.jsonl"):
        b = bundles.get(r.get("bundle_id", ""))
        if not b or r.get("kind") in NO_MATERIAL:
            continue
        if only and not r["bundle_id"].startswith(only):
            continue
        msgs = r["messages"]
        if msgs[-1]["role"] != "assistant":
            continue
        ref = msgs[-1]["content"]
        farmer = "\n".join(m["content"] for m in msgs[:-1] if m["role"] == "user")
        if any(x.split(":")[0] in CHK.BLOCKING
               for x in juge.checker.check(ref, b, final=True, user_text=farmer)):
            ecartees += 1
            continue
        prompt = [{"role": "system", "content": C.BAKED_SYSTEM}] + msgs[:-1]
        n = len(tok.apply_chat_template(prompt, tokenize=True, add_generation_prompt=True))
        if n > max_prompt_tokens:
            continue
        rows.append({"prompt": prompt, "bundle": b, "reference": ref,
                     "farmer": farmer, "bundle_id": r["bundle_id"]})
    print(f"  {ecartees} question(s) ecartee(s) : leur propre reference est condamnee par le lint, "
          f"le gradient y pointerait dans le mauvais sens")
    ids = sorted({r["bundle_id"] for r in rows})
    rng = random.Random(seed)
    rng.shuffle(ids)
    held = set(ids[:int(len(ids) * holdout)])
    kept = [r for r in rows if r["bundle_id"] not in held]
    rng.shuffle(kept)
    return (kept[:max_prompts] if max_prompts else kept), sorted(held)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default=C.EXPERIMENT)
    ap.add_argument("--adapter", default=None, help="defaut : outputs/dpo/<tag>/best_lora")
    ap.add_argument("--prompts", type=int, default=400)
    ap.add_argument("-G", "--generations", type=int, default=4)
    ap.add_argument("--lr", type=float, default=5e-6)
    ap.add_argument("--beta", type=float, default=0.02, help="KL vers la politique de reference")
    ap.add_argument("--max-completion", type=int, default=300)
    ap.add_argument("--max-prompt-tokens", type=int, default=600)
    ap.add_argument("--holdout", type=float, default=0.15)
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--epochs", type=float, default=1.0)
    ap.add_argument("--only", default=None,
                    help="ne garder que les paquets dont le bundle_id commence par ce prefixe, "
                         "par exemple --only handwritten: . Mesure du 18/09/2026 : les paires "
                         "ecrites a la main sont passees de 390 a 1291 et pesent maintenant 22,2 %% "
                         "des 5591 lignes de sft_train jointes a un paquet, contre 5,8 %% avant. Un "
                         "tirage de 400 questions en voit donc environ 89 au lieu d'une vingtaine. "
                         "Le second passage filtre reste utile pour concentrer le RL dessus, mais "
                         "il n'est plus le seul moyen que cette matiere soit travaillee.")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    import torch
    from datasets import Dataset
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from peft import PeftModel
    from trl import GRPOConfig, GRPOTrainer

    if not torch.cuda.is_available():
        print("ARRET : pas de GPU visible.")
        return 2
    adapter = Path(a.adapter) if a.adapter else C.DPO_OUT / a.tag / "best_lora"
    out, prov = C.OUT / "grpo" / a.tag, C.PROV / a.tag
    out.mkdir(parents=True, exist_ok=True)
    prov.mkdir(parents=True, exist_ok=True)

    tok = AutoTokenizer.from_pretrained(str(adapter))
    tok.chat_template = CHATML_GEN
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    tok.padding_side = "left"                      # generation

    rows, held = build_rows(tok, a.holdout, C.SEED, a.prompts, a.max_prompt_tokens, a.only)
    print(f"GRPO : {len(rows)} questions d'entrainement, {len(held)} paquets mis de cote "
          f"(jamais optimises, pour verifier le Goodhart)")
    (prov / "grpo_holdout.json").write_text(json.dumps({"held_bundles": held}, indent=1), encoding="utf-8")
    ds = Dataset.from_list([{"prompt": r["prompt"], "bundle": r["bundle"],
                             "reference": r["reference"], "farmer": r["farmer"]} for r in rows])
    reward = Reward()
    if a.dry_run:
        ex = rows[0]
        print("exemple de question :", ex["farmer"][:120])
        print("recompense de la reference elle-meme :",
              reward([[{"role": "assistant", "content": ex["reference"]}]],
                     bundle=[ex["bundle"]], reference=[ex["reference"]], farmer=[ex["farmer"]]))
        print("recompense d'une reponse inventee    :",
              reward([[{"role": "assistant", "content": "Spray 250 ml of diesel per hectare every Monday "
                                                       "and call ANAMET for the cattle."}]],
                     bundle=[ex["bundle"]], reference=[ex["reference"]], farmer=[ex["farmer"]]))
        return 0

    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                               bnb_4bit_compute_dtype=torch.bfloat16,
                               bnb_4bit_use_double_quant=True) if C.LOAD_IN_4BIT else None
    base = AutoModelForCausalLM.from_pretrained(C.BASE_MODEL, revision=C.BASE_REVISION,
                                                quantization_config=quant, dtype=torch.bfloat16,
                                                device_map={"": 0}, attn_implementation="eager")
    base.config.use_cache = True
    model = PeftModel.from_pretrained(base, str(adapter), is_trainable=True)
    model.config.use_cache = True
    print(f"Adaptateur de depart : {adapter}")

    args = GRPOConfig(
        output_dir=str(out), num_train_epochs=a.epochs, learning_rate=a.lr, beta=a.beta,
        per_device_train_batch_size=a.generations, gradient_accumulation_steps=4,
        num_generations=a.generations, max_completion_length=a.max_completion,
        # TRL 1.13 dropped max_prompt_length from GRPOConfig: build_rows() already refuses a
        # prompt longer than --max-prompt-tokens, so nothing is silently truncated.
        temperature=a.temperature, top_k=40, top_p=0.95, min_p=0.05,   # the jury's own sampling
        bf16=True, gradient_checkpointing=True, logging_steps=2, save_strategy="no",
        report_to=[], seed=C.SEED, use_vllm=False, log_completions=False,
        optim="paged_adamw_8bit", lr_scheduler_type="constant_with_warmup", warmup_steps=5,
    )
    trainer = GRPOTrainer(model=model, args=args, train_dataset=ds,
                          reward_funcs=[reward], processing_class=tok)
    t0 = time.time()
    res = trainer.train()
    model.save_pretrained(str(out / "best_lora"))
    tok.save_pretrained(str(out / "best_lora"))
    log = {"meta": {"adapter": str(adapter), "prompts": len(rows), "G": a.generations,
                    # --only et --holdout DOIVENT figurer ici : sans eux un lecteur ne peut pas
                    # savoir sur quelle partie du jeu ce run a porte, ni combien de paquets sont
                    # restes hors optimisation. La regle 3.4 demande des mesures reproductibles.
                    "only": a.only, "holdout": a.holdout, "held_bundles": len(held),
                    "lr": a.lr, "beta": a.beta, "temperature": a.temperature,
                    "holdout_bundles": len(held), "reward": "lint + ancrage + forme, deterministe"},
           "reward_stats": reward.stats,
           "history": [h for h in trainer.state.log_history],
           "summary": {"seconds": round(time.time() - t0, 1),
                       "peak_gpu_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2),
                       "train_loss": getattr(res, "training_loss", None)}}
    (prov / "grpo_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    n = reward.stats.get("n", 1)
    print(f"\nGRPO termine en {human(time.time() - t0)} : {reward.stats.get('clean', 0)}/{n} "
          f"generations propres pendant l'entrainement -> {out / 'best_lora'}")
    print(f"fautes vues : { {k: v for k, v in sorted(reward.stats.items(), key=lambda x: -x[1]) if k not in ('n', 'clean')} }")
    return 0


if __name__ == "__main__":
    sys.exit(main())
