# -*- coding: utf-8 -*-
"""STEP 1 - supervised fine-tuning, 4-bit QLoRA, no Unsloth.

Runs on the 6 GB laptop GPU. The loss falls ONLY on the adviser's answers: the farmer's question
and the chat scaffolding are masked, so the model learns to answer, not to write questions.

Two things about Qwen3 that this file handles and that would silently ruin the run otherwise:

  1. Its stock chat template writes "<think>\\n\\n</think>" into every assistant turn. Trained that
     way the model learns to emit an empty thinking block on every answer - wasted tokens on the
     criterion that weighs 0.30. We install a plain ChatML template with no thinking block, and
     the same template is used for training, evaluation and export.
  2. TRL computes the answer mask from the chat template itself, so the assistant content must be
     wrapped in {% generation %}...{% endgeneration %}. Verified on the real tokenizer, 12/09/2026:
     the loss then covers "Check the lower leaves first.<|im_end|>" and nothing else.

Everything Gate 2 rule 3.1 asks for is written as the run goes, not reconstructed afterwards:
  provenance/<tag>/training_log.csv    loss and learning rate at every logged step
  provenance/<tag>/training_log.json   the same, plus eval points and the final summary
  provenance/<tag>/train_config.json   every hyper-parameter, the base model and its revision
  outputs/sft/<tag>/best_lora/         the adapter (adapter_model.safetensors + adapter_config.json)

Tested against trl 1.13.0 / transformers 5.17.0 / peft 0.20.0 / torch 2.5.1+cu121.

Usage (TRAINING venv), from concoursllmdata/ :
    .venv-train\\Scripts\\python train-gate2\\01_sft.py --dry-run
    .venv-train\\Scripts\\python train-gate2\\01_sft.py
    .venv-train\\Scripts\\python train-gate2\\01_sft.py --model ibm-granite/granite-4.0-350m --tag B
"""
from __future__ import annotations
import argparse, json, os, platform, sys, time
from pathlib import Path

os.environ.setdefault("WANDB_DISABLED", "true")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

# ChatML with no thinking block, and the assistant content marked so TRL can mask the rest.
CHATML_GEN = (
    "{%- for m in messages %}"
    "{%- if m['role'] == 'assistant' %}"
    "{{- '<|im_start|>assistant\n' }}"
    "{% generation %}{{- m['content'] + '<|im_end|>\n' }}{% endgeneration %}"
    "{%- else %}"
    "{{- '<|im_start|>' + m['role'] + '\n' + m['content'] + '<|im_end|>\n' }}"
    "{%- endif %}{%- endfor %}"
    "{%- if add_generation_prompt %}{{- '<|im_start|>assistant\n' }}{%- endif %}")



# LFM2 uses the SAME ChatML markers as Qwen (<|im_start|>/<|im_end|>, id 7 for the end) and DOES
# have a system role, so the template above transfers as-is. Two differences only: its tokenizer
# prepends a BOS <|startoftext|> (add_bos_token=True in tokenizer_config.json), and there is no
# thinking block to neutralise. Read from LiquidAI/LFM2-700M/chat_template.jinja on 14/09/2026.
LFM2_GEN = "{{- bos_token -}}" + CHATML_GEN

# Gemma has no <|im_end|> token and no system role. Trained with the ChatML template above, the
# 270M wrote "<|im_end|>" as PLAIN TEXT and never emitted a stop token: measured 14/09/2026,
# 1199 of 1200 generations ran to the 400-token cap, pass@1 0.000. Its own markers are
# <start_of_turn>/<end_of_turn> (id 106), and the assistant role is called "model". The system
# message is merged into the first user turn, which is what Gemma's own template does.
GEMMA_GEN = (
    "{%- if messages[0]['role'] == 'system' %}"
    "{%- set sys = messages[0]['content'] + '\n\n' %}{%- set loop_messages = messages[1:] %}"
    "{%- else %}{%- set sys = '' %}{%- set loop_messages = messages %}{%- endif %}"
    "{%- for m in loop_messages %}"
    "{%- if m['role'] == 'assistant' %}"
    "{{- '<start_of_turn>model\n' }}"
    "{% generation %}{{- m['content'] + '<end_of_turn>\n' }}{% endgeneration %}"
    "{%- else %}"
    "{{- '<start_of_turn>user\n' + (sys if loop.first else '') + m['content'] + '<end_of_turn>\n' }}"
    "{%- endif %}{%- endfor %}"
    "{%- if add_generation_prompt %}{{- '<start_of_turn>model\n' }}{%- endif %}")


