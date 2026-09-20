# -*- coding: utf-8 -*-
"""STEP 3 - merge the adapter, convert to GGUF, calibrate an imatrix, quantise. And write down
everything rule 3.1 asks for while doing it.

What comes out of here is what the jury talks to: a bare GGUF, no RAG, no application, no system
prompt sent by the caller. Three things therefore have to be baked into the file itself.

  1. THE TEMPLATE. The adapter folder carries the TRAINING template, which marks the assistant
     content with a {% generation %} block so TRL can build the loss mask. That marker has no
     meaning outside training and llama.cpp's jinja engine has no reason to accept it, so it must
     not reach the GGUF. Export installs the same ChatML, without the markers, plus the persona.
  2. THE PERSONA. The jury sends a user turn and nothing else. If the persona is not in the
     template, the model has no idea it is AgriTG - and three of the five hidden prompts of
     round 1 were about the model itself.
  3. NO THINKING BLOCK. Qwen3's stock template writes "<think>\\n\\n</think>" into every answer.
     That is pure token cost on the criterion that weighs 0.30. The script stops if it sees one.

Honest about one thing: the LoRA was trained against an NF4-quantised base and is merged here
into the fp16 base. That is the standard QLoRA export and it is an approximation - the fp16
weights the adapter is added to are not bit-for-bit the ones it saw. That is exactly why
04_compare.py measures the GGUF and never the adapter: the acceptance test must run on the
artefact we actually submit.

Usage (TRAINING venv), from concoursllmdata/ :
    .venv-train\\Scripts\\python train-gate2\\03_export.py                 # DPO adapter if present
    .venv-train\\Scripts\\python train-gate2\\03_export.py --adapter outputs/sft/A/best_lora
    .venv-train\\Scripts\\python train-gate2\\03_export.py --with-base     # + the untuned base GGUF
    .venv-train\\Scripts\\python train-gate2\\03_export.py --quants Q4_K_M --skip-imatrix   (quick)

Produces
    outputs/merged/<tag>/                  the merged fp16 model (kept: it is the conversion input)
    outputs/gguf/<tag>/*.gguf              F16 + one file per quantisation, imatrix-calibrated
    outputs/gguf/<tag>/imatrix.dat         the importance matrix, and the calibration text
    provenance/<tag>/export_manifest.json  every command run, with its return code and duration
    provenance/<tag>/metadata.json         rule 3.1: base model, commit, checksums, sizes
    provenance/<tag>/checksums.txt         sha256, one line per artefact
"""
from __future__ import annotations
import argparse, hashlib, json, os, platform, subprocess, sys, time
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

CHATML_NOSYS = (
    "{%- for m in messages %}"
    "{{- '<|im_start|>' + m['role'] + '\n' + m['content'] + '<|im_end|>\n' }}"
    "{%- endfor %}"
    "{%- if add_generation_prompt %}{{- '<|im_start|>assistant\n' }}{%- endif %}")


def baked_template(system: str) -> str:
    """ChatML that inserts `system` when the caller sends none - which is what the jury does.

    Deliberately plain: no slicing, no {% set %}, no filters. This template is executed by
    llama.cpp's own jinja engine (minja), not by the Python one, and minja implements a subset.
    A template that renders here and fails there would only show up as a broken answer in front
    of the jury. If the caller DOES send a system message, it is rendered by the loop like any
    other turn and no persona is prepended."""
    lit = system.replace("\\", "\\\\").replace("'", "\\'")
    return (
        "{%- if not (messages and messages[0]['role'] == 'system') %}"
        f"{{{{- '<|im_start|>system\\n' + '{lit}' + '<|im_end|>\\n' }}}}"
        "{%- endif %}"
        "{%- for m in messages %}"
        "{{- '<|im_start|>' + m['role'] + '\n' + m['content'] + '<|im_end|>\n' }}"
        "{%- endfor %}"
        "{%- if add_generation_prompt %}{{- '<|im_start|>assistant\n' }}{%- endif %}")


