# -*- coding: utf-8 -*-
"""STEP 5 - measure a GGUF the way the JURY will see it, not the way our bench likes it.

Why this script exists (13/09/2026):

  * 04_compare.py asks every question ONCE, in greedy decoding (temperature 0, top_k 1). The
    Qwen3 model card says, verbatim: "Do not use greedy decoding, as it can lead to performance
    degradation and endless repetitions", and recommends T 0.7 / top-p 0.8 / top-k 20 for the
    non-thinking mode. The jury will most likely run llama.cpp with ITS defaults
    (T 0.8 / top-k 40 / top-p 0.95 / min-p 0.05). We had never measured the model under either.
  * One draw says nothing about robustness. CME 295 lecture 8 (tau-bench): pass^k = the
    probability that ALL k attempts succeed. That is what a human jury experiences when it asks
    the same kind of question several times. We report pass@1 (mean) AND pass^k (all).
  * The 12 acceptance items partly answer prompts the model was TRAINED on. The honest
    generalisation figure is the held-out test split (5 fiches never seen): here it is replayed
    and graded by the pipeline's own judge (g5_judge.judge_one: sentence by sentence against the
    fiche material, evidence copied before the verdict, binary at the end - lecture 8 p78).
    The judge is qwen (Alibaba) and the answers come from our Qwen3 student - same family, but
    the rule "the writer never corrects" concerns the WRITER of the training data (gpt-oss), and
    the judge only checks support against the fiche, it does not write. The report says so.

Usage, from concoursllmdata/ with .venv-train (needs psutil only for nothing here; Groq key
for --judge, as for the pipeline):
    .venv-train\\Scripts\\python train-gate2\\05_jury.py --quants Q4_K_M Q6_K
    .venv-train\\Scripts\\python train-gate2\\05_jury.py --quants Q6_K --profiles greedy qwen llamacpp -k 5
    .venv-train\\Scripts\\python train-gate2\\05_jury.py --quants Q6_K --set test --test-n 60 --judge
    .venv-train\\Scripts\\python train-gate2\\05_jury.py --model path\\to\\any.gguf --profiles llamacpp -k 3

Produces
    outputs/answers/<tag>/jury-<model>-<profile>.jsonl     every draw, kept as evidence
    provenance/<tag>/jury.json  and  jury.md               the table, pass@1 / pass^k per set
"""
from __future__ import annotations
import argparse, collections, importlib.util, json, random, re, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

HERE = Path(__file__).resolve().parent
PIPE = C.ROOT / "rebuild-gate2" / "pipeline"
GOLD = C.ROOT / "rebuild-gate2" / "gold"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CMP = load_module("compare04", HERE / "04_compare.py")          # Server, to_ascii_punct, checker

# --- the three ways the model will be sampled ------------------------------------------------
# greedy   : what 04_compare.py measured until now. Qwen's card warns against it.
# qwen     : the model card's recommendation for non-thinking mode (Qwen/Qwen3-0.6B, read 13/09/2026).
# llamacpp : llama.cpp's own defaults (tools/cli/README.md), i.e. what a jury member gets by
#            typing `llama-cli -m model.gguf` and nothing else.
PROFILES = {
    "greedy":   {"temperature": 0.0, "top_k": 1},
    "qwen":     {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0},
    "llamacpp": {"temperature": 0.8, "top_k": 40, "top_p": 0.95, "min_p": 0.05},
    # Liquid AI's own recommendation for LFM2 (model card, read 14/09/2026). Much colder than
    # Qwen's: a low temperature plus a high min_p is exactly what suppresses ungrounded and
    # invented_figure, the two dominant faults on the bench.
    "lfm2":     {"temperature": 0.3, "min_p": 0.15, "repeat_penalty": 1.05},
}


