# AgriTG LLM, an offline farm adviser for Togo

An agricultural advisory model that runs on a cheap laptop with no internet. Built for the Africa
Deep Tech Challenge 2026, Laptop LLM track. Semifinalist after Round 1 (submission ADTC2026_556).

Ask it a question in plain English and it answers like a Togolese extension adviser: crops,
livestock, weather decisions and market timing, grounded in the national services (ICAT, ITRA,
ANAMET, ANSAT, CAGIA, SIM). No system prompt needed, the persona is baked into the model file.

| | |
|---|---|
| **Base model** | LFM2-700M (Liquid AI), two LoRA adapters on a bf16 base (one supervised then DPO, one supervised only), merged 0.5 and 0.5 into the shipped adapter |
| **Runtime** | llama.cpp, CPU only, fully offline |
| **Weights** | GGUF Q4_K_M, 468.6 MB (447 MiB) |
| **On the target machine** | 17.1 tok/s cold, 557 MB peak, measured on this exact file by the official profiler in its own Docker recipe, 4 threads, 7.5 GB, no GPU, no network. Section 6 of the report has all three runs, and an earlier session of the same day at 14.6 |

**What changed since Round 1.** The file is 2.4 times smaller. The base model was changed twice,
each time on a measurement and not on a preference. The training data was rebuilt from 60 curated
extension sheets with a word-for-word check on every fact. The three failures the Round 1 judges
named (deferring instead of answering, inventing names, and failing the human-medicine boundary
test) are scored requirements in our own 27 item test. The first two pass. On the third, the
shipped file refuses the human drug and names no disease on every draw of the judges' own
question, and gives no figure on any of the twenty red-team attempts to extract a dose; on one
of 64 safety passes in other wordings it still names an invented drug with an amount, and
section 5.3 of the report shows that answer rather than hides it. The shipped file is a merge
of two adapters, chosen on 21 September over six other candidates measured the same way;
section 4.4 of the report says why.

## Running it

```bash
bash download_model.sh
```

That puts the weights in `model/`. Then:

```bash
llama-cli -m model/adtc-agritgllm-adviser-v4-Q4_K_M.gguf --jinja -t 4 --temp 0.3 --min-p 0.15 --repeat-penalty 1.05
```

Those three sampling values are what Liquid AI recommends for the LFM2 family, and every number in
REPORT.md was measured with them. The model also works with llama.cpp defaults.

Two things to try:

```
Who are you, and what can you help me with?
Is a small local-hen unit profitable in the first year in Togo?
```

## What is in this repository

| file or folder | what it holds |
|---|---|
| [REPORT.md](REPORT.md) | the problem, how the base model and the quantization were chosen, what Round 1 taught us, training, benchmarks, and the Model Provenance section |
| [metadata.json](metadata.json) | submission metadata as the template defines it: team, domain, the two test prompts, the model, and the provenance object (base model source and commit, method, datasets) |
| [NOTICE.md](NOTICE.md) | base model attribution and the statement of changes the licence requires |
| [LICENSE-LFM2-700M.txt](LICENSE-LFM2-700M.txt) | the base model licence, which travels with any derivative |
| [provenance/](provenance/) | the shipped LoRA adapter and its two source adapters, the merge script, training and export scripts, per-step logs, datasets, checksums |
| [provenance/sources.md](provenance/sources.md) | the public documents the sheets were written from: URL, SHA256, size and date of each |
| [provenance/evaluation/](provenance/evaluation/) | the 27 item test, every answer the model gave on the target machine, and the wide benchmark results |
| [provenance/evaluation/target_machine/](provenance/evaluation/target_machine/) | the official profiler output, produced by running the profiler on the target machine |
| `model/` | the weights, not committed to git (see `.gitignore`) |

## References

Papers and specifications consulted while building the data pipeline, the training chain and the merge. Each one is cited where the corresponding decision is explained in REPORT.md or in `provenance/`.

Knowledge base and data

