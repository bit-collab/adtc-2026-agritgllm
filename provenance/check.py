from __future__ import annotations
import json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import ROOT, read_jsonl
from ontology import Lexicon

PAIRS = ROOT / "out" / "pairs" / "pairs.jsonl"
BUNDLES = ROOT / "out" / "facts" / "bundles.jsonl"
CLEAN = ROOT / "out" / "pairs" / "pairs_clean.jsonl"
REJECTED = ROOT / "out" / "pairs" / "pairs_rejected.jsonl"
CHECK_DIR = ROOT / "out" / "check"

GOLD_KINDS = {"identity", "limit", "greeting", "verdict"}
FACT_KINDS = {"problem_fact", "problem_note", "practice_fact", "guidance_fact"}
BLOCKING = ("bare_referral", "unknown_name", "invented_day", "invented_figure", "wrong_host",
            "wrong_institution", "invented_date", "meta_leak", "incomplete_answer", "unsupported_claim",
            "invented_diagnosis", "invented_institution")
DIAGNOSIS = re.compile(r"\b(the (most )?likely cause is|the cause is|this is (probably|likely)|"
                       r"it is (probably|likely)|points to|the diagnosis is|suffering from|"
                       r"caused by the)\b", re.I)
KNOWN_INST = {"ICAT", "ITRA", "ANSAT", "CAGIA", "ANAMET", "SIM", "IPM", "PPR", "NPK", "GGUF", "CPU",
              "LLM", "CMD", "ACMV", "CBB", "MSV", "TYLCV", "OK", "NOT", "ONLY", "DO", "AND"}
ORGLIKE = re.compile(r"\b([A-Z]{3,}[A-Z0-9]*)\b|"
                     r"\b((?:Comisi[oó]n|Institut|Agency|Ministry|Bureau|Council|Association|"
                     r"Federation|Commission)[A-Za-z ]{0,40})")
JUDGE = ROOT / "out" / "pairs" / "judge.jsonl"
JUDGE_BLOCK_AT = 1
META = re.compile(r"\b(the|this|that) (material|fiche|fiches|text provided|information provided|"
                  r"source material|instructions|excerpts?|context)\b", re.I)
MONTHS = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|"
                    r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\b")

REFERRAL = re.compile(
    r"(contact|see|ask|consult|visit|reach out to|refer to|get in touch with|call|go to)\s+"
    r"(your\s+)?(local\s+)?(the\s+)?(ICAT|ITRA|ANSAT|CAGIA|ANAMET|SIM|extension|veterinar\w+|"
    r"agent|officer|expert|specialist|professional|auxiliary)", re.I)
CHAIN = re.compile(r"\b(let me think|let us think|step 1|reasoning:|here is my|I will now|as an AI)\b", re.I)
MARKDOWN = re.compile(r"(^|\n)\s*([-*•]\s|#{1,6}\s|\d+\.\s)")
PLEASANT = re.compile(r"\b(hope (this|that) helps|good question|great question|feel free|"
                      r"don'?t hesitate|happy farming|best of luck|you are welcome|you're welcome)\b", re.I)
WEEKDAYS = re.compile(r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)s?\b")
PROPER = re.compile(r"(?<![.!?:;]\s)(?<!^)(?<!\n)(?<!\()\b([A-Z][a-z]{3,}|[A-Z]{2,}[A-Z0-9]*)\b")
NUM = re.compile(r"(?<![A-Za-z0-9])\d+(?:[.,]\d+)?")
DIMS = re.compile(r"(?<=\d)\s*[x×]\s*(?=\d)")
EMPHASIS = {"ONLY", "NOT", "NEVER", "ALWAYS", "DO", "NO", "YES", "ALL", "AND", "BUT", "IF", "THE",
            "MUST", "STOP", "NOW", "BEFORE", "AFTER", "EVERY", "DRY", "MOVING", "CLOSE", "THREE",
            "SUDDENLY", "NOTIFIABLE", "IMMEDIATELY", "DEFORMATION", "ALONG", "THE", "LOWER", "NECROTIC", "ROT"}
ALWAYS_OK = {"togo", "togolese", "english", "french", "africa", "african", "west", "lome", "ewe",
             "kabiye", "agritg", "llm", "north", "south", "centre", "apache", "granite", "ibm",
             "liquid", "lfm", "mamba", "gguf", "chatml",
             "january", "february", "march", "april", "may", "june", "july", "august",
             "september", "october", "november", "december"}