def template_for(base_id: str) -> str:
    """One template per base family. Getting this wrong does not raise: it produces a model that
    never stops, so the choice is explicit and printed by the script."""
    b = (base_id or "").lower()
    if "gemma" in b:
        return GEMMA_GEN
    if "lfm2" in b:
        return LFM2_GEN
    return CHATML_GEN


def stop_token_for(base_id: str):
    """The token the template ends an answer with. It MUST be the model's EOS, or llama.cpp has
    nothing to stop on."""
    return "<end_of_turn>" if "gemma" in (base_id or "").lower() else "<|im_end|>"


def human(sec):
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def read_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


class LogWriter:
    """Writes the training log as it happens, so a crash still leaves usable provenance."""

    def __init__(self, folder, meta, stem="training"):
        folder.mkdir(parents=True, exist_ok=True)
        self.csv = folder / f"{stem}_log.csv"
        self.json = folder / f"{stem}_log.json"
        self.rows, self.meta, self.t0 = [], meta, time.time()
        self.csv.write_text("step,epoch,loss,eval_loss,learning_rate,seconds\n", encoding="utf-8")

    def add(self, logs, state):
        row = {"step": state.global_step, "epoch": round(float(state.epoch or 0), 4),
               "loss": logs.get("loss"), "eval_loss": logs.get("eval_loss"),
               "learning_rate": logs.get("learning_rate"),
               "seconds": round(time.time() - self.t0, 1)}
        self.rows.append(row)
        with open(self.csv, "a", encoding="utf-8") as f:
            f.write(",".join("" if row[k] is None else str(row[k]) for k in
                             ("step", "epoch", "loss", "eval_loss", "learning_rate", "seconds")) + "\n")

    def close(self, summary):
        self.json.write_text(json.dumps({"meta": self.meta, "summary": summary, "log": self.rows},
                                        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=C.BASE_MODEL)
    ap.add_argument("--revision", default=C.BASE_REVISION)
    ap.add_argument("--tag", default=C.EXPERIMENT)
    ap.add_argument("--epochs", type=float, default=C.SFT_EPOCHS)
    ap.add_argument("--lr", type=float, default=C.SFT_LR)
    ap.add_argument("--rank", type=int, default=C.LORA_R)
    ap.add_argument("--no-4bit", action="store_true", help="base en bf16 au lieu de nf4")
    ap.add_argument("--patience", type=int, default=C.SFT_PATIENCE,
                    help="evaluations sans progres avant l'arret anticipe (0 = jamais)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    import torch
    from datasets import Dataset
    from transformers import (AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig,
                              EarlyStoppingCallback, TrainerCallback)
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from trl import SFTConfig, SFTTrainer

    if not torch.cuda.is_available():
        print("ARRET : torch ne voit pas de GPU. Ce venv doit avoir une build CUDA de torch.")
        print(f"        torch {torch.__version__} sur {platform.python_version()}")
        return 2

    out, prov = C.SFT_OUT / a.tag, C.PROV / a.tag
    print(f"Modele  : {a.model} (revision {a.revision})")
    print(f"GPU     : {torch.cuda.get_device_name(0)}  "
          f"{torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} Go")

    tok = AutoTokenizer.from_pretrained(a.model, revision=a.revision)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    tok.padding_side = "right"
    tok.chat_template = template_for(a.model)   # no thinking block, answers marked for the loss mask
    stop = stop_token_for(a.model)
    stop_id = tok.convert_tokens_to_ids(stop)
    fam = C.family_of(a.model)
    print(f"Gabarit : {'Gemma (start/end_of_turn)' if 'gemma' in a.model.lower() else 'ChatML'}"
          f"{' + BOS' if fam == 'lfm2' else ''} ; jeton de fin {stop} = {stop_id}")
    if stop_id is None or stop_id == tok.unk_token_id:
        print(f"ARRET : {stop} n'existe pas dans ce tokenizer ; le modele ne pourrait jamais s'arreter.")
        return 2
    if tok.eos_token_id != stop_id:
        print(f"  EOS aligne sur {stop} (etait {tok.eos_token} = {tok.eos_token_id})")
        tok.eos_token = stop

    four_bit = C.use_4bit_for(a.model) and not a.no_4bit
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                               bnb_4bit_compute_dtype=torch.bfloat16,
                               bnb_4bit_use_double_quant=True) if four_bit else None
    print(f"Precision de la base : {'QLoRA nf4 4 bits' if four_bit else 'bf16 (base non quantifiee)'}")
    kw = dict(revision=a.revision, quantization_config=quant, device_map={"": 0},
              attn_implementation="eager")
    try:                                    # transformers >= 5 uses dtype, older ones torch_dtype
        model = AutoModelForCausalLM.from_pretrained(a.model, dtype=torch.bfloat16, **kw)
    except TypeError:
        model = AutoModelForCausalLM.from_pretrained(a.model, torch_dtype=torch.bfloat16, **kw)
    model.config.use_cache = False
    if four_bit:
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=C.GRAD_CKPT)
    elif C.GRAD_CKPT:
        # prepare_model_for_kbit_training does this for us in 4-bit. In bf16 nobody does, and
        # without it checkpointing returns activations detached from the graph: the LoRA weights
        # get no gradient at all and the loss simply never moves.
        model.enable_input_require_grads()
    targets = C.targets_for(a.model)
    model = get_peft_model(model, LoraConfig(
        r=a.rank, lora_alpha=C.LORA_ALPHA, lora_dropout=C.LORA_DROPOUT,
        target_modules=targets, bias="none", task_type="CAUSAL_LM"))
    hit = {n.split(".")[-3] for n, _ in model.named_modules() if n.endswith(".lora_A.default")}
    missing = [t for t in targets if t not in hit]
    if missing:
        print(f"ARRET : PEFT n'a trouve aucune couche nommee {missing}. Une cible absente est "
              f"ignoree en silence et l'entrainement n'apprendrait presque rien.")
        return 2
    print(f"Cibles  : {targets} (toutes trouvees)")
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"LoRA    : r={a.rank}  {trainable / 1e6:.1f} M parametres entraines "
          f"sur {total / 1e6:.0f} M ({100 * trainable / total:.2f} %)")

    # Conversational format: TRL applies the chat template itself, which is how it builds the
    # answer mask. Do NOT pre-format into a text column, or the mask cannot be computed.
    # The GGUF template bakes the persona as a system message into EVERY conversation the jury
    # has (03_export.py, config.BAKED_SYSTEM). Until 13/09/2026 training saw no system message at
    # all: the model was served with a preamble it had never learnt with. Train = serve, now.
    def with_persona(msgs):
        if msgs and msgs[0]["role"] == "system":
            return msgs
        return [{"role": "system", "content": C.BAKED_SYSTEM}] + msgs
    train_ds = Dataset.from_list([{"messages": with_persona(r["messages"])}
                                  for r in read_jsonl(C.SPLIT / "sft_train.jsonl")])
    eval_ds = Dataset.from_list([{"messages": with_persona(r["messages"])}
                                 for r in read_jsonl(C.SPLIT / "sft_eval.jsonl")])
    print(f"Donnees : train {len(train_ds)}  eval {len(eval_ds)}")

    sample = tok.apply_chat_template(train_ds[0]["messages"], tokenize=False)
    print("--- un exemple formate ---")
    print(sample[:500])
    print("-" * 78)
    if "<think>" in sample:
        print("ARRET : le gabarit insere un bloc <think>. Corrige-le avant d'entrainer.")
        return 2

    enc = tok.apply_chat_template([train_ds[0]["messages"]], tokenize=True, return_dict=True,
                                  return_assistant_tokens_mask=True)
    ids, mask = enc["input_ids"][0], enc["assistant_masks"][0]
    if not sum(mask):
        print("ARRET : le masque des reponses est vide, la perte porterait sur la question.")
        return 2
    print(f"  perte sur {sum(mask)} tokens de reponse sur {len(ids)} "
          f"({100 * sum(mask) / len(ids):.0f} %) ; le reste est masque")
    print(f"  debut de la partie apprise : {tok.decode([i for i, m in zip(ids, mask) if m])[:90]!r}")

    steps_per_epoch = max(1, len(train_ds) // (C.SFT_BATCH * C.SFT_GRAD_ACCUM))
    total_steps = max(1, int(steps_per_epoch * a.epochs))
    warmup = max(1, int(total_steps * C.SFT_WARMUP_RATIO))
    meta = {"base_model": a.model, "revision": a.revision, "experiment": a.tag,
            "method": ("QLoRA 4-bit (nf4, double quant, bf16 compute)" if four_bit
                       else "LoRA on a bf16 base (no quantisation during training)")
                      + ", loss on assistant turns only",
            "chat_template": ("ChatML" + (" + BOS" if fam == "lfm2" else "")
                              + ", no thinking block, assistant content marked for masking"),
            "lora": {"r": a.rank, "alpha": C.LORA_ALPHA, "dropout": C.LORA_DROPOUT,
                     "targets": targets, "trainable_params": trainable},
            "data": {"train": len(train_ds), "eval": len(eval_ds),
                     # Corrige le 18/09/2026 : sft.jsonl n'est pas la source et ne l'etait plus.
                     # 00_split.py lit les paires, les copies bruitees, les documents, les
                     # reponses hors fiches et les paires on-policy. Annoncer un fichier que
                     # rien ne lit est une fausse piste pour le jury, qui doit pouvoir refaire
                     # le decoupage.
                     "source": "train-gate2/data/sft_train.jsonl, ecrit par 00_split.py "
                               "(voir data/split_manifest.json pour les entrees et les temoins "
                               "de fuite)"},
            "hyper": {"lr": a.lr, "epochs": a.epochs, "batch": C.SFT_BATCH,
                      "grad_accum": C.SFT_GRAD_ACCUM, "max_length": C.MAX_SEQ,
                      "warmup_steps": warmup, "weight_decay": C.SFT_WEIGHT_DECAY,
                      "steps_per_epoch": steps_per_epoch, "total_steps": total_steps,
                      "seed": C.SEED},
            "env": {"python": platform.python_version(), "torch": torch.__version__,
                    "gpu": torch.cuda.get_device_name(0)},
            "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    log = LogWriter(prov, meta)
    (prov / "train_config.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")

    class Recorder(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kw):
            if logs:
                log.add(logs, state)

    every = max(10, steps_per_epoch // 3)
    args = SFTConfig(
        output_dir=str(out), num_train_epochs=(0.02 if a.dry_run else a.epochs),
        per_device_train_batch_size=C.SFT_BATCH, gradient_accumulation_steps=C.SFT_GRAD_ACCUM,
        learning_rate=a.lr, warmup_steps=warmup, weight_decay=C.SFT_WEIGHT_DECAY,
        lr_scheduler_type="cosine", optim="paged_adamw_8bit", bf16=True,
        max_length=C.MAX_SEQ, packing=False, assistant_only_loss=True,
        logging_steps=5, eval_strategy="steps", eval_steps=every,
        save_strategy="steps", save_steps=every, save_total_limit=2,
        # --patience 0 means "run the whole schedule and keep the FINAL model": on LFM2 (14/09/2026)
        # eval_loss picked the 1-epoch checkpoint while the bench is what decides, so reloading the
        # eval_loss winner would silently undo the extra epochs this flag asks for.
        load_best_model_at_end=(a.patience > 0), metric_for_best_model="eval_loss", greater_is_better=False,
        gradient_checkpointing=C.GRAD_CKPT, gradient_checkpointing_kwargs={"use_reentrant": False},
        report_to=[], seed=C.SEED)

    trainer = SFTTrainer(model=model, args=args, train_dataset=train_ds, eval_dataset=eval_ds,
                         processing_class=tok,
                         callbacks=[Recorder()] + ([EarlyStoppingCallback(a.patience)] if a.patience > 0 else []))

    t0 = time.time()
    print(f"\nDepart : {steps_per_epoch} pas par epoque, {total_steps} pas au total, "
          f"{warmup} de chauffe\n")
    res = trainer.train()
    took = time.time() - t0

    metrics = trainer.evaluate()
    summary = {"train_runtime_s": round(took, 1), "train_loss": res.metrics.get("train_loss"),
               "final_eval_loss": metrics.get("eval_loss"),
               "best_eval_loss": trainer.state.best_metric,
               "best_checkpoint": trainer.state.best_model_checkpoint,
               "global_step": trainer.state.global_step,
               "peak_gpu_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2)}
    log.close(summary)

    if not a.dry_run:
        (out / "best_lora").mkdir(parents=True, exist_ok=True)
        trainer.model.save_pretrained(str(out / "best_lora"))
        tok.save_pretrained(str(out / "best_lora"))
        print(f"\nAdaptateur -> {out / 'best_lora'}")

    print(f"\nDuree {human(took)}   perte de validation finale {summary['final_eval_loss']}   "
          f"meilleure {summary['best_eval_loss']}   pic GPU {summary['peak_gpu_gb']} Go")
    print(f"Journal -> {log.csv}")
    tl = summary.get("train_loss")
    if tl is not None and tl < 0.2:
        print("  ATTENTION : perte d'entrainement sous 0.2, signe classique de surapprentissage.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