def ask(port, messages, max_tokens, profile, seed, timeout=900):
    body = {"messages": messages, "max_tokens": max_tokens, "seed": seed, **PROFILES[profile]}
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    ch = d["choices"][0]
    usage = d.get("usage", {})
    return {"answer": (ch["message"].get("content") or "").strip(),
            "finish_reason": ch.get("finish_reason"), "tokens": usage.get("completion_tokens"),
            "seconds": round(time.time() - t0, 2)}


def similarity(answers):
    """Mean pairwise overlap of content words between the k draws of one question. Measured
    13/09/2026: 0.20 on the cycle-2 model - two answers to the SAME question share a fifth of
    their words. That is the regularity problem in one number, so the report carries it."""
    import itertools
    sets = [set(re.findall(r"[a-z]{4,}", a.lower())) for a in answers if a]
    if len(sets) < 2:
        return None
    sims = [len(a & b) / max(1, len(a | b)) for a, b in itertools.combinations(sets, 2)]
    return round(sum(sims) / len(sims), 3)


def looping(answer, n=4, times=4):
    """The failure Qwen's card warns about: the same 4-gram coming back 4+ times, or a cut at
    max_tokens. A looping answer is a failed answer for a human reader whatever the keywords."""
    w = answer.lower().split()
    if len(w) < n * times:
        return False
    c = collections.Counter(tuple(w[i:i + n]) for i in range(len(w) - n + 1))
    return max(c.values()) >= times


