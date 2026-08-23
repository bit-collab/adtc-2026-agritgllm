# ADTC 2026, Agriculture track, technical report

**Model:** `adtc-agritgllm-adviser-Q4_K_M`, a fine-tuned SmolLM2-1.7B-Instruct served as GGUF Q4_K_M through llama.cpp.
**Domain:** agriculture. **Language:** English. **Target:** 8 GB laptop, CPU, fully offline.

## 1. The problem

It started with a maize field in Kara. The leaves went yellow three days after heavy rain, and the grower could not tell whether the rain had washed out the nitrogen or a disease was starting. That question has a clear answer, and it is printed in an ITRA extension sheet sitting in an office in Lomé. But there was no officer nearby that week, no data bundle on the phone, and by the time an answer could reach him the window to act was gone.

This is the ordinary case, not the exception. Togo has real agricultural institutions: ICAT for extension and advice, ITRA for research, ANAMET for weather, ANSAT and CAGIA for grain and inputs, SIM for market prices. The knowledge exists. What fails is delivery, because delivery assumes connectivity and an officer within reach.

Our target user is the extension officer covering several villages, and the literate smallholder who can read English or work with someone who can. They need an answer in the field, in seconds, with no signal. So we built an adviser that runs entirely on a cheap laptop and answers a bare question as a Togolese agricultural adviser, without needing anyone to configure a prompt first.

## 2. Design decisions

### Choosing the base model

We tested three candidates against a fixed battery of twelve domain questions covering crops, livestock, weather decisions, market timing, identity and refusal.

**Qwen3-0.6B** collapsed. Below roughly a billion parameters the model stopped holding several facts together in one answer and fell back on two or three stock replies. No amount of data fixed it.

**Qwen3-1.7B** was the interesting failure. It reasons well, but its pretraining priors fought our data. The clearest case: ask about tiny white insects under tomato leaves and it answers "aphids". We fed it corrected examples, upweighted them, ran preference optimisation against its own wrong output. It kept saying aphids. It also ships a hybrid reasoning mode that emits `<think>` blocks, which costs tokens against a throughput score and looks like scratch work to anyone reading the output.

**SmolLM2-1.7B-Instruct** won on the property that actually mattered, which was not benchmark reasoning but willingness to be corrected. It learned the whitefly distinction that Qwen3 refused. It is English-native, built for on-device use, and has no reasoning mode to suppress. That is the model we shipped.

The lesson we would keep: for narrow domain adaptation on a small model, how easily a base model yields to your data matters more than where it sits on a leaderboard.

### Choosing the quantization

We exported both **Q4_K_M** and **Q5_K_M** and benchmarked them on the same twelve questions rather than assuming the higher bit width would be better.

Q5_K_M ran at 13.5 tok/s against 18.3 for Q4_K_M under llama-server, a 26 percent penalty. It bought nothing in return. Two answers were actually worse: it called fall armyworm damage "maize stalk-borers", and it suggested milk powder as goat feed. We had assumed the small quality drift we saw in Q4 came from quantization. Measuring showed it came from the 1.7B model itself, so paying for Q5 was pointless.

Q4_K_M ships: 1.0 GB on disk, more throughput headroom, more room under the memory budget, same answer quality.

### Training

Fine-tuning was 4-bit QLoRA with Unsloth, rank 32 and alpha 64 across all attention and MLP projections. Supervised fine-tuning ran to a ceiling of three epochs with the best checkpoint selected on validation loss and early stopping armed. It converged near 2.5 epochs, which matches the general guidance that instruction tuning past three epochs mostly buys overfitting. A short DPO pass afterwards handled facts that supervised training left ambiguous.

Two things are baked into the exported GGUF rather than left to the caller. The chat template is plain ChatML with no reasoning block, identical in training, inference and export, so the model cannot emit `<think>`. And a default persona is embedded in that template, so a bare question with no system prompt still gets answered by a Togolese adviser. Judges test the raw model, so anything not baked in does not exist.

### Where most of the work went

Very little of the effort was hyperparameters. Almost all of it was diagnosing what the model had actually learned.

**It thought it was Kenyan.** A first run, asked which country it served, answered Kenya, and described ICAT as a Nairobi organisation. The cause was a few hundred conversations carrying Kenyan institutional names from an upstream source. With no system prompt to anchor it, the model took the only explicit geography it had seen. We removed those conversations and wrote identity examples that state the Togolese institutions plainly.

**It refused questions it could answer.** The next run was polite and useless: ask whether to sell or store maize and it deferred to an extension officer. Counting turns in the training data explained it. Around 38 percent of assistant turns ended by referring the farmer somewhere else, and 63 percent of conversations closed on a deflection. At inference a single question resembles a closing turn, so the model fired its most reinforced reflex. We stripped the reflexive referral sentences from answers that had already answered, and cut the pure-deflection closers. Referrals fell to under 10 percent and the pillar questions came back to life, while genuine refusal on out-of-scope questions was preserved deliberately.

**Some facts would not move.** Whitefly against aphid resisted everything until we made the correct signal loud, roughly ten to one against the competing examples, and capped the competing ones. The same treatment fixed dry-season goat feeding and tick-borne disease naming. Preference optimisation could not do this on its own. When a base model is confident and wrong, the fix belongs in the training data, not in a later alignment pass.

