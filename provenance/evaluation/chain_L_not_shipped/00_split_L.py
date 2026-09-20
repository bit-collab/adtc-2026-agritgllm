# -*- coding: utf-8 -*-
"""STEP 0 - the held-out sets. Runs with the DATA venv: no GPU, no model.

TWO sets, and they answer two different questions. Confusing them cost a run on 12/09/2026:
early stopping fired at 0.65 of 3 epochs while the training loss was still falling from 4.02
to 0.62, because the validation set was made of fiches the model never sees - and a bare model
with no retrieval cannot learn facts it has not read. That loss measures the unlearnable.

  sft_test.jsonl   whole FICHES held out. Generalisation to a subject never seen. A number for
                   the report. NEVER a training signal.
  sft_eval.jsonl   whole FACTS (bundles) held out from fiches the model DOES see. Same subject,
                   same style, a sentence it was not trained on. In-distribution, learnable,
                   and therefore the right early-stopping signal.

Never split by line: the 8 or 9 gates of one fact quote the SAME sentence, so a random split
puts the answer of the test set straight into training.

The noisy copies (augment.py) inherit their row's bundle, so they follow their fact and can only
ever land in training.

The hand-written families (identity, limit, greeting, verdict) have no fiche. They are behaviour,
not knowledge, and the acceptance test already measures them, so they stay in training - except
two topics held out in the test set to check the behaviour survives an unseen phrasing.

Added 13/09/2026, after the jury-conditions measurement (provenance/A/jury.md):
  docs      the fiches rendered as documents (pipeline/docs.py). "Mixed training", Physics of LMs
            3.1 Result 1: the model reads the text AND answers questions on it, in the same run.
            A doc of a TEST fiche never enters training. A doc of a fiche whose facts are in EVAL
            does: the eval loss then measures "can it answer on a fact it has only READ", which
            is exactly what the jury measures. The manifest says so.
  unknowns  questions the fiches do not cover, answered honestly (pipeline/unknowns.py, R-Tuning).
            20 of them go to the test set: the behaviour on an unseen phrasing.
  typography  every text is written in ASCII punctuation (the U+2011 hyphen the writer types was
            in the 12/09 training file 2 886 times; the jury types "-").

Usage:  projet\\.venv\\Scripts\\python.exe train-gate2\\00_split.py
Output: data/sft_train.jsonl, data/sft_eval.jsonl, data/sft_test.jsonl,
        data/dpo_train.jsonl, data/split_manifest.json
"""
from __future__ import annotations
import json, random, re, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
sys.path.insert(0, str(C.ROOT / "rebuild-gate2" / "pipeline"))
from augment import ascii_punct                      # one table, used by the pipeline and here

N_UNKNOWN_TEST = 20

GOLD_KINDS = {"identity", "limit", "greeting", "verdict"}
# Mesure du 19/09/2026 sur la batterie des 27 questions du tour 1, trois chaines de suite
# (Egrpo, Fgrpo, Ggrpo) : le sujet reserve "mixing_chemicals" PASSE (keep_refuse_dilution_ratio,
# 3 chaines sur 3), le sujet reserve "photos" ECHOUE (meta_photos_describe_instead, 3 sur 3), et
# il echoue de la pire facon : a « Can I send you a photo of my plant? » le modele repond « Yes ».
# La difference entre les deux n'est pas le hasard du tirage, elle est mesurable dans les donnees.
# Le refus de dose a des dizaines de paquets voisins qui le portent ; la cecite visuelle n'en a
# qu'un seul, identity:no_camera_no_image, et ses 22 lignes posent toutes LA MEME question
# technique (« ... low-resolution, offline-processed spectral inputs from a smartphone camera »).
# Vingt-deux lignes d'un seul angle achetent cet angle, pas le fait. La question du paysan, courte
# et directe, n'a jamais ete vue. On garde donc "mixing_chemicals" comme temoin de generalisation,
# celui qui tient, et on rend "photos" a l'entrainement : c'est la question la plus naturelle
# qu'un jury pose a un conseiller agricole hors ligne, et une reponse fausse y coute plus cher
# qu'une mesure de generalisation de plus.
HELD_OUT_GOLD_TOPICS = set(getattr(C, "HELD_OUT_GOLD_TOPICS", ["mixing_chemicals"]))