# --- item sets -------------------------------------------------------------------------------
def acceptance_items():
    return [json.loads(l) for l in (GOLD / "acceptance.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def test_items(n, seed):
    """Held-out rows, replayed as the jury would: the whole history up to the last user turn.
    Each row is tied back to its bundle (through pairs_clean.jsonl) so the judge gets the SAME
    material the writer had. Gold rows (hand-written, no bundle) are judged against their gold
    answer instead - said in the report."""
    rows = [json.loads(l) for l in (C.SPLIT / "sft_test.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    pairs = {}
    for l in (C.PAIRS / "pairs_clean.jsonl").read_text(encoding="utf-8").splitlines():
        if l.strip():
            p = json.loads(l)
            pairs[json.dumps(p["messages"], ensure_ascii=False, sort_keys=True)] = p
    items = []
    for i, r in enumerate(rows):
        ms = r["messages"]
        if not ms or ms[-1]["role"] != "assistant":
            continue
        p = pairs.get(json.dumps(ms, ensure_ascii=False, sort_keys=True))
        items.append({"id": f"test:{i}:{p['bundle_id'] if p else 'gold'}", "history": ms[:-1],
                      "gold": ms[-1]["content"], "bundle_id": p["bundle_id"] if p else None,
                      "kind": p["kind"] if p else "gold"})
    rnd = random.Random(seed)
    rnd.shuffle(items)
    return items[:n] if n else items


# --- grading ---------------------------------------------------------------------------------
def grade_acceptance(checker, it, answer):
    clean = CMP.to_ascii_punct(answer)
    core = checker.check(it, it.get("core", {}), clean)
    extra = checker.check(it, it.get("extra", {}), clean)
    return {"ok": not core and not looping(answer), "core": core, "extra": extra}


class Judge:
    """The pipeline's judge, untouched. Loaded only with --judge, because it costs API calls."""
    def __init__(self):
        sys.path.insert(0, str(PIPE))
        import g5_judge, g4_generate, check as chk  # noqa
        self.g5, self.g4, self.block_at = g5_judge, g4_generate, chk.JUDGE_BLOCK_AT
        self.bundles = {b["bundle_id"]: b for b in self.g5.read_jsonl(self.g4.BUNDLES)}
        self.model = g5_judge.JUDGE_MODEL

    def grade(self, it, answer):
        b = self.bundles.get(it["bundle_id"]) if it["bundle_id"] else None
        material = self.g4.material(b) if b else f"REFERENCE ANSWER (hand-written):\n{it['gold']}"
        farmer = "\n".join(m["content"] for m in it["history"] if m["role"] == "user")
        v = self.g5.judge_one(self.model, material, farmer, answer)
        ok = not v["contradicted"] and len(v["unsupported"]) < self.block_at and not looping(answer)
        return {"ok": ok, "contradicted": v["contradicted"], "unsupported": v["unsupported"],
                "material_source": "bundle" if b else "gold_answer",
                "rationale": [{"n": s.get("n"), "verdict": s["verdict"], "evidence": s.get("evidence", "")}
                              for s in v["sentences"]]}


# --- one model x one profile -----------------------------------------------------------------
def run(model_name, path, sets, args, checker, judge):
    res = {"model": model_name, "file": str(path), "size_mb": round(path.stat().st_size / (1 << 20), 1),
           "profiles": {}}
    port = CMP.free_port(args.port)
    log = C.ANSWERS / args.tag / f"jury-{model_name}-server.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with CMP.Server(path, args.threads, port, args.ctx, log):
        for prof in args.profiles:
            k = 1 if prof == "greedy" else args.k
            print(f"\n=== {model_name} | {prof} {PROFILES[prof]} | k={k} ===")
            out = {"sampling": PROFILES[prof], "k": k, "sets": {}}
            draws = []
            for set_name, items in sets.items():
                per_item = []
                for it in items:
                    hist = it.get("history") or [{"role": "user", "content": it["prompt"]}]
                    oks, rows = [], []
                    for i in range(k):
                        r = ask(port, hist, args.max_tokens, prof, C.SEED + i)
                        if set_name == "accept":
                            g = grade_acceptance(checker, it, r["answer"])
                        elif judge is not None:
                            try:
                                g = judge.grade(it, r["answer"])
                            except Exception as e:      # the judge is an API: say it, do not hide it
                                g = {"ok": None, "error": f"{type(e).__name__}: {e}"[:200]}
                        else:
                            g = {"ok": None}
                        loop = looping(r["answer"])
                        oks.append(g["ok"])
                        rows.append({**r, "draw": i, "grade": g, "loop": loop,
                                     "words": len(r["answer"].split())})
                        draws.append({"set": set_name, "id": it["id"], "draw": i, "profile": prof,
                                      "answer": r["answer"], "finish_reason": r["finish_reason"],
                                      "loop": loop, "ok": g["ok"],
                                      "why": g.get("core") or g.get("contradicted") or g.get("unsupported") or g.get("error")})
                    known = [o for o in oks if o is not None]
                    p1 = (sum(known) / len(known)) if known else None
                    pk = all(known) if known and len(known) == k else None
                    per_item.append({"id": it["id"], "pass_at_1": p1, "pass_pow_k": pk,
                                     "similarity": similarity([x["answer"] for x in rows]),
                                     "loops": sum(1 for x in rows if x["loop"]),
                                     "truncated": sum(1 for x in rows if x["finish_reason"] == "length"),
                                     "mean_words": round(sum(x["words"] for x in rows) / len(rows), 1),
                                     "draws": rows})
                    if set_name == "accept" or args.verbose:
                        mark = "PASSE " if pk else ("ECHOUE" if pk is not None else "  ?   ")
                        why = ""
                        if pk is False:
                            bad = next((x["grade"] for x in rows if x["grade"].get("ok") is False), {})
                            why = " ; ".join((bad.get("core") or bad.get("contradicted") or bad.get("unsupported") or [bad.get("error", "")])[:2])
                            if any(x["loop"] for x in rows):
                                why = "BOUCLE ; " + why
                        print(f"  {mark} {it['id'][:40]:40} pass@1 {p1 if p1 is None else round(p1, 2)!s:5} "
                              f"{per_item[-1]['mean_words']:5.0f} mots  {why[:90]}")
                known = [x for x in per_item if x["pass_at_1"] is not None]
                summary = {"items": len(per_item), "graded": len(known),
                           "pass_at_1": round(sum(x["pass_at_1"] for x in known) / len(known), 3) if known else None,
                           "pass_pow_k": round(sum(1 for x in known if x["pass_pow_k"]) / len(known), 3) if known else None,
                           "items_all_pass": sum(1 for x in known if x["pass_pow_k"]),
                           "loop_rate": round(sum(x["loops"] for x in per_item) / max(1, k * len(per_item)), 3),
                           "truncated_rate": round(sum(x["truncated"] for x in per_item) / max(1, k * len(per_item)), 3),
                           "mean_words": round(sum(x["mean_words"] for x in per_item) / max(1, len(per_item)), 1),
                           "similarity": round(sum(x["similarity"] for x in per_item if x["similarity"] is not None)
                                               / max(1, sum(1 for x in per_item if x["similarity"] is not None)), 3),
                           "per_item": per_item}
                out["sets"][set_name] = summary
                print(f"  {set_name}: similarite {summary['similarity']}  pass@1 {summary['pass_at_1']}  pass^{k} {summary['pass_pow_k']} "
                      f"({summary['items_all_pass']}/{summary['graded']})  boucles {summary['loop_rate']}  "
                      f"coupees {summary['truncated_rate']}  {summary['mean_words']} mots")
            f = C.ANSWERS / args.tag / f"jury-{model_name}-{prof}.jsonl"
            f.write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in draws) + "\n", encoding="utf-8")
            out["answers_file"] = str(f)
            res["profiles"][prof] = out
    return res


def markdown(results, args, judge_used):
    L = [f"# Le modele vu par le jury - experience {args.tag}", "",
         f"*Mesure du {time.strftime('%d/%m/%Y %H:%M')}, {args.threads} threads, k = {args.k} tirages "
         f"par question (1 en glouton), max {args.max_tokens} tokens, sans prompt systeme.*", "",
         "**Pourquoi trois echantillonnages.** `greedy` est ce que 04_compare.py mesurait. La carte "
         "de Qwen3-0.6B dit de ne pas l'utiliser (degradation, repetitions sans fin) et recommande "
         "`qwen` = T 0,7 / top-p 0,8 / top-k 20. `llamacpp` = les valeurs par defaut de llama.cpp "
         "(T 0,8 / top-k 40 / top-p 0,95 / min-p 0,05), soit ce qu'un jure obtient sans rien regler.", "",
         "**pass@1** = part des tirages qui passent. **pass^k** = part des questions qui passent a "
         "TOUS les tirages (CME 295 L8, tau-bench) : c'est la robustesse qu'un humain ressent. "
         "Une reponse qui boucle (meme 4-gramme 4 fois ou plus) compte comme ratee.", "",
         "**similarite** = recouvrement moyen des mots de contenu entre les k tirages d'une meme "
         "question. Basse = le modele recompose une reponse differente a chaque fois, et aucun "
         "mot-cle n'est garanti ; c'est la mesure directe de la regularite.", "",
         "| Modele | Echantillonnage | Jeu | similarite | pass@1 | pass^k | questions 100 % | boucles | coupees | mots |",
         "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        for prof, o in r["profiles"].items():
            for s, v in o["sets"].items():
                L.append(f"| {r['model']} | {prof} | {s} | {v['similarity']} | {v['pass_at_1']} | {v['pass_pow_k']} "
                         f"| {v['items_all_pass']}/{v['graded']} | {v['loop_rate']} | {v['truncated_rate']} | {v['mean_words']} |")
    L += ["", "## Ce qui echoue, par question", ""]
    for r in results:
        for prof, o in r["profiles"].items():
            acc = o["sets"].get("accept")
            if not acc:
                continue
            L.append(f"### {r['model']} - {prof}")
            for it in acc["per_item"]:
                if it["pass_pow_k"]:
                    continue
                bad = [d["grade"] for d in it["draws"] if d["grade"].get("ok") is False]
                reasons = collections.Counter()
                for g in bad:
                    for b in (g.get("core") or []):
                        reasons[b] += 1
                loops = it["loops"]
                L.append(f"- **{it['id']}** : pass@1 {it['pass_at_1']}" + (f", {loops} boucle(s)" if loops else "")
                         + " ; " + " ; ".join(f"{b} ({n}/{o['k']})" for b, n in reasons.most_common(4)))
            L.append("")
    if judge_used:
        L += ["## Le jeu test (fiches jamais vues)", "",
              "Juge : `g5_judge.judge_one` du pipeline, phrase par phrase contre le materiel de la "
              "fiche, preuve copiee avant verdict, barre binaire = 0 contredite et moins de "
              f"{judge_used} non soutenue(s), comme pour les donnees. Le juge est un Qwen 27B et "
              "l'eleve un Qwen 0,6B : meme famille, mais le juge ne redige rien, il verifie contre "
              "la fiche ; la regle \"celui qui ecrit ne corrige jamais\" vise le redacteur des "
              "donnees (gpt-oss), et elle tient.", ""]
    L += ["## Comment lire", "",
          "- Un ecart glouton / echantillonne sur pass@1 dit si le 4/12 etait un chiffre de "
          "decodage ou du modele.",
          "- Un pass^k bas avec un pass@1 haut = le modele SAIT mais n'est pas fiable : c'est le "
          "cas ou les donnees on-policy (reponses du modele filtrees) rapportent le plus.",
          "- Les reponses de chaque tirage sont dans `outputs/answers/" + args.tag + "/jury-*.jsonl`.", ""]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default=C.EXPERIMENT)
    ap.add_argument("--quants", nargs="*", default=None, help="ex: Q4_K_M Q6_K (GGUF de outputs/gguf/<tag>)")
    ap.add_argument("--model", nargs="*", default=None, help="chemins GGUF explicites")
    ap.add_argument("--profiles", nargs="*", default=["greedy", "qwen", "llamacpp"], choices=list(PROFILES))
    ap.add_argument("-k", type=int, default=5, help="tirages par question pour les profils echantillonnes")
    ap.add_argument("--set", default="accept", choices=["accept", "test", "both"])
    ap.add_argument("--test-n", type=int, default=60, help="0 = tout le jeu test")
    ap.add_argument("--judge", action="store_true", help="noter le jeu test avec le juge du pipeline (API)")
    ap.add_argument("--threads", type=int, default=C.TARGET_THREADS)
    ap.add_argument("--ctx", type=int, default=2048)
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--port", type=int, default=8109)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    models = []
    for p in args.model or []:
        models.append((Path(p).stem, Path(p)))
    for q in args.quants or []:
        p = C.GGUF / args.tag / f"agritg-{args.tag.lower()}-0.6b-{q}.gguf"
        models.append((q, p))
    if not models:
        sys.exit("donner --quants ou --model")
    for _, p in models:
        if not p.exists():
            sys.exit(f"absent : {p}")

    checker = CMP.load_checker() if hasattr(CMP, "load_checker") else CMP.load_module("acceptance", CMP.ACCEPTANCE_PY)
    sets = {}
    if args.set in ("accept", "both"):
        sets["accept"] = acceptance_items()
    if args.set in ("test", "both"):
        sets["test"] = test_items(args.test_n, C.SEED)
        print(f"jeu test : {len(sets['test'])} conversations rejouees"
              + (" (juge du pipeline)" if args.judge else " (sans juge : longueur, boucles, coupures seulement)"))
    judge = Judge() if (args.judge and "test" in sets) else None

    results = [run(name, path, sets, args, checker, judge) for name, path in models]
    prov = C.PROV / args.tag
    prov.mkdir(parents=True, exist_ok=True)
    (prov / "jury.json").write_text(json.dumps(
        {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "k": args.k, "profiles": PROFILES,
         "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    (prov / "jury.md").write_text(markdown(results, args, judge.block_at if judge else None), encoding="utf-8")
    print(f"\n-> {prov / 'jury.md'}")


if __name__ == "__main__":
    main()
