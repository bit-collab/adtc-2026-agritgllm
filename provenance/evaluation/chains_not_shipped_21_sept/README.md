# Five variants trained and measured on the night of 20 to 21 September, none shipped

The shipped file is unchanged. This folder is the record of what was tried after chain L
(see `../chain_L_not_shipped/`), on the same frozen instruments, with a decision rule written
before the numbers existed (`decide.py`, docstring at the top). Section 4.3 of `REPORT.md`
tells the story; this file is the map of the evidence.

## The variants

| Tag | Training data | SFT | DPO | What it tested |
|---|---|---|---|---|
| Mdpo | L's data + lots T and U (30 lines), eight-paraphrase cap kept | new (M) | 2,814 rows + 145 on-policy safety pairs x3 | safety pairs at 13 percent of the DPO set |
| Ndpo | same | same M | 2,814 + 145 x1 | the same pairs at 5 percent |
| Msft | same | same M | none | the SFT alone |
| Osft | same lots, cap lifted (8,146 lines) | new (O) | none | the cap as the cause of the loss on unseen sheets |
| Odpo | same | same O | 2,814 + 139 x1 | DPO on the uncapped SFT |

## The numbers, four draws per battery, two per red-team

| | v3 (shipped) | L | Mdpo | Ndpo | Msft | Osft | Odpo |
|---|---|---|---|---|---|---|---|
| Round 1 battery /27 | 21.00 | 21.75 | 20.25 | 20.50 | 20.75 | 21.25 | 20.25 |
| Held-out battery /27 | 16.25 | 17.50 | 16.00 | 14.50 | 17.00 | 16.50 | 14.75 |
| Safety items /64 | 44 | 45 | 48 | 44 | 48 | 49 | 47 |
| Red-team regex /23, two draws | 19, 22 | 22, 21 | 20, 22 | 20, 22 | 21, 22 | 20, 23 | 21, 23 |
| Dose leaks, two draws | 2 | 3 | 4 | 2 | 1 | 1 | 3 |
| Migrating formulas, two draws | 5, 6 | 4, 2 | 3, 2 | 2, 3 | 4, 2 | 1, 1 | 2, 2 |
| Wide benchmark, unseen sheets | 0.393 | 0.327 | 0.317 | 0.317 | 0.293 | 0.350 | 0.317 |
| Wide benchmark, taught sheets | 0.720 | 0.707 | 0.710 | 0.710 | 0.780 | 0.790 | 0.777 |
| Rule | | v3 stays | v3 stays | v3 stays | v3 stays | v3 stays | v3 stays |

Standard error of the wide benchmark is about 0.04 at 150 questions. The same adapter (M)
quantised with and without an importance matrix scored 17.0 and 15.5 on the held-out battery;
those files are in `instrument_noise_same_adapter_two_quantisations/`.

## What is in the folder

- `lots/` the two hand-written lots, appended through `../../data/lots/append_gold.py` with
  its guards (no dose figure in a refusal, no meta leak, 40 to 200 words).
- `tools/sample_safety.py` samples twelve answers per lot question from a GGUF and sorts them by
  rules (dose regex, health-centre regex, agronomy drift, vomiting advice); the rejected side of
  a pair is always an answer the model gave, the chosen side always the hand-written one.
  `tools/build_dpo_safety_x3.py` and `_x1.py` add the pairs to the DPO set. The chain scripts
  are the exact sequence run for each variant; `$WORK` stands for a scratch directory.
- `onpolicy_safety/` every sample and every pair, by source model.
- `training/` SFT configs and logs for M and O, DPO logs and safety manifests, the two split
  manifests (capped and uncapped).
- `export/` export manifests and checksums for the five GGUF files. The files themselves are
  not in the repository; their sha256 are in the checksums.
- `batteries_4seeds/`, `redteam/`, `before_after_11_prompts/`, `bench_150x2/` the raw outputs.
- `decisions/` the output of `decide.py` for each variant.

## What we keep from it

The lots work through SFT and DPO undoes them. The cap costs generalisation. The instruments
are noisier than one point on 27 items. The next chain, after the jury, starts from the
uncapped SFT with the lots, and looks for a preference method that does not pull the model
toward the base voice; the identity answers are where that drift shows first.
