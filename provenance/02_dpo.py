# One DPO pass on top of the SFT adapter, using data/dpo_train.jsonl; the reference policy is the same adapter disabled.
from __future__ import annotations
import argparse, json, os, platform, sys, time
from pathlib import Path

os.environ.setdefault("WANDB_DISABLED", "true")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
from importlib import import_module

_sft = import_module("01_sft") if Path(__file__).with_name("01_sft.py").exists() else None
human = _sft.human if _sft else (lambda s: f"{int(s)//60}m{int(s)%60:02d}s")
read_jsonl = _sft.read_jsonl if _sft else None
LogWriter = _sft.LogWriter if _sft else None


# arguments, then the DPO run on the SFT adapter
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default=C.EXPERIMENT)
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--beta", type=float, default=C.DPO_BETA)
    ap.add_argument("--lr", type=float, default=C.DPO_LR)
    ap.add_argument("--epochs", type=float, default=C.DPO_EPOCHS)
    a = ap.parse_args()

    import torch
    from datasets import Dataset
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainerCallback
    from peft import PeftModel
    from trl import DPOConfig, DPOTrainer

    if not torch.cuda.is_available():
        print("ARRET : torch ne voit pas de GPU (build CUDA requise).")
        return 2

    adapter = Path(a.adapter) if a.adapter else (C.SFT_OUT / a.tag / "best_lora")
    if not (adapter / "adapter_config.json").is_file():
        print(f"ARRET : adaptateur SFT introuvable dans {adapter}. Lance 01_sft.py d'abord.")
        return 2
    out = C.DPO_OUT / a.tag
    prov = C.PROV / a.tag

    tok = AutoTokenizer.from_pretrained(str(adapter))
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    if "<think>" in (tok.chat_template or ""):
        from importlib import import_module
        tok.chat_template = import_module("01_sft").CHATML_GEN
        print("  gabarit remplace : le modele ne doit jamais produire de bloc <think>")

    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                               bnb_4bit_compute_dtype=torch.bfloat16,
                               bnb_4bit_use_double_quant=True) if C.LOAD_IN_4BIT else None
    base = AutoModelForCausalLM.from_pretrained(
        C.BASE_MODEL, revision=C.BASE_REVISION, quantization_config=quant,
        dtype=torch.bfloat16, device_map={"": 0}, attn_implementation="eager")
    model = PeftModel.from_pretrained(base, str(adapter), is_trainable=True)
    model.config.use_cache = False

    rows = read_jsonl(C.SPLIT / "dpo_train.jsonl")
    if not rows:
        print("ARRET : aucune paire de preference. Lance 00_split.py.")
        return 2
    for r in rows:
        if isinstance(r.get("prompt"), list) and r["prompt"] and r["prompt"][0]["role"] != "system":
            r["prompt"] = [{"role": "system", "content": C.BAKED_SYSTEM}] + r["prompt"]
    ds = Dataset.from_list(rows)
    print(f"Preferences : {len(ds)} paires  (sources gardees : {C.DPO_SOURCES})")
    print(f"Adaptateur de depart : {adapter}")

    meta = {"stage": "dpo", "base_model": C.BASE_MODEL, "start_adapter": str(adapter),
            "pairs": len(ds), "sources": C.DPO_SOURCES,
            "hyper": {"beta": a.beta, "lr": a.lr, "epochs": a.epochs,
                      "batch": C.DPO_BATCH, "grad_accum": C.DPO_GRAD_ACCUM, "seed": C.SEED},
            "reference_model": "none - adapter-disabled policy, precompute_ref_log_probs=True",
            "env": {"python": platform.python_version(), "torch": torch.__version__},
            "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    log = LogWriter(prov, meta)
    log.csv = prov / "dpo_log.csv"
    log.json = prov / "dpo_log.json"
    log.csv.write_text("step,epoch,loss,eval_loss,learning_rate,seconds\n", encoding="utf-8")

    class Recorder(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kw):
            if logs:
                log.add(logs, state)

    steps = max(1, int(len(ds) / (C.DPO_BATCH * C.DPO_GRAD_ACCUM) * a.epochs))
    args = DPOConfig(
        output_dir=str(out), per_device_train_batch_size=C.DPO_BATCH,
        gradient_accumulation_steps=C.DPO_GRAD_ACCUM, num_train_epochs=a.epochs,
        learning_rate=a.lr, beta=a.beta, warmup_steps=max(1, steps // 10),
        lr_scheduler_type="cosine", optim="paged_adamw_8bit", bf16=True, max_length=C.MAX_SEQ,
        precompute_ref_log_probs=True, logging_steps=5, save_strategy="no",
        gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False},
        report_to=[], seed=C.SEED)

    trainer = DPOTrainer(model=model, ref_model=None, args=args, train_dataset=ds,
                         processing_class=tok, callbacks=[Recorder()])
    t0 = time.time()
    res = trainer.train()
    took = time.time() - t0

    out.mkdir(parents=True, exist_ok=True)
    trainer.model.save_pretrained(str(out / "best_lora"))
    tok.save_pretrained(str(out / "best_lora"))
    log.close({"train_runtime_s": round(took, 1), "train_loss": res.metrics.get("train_loss"),
               "global_step": trainer.state.global_step,
               "peak_gpu_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2)})
    print(f"\nDuree {human(took)}   adaptateur -> {out / 'best_lora'}")
    print(f"Journal -> {prov / 'dpo_log.csv'}")
    print("\nEtape suivante : 03_export.py, puis le test d'acceptation sur le GGUF.")
    print("Si le test d'acceptation baisse apres DPO, garde l'adaptateur SFT : le DPO n'est pas obligatoire.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
