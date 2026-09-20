# NOTICE - base model attribution and statement of changes

This work contains a **Derivative Work** of a model licensed under the **LFM Open License v1.0**.
This file satisfies clause 4(b) of that licence ("cause any modified files to carry prominent
notices stating that You changed the files"). The full licence text is in
[LICENSE-LFM2-700M.txt](LICENSE-LFM2-700M.txt) and travels with every copy of this work.

## Base model

| | |
|---|---|
| Name | **LFM2-700M** |
| Author | **Liquid AI, Inc.** |
| Source | https://huggingface.co/LiquidAI/LFM2-700M |
| Revision used | `86f49fc9a3800c3a325b7320bde179c318062583` |
| Licence | LFM Open License v1.0 |

The LFM Open License v1.0 is an **open-weights licence, not an OSI-approved open-source licence**:
it grants a perpetual, worldwide, royalty-free right to use, modify and redistribute, but restricts
Commercial Use by a Legal Entity whose annual revenue reaches ten million United States dollars
($10,000,000) or more. Team agritgllm is far below that threshold, so the grant applies in full.
We state this plainly rather than describing the base model as "open source", which it is not in
the OSI sense.

Liquid AI's trade names, trademarks and product names are used here only to identify the origin of
the base model, as clause 6 of the licence permits. No endorsement by Liquid AI is claimed or
implied.

## Statement of changes (clause 4(b))

The base model was modified as follows. Nothing else in the weights was touched.

1. **Supervised fine-tuning with LoRA** (rank 32, alpha 64) applied to every linear layer:
   `q_proj`, `k_proj`, `v_proj`, `out_proj` (attention), `in_proj`, `out_proj` (short convolution),
   and `w1`, `w2`, `w3` (feed-forward). The base weights were held frozen in bf16 during training;
   only the adapter was trained.
2. **The adapter was merged** back into the base weights (`merge_and_unload()`), producing modified
   weight tensors. The adapter itself is shipped separately in `provenance/adapter/` so that the
   modification can be inspected and reproduced.
3. **The chat template was replaced.** The base model's template was substituted with a plain
   ChatML template that bakes a fixed system persona into every conversation. The template text is
   recorded in `provenance/export_manifest.json`.
4. **Conversion and quantisation to GGUF** (Q4_K_M / Q5_K_M / Q6_K) with llama.cpp, which changes
   the numerical precision of every tensor.

No source file of the base model was edited; the modification is to the weights and to the
packaging. The scripts that performed each step are in `provenance/` (`01_sft.py`, `03_export.py`,
`config.py`), and the per-step training logs are in `provenance/training_log.csv`.

## Other components

llama.cpp (MIT), Hugging Face transformers / peft / trl / datasets (Apache-2.0), bitsandbytes
(MIT), PyTorch (BSD-3-Clause). Cited in REPORT.md section 9.
