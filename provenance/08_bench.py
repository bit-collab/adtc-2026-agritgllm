# -*- coding: utf-8 -*-
"""STEP 8 - a WIDE, stable score, because 12 binary items cannot tell two models apart.

The problem, measured on 13/09/2026: across six variants of the same model the 12-item battery
gave 5 to 7 passes in greedy and 0 to 3 at pass^5. One item flipping is worth 8 points, so the
column moved more from luck than from training. Every decision we take needs a number with a
small enough error bar to be trusted.

This script builds that number on HUNDREDS of questions instead of twelve, and it is
DETERMINISTIC first - no model, nothing to pay, reproducible:

  faults   the blocking lint of the pipeline (check.Checker): a figure that is not in the fact,
           a crop or animal that is not the subject, an unknown proper name, an invented month
           or weekday, a service that is not in the material, a bare referral, "the fiche" said
           out loud. These are the round-1 jury's own complaints, written as rules.
  grounded the answer shares at least GROUND_MIN of the reference answer's content words - it
           talks about the same thing, in its own words.
  form     no loop (same 4-gram four times), no cut at max_tokens, length within the fiche's
           own bounds (40-200 words).
  A question COUNTS AS GOOD when the three hold. With k draws per question we report
  pass@1 (share of good draws) and pass^k (questions good on EVERY draw, tau-bench, CME 295 L8).

Optional, with --rubric: the local judge scores each answer on the seven dimensions of the
AgriGPT paper (arXiv 2508.08632, Table 3: correctness, match, fluency, coherence, relevance,
logical consistency, completeness), each 0-3 with a written reason BEFORE the score and a
confidence, the final score being confidence-weighted. Model-based, therefore reported apart
from the deterministic block, never mixed into it.

Usage (TRAINING venv), from concoursllmdata/ :
    .venv-train\\Scripts\\python train-gate2\\08_bench.py --model train-gate2\\outputs\\gguf\\A3\\agritg-a3-Q6_K.gguf --n 200 -k 3
    .venv-train\\Scripts\\python train-gate2\\08_bench.py --model ... --set train --n 150 --rubric
Output: provenance/<tag>/bench-<model>.json  and  bench.md
"""
from __future__ import annotations
import argparse, collections, importlib.util, json, random, re, statistics, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

HERE = Path(__file__).resolve().parent
PIPE = C.ROOT / "rebuild-gate2" / "pipeline"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CMP = load_module("compare04", HERE / "04_compare.py")
JURY = load_module("jury05", HERE / "05_jury.py")

GROUND_MIN = 0.25          # same threshold as check.py's "ungrounded" test
WORDS = (40, 200)          # the length the fiches' own answers keep

RUBRIC = ["correctness", "match", "fluency", "coherence", "relevance", "logic", "completeness"]
RUBRIC_SCHEMA = {"type": "object", "additionalProperties": False,
                 "required": ["reason"] + RUBRIC + ["confidence"],
                 "properties": {**{d: {"type": "integer", "enum": [0, 1, 2, 3]} for d in RUBRIC},
                                "reason": {"type": "string"},
                                "confidence": {"type": "number"}}}
RUBRIC_SYSTEM = """You score ONE answer given by an offline agricultural adviser for Togo, against the REFERENCE answer
written from the verified extension fiche. Write the reason FIRST, then the scores.

Each dimension is 0, 1, 2 or 3:
- correctness: 3 = every statement agrees with the reference; 2 = one minor detail off; 1 = one clear error; 0 = names a wrong cause, disease, product or figure.
- match: 3 = answers the question that was asked; 0 = answers another question.
- fluency: 3 = plain, readable sentences a farmer follows; 0 = broken or repetitive.
- coherence: 3 = the steps hold together and follow an order; 0 = contradicts itself.
- relevance: 3 = nothing off-topic; 0 = mostly filler.
- logic: 3 = the advice follows from the signs described; 0 = a step that does not follow.
- completeness: 3 = carries the reference's actions, figures and who to see; 0 = leaves the farmer without an action.
confidence: 0 to 1, how sure you are of this scoring.
OUTPUT strict JSON only."""


