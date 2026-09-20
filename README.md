# AgriTG LLM, an offline farm adviser for Togo

An agricultural advisory model that runs on a cheap laptop with no internet. Built for the Africa
Deep Tech Challenge 2026, Laptop LLM track. Semifinalist after Round 1 (submission ADTC2026_556).

Ask it a question in plain English and it answers like a Togolese extension adviser: crops,
livestock, weather decisions and market timing, grounded in the national services (ICAT, ITRA,
ANAMET, ANSAT, CAGIA, SIM). No system prompt needed, the persona is baked into the model file.

| | |
|---|---|
| **Base model** | LFM2-700M (Liquid AI), LoRA on a bf16 base, supervised fine-tuning then DPO |
| **Runtime** | llama.cpp, CPU only, fully offline |
| **Weights** | GGUF Q4_K_M, 468.6 MB (447 MiB) |
| **On the target machine** | 15.6 tok/s cold, 557 MB peak, official profiler on 8 GB RAM / 4 vCPU / no GPU. Section 6 of the report says exactly which file was measured and how |

**What changed since Round 1.** The file is 2.4 times smaller. The base model was changed twice,
each time on a measurement and not on a preference. The training data was rebuilt from 60 curated
extension sheets with a word-for-word check on every fact. The three failures the Round 1 judges
named (deferring instead of answering, inventing names, and failing the human-medicine boundary
test) are scored requirements in our own 27 item test. The first two pass. On the third, the
dangerous half is gone: across every draw we ran, the model never gives a human drug dose for an
animal, under any wording we tried. It still sometimes names a disease from the signs, which we
also count as a failure, and section 5.3 of the report says so.

## Running it

```bash
bash download_model.sh
```

That puts the weights in `model/`. Then:

```bash
llama-cli -m model/adtc-agritgllm-adviser-v3-Q4_K_M.gguf --jinja -t 4 --temp 0.3 --min-p 0.15 --repeat-penalty 1.05
```

Those three sampling values are what Liquid AI recommends for the LFM2 family, and every number in
REPORT.md was measured with them. The model also works with llama.cpp defaults.

Something to try:

```
My tomato leaves have tiny white insects underneath and are turning yellow. What is wrong?
```

## What is in this repository

| file or folder | what it holds |
|---|---|
| [REPORT.md](REPORT.md) | the problem, how the base model and the quantization were chosen, what Round 1 taught us, training, benchmarks, and the Model Provenance section |
| [metadata.json](metadata.json) | submission metadata as the profiler's schema defines it: team, domain, the two test prompts, the model, and the commit of the base model it was built from |
| [NOTICE.md](NOTICE.md) | base model attribution and the statement of changes the licence requires |
| [LICENSE-LFM2-700M.txt](LICENSE-LFM2-700M.txt) | the base model licence, which travels with any derivative |
| [provenance/](provenance/) | LoRA adapter, training and export scripts, per-step logs, dataset, checksums |
| [provenance/evaluation/](provenance/evaluation/) | the 27 item test, every answer the model gave on the target machine, and the wide benchmark results |
| `submission.json` | the official profiler output. It is produced by running the profiler on the target machine, not written by hand, so it is added once that run is done and is absent until then. |
| `model/` | the weights, not committed to git (see `.gitignore`) |
