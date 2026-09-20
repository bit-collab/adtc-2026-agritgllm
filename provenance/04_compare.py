# -*- coding: utf-8 -*-
"""STEP 4 - measure every GGUF we produced, against each other and against the untuned base.

Three questions, and none of them is answered by an opinion:

  1. ACCURACY (weight 0.50). The 12-item acceptance test is replayed against the real GGUF,
     served by llama-server, with NO system prompt - exactly the way the jury talks to it. The
     grading is the deterministic checker of rebuild-gate2/pipeline/acceptance.py, imported, not
     re-implemented: the same rules that scored the round-1 answers 5/12 score these.
  2. THROUGHPUT (weight 0.30) and MEMORY (weight 0.20). Measured the way the ORGANISERS measure,
     because that is the only measurement that can reconcile with theirs. Read from their own
     profiler (adtc-2026/profiler-src, read 12/09/2026):
        throughput -> llama-bench -m M -p 512 -n 128 -ngl 0 --output json, generation row avg_ts
        memory     -> peak and steady-state RSS of the bench process family, sampled at 10 Hz
     Their comparator flags a submission above 25 % of throughput deviation and fails it above
     50 % (comparator.py, TOLERANCES). Rule 3.4 is that check.
  3. THE CHOICE OF QUANTISATION. Q5_K_M is bigger than Q4_K_M, so it costs efficiency (0.20).
     It is worth it only if it buys accuracy (0.50). This script puts both numbers on one line
     so the trade is arithmetic instead of a feeling.

About the numbers this bench produces: they are NOT the numbers to declare. The round-1 report
anchors the translation - the same model measured 6.34 tok/s here and scored Sperf 21.33, i.e.
3.20 tok/s on the audit VM. The audit machine runs at about HALF this bench (config.AUDIT_SPEED_FACTOR),
and the report prints both, labelled, so nobody declares the wrong one.

Usage (a venv with psutil - .venv-train or .venv-profiler), from concoursllmdata/ :
    .venv-train\\Scripts\\python train-gate2\\04_compare.py
    .venv-train\\Scripts\\python train-gate2\\04_compare.py --quants Q4_K_M Q5_K_M
    .venv-train\\Scripts\\python train-gate2\\04_compare.py --no-bench       # acceptance only
    .venv-train\\Scripts\\python train-gate2\\04_compare.py --bench-only     # speed and RAM only
    .venv-train\\Scripts\\python train-gate2\\04_compare.py --extra          # + identity/limits probes

Produces
    outputs/answers/<tag>/<model>.jsonl          every answer, kept as evidence
    provenance/<tag>/compare.md                  the before/after table rule 3.1 asks for
    provenance/<tag>/compare.json                the same, machine-readable
    provenance/<tag>/measurements.json           throughput + memory in the profiler's own shape
"""
from __future__ import annotations
import argparse, importlib.util, json, os, re, socket, subprocess, sys, threading, time, urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

GOLD = C.ROOT / "rebuild-gate2" / "gold"
ACCEPTANCE_PY = C.ROOT / "rebuild-gate2" / "pipeline" / "acceptance.py"
EXE = ".exe" if os.name == "nt" else ""
SERVER_BIN = C.LLAMA_BIN / f"llama-server{EXE}"
BENCH_BIN = C.LLAMA_BIN / f"llama-bench{EXE}"

# Sperf is linear in generation speed and saturates at 15 tok/s: the round-1 report gives
# Sperf 21.33 for 3.20 tok/s, and 3.20/15*100 = 21.33 to the cent. Seff is a reconstruction from
# a SINGLE point (Seff 82.99 <-> 1219 MB, and 100*(1-1219/7168) = 82.99), so it is one plausible
# fit, not a published formula - the report says so wherever it prints an Seff.
PERF_SATURATION_TOK_S = 15.0
EFF_BUDGET_MB = 7168.0
ROUND1 = {"Sacc": 65.54, "Sperf": 21.33, "Seff": 82.99, "total": 55.77}


def human(sec):
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def read_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


