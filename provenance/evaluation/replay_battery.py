# -*- coding: utf-8 -*-
"""Rejoue la batterie des 27 questions construite depuis le rapport des juges du tour 1.

Cette batterie vaut mieux que le jury de 24 que j'avais fabrique, pour une raison simple :
ses items viennent du rapport de jugement reel (ADTC2026_556), avec la reponse du tour 1 et
le defaut precis que le juge a signale. Le barème est dans le fichier lui-meme.

CORE = les criteres obligatoires. EXTRA = la barre supplementaire que l'equipe s'est fixee.
Les criteres marques `manual` ne sont pas verifiables par machine et sont listes pour lecture.

Usage : python acc27.py <gguf> <sortie.json>
"""
import json, io, os, re, signal, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(r"C:\Users\HP VICTUS\Documents\concoursllmdata")
SERVER = ROOT / "tools" / "llama-cpu" / "llama-server.exe"
# BANC=round1 (defaut) ou BANC=heldout, le second banc reformule du 19/09/2026 dont aucune
# question n'est dans l'entrainement (similarite maximale mesuree 0,55).
ACC = ROOT / ("adtc-submission-gate2/provenance/evaluation/acceptance_27_%s.jsonl"
              % {"round1": "round1", "heldout": "heldout"}[os.environ.get("BANC", "round1")])
GGUF = Path(sys.argv[1])
OUT = Path(sys.argv[2])
PORT = int(os.environ.get("PORT", "8192"))
SEED = int(sys.argv[3]) if len(sys.argv) > 3 else 42

items = [json.loads(l) for l in io.open(ACC, encoding="utf-8") if l.strip()]
MANUELS = {"must_refuse", "must_give_verdict", "must_answer_then_ask", "must_distinguish",
           "must_answer_about_itself", "no_invented_mechanism", "no_invented_institution",
           "no_diagnosis", "forbid_using_unregistered", "no_dose"}


def juge(ans, spec):
    """Renvoie (ok, [fautes], [criteres a lire a la main])."""
    faut, manu = [], []
    low = ans.lower()
    for k, v in spec.items():
        if k in MANUELS:
            manu.append(k)
            continue
        if k == "must_contain_any":
            for groupe in v:
                if not any(re.search(re.escape(x), low, re.I) for x in groupe):
                    faut.append("manque: " + "/".join(groupe))
        elif k == "must_not_contain":
            for x in v:
                if re.search(r"\b" + re.escape(x) + r"\b", low, re.I):
                    faut.append("interdit present: %r" % x)
        elif k == "min_words":
            n = len(ans.split())
            if n < v:
                faut.append("%d mots < %d" % (n, v))
        elif k == "max_words":
            n = len(ans.split())
            if n > v:
                faut.append("%d mots > %d" % (n, v))
    return (not faut), faut, manu


srv = subprocess.Popen([str(SERVER), "-m", str(GGUF), "--jinja", "-t", "6", "-ngl", "0",
                        "--ctx-size", "2048", "--host", "127.0.0.1", "--port", str(PORT)],
                       stdout=subprocess.DEVNULL, stderr=open(str(OUT) + ".server.log", "w"))
res = {"model": GGUF.name, "seed": SEED, "banc": os.environ.get("BANC", "round1"), "core": 0, "extra": 0, "items": []}
try:
    for _ in range(180):
        try:
            if urllib.request.urlopen("http://127.0.0.1:%d/health" % PORT, timeout=2).status == 200:
                break
        except Exception:
            time.sleep(1)
    else:
        raise SystemExit("serveur injoignable")

    for i, it in enumerate(items, 1):
        body = json.dumps({"messages": [{"role": "user", "content": it["prompt"]}],
                           "temperature": 0.3, "min_p": 0.15, "repeat_penalty": 1.05,
                           "max_tokens": 400, "seed": SEED}).encode()
        req = urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions" % PORT, body,
                                     {"Content-Type": "application/json"})
        ans = json.load(urllib.request.urlopen(req, timeout=900))["choices"][0]["message"]["content"].strip()
        okc, fc, mc = juge(ans, it.get("core", {}))
        oke, fe, _ = juge(ans, it.get("extra", {}))
        res["core"] += int(okc)
        res["extra"] += int(oke)
        res["items"].append({"id": it["id"], "kind": it["kind"], "prompt": it["prompt"],
                             "answer": ans, "core": "ok" if okc else "ECHEC",
                             "extra": "ok" if oke else "echec",
                             "fails": fc + ["(extra) " + x for x in fe], "manual": mc})
        print("  %2d/%d %-42s CORE %-6s EXTRA %s" % (i, len(items), it["id"],
                                                     "ok" if okc else "ECHEC",
                                                     "ok" if oke else "echec"), flush=True)
finally:
    srv.send_signal(signal.SIGTERM)
    try:
        srv.wait(20)
    except subprocess.TimeoutExpired:
        srv.kill()

io.open(OUT, "w", encoding="utf-8", newline="\n").write(json.dumps(res, ensure_ascii=False, indent=1))
print("\n%s  CORE %d/%d  EXTRA %d/%d" % (GGUF.name, res["core"], len(items), res["extra"], len(items)))
