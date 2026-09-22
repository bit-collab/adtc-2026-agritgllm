# Split the generated pairs into train / eval / test by sheet, never by line, and write data/*.jsonl with the leakage checks.
from __future__ import annotations
import json, random, re, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
sys.path.insert(0, str(C.ROOT / "rebuild-gate2" / "pipeline"))
from augment import ascii_punct

N_UNKNOWN_TEST = 20

GOLD_KINDS = {"identity", "limit", "greeting", "verdict"}
HELD_OUT_GOLD_TOPICS = set(getattr(C, "HELD_OUT_GOLD_TOPICS", ["mixing_chemicals"]))


def read(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def write(p, rows, keys=("messages",)):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            d = {k: r[k] for k in keys if k in r}
            if "messages" in d:
                d["messages"] = [{"role": m["role"], "content": ascii_punct(m["content"])} for m in d["messages"]]
            for k in ("prompt", "chosen", "rejected"):
                if isinstance(d.get(k), str):
                    d[k] = ascii_punct(d[k])
                elif isinstance(d.get(k), list):
                    d[k] = [{**m, "content": ascii_punct(m["content"])} if isinstance(m, dict) else m for m in d[k]]
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    return len(rows)


def fiche_of(bundle_id):
    parts = bundle_id.split(":")
    if parts[0] in GOLD_KINDS:
        return None
    return parts[1] if len(parts) >= 2 else bundle_id


def touches(bundle_id, fiches):
    f = fiche_of(bundle_id)
    return False if f is None else any(x in fiches for x in f.split("|"))


def content_words(t):
    return set(re.findall(r"[a-z]{4,}", t.lower()))


def canonical_answers(rows, k):
    groups = defaultdict(list)
    for r in rows:
        turns = sum(1 for m in r["messages"] if m["role"] == "assistant")
        groups[(r["bundle_id"], turns)].append(r)
    changed = 0
    for (_, _), grp in groups.items():
        answers = []
        for r in grp:
            a = [m["content"] for m in r["messages"] if m["role"] == "assistant"][-1]
            if a not in answers:
                answers.append(a)
        if len(answers) <= k:
            continue
        toks = [content_words(a) for a in answers]
        score = []
        for i, ti in enumerate(toks):
            sims = [len(ti & tj) / max(1, len(ti | tj)) for j, tj in enumerate(toks) if i != j]
            score.append((sum(sims) / len(sims), -abs(len(answers[i].split()) - 110), i))
        keep = [answers[i] for _, _, i in sorted(score, reverse=True)[:k]]
        for n, r in enumerate(grp):
            last = max(i for i, m in enumerate(r["messages"]) if m["role"] == "assistant")
            if r["messages"][last]["content"] in keep:
                continue
            r["messages"] = [dict(m) for m in r["messages"]]
            r["messages"][last]["content"] = keep[n % len(keep)]
            changed += 1
    return changed


def gold_topic(row):
    return (row.get("topic") or row.get("bundle_id", "")).split(":")[-1]


def main():
    clean = read(C.PAIRS / "pairs_clean.jsonl")
    hand_p = C.PAIRS / "pairs_handwritten.jsonl"
    hand = read(hand_p) if hand_p.is_file() else []
    clean += hand
    noisy_p = C.PAIRS / "pairs_noisy.jsonl"
    noisy = read(noisy_p) if noisy_p.is_file() else []
    dpo = read(C.DATA / "dpo.jsonl")
    docs_p, unk_p = C.DATA / "docs.jsonl", C.DATA / "unknowns.jsonl"
    docs = read(docs_p) if docs_p.is_file() else []
    unknowns = read(unk_p) if unk_p.is_file() else []
    onp_sft_p, onp_dpo_p = C.DATA / "onpolicy_sft.jsonl", C.DATA / "onpolicy_dpo.jsonl"
    onp_sft = read(onp_sft_p) if onp_sft_p.is_file() else []
    dpo += read(onp_dpo_p) if onp_dpo_p.is_file() else []
    n_expose = sum(1 for r in clean if str(r.get("gate", "")).startswith("expose"))
    print(f"{len(clean)} paires propres dont {len(hand)} ecrites a la main (et {n_expose} "
          f"reformulations 'expose'), {len(noisy)} copies "
          f"bruitees, {len(docs)} documents, {len(unknowns)} reponses hors fiches, {len(dpo)} paires de preference")

    test_fiches = set(C.TEST_FICHES)
    known = {fiche_of(r["bundle_id"]) for r in clean} - {None}
    missing = [f for f in test_fiches if f not in known and not any(f in k for k in known)]
    if missing:
        print(f"  ATTENTION : fiches de test introuvables dans les paires : {missing}")

    parts = defaultdict(list)
    rest = []
    for r in clean:
        if touches(r["bundle_id"], test_fiches):
            parts["test"].append(r)
        elif r["kind"] in GOLD_KINDS and gold_topic(r) in HELD_OUT_GOLD_TOPICS:
            parts["test"].append(r)
        else:
            rest.append(r)

    kind_of = {}
    for r in rest:
        kind_of.setdefault(r["bundle_id"], r.get("kind"))
    bundles = sorted({r["bundle_id"] for r in rest
                      if kind_of.get(r["bundle_id"]) not in GOLD_KINDS
                      and not r["bundle_id"].startswith("handwritten:")})
    rng = random.Random(C.SEED)
    rng.shuffle(bundles)
    n_eval = max(1, int(len(bundles) * C.EVAL_BUNDLE_FRACTION))
    eval_bundles = set(bundles[:n_eval])
    for r in rest:
        parts["eval" if r["bundle_id"] in eval_bundles else "train"].append(r)

    train_ids = {r["row_id"] for r in parts["train"]}
    for r in noisy:
        if r.get("row_id", "").split("#noisy")[0] in train_ids:
            parts["train"].append(r)

    n_docs_train = n_docs_dropped = 0
    for r in docs:
        if touches(r["bundle_id"], test_fiches):
            n_docs_dropped += 1
        else:
            parts["train"].append(r)
            n_docs_train += 1

    n_onp = 0
    for r in onp_sft:
        if touches(r["bundle_id"], test_fiches) or r["bundle_id"] in eval_bundles:
            continue
        if r["kind"] in GOLD_KINDS and gold_topic(r) in HELD_OUT_GOLD_TOPICS:
            continue
        parts["train"].append(r)
        n_onp += 1

    unk_bundles = sorted({r["bundle_id"] for r in unknowns})
    rng_u = random.Random(C.SEED + 1)
    rng_u.shuffle(unk_bundles)
    unk_test = set(unk_bundles[:N_UNKNOWN_TEST])
    for r in unknowns:
        parts["test" if r["bundle_id"] in unk_test else "train"].append(r)

    n_canon = 0
    if getattr(C, "ANSWER_VARIANTS", 0):
        target = [r for r in parts["train"] if r.get("bundle_id") and r.get("kind") not in ("doc", "unknown")]
        n_canon = canonical_answers(target, C.ANSWER_VARIANTS)
        n_canon += canonical_answers([r for r in parts["eval"] if r.get("bundle_id")], C.ANSWER_VARIANTS)
        distinct = defaultdict(set)
        for r in target:
            distinct[r["bundle_id"]].add([m["content"] for m in r["messages"] if m["role"] == "assistant"][-1])
        med = sorted(len(v) for v in distinct.values())[len(distinct) // 2] if distinct else 0
        print(f"  canonisation : {n_canon} reponses remplacees, mediane {med} reponses distinctes "
              f"par fait (cible {C.ANSWER_VARIANTS}) ; toutes les questions sont conservees")

    n_tr = write(C.SPLIT / "sft_train.jsonl", parts["train"], keys=("messages", "bundle_id", "gate", "kind"))
    n_ev = write(C.SPLIT / "sft_eval.jsonl", parts["eval"], keys=("messages", "bundle_id", "gate", "kind"))
    n_te = write(C.SPLIT / "sft_test.jsonl", parts["test"],
                 keys=("messages", "bundle_id", "gate", "kind"))

    keep_dpo, drop_dpo, drop_judge_error = [], 0, 0
    for r in dpo:
        bid = str(r.get("row_id", "")).split("#")[0]
        if touches(bid, test_fiches) or bid in eval_bundles:
            drop_dpo += 1
            continue
        if C.DPO_SOURCES and str(r.get("source", "")).split(":")[0] not in C.DPO_SOURCES:
            continue
        if str(r.get("source", "")).endswith("judge_error"):
            drop_judge_error += 1
            continue
        keep_dpo.append(r)
    n_dpo = write(C.SPLIT / "dpo_train.jsonl", keep_dpo, keys=("prompt", "chosen", "rejected"))

    def answers(rows):
        out = set()
        for r in rows:
            last = [m["content"].strip() for m in r["messages"] if m["role"] == "assistant"]
            if last:
                out.add(last[-1])
        return out
    tr_a = answers(parts["train"])
    leak_ev = len(answers(parts["eval"]) & tr_a)
    leak_te = len(answers(parts["test"]) & tr_a)
    tr_b = {r["bundle_id"] for r in parts["train"]}
    share_ev = len(({r["bundle_id"] for r in parts["eval"]}) & tr_b)
    share_te = len(({r["bundle_id"] for r in parts["test"]}) & tr_b)

    manifest = {
        "seed": C.SEED, "base_model": C.BASE_MODEL, "base_revision": C.BASE_REVISION,
        "test_fiches": sorted(test_fiches),
        "held_out_gold_topics": sorted(HELD_OUT_GOLD_TOPICS),
        "eval_bundle_fraction": C.EVAL_BUNDLE_FRACTION,
        "eval_bundles": sorted(eval_bundles),
        "counts": {"sft_train": n_tr, "sft_eval": n_ev, "sft_test": n_te,
                   "dpo_train": n_dpo, "dpo_dropped_held_out": drop_dpo,
                   "dpo_dropped_judge_error": drop_judge_error,
                   "expose_rows_in_clean": n_expose, "docs_in_train": n_docs_train,
                   "onpolicy_sft_in_train": n_onp, "answers_canonicalised": n_canon,
                   "answer_variants_per_fact": getattr(C, "ANSWER_VARIANTS", 0),
                   "docs_dropped_test_fiche": n_docs_dropped,
                   "unknowns_train": len(unknowns) - sum(1 for r in unknowns if r["bundle_id"] in unk_test),
                   "unknowns_test": sum(1 for r in unknowns if r["bundle_id"] in unk_test)},
        "mixed_training_note": "docs of fiches whose FACTS are held out in EVAL are in training on purpose "
                               "(Physics of LMs 3.1, Result 1): the eval loss measures answering on a fact "
                               "the model has only READ, never seen as a Q/A.",
        "typography": "all texts written with ASCII punctuation (augment.ascii_punct)",
        "dpo_sources_kept": C.DPO_SOURCES,
        "leak_check": {"identical_answers_eval_in_train": leak_ev,
                       "identical_answers_test_in_train": leak_te,
                       "bundles_shared_eval_train": share_ev,
                       "bundles_shared_test_train": share_te},
        "note": "TEST holds whole fiches (generalisation, for the report). EVAL holds whole facts "
                "from fiches the model does see (in-distribution, the early-stopping signal). "
                "Never split by line: the gates of one fact quote the same sentence.",
    }
    (C.SPLIT / "split_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n  train {n_tr}   eval {n_ev}   test {n_te}   dpo {n_dpo} "
          f"({drop_dpo} ecartees car reservees, {drop_judge_error} car le juge a plante)")
    n_unk_te = sum(1 for r in unknowns if r["bundle_id"] in unk_test)
    print(f"  dont : {n_expose} reformulations, {n_onp} reponses on-policy, {n_docs_train} documents en train "
          f"({n_docs_dropped} ecartes : fiches de test), inconnus {len(unknowns) - n_unk_te} train / {n_unk_te} test")
    print(f"  test  : {len(test_fiches)} fiches entieres -> {', '.join(sorted(test_fiches))}")
    print(f"  eval  : {len(eval_bundles)} faits entiers tires des fiches vues "
          f"({100 * C.EVAL_BUNDLE_FRACTION:.0f} %)")
    print(f"  types dans l'eval : {dict(Counter(r['kind'] for r in parts['eval']))}")
    print(f"  types dans le test: {dict(Counter(r['kind'] for r in parts['test']))}")
    print(f"\n  fuite : {leak_ev} reponse(s) d'eval et {leak_te} de test identiques a une reponse "
          f"d'entrainement ; {share_ev} et {share_te} paquet(s) partages")
    bad = leak_ev or leak_te or share_ev or share_te
    print("  " + ("FUITE DETECTEE : ne pas entrainer" if bad else "aucune fuite"))
    if n_ev < 80:
        print(f"  ATTENTION : eval de {n_ev} paires, un peu court ; monte EVAL_BUNDLE_FRACTION")
    print(f"-> {C.SPLIT / 'split_manifest.json'}")
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