# Typography, not agronomy. Measured on the first real run, 12/09/2026: the model writes
# "tick‑borne" with U+2011 (a NON-BREAKING hyphen) because 2886 of them are in sft_train.jsonl,
# and the acceptance checker looks for the ASCII "tick-borne". The item failed on a character the
# jury cannot even see. Folding this punctuation to ASCII before the textual check is a reading
# fix, not a lowered bar - and the report prints how many items it flipped, so the difference is
# never silent. The data itself should lose these characters; that is a pipeline job, not this one.
TYPO = {0x2010: "-", 0x2011: "-", 0x2012: "-", 0x2013: "-", 0x2014: "-", 0x2015: "-",
        0x00A0: " ", 0x202F: " ", 0x2009: " ", 0x2018: "'", 0x2019: "'",
        0x201C: '"', 0x201D: '"', 0x2026: "..."}


def to_ascii_punct(s: str) -> str:
    return (s or "").translate(TYPO)


def load_checker():
    """The deterministic acceptance checker, imported from the data pipeline. Never a copy: a
    second copy would drift, and then the test that says 12/12 would not be the test that
    scored the round-1 answers 5/12."""
    spec = importlib.util.spec_from_file_location("acceptance_check", ACCEPTANCE_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def free_port(preferred: int) -> int:
    for port in range(preferred, preferred + 40):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("aucun port libre")


class Server:
    """llama-server around one GGUF. --jinja so the template BAKED IN THE FILE is the one used:
    if the persona is missing from the GGUF, this is where it shows."""

    def __init__(self, model: Path, threads: int, port: int, ctx: int, log: Path):
        self.model, self.threads, self.port, self.ctx, self.log = model, threads, port, ctx, log
        self.proc = None

    def __enter__(self):
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.log, "w", encoding="utf-8", errors="replace")
        cmd = [str(SERVER_BIN), "-m", str(self.model), "-c", str(self.ctx),
               "-t", str(self.threads), "-ngl", "0", "--host", "127.0.0.1",
               "--port", str(self.port), "--jinja"]
        print(f"  serveur : {' '.join(cmd[-8:])}")
        self.proc = subprocess.Popen(cmd, stdout=self.fh, stderr=subprocess.STDOUT)
        deadline = time.time() + 240
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"llama-server s'est arrete (code {self.proc.returncode}), "
                                   f"voir {self.log}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=3) as r:
                    if r.status == 200:
                        return self
            except Exception:
                time.sleep(1)
        raise RuntimeError(f"llama-server n'a pas repondu sur /health en 240 s, voir {self.log}")

    def __exit__(self, *exc):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        try:
            self.fh.close()
        except Exception:
            pass

    def ask(self, question: str, max_tokens: int, timeout: int = 900) -> dict:
        """One bare user turn. No system message on purpose: that is the jury's input."""
        body = json.dumps({"messages": [{"role": "user", "content": question}],
                           "temperature": 0.0, "top_k": 1, "seed": C.SEED,
                           "max_tokens": max_tokens}).encode("utf-8")
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/v1/chat/completions",
                                     data=body, headers={"Content-Type": "application/json"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read())
        dt = time.time() - t0
        answer = (d["choices"][0]["message"].get("content") or "").strip()
        usage = d.get("usage", {})
        timings = d.get("timings", {}) or {}
        return {"answer": answer, "seconds": round(dt, 2),
                "completion_tokens": usage.get("completion_tokens"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "tok_s": round(timings.get("predicted_per_second")
                               or ((usage.get("completion_tokens") or 0) / dt if dt else 0), 2),
                "finish_reason": d["choices"][0].get("finish_reason")}


def memory_of_server_log(log: Path) -> dict:
    """Fallback when psutil is absent: llama.cpp prints the buffers it allocated. This is not RSS
    and must not be declared as such - it is a floor, and the report labels it."""
    out, text = {}, log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    total = 0.0
    for m in re.finditer(r"(model buffer size|KV buffer size|compute buffer size)\s*=\s*"
                         r"([0-9.]+)\s*MiB", text):
        total += float(m.group(2))
        out[m.group(1)] = out.get(m.group(1), 0.0) + float(m.group(2))
    out["reported_buffers_mb"] = round(total, 1)
    return out


def bench(model: Path, threads: int | None, n_prompt=512, n_gen=128) -> dict:
    """The organisers' own throughput command, plus RSS sampling around it, so the two numbers
    they compare against our declaration are produced by the same run."""
    cmd = [str(BENCH_BIN), "-m", str(model), "-p", str(n_prompt), "-n", str(n_gen),
           "-ngl", "0", "--output", "json"]
    if threads:
        cmd += ["-t", str(threads)]
    try:
        import psutil
    except ImportError:
        psutil = None

    samples, stop = [], threading.Event()
    t0 = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def poll():
        p = psutil.Process(proc.pid)
        while not stop.is_set():
            try:
                fam = [p] + p.children(recursive=True)
                samples.append((time.time() - t0,
                                sum(q.memory_info().rss for q in fam if q.is_running()) / (1 << 20)))
            except Exception:
                pass
            stop.wait(0.1)

    th = None
    if psutil is not None:
        th = threading.Thread(target=poll, daemon=True)
        th.start()
    out, err = proc.communicate()
    stop.set()
    if th:
        th.join(timeout=2)
    if proc.returncode != 0:
        return {"error": f"llama-bench code {proc.returncode}", "stderr": (err or "")[-1500:]}
    try:
        rows = json.loads(out)
    except json.JSONDecodeError:
        return {"error": "sortie de llama-bench illisible", "stdout": (out or "")[:500]}

    pp = next((r for r in rows if r.get("n_gen", 0) == 0 and r.get("n_prompt", 0) > 0), None)
    tg = next((r for r in rows if r.get("n_gen", 0) > 0), None)
    res = {"threads": threads or (rows[0].get("n_threads") if rows else None),
           "tokens_per_second_generation": round(float(tg["avg_ts"]), 2) if tg else None,
           "tokens_per_second_prompt": round(float(pp["avg_ts"]), 2) if pp else None,
           "generated_tokens": int(tg.get("n_gen", 0)) if tg else 0,
           "prompt_tokens": int(pp.get("n_prompt", 0)) if pp else 0,
           "model_size_mb": round(float(rows[0].get("model_size", 0)) / (1 << 20), 1) if rows else None,
           "seconds": round(time.time() - t0, 1)}
    if pp and pp.get("avg_ts"):
        res["first_token_latency_ms"] = round(res["prompt_tokens"] / float(pp["avg_ts"]) * 1000, 2)
    if samples:
        rss = [s[1] for s in samples]
        cut = samples[-1][0] - min(60.0, (samples[-1][0] - samples[0][0]) / 2)
        tail = [v for t, v in samples if t >= cut] or rss
        res["memory"] = {"peak_rss_mb": round(max(rss), 2),
                         "steady_state_rss_mb": round(sum(tail) / len(tail), 2),
                         "samples": len(rss), "method": "psutil, 10 Hz, process family, "
                                                        "same as adtc-profiler memory.py"}
    else:
        res["memory"] = {"note": "psutil absent de ce venv : pas de mesure RSS. "
                                 "Lance ce script depuis .venv-train ou .venv-profiler."}
    return res


def sperf(tok_s):
    return None if not tok_s else round(min(100.0, 100.0 * tok_s / PERF_SATURATION_TOK_S), 2)


def seff(rss_mb):
    return None if not rss_mb else round(max(0.0, 100.0 * (1 - rss_mb / EFF_BUDGET_MB)), 2)


def battery(tag_extra: bool):
    """The 12 scored items, and optionally the unscored probes that answer the jury's OTHER
    habit: three of the five hidden prompts of round 1 were about the model itself."""
    items = read_jsonl(GOLD / "acceptance.jsonl")
    extra = []
    if tag_extra:
        for name, n in (("identity.jsonl", 6), ("limits.jsonl", 4), ("greetings.jsonl", 2)):
            for row in read_jsonl(GOLD / name)[:n]:
                extra.append({"id": f"{name.split('.')[0]}:{row.get('topic', '?')}",
                              "prompt": row["question"], "gold": row.get("answer", "")})
    return items, extra


def run_model(name, path, items, extra, args, checker):
    """Serve one GGUF, ask everything, grade the scored part, keep every answer."""
    print(f"\n=== {name}  ({path.name}, {path.stat().st_size / (1 << 20):.1f} Mo) ===")
    res = {"name": name, "file": str(path), "size_mb": round(path.stat().st_size / (1 << 20), 1)}
    answers, rows = [], []
    if not args.bench_only:
        port = free_port(args.port)
        log = C.ANSWERS / args.tag / f"{name}-server.log"
        t0 = time.time()
        with Server(path, args.threads, port, args.ctx, log) as srv:
            for it in items:
                r = srv.ask(it["prompt"], args.max_tokens)
                answers.append({"id": it["id"], "answer": r["answer"]})
                clean = to_ascii_punct(r["answer"])
                core = checker.check(it, it.get("core", {}), clean)
                more = checker.check(it, it.get("extra", {}), clean)
                raw_core = checker.check(it, it.get("core", {}), r["answer"])
                rows.append({"id": it["id"], "kind": it["kind"], "core": core, "extra": more,
                             "core_before_typography": raw_core,
                             "typography_flipped": bool(raw_core) and not core,
                             "tok_s": r["tok_s"], "tokens": r["completion_tokens"],
                             "words": len(r["answer"].split()),
                             "finish_reason": r["finish_reason"], "answer": r["answer"]})
                mark = "PASSE " if not core else "ECHOUE"
                print(f"  {mark} {it['id']:38} {len(r['answer'].split()):4} mots  "
                      f"{r['tok_s']:5.1f} tok/s")
                for b in core:
                    print(f"           - {b}")
                for b in more:
                    print(f"           + notre barre : {b}")
            for it in extra:
                r = srv.ask(it["prompt"], args.max_tokens)
                answers.append({"id": it["id"], "answer": r["answer"]})
                rows.append({"id": it["id"], "kind": "probe", "core": [], "extra": [],
                             "tok_s": r["tok_s"], "tokens": r["completion_tokens"],
                             "words": len(r["answer"].split()),
                             "finish_reason": r["finish_reason"], "answer": r["answer"]})
                print(f"  (sonde) {it['id']:36} {len(r['answer'].split()):4} mots")
            res["server_memory_reported"] = memory_of_server_log(log)
        scored = [r for r in rows if r["kind"] != "probe"]
        res["acceptance"] = {
            "jury": sum(1 for r in scored if not r["core"]),
            "our_bar": sum(1 for r in scored if not r["core"] and not r["extra"]),
            "total": len(scored),
            "jury_before_typography": sum(1 for r in scored if not r["core_before_typography"]),
            "typography_flipped": [r["id"] for r in scored if r["typography_flipped"]],
            "failures": {r["id"]: r["core"] + [f"(notre barre) {b}" for b in r["extra"]]
                         for r in scored if r["core"] or r["extra"]}}
        res["chat"] = {"mean_tok_s": round(sum(r["tok_s"] for r in rows) / max(1, len(rows)), 2),
                       "mean_words": round(sum(r["words"] for r in rows) / max(1, len(rows)), 1),
                       "truncated": sum(1 for r in rows if r["finish_reason"] == "length"),
                       "seconds": round(time.time() - t0, 1)}
        res["rows"] = rows
        out = C.ANSWERS / args.tag / f"{name}.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(json.dumps(a, ensure_ascii=False) for a in answers) + "\n",
                       encoding="utf-8")
        res["answers_file"] = str(out)
        print(f"  acceptation : jury {res['acceptance']['jury']}/{res['acceptance']['total']}  "
              f"notre barre {res['acceptance']['our_bar']}/{res['acceptance']['total']}   "
              f"reponses -> {out.name}")
        if res["acceptance"]["typography_flipped"]:
            print(f"  dont {len(res['acceptance']['typography_flipped'])} qui ne passaient qu'apres "
                  f"remise en ASCII de la ponctuation "
                  f"({', '.join(res['acceptance']['typography_flipped'])}) : "
                  f"le modele ecrit des traits d'union insecables, comme ses donnees.")
        if res["chat"]["truncated"]:
            print(f"  ATTENTION : {res['chat']['truncated']} reponses coupees a "
                  f"{args.max_tokens} tokens ; le test juge alors une phrase tronquee.")

    if not args.no_bench:
        print(f"  banc de debit ({args.threads} threads, methode du profiler officiel)...")
        res["bench"] = bench(path, args.threads)
        b = res["bench"]
        if b.get("error"):
            print(f"  banc en echec : {b['error']}")
        else:
            tg = b["tokens_per_second_generation"]
            mem = (b.get("memory") or {}).get("peak_rss_mb")
            print(f"  {tg} tok/s generation, {b['tokens_per_second_prompt']} tok/s prompt, "
                  f"RSS pic {mem} Mo")
            f = args.audit_factor
            res["estimates"] = {
                "measured_here": {"tok_s": tg, "Sperf": sperf(tg)},
                "audit_vm_estimate": {"tok_s": round(tg * f, 3), "Sperf": sperf(tg * f)},
                "audit_factor": f, "audit_factor_source": args.audit_factor_source,
                "Seff_estimate": seff((b.get("memory") or {}).get("steady_state_rss_mb")),
                "caveat": "Sperf = 100*tok_s/15 (exact sur l'ancrage du tour 1 : 3.20 tok/s -> "
                          "21.33). Seff = 100*(1-RSS/7168 Mo) est une RECONSTRUCTION a partir "
                          "d'un seul point (1219 Mo <-> 82.99), pas une formule publiee."}
    return res


