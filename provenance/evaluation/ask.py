#!/usr/bin/env python3
import json, subprocess, sys, time, urllib.request, os, signal

GGUF, ACC, OUT = sys.argv[1:4]
PORT = int(os.environ.get("PORT", "8089"))
SERVER = os.path.expanduser("~/adtc-2026/llama.cpp/build/bin/llama-server")
items = [json.loads(l) for l in open(ACC) if l.strip()]

srv = subprocess.Popen([SERVER, "-m", GGUF, "--jinja", "-t", "6", "-ngl", "0", "--ctx-size", "2048",
                        "--host", "127.0.0.1", "--port", str(PORT), "--log-disable"],
                       stdout=subprocess.DEVNULL, stderr=open(OUT + ".server.log", "w"))
try:
    for _ in range(120):
        try:
            if urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2).status == 200: break
        except Exception: time.sleep(1)
    else: sys.exit("serveur injoignable")

    with open(OUT, "w") as f:
        for i, it in enumerate(items, 1):
            body = json.dumps({"messages": [{"role": "user", "content": it["prompt"]}],
                               "temperature": 0.3, "min_p": 0.15, "repeat_penalty": 1.05,
                               "max_tokens": 400, "seed": 42}).encode()
            req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions", body,
                                         {"Content-Type": "application/json"})
            t0 = time.time()
            r = json.load(urllib.request.urlopen(req, timeout=600))
            ans = r["choices"][0]["message"]["content"].strip()
            u = r.get("usage", {})
            rec = {"id": it["id"], "kind": it["kind"], "prompt": it["prompt"], "answer": ans,
                   "tokens": u.get("completion_tokens"), "seconds": round(time.time() - t0, 1),
                   "finish": r["choices"][0].get("finish_reason")}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
            print(f"  {i:2d}/{len(items)} {it['id']:<40} {rec['tokens']:>4} tok  {rec['seconds']:>6.1f}s", flush=True)
finally:
    srv.send_signal(signal.SIGINT)
    try: srv.wait(15)
    except subprocess.TimeoutExpired: srv.kill()
