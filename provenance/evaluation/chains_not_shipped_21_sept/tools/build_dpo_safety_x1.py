import io, json, sys, random
from collections import Counter
dst, manifest = sys.argv[1], sys.argv[2]
srcs = sys.argv[3:]
base = [json.loads(l) for l in io.open(dst, encoding="utf-8") if l.strip()]
n0 = len(base)
extra, stats = [], Counter()
for p in srcs:
    for l in io.open(p, encoding="utf-8"):
        if not l.strip(): continue
        r = json.loads(l)
        stats[(p.split("\\")[-1], r["source"].split(":")[1], r["chosen_from"])] += 1
        for _ in range(1):
            extra.append({"prompt": r["prompt"], "chosen": r["chosen"], "rejected": r["rejected"]})
random.Random(23).shuffle(extra)
rows = base + extra
random.Random(23).shuffle(rows)
io.open(dst, "w", encoding="utf-8", newline="\n").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
m = {"dpo_rows_from_split": n0, "safety_pairs_distinct": len(extra), "oversample": 1,
     "safety_rows_added": len(extra), "dpo_rows_total": len(rows),
     "safety_share": round(len(extra) / len(rows), 3),
     "by_source": [{"file": k[0], "fault": k[1], "chosen_from": k[2], "n": v} for k, v in sorted(stats.items())]}
io.open(manifest, "w", encoding="utf-8", newline="\n").write(json.dumps(m, indent=2, ensure_ascii=False))
print(json.dumps(m, indent=2))