### Alternatives we rejected

Full fine-tuning was out on 6 GB of VRAM and would not have helped. GRPO needs a programmatic reward, and there is no automatic scorer for whether agronomic advice is sound, so it does not fit this task. A larger base would have cost throughput and memory for accuracy we did not need at this scale.

## 3. Constraints

Training hardware was an RTX 3050 laptop with 6 GB of VRAM, which ruled out anything but 4-bit QLoRA and required gradient offloading to fit.

The deployment target is stricter than the training box in the ways that matter: 8 GB of RAM, 4 vCPU, integrated graphics, CPU inference, and no network at all during evaluation.

Language was a constraint in a less obvious way. Judging happens in English while most Togolese and West African source material is in French, so every training answer had to be written in English while keeping the agronomy local. Fodder species, planting calendars, pest pressure and market institutions are regional facts, and a model that answers correctly in English about Kenyan conditions is still wrong here.

## 4. Benchmarks

Measured with the official ADTC profiler in participant mode, CPU-only llama.cpp build, `measured_on: participant_laptop`.

| Metric | Value | Score component |
|---|---|---|
| Generation throughput | 32.84 tok/s | `S_perf = min(32.84/15, 1)*100` = 100 |
| Peak RSS | 1958 MB (1.91 GB) | `S_eff = (7-1.91)/7*100` = 72.7 |
| Steady-state RSS | 1840 MB | |
| First-token latency | 4531 ms on a 512-token prompt | |
| CPU throttled | false | `P_thermal` = 0 |
| Parameters detected against claimed | 1,711,378,432 against 1.7B, match | integrity check passed |

Peak memory of 1.91 GB against a 7 GB budget leaves a wide margin, so there is no realistic path to an out-of-memory failure on the target profile.

One caveat we would rather state than have discovered. The development laptop exposes 16 logical cores while the evaluation profile allows 4 vCPU, so generation throughput on the evaluation host will be lower than 32.84 tok/s. We expect roughly 15 to 20 tok/s there, which still meets or exceeds the 15 tok/s reference. Preserving that margin is precisely why we kept Q4_K_M after measuring Q5_K_M. Core temperature was not readable through the sensor on this machine, so the `false` throttling result reflects no observed throttling rather than a verified temperature ceiling.

On the twelve-question battery, run against the quantized GGUF with no system prompt, the model identifies itself as a Togo adviser, distinguishes whiteflies from aphids, recognises cassava mosaic disease, names anaplasmosis and babesiosis for a tick-borne presentation, gives locally available dry-season goat fodder, handles the maize whorl caterpillar, advises waiting before sowing beans into saturated soil, recommends drying and storing maize rather than selling into the post-harvest price trough, declines to advise on Kenya, and refuses to invent instructions for building a solar pump, deferring to ICAT instead.

## 5. Running the model

`download_model.sh` fetches the published GGUF into `model/`, after which it runs
through llama.cpp with no network access at any point.

The pipeline that produced it, described in section 2, ran in this order: 4-bit
QLoRA supervised fine-tuning with Unsloth on the conversation dataset, with the
best checkpoint selected on validation loss and early stopping armed; a short DPO
pass on hand-written preference pairs built from the model's own wrong answers;
then a merge and export to GGUF Q4_K_M, with the non-thinking chat template and
the Togo persona baked into the model file itself.

## 6. Open-source tools used

| Tool | Licence | What we used it for |
|---|---|---|
| [llama.cpp](https://github.com/ggml-org/llama.cpp) | MIT | GGUF conversion, quantization, CPU inference, `llama-bench` |
| [SmolLM2-1.7B-Instruct](https://huggingface.co/HuggingFaceTB/SmolLM2-1.7B-Instruct) | Apache 2.0 | base model |
| [Unsloth](https://github.com/unslothai/unsloth) | Apache 2.0 | 4-bit QLoRA training and GGUF export |
| [TRL](https://github.com/huggingface/trl) | Apache 2.0 | `SFTTrainer` and `DPOTrainer` |
| [PEFT](https://github.com/huggingface/peft) | Apache 2.0 | LoRA adapters |
| [Transformers](https://github.com/huggingface/transformers) / [Datasets](https://github.com/huggingface/datasets) | Apache 2.0 | tokenisation, chat templates, data pipeline |
| [bitsandbytes](https://github.com/bitsandbytes-foundation/bitsandbytes) | MIT | 4-bit quantized training |
| [PyTorch](https://github.com/pytorch/pytorch) | BSD-3-Clause | training runtime |
| [Trackio](https://huggingface.co/docs/trackio) | Apache 2.0 | training and validation loss monitoring |
| [adtc-profiler](https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler) | GPL-3.0 | the benchmark numbers in section 4 |

Method reference: the grounded conversation-generation approach follows [Agri-LLaVA](https://arxiv.org/abs/2412.02158), which builds a structured knowledge base first and generates conversations anchored to it to limit hallucination.

Domain knowledge is drawn from Togolese and West African agricultural extension material, and from open agricultural sources including FAO post-harvest guidance, APHLIS loss data and ICRISAT material.