SMALL_NUMBERS = {"0", "1", "2", "3"}
WORD = re.compile(r"[a-z]{3,}")


def stem(w):
    if w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def content_words(t):
    stop = {"the", "and", "for", "with", "from", "that", "this", "your", "you", "are", "not", "only",
            "into", "each", "then", "they", "them", "their", "can", "will", "when", "while", "keep"}
    return {stem(w) for w in WORD.findall((t or "").lower()) if w not in stop}


def last_clause(text):
    parts = [p.strip() for p in re.split(r"(?<=[.!?;:])\s+|\n+", text.strip()) if p.strip()]
    return parts[-1] if parts else ""


class Checker:
    def __init__(self):
        self.lex = Lexicon()
        onto = self.lex.onto
        base = set(ALWAYS_OK)
        for kind in ("hosts", "problems", "agents", "inputs", "institutions", "regions"):
            for eid, spec in onto[kind].items():
                if eid.startswith("_"):
                    continue
                for s in [eid] + spec.get("aliases", []) + [spec.get("label", ""), spec.get("full", "")]:
                    base |= set(re.findall(r"[a-z0-9]+", str(s).lower()))
        self.base_vocab = base

    def check(self, answer, b, final=True, user_text=""):
        issues = []
        words = answer.split()
        allowed = b.get("allowed_text", "")
        gold = b["kind"] in GOLD_KINDS

        if not gold:
            tail = last_clause(answer)
            if final and REFERRAL.search(tail) and len(words) - len(tail.split()) < 15:
                issues.append("bare_referral")
            if final and len(words) < 40:
                issues.append("incomplete_answer")
            days = [d for d in WEEKDAYS.findall(answer) if not re.search(rf"\b{d}", allowed)]
            if days:
                issues.append("invented_day:" + ",".join(sorted(set(days))[:3]))
            extra = (set(NUM.findall(DIMS.sub(" x ", answer))) - set(NUM.findall(DIMS.sub(" x ", allowed)))
                     - set(NUM.findall(DIMS.sub(" x ", user_text))) - SMALL_NUMBERS)
            if extra:
                issues.append("invented_figure:" + ",".join(sorted(extra)[:4]))
            wrong = set()
            for hid, pat in self.lex.all_host_patterns():
                m = pat.search(answer)
                if m and hid not in b.get("hosts", []) and not pat.search(allowed):
                    wrong.add(m.group(0).lower())
            if wrong:
                issues.append("wrong_host:" + ",".join(sorted(wrong)[:4]))
            bad_inst = [ins for ins in self.lex.find(answer, "institutions")
                        if not any(p.search(allowed) for eid, pats in self.lex.index["institutions"]
                                   if eid == ins for p in pats)]
            if bad_inst:
                issues.append("wrong_institution:" + ",".join(bad_inst))
            months = {m for m in MONTHS.findall(answer) if not re.search(rf"\b{m[:3]}", allowed, re.I)}
            if months:
                issues.append("invented_date:" + ",".join(sorted(months)))
            if META.search(answer):
                issues.append("meta_leak")
            vocab = self.base_vocab | set(re.findall(r"[a-z0-9]+", allowed.lower()))
            unknown = []
            for tok in PROPER.findall(answer):
                if tok.isupper():
                    if tok not in EMPHASIS and tok.lower() not in vocab:
                        unknown.append(tok)
                elif tok.lower() not in vocab:
                    unknown.append(tok)
            if unknown:
                issues.append("unknown_name:" + ",".join(sorted(set(unknown))[:4]))

        if gold:
            if b["kind"] == "limit" and DIAGNOSIS.search(answer):
                issues.append("invented_diagnosis:" + DIAGNOSIS.search(answer).group(0))
            for m in ORGLIKE.finditer(answer):
                tok = (m.group(1) or m.group(2) or "").strip()
                if tok and tok not in KNOWN_INST and tok.lower() not in allowed.lower():
                    issues.append("invented_institution:" + tok[:40])
                    break

        if final and not gold and len(words) < 60:
            issues.append("too_short")
        if len(words) > 260:
            issues.append("too_long")
        if MARKDOWN.search(answer):
            issues.append("markdown")
        if CHAIN.search(answer):
            issues.append("chain_of_thought")
        if PLEASANT.search(answer) and b["kind"] != "greeting":
            issues.append("pleasantry")
        sentences = [s for s in re.split(r"[.!?]+", answer) if s.strip()]
        if sentences and len(words) / len(sentences) > 28:
            issues.append("long_sentences")
        if final and b["kind"] in FACT_KINDS:
            fw = content_words(b["fact"]["text"])
            if fw and len(fw & content_words(answer)) / len(fw) < 0.25:
                issues.append("ungrounded")
        return issues


