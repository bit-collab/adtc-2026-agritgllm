# AgriTG LLM, an offline farm adviser for Togo

An agricultural advisory model that runs on a cheap laptop with no internet, built for the Africa Deep Tech Challenge 2026 Laptop LLM track.

Ask it a question in plain English and it answers as a Togolese agricultural adviser: crops, livestock, weather decisions and market timing, grounded in the national services (ICAT, ITRA, ANAMET, ANSAT, CAGIA, SIM). No system prompt needed, the persona is baked into the model file.

- **Base:** SmolLM2-1.7B-Instruct, fine-tuned with QLoRA and a DPO pass
- **Runtime:** llama.cpp. **Weights:** GGUF Q4_K_M, about 1.0 GB
- **Measured:** 32.84 tok/s generation, 1.91 GB peak RSS, no throttling

## Running it

```bash
bash download_model.sh
```

That pulls the weights into `model/`. From there, point llama.cpp at the file and ask it something:

```
My tomato leaves have tiny white insects underneath and are turning yellow. What is wrong?
```

Read **[REPORT.md](REPORT.md)** for the problem it solves, why this base model and this quantization won over the alternatives we measured, and the full benchmark numbers from the official ADTC profiler. **[metadata.json](metadata.json)** holds the submission metadata and the test prompts.