def baked_template_gemma(system: str) -> str:
    """Same idea for Gemma: its own markers, the assistant role called "model", and the persona
    merged into the FIRST user turn because Gemma has no system role. Kept as plain as the ChatML
    one - minja runs it inside llama.cpp, not Python."""
    lit = system.replace("\\", "\\\\").replace("'", "\\'")
    return (
        "{%- for m in messages %}"
        "{%- if m['role'] == 'assistant' or m['role'] == 'model' %}"
        "{{- '<start_of_turn>model\n' + m['content'] + '<end_of_turn>\n' }}"
        "{%- elif m['role'] == 'system' %}"
        "{{- '<start_of_turn>user\n' + m['content'] + '<end_of_turn>\n' }}"
        "{%- else %}"
        "{{- '<start_of_turn>user\n' }}"
        f"{{%- if loop.first %}}{{{{- '{lit}' + '\\n\\n' }}}}{{%- endif %}}"
        "{{- m['content'] + '<end_of_turn>\n' }}"
        "{%- endif %}{%- endfor %}"
        "{%- if add_generation_prompt %}{{- '<start_of_turn>model\n' }}{%- endif %}")


def human(sec):
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def sha256(path: Path, blocks=1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(blocks), b""):
            h.update(chunk)
    return h.hexdigest()


def mb(path: Path) -> float:
    return round(path.stat().st_size / (1 << 20), 1)


def run(cmd, log, what, cwd=None):
    """Run one external command, echo it, keep it in the manifest. Stops the script on failure."""
    cmd = [str(c) for c in cmd]
    printable = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    print(f"\n$ {printable}\n", flush=True)
    t0 = time.time()
    r = subprocess.run(cmd, cwd=str(cwd) if cwd else None)
    took = round(time.time() - t0, 1)
    log.append({"step": what, "cmd": cmd, "returncode": r.returncode, "seconds": took})
    if r.returncode != 0:
        print(f"ARRET : '{what}' a echoue (code {r.returncode}) apres {human(took)}.")
        sys.exit(2)
    print(f"  [{what} OK en {human(took)}]")
    return took


def git_sha(path: Path):
    try:
        r = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None
    except Exception:
        return None


def binary_version(exe: Path):
    try:
        r = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=30)
        out = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
        return out[0] if out else None
    except Exception:
        return None


