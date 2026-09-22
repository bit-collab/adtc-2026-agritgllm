# Weighted merge of two LoRA adapters with PEFT add_weighted_adapter, then a layer-by-layer check of the result against the sources.
import sys, shutil, json, io, os
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
ROOT = Path(r"C:\Users\HP VICTUS\Documents\concoursllmdata")
sys.path.insert(0, str(ROOT / "train-gate2")); import config as C
tag, method, wk, wo = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
density = float(sys.argv[5]) if len(sys.argv) > 5 else 0.7
K = ROOT / "train-gate2/outputs/dpo/Kdpo/best_lora"
O = ROOT / "train-gate2/outputs/sft/O/best_lora"
OUT = ROOT / "train-gate2/outputs/merged_adapters" / tag / "best_lora"
base = AutoModelForCausalLM.from_pretrained(C.BASE_MODEL, revision=C.BASE_REVISION, dtype=torch.bfloat16, device_map={"": 0}, attn_implementation="eager")
model = PeftModel.from_pretrained(base, str(K), adapter_name="kv3")
model.load_adapter(str(O), adapter_name="osft")
kw = dict(adapters=["kv3", "osft"], weights=[wk, wo], adapter_name="merged", combination_type=method)
if method.endswith("svd"):
    kw["svd_rank"] = 64
if "ties" in method or "dare" in method or "magnitude" in method:
    kw["density"] = density
model.add_weighted_adapter(**kw)
model.set_adapter("merged")
OUT.parent.mkdir(parents=True, exist_ok=True)
if OUT.exists(): shutil.rmtree(OUT)
model.save_pretrained(str(OUT.parent), selected_adapters=["merged"])
(OUT.parent / "merged").rename(OUT)
for f in ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja", "README.md"):
    if (K / f).exists(): shutil.copy2(K / f, OUT / f)
cfg = json.load(io.open(OUT / "adapter_config.json", encoding="utf-8"))
io.open(OUT / "MERGE.json", "w", encoding="utf-8", newline="\n").write(json.dumps({
    "method": method, "weights": {"Kdpo (v3)": wk, "O sft": wo}, "density": density if "ties" in method or "dare" in method else None,
    "rank_out": cfg.get("r"), "sources": {"Kdpo": str(K), "O": str(O)}, "tool": "peft add_weighted_adapter"}, indent=2))
print("ok", OUT, "r =", cfg.get("r"))
