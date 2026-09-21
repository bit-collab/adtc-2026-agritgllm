# Dataset information

Every file named here is in this folder and its SHA256 is in `provenance/checksums.txt`.
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

## Base model and adapter

Base: `LiquidAI/LFM2-700M`, Hugging Face commit `86f49fc9a3800c3a325b7320bde179c318062583`,
LFM Open License v1.0 (`LICENSE-LFM2-700M.txt`). Adapter: LoRA rank 32, alpha 64, on every
linear layer, trained on the bf16 base, then one DPO pass; `adapter/adapter_model.safetensors`,
sha256 `8e4e4b5684fb174b309a57812dbd99407ab7bc786bb73a1d455f80968863d445`. Merge and
quantization: `03_export.py`, run log in `export_manifest.json`.