def markdown(results, args, meta):
    L = [f"# Comparaison des quantifications - experience {args.tag}", "",
         f"*Mesure du {time.strftime('%d/%m/%Y %H:%M')} sur {meta['machine']}, "
         f"{args.threads} threads, llama.cpp {meta['bench_version']}.*", "",
         "Le test d'acceptation est joue sur le GGUF servi par llama-server, **sans prompt "
         "systeme** : la persona vient du gabarit grave dans le fichier, comme chez le jury. "
         "La notation est celle de `rebuild-gate2/pipeline/acceptance.py`, importee telle quelle.",
         "", "## Le tableau qui decide", "",
         "| Modele | Taille | Acceptation jury | Notre barre | tok/s ici | tok/s estimes VM audit "
         "| Sperf est. | RSS pic | RSS regime | Seff est. |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        acc = r.get("acceptance") or {}
        b = r.get("bench") or {}
        m = b.get("memory") or {}
        est = r.get("estimates") or {}
        tg = b.get("tokens_per_second_generation")
        L.append(
            f"| {r['name']} | {r['size_mb']:.0f} Mo "
            f"| {acc.get('jury', '-')}/{acc.get('total', '-')} "
            f"| {acc.get('our_bar', '-')}/{acc.get('total', '-')} "
            f"| {tg if tg else '-'} "
            f"| {est.get('audit_vm_estimate', {}).get('tok_s', '-')} "
            f"| {est.get('audit_vm_estimate', {}).get('Sperf', '-')} "
            f"| {m.get('peak_rss_mb', '-')} | {m.get('steady_state_rss_mb', '-')} "
            f"| {est.get('Seff_estimate', '-')} |")
    L += ["", "Rappel du tour 1 : Sacc %.2f, Sperf %.2f, Seff %.2f, total %.2f."
          % (ROUND1["Sacc"], ROUND1["Sperf"], ROUND1["Seff"], ROUND1["total"]), ""]
    cal = meta.get("calibration")
    if cal:
        L += [f"**D'ou vient le facteur {meta['audit_speed_factor']}** : le modele soumis au "
              f"tour 1 (`{Path(cal['file']).name}`) a ete rejoue ici avec la commande des "
              f"organisateurs. Il rend **{cal['here_tok_s']} tok/s sur ce banc** et la VM d'audit "
              f"a rendu **{cal['audit_tok_s']} tok/s** dessus (Sperf 21.33). Meme fichier, meme "
              f"commande, deux machines : le rapport est mesure, pas suppose. Pour memoire, le "
              f"tour 1 avait declare {cal['declared_round1_tok_s']} tok/s.", ""]
    else:
        L += [f"**Attention au facteur {meta['audit_speed_factor']}** : {meta['audit_factor_source']}.",
              ""]
    L += ["**Ce qu'il faut declarer** : la colonne *tok/s estimes VM audit*, pas la colonne "
          "*tok/s ici*. Le comparateur des organisateurs (`profiler-src/comparator.py`) signale "
          "au-dela de 25 % d'ecart et fait echouer au-dela de 50 %. Le seul chiffre vraiment sur "
          "reste celui de leur profiler dans leur image d'audit.", "",
          "**Ce que Seff vaut vraiment** : la colonne Seff est reconstruite d'un seul point "
          "(1219 Mo <-> 82.99). Elle sert a comparer les quantifications entre elles, pas a "
          "annoncer un score.", ""]
    if any("avant" in r["name"] for r in results):
        L += ["**Sur la taille du modele de base** : son GGUF porte un tenseur `output.weight` "
              "separe alors que le notre a des embeddings lies (verifie dans le journal de "
              "conversion, 13/09/2026). Environ 90 Mo de l'ecart de taille vient de la, pas du "
              "fine-tuning. La comparaison qui compte entre les deux est celle des reponses.", ""]
    L += ["## Ce que chaque modele a rate", ""]
    for r in results:
        acc = r.get("acceptance")
        if not acc:
            continue
        L.append(f"### {r['name']} - jury {acc['jury']}/{acc['total']}, "
                 f"notre barre {acc['our_bar']}/{acc['total']}")
        if acc.get("typography_flipped"):
            L.append(f"\n*{acc['jury_before_typography']}/{acc['total']} avant remise en ASCII de "
                     f"la ponctuation ; {', '.join(acc['typography_flipped'])} ne passait que sur "
                     f"un trait d'union insecable (U+2011), present 2886 fois dans les donnees "
                     f"d'entrainement. A corriger dans les donnees, pas ici.*")
        if not acc["failures"]:
            L.append("\nRien. Les 12 exigences passent, la notre comprise.\n")
        for pid, bad in acc["failures"].items():
            L.append(f"- **{pid}** : " + " ; ".join(bad))
        L.append("")
    L += ["## Une reponse de chaque modele, pour lire et pas seulement compter", ""]
    probe = "keep_off_topic_refusal"
    for r in results:
        row = next((x for x in r.get("rows", []) if x["id"] == probe), None)
        if row:
            L += [f"**{r['name']}** sur *\"What's the capital of France?\"* :", "",
                  "> " + row["answer"].replace("\n", "\n> "), ""]
    L += ["## Comment ces chiffres ont ete produits", "",
          "```", meta["bench_cmd"], "```", "",
          "Meme commande que `adtc-profiler` (`throughput.py`), meme echantillonnage RSS que son "
          "`memory.py` (psutil, 10 Hz, processus et enfants). Les reponses brutes sont dans "
          f"`outputs/answers/{args.tag}/`.", ""]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default=C.EXPERIMENT)
    ap.add_argument("--models", nargs="*", default=None,
                    help="chemins de GGUF a mesurer ; par defaut tout outputs/gguf/<tag> + la base")
    ap.add_argument("--quants", nargs="*", default=None, help="sous-ensemble, ex: Q4_K_M Q5_K_M")
    ap.add_argument("--with-f16", action="store_true",
                    help="mesurer aussi le F16 (le plafond de justesse, trop gros pour la cible)")
    ap.add_argument("--threads", type=int, default=C.TARGET_THREADS,
                    help=f"defaut {C.TARGET_THREADS} : la machine du jury a 4 vCPU")
    ap.add_argument("--ctx", type=int, default=2048)
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--extra", action="store_true",
                    help="ajouter les sondes identite / limites / salutations (non notees)")
    ap.add_argument("--no-bench", action="store_true", help="acceptation seule")
    ap.add_argument("--bench-only", action="store_true", help="debit et RAM seuls")
    ap.add_argument("--no-calibrate", action="store_true",
                    help="ne pas mesurer le GGUF du tour 1 ; utiliser le facteur fixe de config.py")
    args = ap.parse_args()

    for p, what in ((SERVER_BIN, "llama-server"), (BENCH_BIN, "llama-bench")):
        if not p.exists():
            print(f"ARRET : {what} introuvable : {p}  (variable LLAMA_BIN)")
            return 2
    if not ACCEPTANCE_PY.is_file():
        print(f"ARRET : le testeur d'acceptation est introuvable : {ACCEPTANCE_PY}")
        return 2
    try:
        import psutil  # noqa: F401
    except ImportError:
        print("NOTE : psutil absent de ce venv, la RAM ne sera pas mesuree (le debit, si). "
              "Utilise .venv-train ou .venv-profiler pour la mesure complete.\n")

    # --- which files ------------------------------------------------------------------------
    gdir = C.GGUF / args.tag
    if args.models:
        files = [(Path(m).stem, Path(m)) for m in args.models]
    else:
        if not gdir.is_dir():
            print(f"ARRET : rien dans {gdir}. Lance 03_export.py d'abord.")
            return 2
        found = []
        for f in sorted(gdir.glob("*.gguf")):
            q = f.stem.rsplit("-", 1)[-1]
            if q == "F16" and not args.with_f16:
                continue
            if args.quants and q not in args.quants:
                continue
            found.append((q, f))
        # The untuned base is the one 03_export recorded for THIS tag (one folder per base model).
        base = None
        man = C.PROV / args.tag / "metadata.json"
        if man.is_file():
            b = json.loads(man.read_text(encoding="utf-8")).get("base_gguf_for_comparison")
            base = Path(b) if b else None
        if base and base.exists():
            found.insert(0, ("base-Q4_K_M (avant)", base))
        files = found
    if not files:
        print(f"ARRET : aucun GGUF a mesurer dans {gdir}.")
        return 2
    for _, f in files:
        if not f.is_file():
            print(f"ARRET : fichier absent : {f}")
            return 2
    print(f"A mesurer : {', '.join(n for n, _ in files)}")
    if not any("avant" in n for n, _ in files):
        print("NOTE : pas de GGUF de base ici, donc pas d'avant/apres. "
              "Relance 03_export.py --with-base pour l'obtenir (regle 3.1).")

    # --- calibrate this bench against the audit VM, on the one model whose audit score we know --
    args.audit_factor = C.AUDIT_SPEED_FACTOR
    args.audit_factor_source = (f"constante config.AUDIT_SPEED_FACTOR={C.AUDIT_SPEED_FACTOR}, "
                                f"mesuree sur un AUTRE banc au tour 1 - a ne pas prendre pour "
                                f"une mesure de cette machine")
    calibration = None
    if not (args.no_calibrate or args.no_bench) and C.ROUND1_GGUF.is_file():
        print(f"\nCalibrage du banc sur le modele DEJA AUDITE du tour 1 ({C.ROUND1_GGUF.name}) : "
              f"la VM des organisateurs a rendu {C.ROUND1_AUDIT_TOK_S} tok/s dessus.")
        cb = bench(C.ROUND1_GGUF, args.threads)
        here = cb.get("tokens_per_second_generation")
        if here:
            args.audit_factor = round(C.ROUND1_AUDIT_TOK_S / here, 4)
            args.audit_factor_source = (
                f"mesure : {C.ROUND1_AUDIT_TOK_S} tok/s sur la VM d'audit contre {here} tok/s ici, "
                f"sur le MEME fichier ({C.ROUND1_GGUF.name}), meme commande, {args.threads} threads")
            calibration = {"file": str(C.ROUND1_GGUF), "here_tok_s": here,
                           "audit_tok_s": C.ROUND1_AUDIT_TOK_S, "factor": args.audit_factor,
                           "memory_here": cb.get("memory"),
                           "declared_round1_tok_s": 32.84,
                           "note": "Ce facteur remplace la constante de config.py : il compare la "
                                   "meme machine au meme fichier, pas deux bancs differents."}
            print(f"  ici {here} tok/s -> facteur {args.audit_factor} "
                  f"(la constante de config.py disait {C.AUDIT_SPEED_FACTOR})")
        else:
            print(f"  calibrage impossible ({cb.get('error')}), on garde le facteur fixe.")
    elif not C.ROUND1_GGUF.is_file():
        print(f"\nNOTE : {C.ROUND1_GGUF.name} absent, donc pas de calibrage de ce banc. "
              f"Le facteur reste la constante de config.py, qui vient d'un autre banc.")

    checker = load_checker()
    items, extra = battery(args.extra)
    print(f"Batterie : {len(items)} exigences notees" + (f" + {len(extra)} sondes" if extra else ""))

    t0, results = time.time(), []
    for name, path in files:
        try:
            results.append(run_model(name, path, items, extra, args, checker))
        except Exception as e:
            print(f"  ECHEC sur {name} : {type(e).__name__}: {e}")
            results.append({"name": name, "file": str(path), "error": f"{type(e).__name__}: {e}",
                            "size_mb": round(path.stat().st_size / (1 << 20), 1)})

    prov = C.PROV / args.tag
    prov.mkdir(parents=True, exist_ok=True)
    # llama-bench has no --version; llama-cli of the same build prints it.
    try:
        v = subprocess.run([str(C.LLAMA_BIN / f"llama-cli{EXE}"), "--version"],
                           capture_output=True, text=True, timeout=30)
        version = ((v.stdout or "") + (v.stderr or "")).strip().splitlines()[0]
    except Exception:
        version = "inconnue"
    import platform
    meta = {"machine": platform.processor() or platform.machine(),
            "platform": platform.platform(), "threads": args.threads,
            "bench_version": version, "measured": time.strftime("%Y-%m-%d %H:%M:%S"),
            "bench_cmd": f"llama-bench -m <model> -p 512 -n 128 -ngl 0 -t {args.threads} "
                         f"--output json",
            "audit_speed_factor": args.audit_factor,
            "audit_factor_source": args.audit_factor_source,
            "calibration": calibration, "round1": ROUND1}
    (prov / "compare.json").write_text(
        json.dumps({"meta": meta, "results": results}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    (prov / "compare.md").write_text(markdown(results, args, meta), encoding="utf-8")

    # what a submission.json needs, in the profiler's own shape, for the best model measured
    best = max((r for r in results if (r.get("bench") or {}).get("tokens_per_second_generation")),
               key=lambda r: ((r.get("acceptance") or {}).get("jury", 0),
                              r["bench"]["tokens_per_second_generation"]), default=None)
    if best:
        b = best["bench"]
        (prov / "measurements.json").write_text(json.dumps({
            "model": best["name"], "file": best["file"], "measured_on": meta["platform"],
            "threads": args.threads,
            "throughput": {k: b.get(k) for k in ("tokens_per_second_generation",
                                                 "first_token_latency_ms", "prompt_tokens",
                                                 "generated_tokens")},
            "memory": b.get("memory"),
            "declare_instead": best.get("estimates", {}).get("audit_vm_estimate"),
            "note": "Mesure sur CE banc. Le tour 1 montre un facteur 0.5 entre ce banc et la VM "
                    "d'audit ; la regle 3.4 sanctionne l'ecart non explique. Le chiffre a "
                    "declarer se verifie en relancant adtc-profiler dans l'image d'audit."},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # --- the summary, on screen ----------------------------------------------------------------
    print("\n" + "=" * 96)
    print(f"{'modele':26} {'taille':>9} {'jury':>7} {'barre':>7} {'tok/s':>8} "
          f"{'~VM audit':>10} {'RSS pic':>9}")
    for r in results:
        acc, b = r.get("acceptance") or {}, r.get("bench") or {}
        est = (r.get("estimates") or {}).get("audit_vm_estimate", {})
        print(f"{r['name']:26} {r.get('size_mb', 0):8.0f}M "
              f"{str(acc.get('jury', '-')) + '/' + str(acc.get('total', '-')):>7} "
              f"{str(acc.get('our_bar', '-')) + '/' + str(acc.get('total', '-')):>7} "
              f"{b.get('tokens_per_second_generation', '-'):>8} {est.get('tok_s', '-'):>10} "
              f"{(b.get('memory') or {}).get('peak_rss_mb', '-'):>9}")
    print("=" * 96)
    print(f"Duree {human(time.time() - t0)}")
    print(f"  rapport   -> {prov / 'compare.md'}")
    print(f"  chiffres  -> {prov / 'compare.json'}"
          + (f" et {prov / 'measurements.json'}" if best else ""))
    print(f"  reponses  -> {C.ANSWERS / args.tag}")
    print("\nRappel : aucune de ces mesures n'est le chiffre a declarer tel quel. Facteur applique "
          f"{args.audit_factor} ({args.audit_factor_source}). La regle 3.4 sanctionne un ecart "
          "non explique entre ce qu'on declare et ce que leur audit mesure.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