def read_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def write_calibration(tok, path: Path) -> dict:
    """The imatrix calibration text: our own training conversations, rendered exactly the way the
    served model renders them. Train split ONLY - the five test fiches stay out, or the
    quantisation would be steered by the very text the test pretends not to know.

    Full conversations, not the questions alone: the importance matrix weighs the activations the
    model produces, and at serving time most of those tokens are the ANSWER."""
    rows = read_jsonl(C.SPLIT / "sft_train.jsonl")
    blocks, questions = [], set()
    for r in rows:
        blocks.append(tok.apply_chat_template(r["messages"], tokenize=False))
        for m in r["messages"]:
            if m["role"] == "user":
                questions.add(m["content"])
    text = "\n".join(blocks)
    path.write_text(text, encoding="utf-8")
    ntok = len(tok(text).input_ids)
    return {"file": str(path), "conversations": len(rows), "unique_questions": len(questions),
            "characters": len(text), "tokens": ntok,
            "source": "train-gate2/data/sft_train.jsonl (train split only, no test fiche)"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default=C.EXPERIMENT)
    ap.add_argument("--adapter", default=None,
                    help="default: outputs/dpo/<tag>/best_lora if it exists, else the SFT one")
    ap.add_argument("--quants", nargs="*", default=C.QUANTS)
    ap.add_argument("--skip-imatrix", action="store_true",
                    help="quantise without the importance matrix (faster, measurably worse)")
    ap.add_argument("--reuse-imatrix", action="store_true",
                    help="reuse outputs/gguf/<tag>/imatrix.dat instead of recomputing it (13 min "
                         "on this bench). Only valid while the F16 it was computed from is the "
                         "same file - it is keyed to those weights, not to the quantisation.")
    ap.add_argument("--imatrix-chunks", type=int, default=C.IMATRIX_CHUNKS,
                    help="0 = the whole calibration file")
    ap.add_argument("--with-base", action="store_true",
                    help="also convert the UNTUNED base to Q4_K_M - the 'before' of rule 3.1")
    ap.add_argument("--no-system", action="store_true",
                    help="bake the template but not the persona (an ablation, not the submission)")
    ap.add_argument("--threads", type=int, default=os.cpu_count() or 8,
                    help="threads for imatrix and quantisation on THIS machine, not on the target")
    a = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    # --- where everything is, checked before an hour of work is spent -------------------------
    adapter = Path(a.adapter) if a.adapter else None
    if adapter is None:
        dpo, sft = C.DPO_OUT / a.tag / "best_lora", C.SFT_OUT / a.tag / "best_lora"
        adapter = dpo if (dpo / "adapter_config.json").is_file() else sft
    if not (adapter / "adapter_config.json").is_file():
        print(f"ARRET : pas d'adaptateur dans {adapter}. Lance 01_sft.py (puis 02_dpo.py).")
        return 2
    exe = ".exe" if os.name == "nt" else ""
    quantize_bin = C.LLAMA_BIN / f"llama-quantize{exe}"
    imatrix_bin = C.LLAMA_BIN / f"llama-imatrix{exe}"
    for p, what in ((C.CONVERT_HF, "convert_hf_to_gguf.py (variable LLAMA_CPP_REPO)"),
                    (quantize_bin, "llama-quantize (variable LLAMA_BIN)")):
        if not p.exists():
            print(f"ARRET : {what} introuvable : {p}")
            return 2
    if not a.skip_imatrix and not imatrix_bin.exists():
        print(f"ARRET : llama-imatrix introuvable ({imatrix_bin}). Relance avec --skip-imatrix.")
        return 2
    # Qwen2Model.set_vocab (conversion/qwen.py, which Qwen3 inherits) tries the sentencepiece
    # loader first and falls back to the BPE one on FileNotFoundError. But the `import
    # sentencepiece` happens BEFORE the tokenizer.model check (conversion/base.py:1843), so a
    # missing package raises ModuleNotFoundError and kills a conversion that would have worked.
    # Cost us a run on 12/09/2026. Checked here, before the merge, not after.
    try:
        import sentencepiece  # noqa: F401
    except ImportError:
        print("ARRET : le paquet sentencepiece manque dans ce venv. convert_hf_to_gguf.py "
              "l'importe avant de decider qu'il n'en a pas besoin, donc la conversion echouerait "
              "apres la fusion.\n        .venv-train\\Scripts\\pip install sentencepiece")
        return 2

    merged, gguf, prov = C.MERGED / a.tag, C.GGUF / a.tag, C.PROV / a.tag
    for d in (merged, gguf, prov):
        d.mkdir(parents=True, exist_ok=True)
    steps, t_all = [], time.time()

    print(f"Adaptateur : {adapter}")
    # 14/09/2026: the base is read from the ADAPTER, not from config.BASE_MODEL. Exporting the
    # Gemma-270M adapter loaded Qwen3-0.6B and died on a shape mismatch (640 against 1024).
    # PEFT writes the base it was trained on into adapter_config.json; that is the truth.
    base_id, base_rev = C.BASE_MODEL, C.BASE_REVISION
    cfg_p = adapter / "adapter_config.json"
    if cfg_p.is_file():
        trained_on = json.loads(cfg_p.read_text(encoding="utf-8")).get("base_model_name_or_path")
        if trained_on and trained_on != base_id:
            print(f"  base lue dans l'adaptateur : {trained_on} (config.py disait {base_id})")
            base_id, base_rev = trained_on, "main"
    print(f"Base       : {base_id} (revision {base_rev})")
    print(f"Sortie     : {gguf}")

    # --- 1. merge -------------------------------------------------------------------------------
    print("\n1/5  fusion de l'adaptateur dans le modele de base en fp16 (CPU)")
    t0 = time.time()
    kw = dict(revision=C.BASE_REVISION, device_map="cpu", low_cpu_mem_usage=True)
    try:
        base = AutoModelForCausalLM.from_pretrained(base_id, dtype=torch.float16, **kw)
    except TypeError:
        base = AutoModelForCausalLM.from_pretrained(base_id, torch_dtype=torch.float16, **kw)
    model = PeftModel.from_pretrained(base, str(adapter)).merge_and_unload()
    model.config.use_cache = True
    model.save_pretrained(str(merged), safe_serialization=True)

    tok = AutoTokenizer.from_pretrained(str(adapter))
    # Gemma 3: the tokenizer carries <image_soft_token> at id 262144 while the TEXT model's
    # vocab_size is 262144, so convert_hf_to_gguf asserts (base.py get_vocab_base). The token is
    # the multimodal placeholder; a text-only model can never emit it. Dropped here, and only
    # when it is out of range - nothing else is touched. Verified 14/09/2026.
    n_vocab = getattr(model.config, "vocab_size", None) or getattr(
        getattr(model.config, "text_config", None), "vocab_size", None)
    extra = [t for t, i in tok.get_vocab().items() if n_vocab and i >= n_vocab]
    if extra:
        print(f"  jeton hors vocabulaire retire du tokenizer : {extra} (vocab_size={n_vocab})")
    is_gemma = "gemma" in base_id.lower()
    if is_gemma:
        # the SFT aligned EOS on <end_of_turn>; the GGUF must carry the same or nothing stops it
        tok.eos_token = "<end_of_turn>"
        tok.chat_template = baked_template_gemma(C.BAKED_SYSTEM)
    else:
        tok.chat_template = CHATML_NOSYS if a.no_system else baked_template(C.BAKED_SYSTEM)
    print(f"  gabarit grave : {'Gemma' if is_gemma else 'ChatML'} ; EOS = {tok.eos_token} "
          f"({tok.convert_tokens_to_ids(tok.eos_token)})")
    tok.save_pretrained(str(merged))
    if extra:
        tj = json.loads((merged / "tokenizer.json").read_text(encoding="utf-8"))
        tj["added_tokens"] = [t for t in tj.get("added_tokens", []) if t["id"] < n_vocab]
        v = tj.get("model", {}).get("vocab")
        if isinstance(v, dict):
            tj["model"]["vocab"] = {k: i for k, i in v.items() if i < n_vocab}
        (merged / "tokenizer.json").write_text(json.dumps(tj, ensure_ascii=False), encoding="utf-8")
        tcfg0 = json.loads((merged / "tokenizer_config.json").read_text(encoding="utf-8"))
        tcfg0["added_tokens_decoder"] = {k: x for k, x in tcfg0.get("added_tokens_decoder", {}).items()
                                         if int(k) < n_vocab}
        # Gemma's tokenizer_config also declares the multimodal placeholders by NAME
        # (image_token / boi_token / eoi_token); transformers re-adds image_token when it loads,
        # which puts id 262144 straight back. They mean nothing for a text-only export.
        for k in ("image_token", "boi_token", "eoi_token", "image_token_id"):
            tcfg0.pop(k, None)
        # transformers 5 re-adds them from this block when the tokenizer is loaded again, which
        # is what put id 262144 back three times on 14/09/2026.
        msst = tcfg0.get("model_specific_special_tokens")
        if isinstance(msst, dict):
            tcfg0["model_specific_special_tokens"] = {
                k: v for k, v in msst.items() if "image" not in k.lower()}
        (merged / "tokenizer_config.json").write_text(json.dumps(tcfg0, ensure_ascii=False, indent=1),
                                                      encoding="utf-8")
    # transformers 5 writes the template to chat_template.jinja and the converter reads that file
    # (gguf-py/gguf/vocab.py, checked 12/09/2026), but older tooling looks in tokenizer_config.json.
    # Write both, so whichever is read carries the same template.
    (merged / "chat_template.jinja").write_text(tok.chat_template, encoding="utf-8")
    tcfg = json.loads((merged / "tokenizer_config.json").read_text(encoding="utf-8"))
    tcfg["chat_template"] = tok.chat_template
    (merged / "tokenizer_config.json").write_text(
        json.dumps(tcfg, ensure_ascii=False, indent=2), encoding="utf-8")
    steps.append({"step": "merge", "seconds": round(time.time() - t0, 1),
                  "adapter": str(adapter), "merged": str(merged),
                  "note": "LoRA trained on an NF4 base, merged into the fp16 base "
                          "(standard QLoRA export, an approximation)"})
    print(f"  fusionne -> {merged}   ({human(time.time() - t0)})")

    # --- 2. the template the jury will actually hit -----------------------------------------------
    rendered = tok.apply_chat_template([{"role": "user", "content": "Hello, who are you?"}],
                                       tokenize=False, add_generation_prompt=True)
    print("\n2/5  ce que devient un tour utilisateur nu (c'est l'entree du jury)")
    print("-" * 78)
    print(rendered)
    print("-" * 78)
    if "<think>" in rendered:
        print("ARRET : le gabarit exporte contient encore un bloc <think>.")
        return 2
    # "generation" alone would match add_generation_prompt, which is legitimate; the training
    # marker is the {% generation %} ... {% endgeneration %} pair, so look for its closing tag.
    if "endgeneration" in (tok.chat_template or ""):
        print("ARRET : le marqueur d'entrainement {% generation %} est parti dans l'export.")
        return 2
    if not a.no_system and "AgriTG" not in rendered:
        print("ARRET : la persona n'est pas dans le gabarit ; le modele nu ne saura pas qui il est.")
        return 2

    # --- 3. GGUF F16 --------------------------------------------------------------------------------
    print("\n3/5  conversion en GGUF F16")
    params = C.BASE_MODELS.get(a.tag, {}).get("params", "")
    stem = f"agritg-{a.tag.lower()}" + (f"-{params.lower()}" if params else "")
    f16 = gguf / f"{stem}-F16.gguf"
    run([sys.executable, C.CONVERT_HF, merged, "--outfile", f16, "--outtype", "f16"],
        steps, "convert_hf_to_gguf")
    print(f"  F16 : {mb(f16)} Mo")

    # --- 4. imatrix ------------------------------------------------------------------------------------
    imatrix = gguf / "imatrix.dat"
    calib_info = None
    if a.reuse_imatrix and imatrix.exists() and not a.skip_imatrix:
        print(f"\n4/5  imatrix REUTILISEE : {imatrix} ({mb(imatrix)} Mo)")
        calib_info = {"reused": True, "imatrix": str(imatrix), "imatrix_sha256": sha256(imatrix),
                      "note": "non recalculee ; valable tant que le F16 n'a pas change"}
    elif not a.skip_imatrix:
        print("\n4/5  matrice d'importance, calibree sur nos propres conversations")
        calib = gguf / "imatrix-calibration.txt"
        calib_info = write_calibration(tok, calib)
        print(f"  calibration : {calib_info['conversations']} conversations, "
              f"{calib_info['unique_questions']} questions uniques, {calib_info['tokens']} tokens")
        cmd = [imatrix_bin, "-m", f16, "-f", calib, "-o", imatrix,
               "-t", a.threads, "-c", C.IMATRIX_CTX, "-ngl", 0]
        if a.imatrix_chunks:
            cmd += ["--chunks", a.imatrix_chunks]
        run(cmd, steps, "llama-imatrix")
        calib_info.update({"chunks_requested": a.imatrix_chunks or "all",
                           "context": C.IMATRIX_CTX, "imatrix": str(imatrix),
                           "imatrix_sha256": sha256(imatrix)})
    else:
        print("\n4/5  imatrix SAUTEE (--skip-imatrix) : les quantifications seront moins bonnes "
              "que ce qu'on peut soumettre.")

    # --- 5. quantisations ---------------------------------------------------------------------------------
    print(f"\n5/5  quantifications : {', '.join(a.quants)}")
    produced = []
    for q in a.quants:
        out = gguf / f"{stem}-{q}.gguf"
        # llama-quantize has no k-quant blocks to steer in Q8_0, so an imatrix buys nothing there.
        # We do not pass one, and the manifest says so rather than implying a calibration
        # that did not happen.
        used_im = bool(imatrix.exists() and not a.skip_imatrix and q != "Q8_0")
        cmd = [quantize_bin] + (["--imatrix", imatrix] if used_im else []) + [f16, out, q, a.threads]
        run(cmd, steps, f"llama-quantize {q}")
        produced.append({"quant": q, "file": str(out), "size_mb": mb(out),
                         "imatrix": used_im, "sha256": sha256(out)})
        print(f"  {q:8} {mb(out):8.1f} Mo   imatrix={'oui' if used_im else 'non'}")

    # --- the untuned base, for the before/after of rule 3.1 -------------------------------------------
    base_gguf = None
    if a.with_base:
        print("\n+    modele de base NU (le 'avant' de la regle 3.1)")
        try:
            from huggingface_hub import snapshot_download
            snap = Path(snapshot_download(base_id, revision=base_rev))
            # One folder PER base model. With a single shared folder the 14/09 run found Qwen's
            # base-F16.gguf from the day before, skipped the conversion, and quantised Qwen as the
            # "before" of an LFM2 fine-tune.
            bdir = C.GGUF / "base" / base_id.replace("/", "--")
            bdir.mkdir(parents=True, exist_ok=True)
            bf16 = bdir / "base-F16.gguf"
            if not bf16.exists():
                run([sys.executable, C.CONVERT_HF, snap, "--outfile", bf16, "--outtype", "f16"],
                    steps, "convert_hf_to_gguf (base)")
            base_gguf = bdir / "base-Q4_K_M.gguf"
            run([quantize_bin, bf16, base_gguf, "Q4_K_M", a.threads], steps,
                "llama-quantize base Q4_K_M")
            print(f"  base Q4_K_M : {mb(base_gguf)} Mo  - gabarit d'origine, bloc <think> compris : "
                  f"c'est justement ce que la comparaison doit montrer")
        except Exception as e:
            print(f"  base non exportee ({type(e).__name__}: {e}). "
                  f"La comparaison avant/apres restera incomplete.")
            base_gguf = None

    # --- provenance ---------------------------------------------------------------------------------------
    inputs = {}
    for p in [adapter / "adapter_model.safetensors", adapter / "adapter_config.json",
              C.SPLIT / "sft_train.jsonl", C.SPLIT / "sft_eval.jsonl", C.SPLIT / "sft_test.jsonl",
              C.SPLIT / "dpo_train.jsonl", C.SPLIT / "split_manifest.json",
              Path(__file__).with_name("00_split.py"), Path(__file__).with_name("01_sft.py"),
              Path(__file__).with_name("02_dpo.py"), Path(__file__),
              Path(__file__).with_name("config.py")]:
        if p.exists():
            try:
                key = str(p.relative_to(C.ROOT))
            except ValueError:
                key = p.name
            inputs[key] = {"sha256": sha256(p), "size_mb": mb(p)}

    meta = {
        "artifact": "AgriTG LLM - ADTC 2026 Gate 2",
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "experiment": a.tag,
        "base_model": {"id": base_id, "revision": base_rev,
                       "params": C.BASE_MODELS.get(a.tag, {}).get("params")},
        "method": "QLoRA 4-bit SFT (+ DPO when the adapter comes from outputs/dpo), merged fp16, "
                  "converted to GGUF, quantised with an imatrix calibrated on our own data",
        "adapter": {"path": str(adapter),
                    "sha256": sha256(adapter / "adapter_model.safetensors"),
                    "lora": {"r": C.LORA_R, "alpha": C.LORA_ALPHA, "targets": C.TARGET_MODULES}},
        "merged_model": str(merged),
        "chat_template": {"baked_persona": not a.no_system, "thinking_block": False,
                          "text": tok.chat_template},
        "quantisations": produced,
        "base_gguf_for_comparison": str(base_gguf) if base_gguf else None,
        "imatrix": calib_info,
        "git_commit": git_sha(C.ROOT),
        "llama_cpp": {"repo": str(C.LLAMA_CPP), "repo_commit": git_sha(C.LLAMA_CPP),
                      "binaries": str(C.LLAMA_BIN),
                      # llama-quantize has no --version and prints its usage instead; llama-cli of
                      # the same build carries the build number and commit.
                      "build": binary_version(C.LLAMA_BIN / f"llama-cli{exe}")},
        "environment": {"python": platform.python_version(), "torch": torch.__version__,
                        "platform": platform.platform()},
        "inputs": inputs,
        "commands": steps,
        "total_seconds": round(time.time() - t_all, 1),
    }
    if meta["git_commit"] is None:
        meta["git_commit_note"] = (
            "ce dossier n'est pas un depot git ; la section 3.1 demande un Git Commit SHA, "
            "il faut donc `git init` + un commit avant l'envoi, puis relancer ce script "
            "pour que le SHA soit fige dans metadata.json.")
    (prov / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8")
    (prov / "export_manifest.json").write_text(
        json.dumps({"steps": steps, "outputs": produced}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    lines = [f"{d['sha256']}  {Path(d['file']).name}" for d in produced]
    if base_gguf:
        lines.append(f"{sha256(base_gguf)}  {base_gguf.name}")
    (gguf / "checksums.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (prov / "checksums.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nTermine en {human(time.time() - t_all)}")
    print(f"  GGUF        -> {gguf}")
    print(f"  provenance  -> {prov / 'metadata.json'}  et  checksums.txt")
    if meta["git_commit"] is None:
        print("  ATTENTION : pas de depot git ici, donc pas de Git Commit SHA. La section 3.1 en "
              "demande un : `git init`, un commit, puis relancer ce script.")
    print("\nEtape suivante :")
    print(f"  python train-gate2\\04_compare.py --tag {a.tag}"
          + ("" if base_gguf else "   (relance d'abord avec --with-base pour l'avant/apres)"))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