- Andrej Karpathy, *LLM Wiki* (gist, 2026). https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- Google, *Open Knowledge Format v0.2*, SPEC.md. https://github.com/GoogleCloudPlatform/open-knowledge-format
- Sewon Min et al., *FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation*, 2023. https://arxiv.org/abs/2305.14251
- Sanyam Singh et al., *Fine-Tuning and Evaluating Conversational AI for Agricultural Advisory*, 2026. https://arxiv.org/abs/2603.03294
- Zeyuan Allen-Zhu, Yuanzhi Li, *Physics of Language Models: Part 3.1, Knowledge Storage and Extraction*, 2023. https://arxiv.org/abs/2309.14316
- Zeyuan Allen-Zhu, Yuanzhi Li, *Physics of Language Models: Part 3.3, Knowledge Capacity Scaling Laws*, 2024. https://arxiv.org/abs/2404.05405
- Zitong Yang et al., *Synthetic Continued Pretraining* (EntiGraph), 2024. https://arxiv.org/abs/2409.07431
- Pratyush Maini et al., *Rephrasing the Web* (WRAP), 2024. https://arxiv.org/abs/2401.16380
- Darren Edge et al., *From Local to Global: A Graph RAG Approach to Query-Focused Summarization*, 2024. https://arxiv.org/abs/2404.16130
- Zorik Gekhman et al., *Does Fine-Tuning LLMs on New Knowledge Encourage Hallucinations?*, EMNLP 2024. https://arxiv.org/abs/2405.05904
- Hanning Zhang et al., *R-Tuning: Instructing Large Language Models to Say "I Don't Know"*, NAACL 2024. https://arxiv.org/abs/2311.09677
- Chunting Zhou et al., *LIMA: Less Is More for Alignment*, 2023. https://arxiv.org/abs/2305.11206
- Lichang Chen et al., *AlpaGasus: Training a Better Alpaca with Fewer Data*, 2023. https://arxiv.org/abs/2307.08701
- Yuetai Li et al., *Small Models Struggle to Learn from Strong Reasoners*, ACL 2025. https://arxiv.org/abs/2502.12143

Training and preference optimisation

- Edward Hu et al., *LoRA: Low-Rank Adaptation of Large Language Models*, 2021. https://arxiv.org/abs/2106.09685
- Tim Dettmers et al., *QLoRA: Efficient Finetuning of Quantized LLMs*, 2023. https://arxiv.org/abs/2305.14314
- Rafael Rafailov et al., *Direct Preference Optimization*, 2023. https://arxiv.org/abs/2305.18290
- Yu Meng et al., *SimPO: Simple Preference Optimization with a Reference-Free Reward*, 2024. https://arxiv.org/abs/2405.14734
- Noam Razin et al., *Unintentional Unalignment: Likelihood Displacement in Direct Preference Optimization*, 2024. https://arxiv.org/abs/2410.08847

Safety

- Xiangyu Qi et al., *Safety Alignment Should Be Made More Than Just a Few Tokens Deep*, 2024. https://arxiv.org/abs/2406.05946
- Federico Bianchi et al., *Safety-Tuned LLaMAs: Lessons From Improving the Safety of Large Language Models that Follow Instructions*, 2023. https://arxiv.org/abs/2309.07875

Model merging

- Mitchell Wortsman et al., *Model soups: averaging weights of multiple fine-tuned models improves accuracy without increasing inference time*, ICML 2022. https://arxiv.org/abs/2203.05482
- Prateek Yadav et al., *TIES-Merging: Resolving Interference When Merging Models*, NeurIPS 2023. https://arxiv.org/abs/2306.01708
- Le Yu et al., *Language Models are Super Mario: Absorbing Abilities from Homologous Models as a Free Lunch* (DARE), 2023. https://arxiv.org/abs/2311.03099

Tools and evaluation

- llama.cpp, https://github.com/ggerganov/llama.cpp ; Hugging Face transformers, peft, trl ; Groq structured outputs documentation ; adtc-profiler, https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler
- Liquid AI, *LFM2-700M* model card. https://huggingface.co/LiquidAI/LFM2-700M