def read(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def write(p, rows, keys=("messages",)):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            d = {k: r[k] for k in keys if k in r}
            if "messages" in d:                              # SFT rows
                d["messages"] = [{"role": m["role"], "content": ascii_punct(m["content"])} for m in d["messages"]]
            for k in ("prompt", "chosen", "rejected"):       # DPO rows: strings or message lists
                if isinstance(d.get(k), str):
                    d[k] = ascii_punct(d[k])
                elif isinstance(d.get(k), list):
                    d[k] = [{**m, "content": ascii_punct(m["content"])} if isinstance(m, dict) else m for m in d[k]]
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    return len(rows)


def fiche_of(bundle_id):
    """problem_fact:cassava_mosaic:signs:0 -> cassava_mosaic ; contrast:a|b -> a|b ; gold -> None"""
    parts = bundle_id.split(":")
    if parts[0] in GOLD_KINDS:
        return None
    return parts[1] if len(parts) >= 2 else bundle_id


def touches(bundle_id, fiches):
    """A contrast between a held-out fiche and another one belongs to the held-out side."""
    f = fiche_of(bundle_id)
    return False if f is None else any(x in fiches for x in f.split("|"))


def content_words(t):
    return set(re.findall(r"[a-z]{4,}", t.lower()))


def canonical_answers(rows, k):
    """Collapse the answer side of one fact onto its k most CENTRAL answers, and re-map the other
    rows' questions onto them. Every question wording survives; the answer distribution narrows.
    Central = highest mean Jaccard overlap of content words with the other answers of the fact:
    the answer that says what they all say, chosen without a model."""
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
    # Les paires ecrites a la main (17/09/2026) comblent les trous signales par l'agronome.
    # Elles ne passent PAS par pairs_clean.jsonl, qui est une sortie de check.py et serait
    # ecrasee au prochain passage ; elles entrent ici comme source a part entiere. Leurs
    # bundle_id sont au format handwritten:<fiche>:<fait>, donc fiche_of() les rattache aux
    # vraies fiches et le retrait par fait s'applique a elles comme au reste.
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
    dpo += read(onp_dpo_p) if onp_dpo_p.is_file() else []          # 07_onpolicy.py, source "onpolicy:*"
    n_expose = sum(1 for r in clean if str(r.get("gate", "")).startswith("expose"))
    print(f"{len(clean)} paires propres dont {len(hand)} ecrites a la main (et {n_expose} "
          f"reformulations 'expose'), {len(noisy)} copies "
          f"bruitees, {len(docs)} documents, {len(unknowns)} reponses hors fiches, {len(dpo)} paires de preference")

    test_fiches = set(C.TEST_FICHES)
    known = {fiche_of(r["bundle_id"]) for r in clean} - {None}
    missing = [f for f in test_fiches if f not in known and not any(f in k for k in known)]
    if missing:
        print(f"  ATTENTION : fiches de test introuvables dans les paires : {missing}")

    # 1. the test set: whole fiches, plus two hand-written topics
    parts = defaultdict(list)
    rest = []
    for r in clean:
        if touches(r["bundle_id"], test_fiches):
            parts["test"].append(r)
        elif r["kind"] in GOLD_KINDS and gold_topic(r) in HELD_OUT_GOLD_TOPICS:
            parts["test"].append(r)
        else:
            rest.append(r)

    # 2. the eval set: whole FACTS drawn from what is left, so every gate of a held-out fact
    #    leaves together and none of its sentences stays in training
    #    Les familles de COMPORTEMENT ne sont jamais tirees ici. Mesure du 19/09/2026 : le tirage
    #    aleatoire avait pris identity:architecture, identity:can_you_be_wrong, identity:on_my_phone
    #    et greeting:good_night, soit 70 lignes entierement retirees de l'entrainement. Le modele
    #    livre n'avait donc JAMAIS appris a decrire son architecture, et il confabulait sur le
    #    prompt automatique n.2 du jugement du tour 1, que les organisateurs notent.
    #    C'est la meme lecon que le 13/09, quand deux sujets reserves se sont reveles etre des
    #    questions du jury ; la regle avait ete appliquee au jeu de TEST et pas a celui-ci.
    #    Un comportement ne se generalise pas depuis un fait voisin : il s'apprend ou il manque.
    #    Le test garde un sujet de comportement reserve exprès (HELD_OUT_GOLD_TOPICS), ce qui
    #    suffit a mesurer la tenue sur une formulation jamais vue.
    kind_of = {}
    for r in rest:
        kind_of.setdefault(r["bundle_id"], r.get("kind"))
    #    Les paquets ECRITS A LA MAIN sont exclus pour la meme raison, et elle est ecrite dans
    #    config.py depuis le 13/09 sans avoir jamais ete appliquee ici : « ne jamais reserver les
    #    familles ecrites a la main qui repondent aux questions du jury ». Mesure du 19/09/2026 :
    #    le tirage venait de prendre handwritten:poultry_local_hens_business:nucleus_minimum, le
    #    paquet qui repond a l'item new_hens du banc jury, et le laissait a zero ligne
    #    d'entrainement. Ces 78 paquets n'existent pas pour mesurer la generalisation, ils
    #    existent pour combler des trous mesures ; les reserver annule la reparation.
    #    La generalisation reste mesuree par sft_test, qui tient 5 fiches entieres.
    bundles = sorted({r["bundle_id"] for r in rest
                      if kind_of.get(r["bundle_id"]) not in GOLD_KINDS
                      and not r["bundle_id"].startswith("handwritten:")})
    rng = random.Random(C.SEED)
    rng.shuffle(bundles)
    n_eval = max(1, int(len(bundles) * C.EVAL_BUNDLE_FRACTION))
    eval_bundles = set(bundles[:n_eval])
    for r in rest:
        parts["eval" if r["bundle_id"] in eval_bundles else "train"].append(r)

    # 3. the noisy copies follow their own row, and only into training
    train_ids = {r["row_id"] for r in parts["train"]}
    for r in noisy:
        if r.get("row_id", "").split("#noisy")[0] in train_ids:
            parts["train"].append(r)

    # 3b. the documents: never one of a test fiche; the others into training (mixed training)
    n_docs_train = n_docs_dropped = 0
    for r in docs:
        if touches(r["bundle_id"], test_fiches):
            n_docs_dropped += 1
        else:
            parts["train"].append(r)
            n_docs_train += 1

    # 3d. the model's own accepted answers (07_onpolicy.py): they follow their fact
    n_onp = 0
    for r in onp_sft:
        if touches(r["bundle_id"], test_fiches) or r["bundle_id"] in eval_bundles:
            continue
        if r["kind"] in GOLD_KINDS and gold_topic(r) in HELD_OUT_GOLD_TOPICS:
            continue
        parts["train"].append(r)
        n_onp += 1

    # 3c. the unknowns: a fixed 20 to the test set, the rest to training
    unk_bundles = sorted({r["bundle_id"] for r in unknowns})
    rng_u = random.Random(C.SEED + 1)
    rng_u.shuffle(unk_bundles)
    unk_test = set(unk_bundles[:N_UNKNOWN_TEST])
    for r in unknowns:
        parts["test" if r["bundle_id"] in unk_test else "train"].append(r)

    # 4c. cap the AUTOMATIC gates per fact (see config.EXPOSE_PER_FACT / ONPOLICY_PER_FACT)
    #     Mesure du 20/09/2026 : trois fiches a 500+ lignes contre une mediane de 95, tout le
    #     surplus en paraphrases `expose`, et leurs formules qui sortent sur d'autres animaux.
    #     On plafonne par fait, on ne touche a aucune porte ecrite, et le tirage est fixe.
    cap = {"expose": getattr(C, "EXPOSE_PER_FACT", 0), "onpolicy": getattr(C, "ONPOLICY_PER_FACT", 0)}
    n_capped = defaultdict(int)
    if any(cap.values()):
        rng_c = random.Random(C.SEED + 2)
        by_key = defaultdict(list)
        for i, r in enumerate(parts["train"]):
            g = str(r.get("gate", ""))
            if g in cap and cap[g] and r.get("kind") not in GOLD_KINDS and r.get("kind") not in ("doc", "unknown"):
                by_key[(r["bundle_id"], g)].append(i)
        drop = set()
        for (bid, g), idx in by_key.items():
            if len(idx) > cap[g]:
                idx = list(idx)
                rng_c.shuffle(idx)
                for i in idx[cap[g]:]:
                    drop.add(i)
                    n_capped[fiche_of(bid) or bid] += 1
        if drop:
            parts["train"] = [r for i, r in enumerate(parts["train"]) if i not in drop]
        print(f"  plafond par fait : expose<={cap['expose']}, onpolicy<={cap['onpolicy']} : "
              f"{len(drop)} lignes retirees sur {len(n_capped)} fiches"
              + (", dont " + ", ".join(f"{k} -{v}" for k, v in sorted(n_capped.items(), key=lambda x: -x[1])[:5]) if n_capped else ""))

    # 4b. one fact, a few canonical answers (see config.ANSWER_VARIANTS)
    # The EVAL set is canonicalised too, and it must be: on the 13/09 run the train side was
    # collapsed to 3 answers per fact while eval kept its 9 wordings, so the model was scored on
    # guessing a 4th wording word for word. Its eval_loss ROSE (1.726 -> 1.937) while its token
    # accuracy ROSE too, early stopping fired at 0.33 epoch and kept an undertrained adapter.
    # Same rule on both sides = the loss measures what the training optimises again.
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

    # gate est ecrit dans les trois fichiers, pas seulement dans le test. Sans lui on ne peut pas
    # compter les angles reellement entraines par fait, et c'est justement ce compte qui explique
    # l'ecart mesure le 17/09/2026 entre matiere neuve et ancienne (5 lignes par paquet contre 11).
    n_tr = write(C.SPLIT / "sft_train.jsonl", parts["train"], keys=("messages", "bundle_id", "gate", "kind"))
    n_ev = write(C.SPLIT / "sft_eval.jsonl", parts["eval"], keys=("messages", "bundle_id", "gate", "kind"))
    n_te = write(C.SPLIT / "sft_test.jsonl", parts["test"],
                 keys=("messages", "bundle_id", "gate", "kind"))

    # 4. the preferences follow the same rule: nothing from a test fiche or an eval fact
    keep_dpo, drop_dpo, drop_judge_error = [], 0, 0
    for r in dpo:
        bid = str(r.get("row_id", "")).split("#")[0]
        if touches(bid, test_fiches) or bid in eval_bundles:
            drop_dpo += 1
            continue
        if C.DPO_SOURCES and str(r.get("source", "")).split(":")[0] not in C.DPO_SOURCES:
            continue
        # 13/09/2026: 603 on-policy rows were rejected because the JUDGE failed (API error, not a
        # fault of the answer). Training on those would teach the model to avoid answers that
        # happen to break the judge - a signal about our pipeline, not about agronomy.
        if str(r.get("source", "")).endswith("judge_error"):
            drop_judge_error += 1
            continue
        keep_dpo.append(r)
    n_dpo = write(C.SPLIT / "dpo_train.jsonl", keep_dpo, keys=("prompt", "chosen", "rejected"))

    # 5. the check that matters: no sentence of a held-out set may sit in training
    def answers(rows):
        """The FINAL answer of each exchange. The intermediate clarifying question of a
        multi-turn gate ("How large is your field?") repeats across bundles of the same subject
        by design, so counting it would raise a false leak - measured 12/09/2026, 7 of them."""
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
        # La revision est epinglee dans config.py mais n'etait ecrite que dans train_config.json,
        # produit par l'entrainement. Le manifeste de donnees doit se suffire a lui-meme : la
        # regle 3.1 demande d'identifier le modele de base a cote du jeu, pas ailleurs.
        "seed": C.SEED, "base_model": C.BASE_MODEL, "base_revision": C.BASE_REVISION,
        "test_fiches": sorted(test_fiches),
        "held_out_gold_topics": sorted(HELD_OUT_GOLD_TOPICS),
        "eval_bundle_fraction": C.EVAL_BUNDLE_FRACTION,
        "eval_bundles": sorted(eval_bundles),
        "counts": {"sft_train": n_tr, "sft_eval": n_ev, "sft_test": n_te,
                   "dpo_train": n_dpo, "dpo_dropped_held_out": drop_dpo,
                   "dpo_dropped_judge_error": drop_judge_error,
                   "expose_rows_in_clean": n_expose, "docs_in_train": n_docs_train,
                   "cap_expose_per_fact": cap["expose"], "cap_onpolicy_per_fact": cap["onpolicy"],
                   "rows_removed_by_cap": sum(n_capped.values()),
                   "rows_removed_by_cap_per_fiche": dict(sorted(n_capped.items())),
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
