# -*- coding: utf-8 -*-
"""Ajoute des paires aux familles de COMPORTEMENT (identity, limit, greeting, verdict).

Ces paquets n'ont pas de fiche, donc le Checker du pipeline les laisse presque passer :
tout son travail est sous `if not gold:`. La verification doit donc etre faite ici, et elle
est plus severe que pour la matiere factuelle sur un point precis.

LE GARDE-FOU QUI MANQUAIT. Une reponse de la famille `limit:` ne doit porter AUCUN chiffre
de dose, de ratio ni de concentration, meme sous forme derivee. Mesure du 19/09/2026 : le
modele livre refusait le ratio exact puis ecrivait « if the merchant gave you a concentration,
do not exceed half that figure », ce qui est une consigne de dosage batie sur la parole d'un
marchand pour un produit non homologue. C'est exactement la fuite que le juge 2 du tour 1
avait nommee. Une regle qui interdit le chiffre exact mais tolere la fraction ne protege rien.

Usage : python append_gold.py <module_de_lot>
"""
import importlib, io, json, re, sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"C:\Users\HP VICTUS\Documents\concoursllmdata")
sys.path.insert(0, str(ROOT / "rebuild-gate2" / "pipeline"))
import check as _CHK

PAIRS = ROOT / "rebuild-gate2/out/pairs/pairs_clean.jsonl"
BUNDLES = ROOT / "rebuild-gate2/out/facts/bundles.jsonl"

_CK = _CHK.Checker()
META = re.compile(_CHK.META.pattern + r"|\b(the sheet|the document|the card)\b", re.I)
UNICODE = re.compile("[\u2014\u2013\u2012\u2011\u2018\u2019\u201c\u201d\u2026\u00a0]")
TRACE_IA = re.compile(r"\b(as an AI|language model|I am an AI|as a large language|"
                      r"I cannot assist with that|here'?s how I can help)\b", re.I)
# un chiffre suivi d'une unite de dose, ou une fraction d'un chiffre donne par un tiers
DOSE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(ml|cl|l\b|litre|litres|g\b|kg|mg|cc|%|per\s?cent|percent|"
                  r"tablets?|sachets?|caps?|doses?|spoons?|capfuls?)|"
                  r"\b(half|a third|a quarter|двойн)\b[^.]{0,30}\b(that|the)\b[^.]{0,20}"
                  r"\b(figure|rate|dose|concentration|amount)\b|"
                  r"\b(?:do not exceed|no more than|at most)\b[^.]{0,30}\b\d", re.I)
INTERDIT_DOSE = ("limit:",)


def mots(t):
    return len(t.split())


def charge():
    return [json.loads(l) for l in io.open(PAIRS, encoding="utf-8") if l.strip()]


def main(nom_module):
    lot = importlib.import_module(nom_module).LOT
    rows = charge()
    bundles = {b["bundle_id"]: b for b in
               (json.loads(l) for l in io.open(BUNDLES, encoding="utf-8") if l.strip())}
    deja_gate = {}
    deja_q = set()
    for r in rows:
        deja_gate.setdefault(r["bundle_id"], set()).add(r.get("gate"))
        deja_q.add(re.sub(r"\s+", " ", r["messages"][0]["content"]).strip().lower())
    compteur = Counter(r["bundle_id"] for r in rows)

    fautes, neuf = [], []
    for i, item in enumerate(lot):
        bid, gate, msgs = item[0], item[1], item[2]
        ref = "%s#%s" % (bid, gate)
        b = bundles.get(bid)
        if not b:
            fautes.append("%-34s paquet inconnu" % ref)
            continue
        if gate in deja_gate.get(bid, set()):
            fautes.append("%-34s angle deja present" % ref)
            continue
        attendu = 4 if gate == "multiturn" else 2
        if len(msgs) != attendu:
            fautes.append("%-34s %d messages au lieu de %d" % (ref, len(msgs), attendu))
            continue
        q = re.sub(r"\s+", " ", msgs[0]).strip().lower()
        if q in deja_q:
            fautes.append("%-34s question deja posee" % ref)
            continue
        deja_q.add(q)
        rep = msgs[-1]
        n = mots(rep)
        maxi = 200
        mini = 12 if bid.startswith("greeting:") else 40
        if not (mini <= n <= maxi):
            fautes.append("%-34s %d mots, attendu %d a %d" % (ref, n, mini, maxi))
        for t in msgs:
            if UNICODE.search(t):
                fautes.append("%-34s ponctuation unicode %r" % (ref, UNICODE.search(t).group()))
        if META.search(rep):
            fautes.append("%-34s fuite meta %r" % (ref, META.search(rep).group()))
        if TRACE_IA.search(rep):
            fautes.append("%-34s trace IA %r" % (ref, TRACE_IA.search(rep).group()))
        if bid.startswith(INTERDIT_DOSE):
            m = DOSE.search(rep)
            if m:
                fautes.append("%-34s CHIFFRE DE DOSE dans un refus : %r" % (ref, m.group()))
        # Les paquets qui ne sont PAS des familles de comportement passent le lint complet du
        # pipeline : leur allowed_text est une fiche, donc chaque chiffre, nom propre, service
        # et hote doit s'y retrouver. Ajoute le 19/09/2026, quand le lot F a commence a viser
        # des paquets guidance_fact et practice_fact et plus seulement des familles gold.
        if b["kind"] not in ("identity", "limit", "greeting", "verdict"):
            user = "\n".join(msgs[i] for i in range(0, len(msgs), 2))
            dures = [x for x in _CK.check(rep, b, final=True, user_text=user)
                     if x.split(":")[0] in _CHK.BLOCKING]
            for x in dures:
                fautes.append("%-34s lint : %s" % (ref, x))
        deja_gate.setdefault(bid, set()).add(gate)
        neuf.append({
            "row_id": "%s#hand%d" % (bid, compteur[bid] + i),
            "bundle_id": bid, "kind": b["kind"], "gate": gate,
            "subjects": b.get("subjects", []), "hosts": b.get("hosts", []),
            "model": "handwritten",
            "messages": [{"role": "user" if k % 2 == 0 else "assistant", "content": c}
                         for k, c in enumerate(msgs)],
        })

    if fautes:
        print("LOT REFUSE, %d faute(s), rien n'est ecrit :" % len(fautes))
        for f in fautes:
            print("   ", f)
        return 1
    with io.open(PAIRS, "a", encoding="utf-8", newline="\n") as f:
        for r in neuf:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("%d paires ajoutees" % len(neuf))
    for bid, n in Counter(r["bundle_id"] for r in neuf).most_common():
        print("   %-46s +%d  (total %d angles)" % (bid, n, len(deja_gate[bid])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
