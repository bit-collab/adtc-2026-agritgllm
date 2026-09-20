# Evaluation files

Everything here was produced on the **target machine** (8 GB RAM, 4 vCPU Intel i5, integrated
graphics, no network), except where the filename says `dev_laptop`.

## The test set

| file | what it is |
|---|---|
| `acceptance_27_items.jsonl` | the 27 questions and the pass rules for each one |
| `acceptance_scorer_dev_laptop.py` | the scorer used on the development laptop, checks every rule |
| `score.py` | the scorer used on the target machine, leaves 8 rules to human reading |
| `ask.py`, `gen.sh` | how the answers were generated on the target machine |

The 27 items are: the 5 automated prompts from Round 1, the 6 judge questions, and 16 we added
after tracing how the automated prompts were built. Two of the five automated prompts were our own
declared test prompts run word for word, and three were generated from sentences in our README.

## The results

| file | what it is |
|---|---|
| `scores_target_machine.json` | pass/fail per item for the three quantizations |
| `answers_Q4_K_M_target_machine.md` | every answer Q4_K_M gave, with timing and the failure reason |
| `answers_Q5_K_M_target_machine.md` | same for Q5_K_M |
| `answers_Q6_K_target_machine.md` | same for Q6_K |
| `answers_v2-*.jsonl` | the same answers in machine-readable form |

Generation settings on the target machine: llama.cpp b10220, `--jinja`, temperature 0.3,
min_p 0.15, repeat penalty 1.05, 400 token cap, seed 42, no system prompt (the persona is baked
into the GGUF, which is how a judge sees it).

Summary: **Q4_K_M 18/27, Q5_K_M 17/27, Q6_K 19/27**. The untuned base model scores 2/27.

## Why these numbers are lower than the development laptop

The same 27 items scored 20/27 for Q4_K_M on our development laptop. Two differences, both of
which make the target machine stricter:

1. **Sampling.** The laptop ran greedy decoding at temperature 0. The target machine ran the
   sampling we actually recommend in the README (temperature 0.3, min_p 0.15), which is what a
   judge following our instructions will use.
2. **Scorer.** The laptop scorer checks all rules automatically, including ones like "must refuse"
   and "must give a verdict". The target machine scorer marks those 8 rules `manuel` and does not
   grant them, so any item carrying one of those rules can only pass on the rules a machine can
   check.

We report the target machine numbers.

## The wide benchmark

| file | what it is |
|---|---|
| `widebench_learned_facts.json` | 150 questions on facts the model was trained on, 2 draws each |
| `widebench_unseen_sheets.json` | 150 questions on the 5 sheets held out of training |

Each file carries `pass_at_1` with its standard error, `pass_pow_k` (clean on both draws),
`grounding`, `similarity` (word overlap between the two draws), and the count of each fault type.
These were scored by the same deterministic linter that grades the training data, so no model
judges the results.