def expected(b):
    return {"original", "paraphrase"} if b["kind"] in GOLD_KINDS else set(b["gates"])


def run():
    pairs = read_jsonl(PAIRS)
    if not pairs:
        print("controle : aucune paire")
        return {}
    bundles = {b["bundle_id"]: b for b in read_jsonl(BUNDLES)}
    C = Checker()
    judged = {j["row_id"]: j for j in read_jsonl(JUDGE, quiet=True)}
    counts, per_kind, per_kind_bad = Counter(), Counter(), Counter()
    clean, rejected, violations, hard_rows, judge_rows = [], [], [], [], []
    got = defaultdict(set)
    answers = 0
    for row in pairs:
        b = bundles.get(row["bundle_id"])
        if b is None:
            continue
        got[row["bundle_id"]].add(row["gate"])
        per_kind[row["kind"]] += 1
        idx = [i for i, m in enumerate(row["messages"]) if m["role"] == "assistant"]
        blocked = hard = False
        row_issues = []
        for i, m in enumerate(row["messages"]):
            if m["role"] != "assistant":
                continue
            answers += 1
            final = i == idx[-1]
            user_text = " ".join(x["content"] for x in row["messages"][:i] if x["role"] == "user")
            issues = C.check(m["content"], b, final=final, user_text=user_text)
            j = judged.get(row.get("row_id", ""))
            if final and j:
                if j.get("contradicted") or len(j.get("unsupported", [])) >= JUDGE_BLOCK_AT:
                    issues.append("unsupported_claim:" + " | ".join((j.get("contradicted", []) + j.get("unsupported", []))[:2])[:160])
            for x in issues:
                k = x.split(":")[0]
                counts[k] += 1
                if k in BLOCKING:
                    blocked = True
                    if k != "unsupported_claim":
                        hard = True
            if issues:
                row_issues += issues
                violations.append({"bundle_id": row["bundle_id"], "gate": row["gate"],
                                   "issues": issues, "answer": m["content"][:600]})
        row["check"] = row_issues
        if blocked:
            rejected.append(row)
            per_kind_bad[row["kind"]] += 1
            (hard_rows if hard else judge_rows).append(row["row_id"])
        else:
            clean.append(row)

    incomplete = {bid: sorted(expected(bundles[bid]) - gs) for bid, gs in got.items()
                  if not expected(bundles[bid]) <= gs}
    for path, rows in ((CLEAN, clean), (REJECTED, rejected)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    CHECK_DIR.mkdir(parents=True, exist_ok=True)
    (CHECK_DIR / "violations.jsonl").write_text(
        "".join(json.dumps(v, ensure_ascii=False) + "\n" for v in violations), encoding="utf-8")

    n = len(pairs)
    trimmed = sum(1 for r in pairs if r.get("trimmed"))
    trimmed_clean = sum(1 for r in clean if r.get("trimmed"))
    reject_rate = len(rejected) / n
    hard_rate = len(hard_rows) / n
    judge_rate = len(judge_rows) / n
    incomplete_rate = len(incomplete) / max(1, len(got))
    verdict = hard_rate < 0.08 and incomplete_rate < 0.10
    pct = lambda k: f"{100 * counts[k] / answers:.1f} %" if answers else "-"
    L = ["# Controle qualite\n",
         f"- paires : **{n}**  ·  reponses verifiees : **{answers}**  ·  paquets couverts : **{len(got)}**",
         f"- **retenues : {len(clean)}**  ·  ecartees : {len(rejected)} (**{100 * reject_rate:.1f} %** de rejet)",
         f"- dont **faute dure du redacteur : {len(hard_rows)} ({100 * hard_rate:.1f} %)** · ecartees par le juge : "
         f"{len(judge_rows)} ({100 * judge_rate:.1f} %)",
         f"- paquets incomplets : {len(incomplete)} ({100 * incomplete_rate:.1f} %)"]
    if trimmed:
        L.append(f"- **reparees par retrait d'une phrase : {trimmed}** (dont {trimmed_clean} retenues) : la "
                 f"phrase refusee par le juge est coupee, rien n'est reecrit, et l'originale devient un "
                 f"mauvais exemple (originaux dans `pairs_before_trim.jsonl`)")
    L += ["\n## Par type de paquet\n"]
    for k, v in per_kind.most_common():
        L.append(f"- {k} : {v} paires, {per_kind_bad[k]} ecartees")
    L += ["\n## Compteurs bloquants (cible 0 dans les paires retenues : elles sont ecartees)\n",
          f"- renvoi sec en fin de reponse : **{counts['bare_referral']}**  {pct('bare_referral')}",
          f"- nom absent du paquet : **{counts['unknown_name']}**  {pct('unknown_name')}",
          f"- chiffre absent du paquet : **{counts['invented_figure']}**  {pct('invented_figure')}",
          f"- autre animal ou culture : **{counts['wrong_host']}**  {pct('wrong_host')}",
          f"- jour de la semaine : **{counts['invented_day']}**  {pct('invented_day')}",
          f"- service cite hors du paquet : **{counts['wrong_institution']}**  {pct('wrong_institution')}",
          f"- mois absent du paquet : **{counts['invented_date']}**  {pct('invented_date')}",
          f"- la reponse parle de « la fiche / le materiel » : **{counts['meta_leak']}**  {pct('meta_leak')}",
          f"- reponse incomplete (moins de 40 mots) : **{counts['incomplete_answer']}**  {pct('incomplete_answer')}",
          f"- phrase non soutenue ou contredite selon le juge ({len(judged)} reponses jugees, "
          f"bloquant des {JUDGE_BLOCK_AT} phrase) : **{counts['unsupported_claim']}**  {pct('unsupported_claim')}",
          "\n## Indicateurs (a surveiller, non bloquants)\n",
          f"- reponse de moins de 60 mots : {counts['too_short']}  {pct('too_short')}",
          f"- phrases trop longues pour un paysan (>28 mots en moyenne) : {counts['long_sentences']}  {pct('long_sentences')}",
          f"- faible recouvrement avec le fait : {counts['ungrounded']}  {pct('ungrounded')}",
          f"- trop longue : {counts['too_long']} · markdown : {counts['markdown']} · "
          f"raisonnement affiche : {counts['chain_of_thought']} · politesse : {counts['pleasantry']}",
          f"\n## Verdict : **{'PASSE' if verdict else 'NE PASSE PAS'}**\n",
          "Passe si moins de 8 % de FAUTES DURES du redacteur (verifiables sans modele) et moins de "
          "10 % de paquets incomplets. Les paires ecartees par le juge ne comptent pas dans le verdict : "
          "elles servent de mauvais exemples pour l'entrainement par preferences.",
          "Un taux de rejet eleve veut dire que le prompt ou le modele doit changer, pas le filtre.\n"]
    if incomplete:
        L.append("### Paquets incomplets (relancer avec --retry-incomplete)\n")
        for bid, miss in list(incomplete.items())[:20]:
            L.append(f"- `{bid}` : manque {', '.join(miss)}")
    blocking_v = [v for v in violations if any(x.split(':')[0] in BLOCKING for x in v["issues"])]
    if blocking_v:
        L.append(f"\n### Premieres paires ecartees ({min(15, len(blocking_v))} sur {len(blocking_v)})\n")
        for v in blocking_v[:15]:
            L.append(f"- `{v['bundle_id']}` [{v['gate']}] {', '.join(v['issues'])}")
            L.append(f"  > {v['answer'][:240]}")
    (CHECK_DIR / "rapport.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:28]))
    print(f"\n-> {CHECK_DIR / 'rapport.md'}")
    return {"verdict": verdict, "reject_rate": reject_rate, "hard_rate": hard_rate,
            "judge_rate": judge_rate, "counts": dict(counts)}


if __name__ == "__main__":
    run()