def read_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()] if Path(p).is_file() else []


def content(t):
    return set(re.findall(r"[a-z]{4,}", (t or "").lower()))


def grounding(answer, reference):
    ref = content(reference)
    return round(len(ref & content(answer)) / max(1, len(ref)), 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--set", default="test", choices=["test", "train", "both"])
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("-k", type=int, default=3)
    ap.add_argument("--profile", default="llamacpp", choices=list(JURY.PROFILES))
    ap.add_argument("--rubric", action="store_true", help="+ les 7 dimensions, juge local (lent)")
    ap.add_argument("--rubric-n", type=int, default=60)
    ap.add_argument("--threads", type=int, default=C.TARGET_THREADS)
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--port", type=int, default=8129)
    ap.add_argument("--tag", default=C.EXPERIMENT)
    ap.add_argument("--label", default=None,
                    help="suffixe de fichier quand --only porte plusieurs prefixes")
    ap.add_argument("--only", default=None,
                    help="ne garder que les questions dont le bundle_id commence par ce prefixe, "
                         "par exemple --only handwritten: . Sans filtre, les 390 paires ecrites a la "
                         "main ne pesent que 5,5 %% du jeu et un tirage de 150 n'en attrape que 4 : le "
                         "banc ne dirait rien du materiel ajoute. Le suffixe est ajoute au nom du rapport.")
    ap.add_argument("--dump-dpo", action="store_true",
                    help="ecrire les reponses FAUTIVES comme paires de preference on-policy "
                         "(chosen = la reference, rejected = ce que le modele a repondu). "
                         "Fautes dures du lint seulement : aucun juge, aucun appel API.")
    a = ap.parse_args()

    sys.path.insert(0, str(PIPE))
    import g4_generate as G4, check as CHK
    from lib import chat, parse_json
    import g5_judge as G5
    bundles = {b["bundle_id"]: b for b in read_jsonl(G4.BUNDLES)}
    checker = CHK.Checker()

    # --only accepte plusieurs prefixes separes par une virgule, ou un chemin de fichier JSON
    # contenant {"held_bundles": [...]}. C'est ce qui permet de mesurer separement les paquets
    # tenus a l'ecart du GRPO : sans cette separation on ne peut pas distinguer -le modele a
    # appris la matiere- de -le modele a appris le banc-.
    only = None
    if a.only:
        if a.only.lower().endswith(".json"):
            only = tuple(json.loads(Path(a.only).read_text(encoding="utf-8"))["held_bundles"])
        else:
            only = tuple(x for x in a.only.split(",") if x)

    rows = []
    for name in (["sft_test"] if a.set == "test" else ["sft_train"] if a.set == "train"
                 else ["sft_test", "sft_train"]):
        for r in read_jsonl(C.SPLIT / f"{name}.jsonl"):
            b = bundles.get(r.get("bundle_id", ""))
            if not b or r.get("kind") in ("doc",):
                continue
            msgs = r["messages"]
            if msgs[-1]["role"] != "assistant":
                continue
            if only and not any(r["bundle_id"].startswith(x) for x in only):
                continue
            rows.append({"set": name, "bundle_id": r["bundle_id"], "kind": r.get("kind"),
                         "history": msgs[:-1], "reference": msgs[-1]["content"], "bundle": b})
    random.Random(C.SEED + 8).shuffle(rows)
    if a.n:
        rows = rows[:a.n]
    path = Path(a.model)
    print(f"banc large : {len(rows)} questions x {a.k} tirages ({a.profile}) sur {path.name}")

    port = CMP.free_port(a.port)
    log = C.ANSWERS / a.tag / f"bench-{path.stem}-server.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    per_item, draws_out, dpo_rows = [], [], []
    faults = collections.Counter()
    t0 = time.time()
    with CMP.Server(path, a.threads, port, 2048, log):
        for i, r in enumerate(rows):
            farmer = "\n".join(m["content"] for m in r["history"] if m["role"] == "user")
            draws = []
            for s in range(a.k):
                try:
                    out = JURY.ask(port, r["history"], a.max_tokens, a.profile, C.SEED + s)
                except Exception as e:
                    faults["server_error"] += 1
                    continue
                ans = CMP.to_ascii_punct(out["answer"])
                bad = [x for x in checker.check(ans, r["bundle"], final=True, user_text=farmer)
                       if x.split(":")[0] in CHK.BLOCKING]
                g = grounding(ans, r["reference"])
                nw = len(ans.split())
                form = (not JURY.looping(ans) and out["finish_reason"] != "length"
                        and WORDS[0] <= nw <= WORDS[1])
                ok = not bad and g >= GROUND_MIN and form
                for x in bad:
                    faults[x.split(":")[0]] += 1
                if not form:
                    faults["form"] += 1
                if g < GROUND_MIN:
                    faults["ungrounded"] += 1
                draws.append({"answer": ans, "ok": ok, "faults": bad, "grounding": g, "words": nw})
                if a.dump_dpo and bad and r["set"] == "sft_train" and ans != r["reference"]:
                    # A hard lint fault is a fault the fiche itself contradicts: an invented
                    # figure, another crop, a service that is not in the material. The reference
                    # answer of the same question is the chosen side. No model judges this.
                    dpo_rows.append({"row_id": f"bench:{r['bundle_id']}#{i}.{s}",
                                     "bundle_id": r["bundle_id"], "source": "onpolicy:" + bad[0].split(":")[0],
                                     "prompt": r["history"],
                                     "chosen": [{"role": "assistant", "content": r["reference"]}],
                                     "rejected": [{"role": "assistant", "content": ans}],
                                     "why": bad})
                draws_out.append({"bundle_id": r["bundle_id"], "set": r["set"], "draw": s,
                                  "ok": ok, "faults": bad, "grounding": g, "answer": ans})
            if not draws:
                continue
            per_item.append({"bundle_id": r["bundle_id"], "set": r["set"], "kind": r["kind"],
                             "reference": r["reference"], "history": r["history"],
                             "pass_at_1": sum(1 for d in draws if d["ok"]) / len(draws),
                             "all_pass": all(d["ok"] for d in draws),
                             "grounding": round(statistics.mean(d["grounding"] for d in draws), 3),
                             "similarity": JURY.similarity([d["answer"] for d in draws]),
                             "draws": draws})
            if (i + 1) % 25 == 0 or i + 1 == len(rows):
                el = time.time() - t0
                p1 = statistics.mean(x["pass_at_1"] for x in per_item)
                print(f"  {i + 1}/{len(rows)}  pass@1 {p1:.3f}  "
                      f"pass^{a.k} {sum(1 for x in per_item if x['all_pass']) / len(per_item):.3f}  "
                      f"{CMP.human(el)}  reste ~{CMP.human(el / (i + 1) * (len(rows) - i - 1))}")

    # Le filtre est ecrit DANS la mesure, pas seulement dans le nom du fichier. Corrige le
    # 18/09/2026 : evolution_report.py devinait le jeu en cherchant "handwritten" ou "holdout"
    # dans le nom, donc les bancs nommes autrement s'affichaient tous comme "tout" et le rapport
    # montrait 0,16 et 0,79 sur la meme ligne, pour le meme modele, avec la meme etiquette.
    res = {"model": str(path), "profile": a.profile, "k": a.k, "questions": len(per_item),
           "set": a.set, "only": (list(only) if only else None), "label": a.label,
           "pass_at_1": round(statistics.mean(x["pass_at_1"] for x in per_item), 4),
           "pass_pow_k": round(sum(1 for x in per_item if x["all_pass"]) / len(per_item), 4),
           "grounding": round(statistics.mean(x["grounding"] for x in per_item), 3),
           "similarity": round(statistics.mean(x["similarity"] for x in per_item
                                               if x["similarity"] is not None), 3),
           "faults": dict(faults.most_common()),
           "per_set": {}}
    for s in sorted({x["set"] for x in per_item}):
        sub = [x for x in per_item if x["set"] == s]
        res["per_set"][s] = {"questions": len(sub),
                             "pass_at_1": round(statistics.mean(x["pass_at_1"] for x in sub), 4),
                             "pass_pow_k": round(sum(1 for x in sub if x["all_pass"]) / len(sub), 4)}
    # the error bar, so two runs can actually be compared
    n = len(per_item)
    res["pass_at_1_stderr"] = round((res["pass_at_1"] * (1 - res["pass_at_1"]) / n) ** 0.5, 4)

    if a.rubric:
        print(f"\nrubrique ({G5.JUDGE_MODEL}, {a.rubric_n} questions, 1 tirage chacune)...")
        scores = collections.defaultdict(list)
        for j, it in enumerate(per_item[:a.rubric_n]):
            d = it["draws"][0]
            user = (f"QUESTION:\n{it['history'][-1]['content']}\n\nREFERENCE ANSWER:\n{it['reference']}"
                    f"\n\nANSWER TO SCORE:\n{d['answer']}")
            try:
                v = parse_json(chat(G5.JUDGE_MODEL, RUBRIC_SYSTEM, user, temperature=0,
                                    num_ctx=8192, num_predict=700, think=False,
                                    schema=RUBRIC_SCHEMA)[0])
                w = max(0.0, min(1.0, float(v.get("confidence", 1))))
                for dim in RUBRIC:
                    scores[dim].append((float(v[dim]), w))
            except Exception as e:
                scores["error"].append((0.0, 0.0))
            if (j + 1) % 20 == 0:
                print(f"  {j + 1}/{min(a.rubric_n, len(per_item))}")
        res["rubric"] = {dim: round(sum(s * w for s, w in v) / max(1e-9, sum(w for _, w in v)), 2)
                         for dim, v in scores.items() if dim != "error" and v}
        if res["rubric"]:
            res["rubric"]["overall"] = round(statistics.mean(res["rubric"].values()), 2)
        res["rubric_judge"] = G5.JUDGE_MODEL
        res["rubric_errors"] = len(scores.get("error", []))

    prov = C.PROV / a.tag
    prov.mkdir(parents=True, exist_ok=True)
    suffixe = ("-" + a.label if a.label else
               "" if not only else
               "-" + only[0].strip(":").replace(":", "-") if len(only) == 1 else
               "-subset%d" % len(only))
    (prov / f"bench-{path.stem}{suffixe}.json").write_text(
        json.dumps({**res, "per_item": per_item}, ensure_ascii=False, indent=1), encoding="utf-8")
    (C.ANSWERS / a.tag / f"bench-{path.stem}{suffixe}.jsonl").write_text(
        "\n".join(json.dumps(d, ensure_ascii=False) for d in draws_out) + "\n", encoding="utf-8")

    print(f"\n=== {path.name} ===")
    print(f"  questions      {res['questions']}  x {a.k} tirages")
    print(f"  pass@1         {res['pass_at_1']:.3f} +/- {res['pass_at_1_stderr']:.3f}")
    print(f"  pass^{a.k}         {res['pass_pow_k']:.3f}")
    print(f"  ancrage        {res['grounding']:.3f}   similarite entre tirages {res['similarity']:.3f}")
    print(f"  fautes         {res['faults']}")
    for s, v in res["per_set"].items():
        print(f"  {s:10}     pass@1 {v['pass_at_1']:.3f}  pass^{a.k} {v['pass_pow_k']:.3f}  ({v['questions']} questions)")
    if res.get("rubric"):
        print(f"  rubrique       {res['rubric']}")
    if a.dump_dpo and dpo_rows:
        out = C.DATA / "onpolicy_dpo.jsonl"
        seen = {json.dumps([r["prompt"], r["rejected"]], sort_keys=True) for r in read_jsonl(out)}
        fresh = [r for r in dpo_rows
                 if json.dumps([r["prompt"], r["rejected"]], sort_keys=True) not in seen]
        with open(out, "a", encoding="utf-8") as f:
            for r in fresh:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"  paires de preference on-policy : +{len(fresh)} (sur {len(dpo_rows)} fautes) -> {out}")
    print(f"-> {prov / f'bench-{path.stem}.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
