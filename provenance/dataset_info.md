# Dataset information

Every file named here is in this folder and its SHA256 is in `provenance/checksums.txt`. Two
chains contributed to the shipped adapter (see `REPORT.md` 4.4); their data are listed apart.
`REPORT.md` section 4.1 explains how the data was built; `data/handwritten_repairs.md` traces
every hand-written lot to the measurement that motivated it.

## Names, sources, sizes

| name | file | size | source |
|---|---|---|---|
| agritgllm-gate2-sft (train) | `data/sft_train.jsonl` | 7,987 conversations | 60 extension sheets on Togolese crops, livestock, weather and markets, written from the public material of ICAT, ITRA, ANAMET, ANSAT, CAGIA and the SIM market information service, then turned into questions and answers by the pipeline in `REPORT.md` 4.1 (writer, judge, deterministic linter) plus about 1,300 hand-written lines |
| agritgllm-gate2-sft (eval) | `data/sft_eval.jsonl` | 382 | 8 percent of the fact bundles of the sheets above, held out of training |
| agritgllm-gate2-sft (test) | `data/sft_test.jsonl` | 344 | three whole sheets never seen in training: cassava brown streak, small ruminant PPR, sorghum striga |
| agritgllm-gate2-dpo | `data/dpo_train.jsonl` | 2,817 pairs | the same sheets: 655 pairs that differ by one invented sentence, and on-policy pairs where the rejected side is the model's own answer sorted by a judge |
| split | `data/split_manifest.json` | | which sheets and which facts are held out, with the leakage checks |
| agritgllm-gate2-sft-o (train) | `data_o/sft_train.jsonl` | 8,146 conversations | chain O: the same sheets and pipeline without the eight-paraphrase cap per fact, the 39 hand-written pairs of lots O to S (framing, harmful intent, too few signs, what the model holds about itself, banned pesticides in Togo) and the 30 of lots T and U (a person exposed to a product; refusals that hold under pressure), four questions identical to held-out battery items removed |
| agritgllm-gate2-sft-o (eval, test) | `data_o/sft_eval.jsonl`, `data_o/sft_test.jsonl` | 327, 344 | same rule as above; the three test sheets are the same |
| split of chain O | `data_o/split_manifest.json` | | |

No external instruction-tuning corpus, no benchmark data and no data from the judging report
were used in training. The 27 questions of the held-out battery were written on 19 September
2026 after the training set was built; four of them were later found word for word in two
repair lots and that is recorded in `REPORT.md` 5.2.

## Checksums

```
f1db4987525f9583b922a8afa35c0478473e473bac201ae4cecf0e7ee78bf118  provenance/data/sft_train.jsonl
3889db525dbe9eddba825dcf69b118f016716792f0395f4b8a1987ba9cda4946  provenance/data/sft_eval.jsonl
97166049bc255ef895d2758ed07528a46103576c06a09632c47888fabfe2a16f  provenance/data/sft_test.jsonl
1901ccb621965e1a6e3bfc55396156cdaedc29d31ced8a608e25d2dbea36f330  provenance/data/dpo_train.jsonl
7ed6526a38c9511583ac2987765de7fac7b9a5b0342cdf69fa8f35653a99a85e  provenance/data/split_manifest.json
```

## Base model and adapters

Base: `LiquidAI/LFM2-700M`, Hugging Face commit `86f49fc9a3800c3a325b7320bde179c318062583`,
LFM Open License v1.0 (`LICENSE-LFM2-700M.txt`). Two LoRA adapters, rank 32, alpha 64, on every
linear layer, trained on the bf16 base: `adapter_sources/kdpo/` (chain K, supervised then one
DPO pass, the file measured on the replica on 20 September) and `adapter_sources/o_sft/`
(chain O, supervised only). The shipped adapter, `adapter/adapter_model.safetensors`, is their
merge at 0.5 and 0.5, rank 64, made by `merge_adapters.py` and described in `adapter/MERGE.json`.
Merge into the base and quantization: `03_export.py`, run log in `export_manifest.json`.
Every sha256 is in `checksums.txt`.
