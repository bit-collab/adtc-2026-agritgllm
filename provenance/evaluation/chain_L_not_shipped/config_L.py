from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "rebuild-gate2" / "out" / "train"
PAIRS = ROOT / "rebuild-gate2" / "out" / "pairs"
SPLIT = HERE / "data"
OUT = HERE / "outputs"
PROV = HERE / "provenance"

BASE_MODELS = {
    "A": {"id": "Qwen/Qwen3-0.6B",            "revision": "main", "params": "0.6B"},
    "B": {"id": "ibm-granite/granite-4.0-350m", "revision": "main", "params": "0.35B"},
    "D": {"id": "LiquidAI/LFM2-700M",         "revision": "86f49fc9a3800c3a325b7320bde179c318062583", "params": "0.70B"},
}
EXPERIMENT = "D"
BASE_MODEL = BASE_MODELS[EXPERIMENT]["id"]
BASE_REVISION = BASE_MODELS[EXPERIMENT]["revision"]

MAX_SEQ = 1024
LOAD_IN_4BIT = True

HELD_OUT_GOLD_TOPICS = ["mixing_chemicals"]

TEST_FICHES = [
    "cassava_brown_streak", "small_ruminant_ppr", "sorghum_striga",
]
EVAL_BUNDLE_FRACTION = 0.08

ANSWER_VARIANTS = 0

EXPOSE_PER_FACT = 8
ONPOLICY_PER_FACT = 4

LORA_R = 32
LORA_ALPHA = 64
LORA_DROPOUT = 0.0
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

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


def use_4bit_for(base_id: str) -> bool:
    return LOAD_IN_4BIT and family_of(base_id) != "lfm2"

SFT_OUT = OUT / "sft"
SFT_LR = 2e-4
SFT_EPOCHS = 3
SFT_BATCH = 2
SFT_GRAD_ACCUM = 8
SFT_WARMUP_RATIO = 0.05
SFT_WEIGHT_DECAY = 0.01
SFT_PATIENCE = 3
GRAD_CKPT = True

DPO_OUT = OUT / "dpo"
DPO_LR = 5e-6
DPO_EPOCHS = 1
DPO_BETA = 0.1
DPO_BATCH = 1
DPO_GRAD_ACCUM = 8
DPO_SOURCES = ["trim", "onpolicy"]

MERGED = OUT / "merged"
GGUF = OUT / "gguf"
ANSWERS = OUT / "answers"
QUANTS = ["Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M"]

import os as _os
LLAMA_CPP = Path(_os.environ.get("LLAMA_CPP_REPO", ROOT / "adtc-2026" / "llama.cpp"))
LLAMA_BIN = Path(_os.environ.get("LLAMA_BIN", ROOT / "tools" / "llama-cpu"))
CONVERT_HF = LLAMA_CPP / "convert_hf_to_gguf.py"

IMATRIX_CHUNKS = 400
IMATRIX_CTX = 512

TARGET_THREADS = 4
AUDIT_SPEED_FACTOR = 0.5
ROUND1_GGUF = ROOT / "adtc-submission" / "model" / "adtc-agritgllm-adviser-Q4_K_M.gguf"
ROUND1_AUDIT_TOK_S = 3.20

BAKED_SYSTEM = (
    "You are AgriTG, an offline agricultural adviser for Togo. You help smallholder farmers "
    "and extension officers across Maritime, Plateaux, Centrale, Kara and Savanes with crops, "
    "livestock, weather and market advice, grounded in the Togolese services ICAT, ITRA, "
    "ANAMET, ANSAT, CAGIA and SIM. Answer directly and practically, in clear English. Never "
    "give a human medicine, a pesticide dose or a dilution ratio, and never name a disease you "
    "cannot support from what the farmer described."
)

SEED = 23
