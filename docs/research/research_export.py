"""Export a deep-research workflow run into docs/research/<folder>/ for future reference.

    python3 production/build/research_export.py <workflow transcript dir> <output folder> [--question "…"]

Writes: journal.jsonl (raw copy), sources.md (every fetched source with quality and angle), claims.jsonl (every extracted
claim with the verifiers' votes), report.md and findings.json (from the synthesis agent, if the run reached it).
"""
import ast, json, os, shutil, sys

def parse(s):
    if not isinstance(s, str): return s
    for f in (json.loads, ast.literal_eval):
        try: return f(s)
        except Exception: pass
    return {"raw": s}

def export(wf_dir, out, question=""):
    os.makedirs(out, exist_ok=True)
    journal = os.path.join(wf_dir, "journal.jsonl")
    shutil.copy(journal, os.path.join(out, "journal.jsonl"))
    started, results = {}, {}
    for line in open(journal):
        try: d = json.loads(line)
        except Exception: continue
        if d.get("type") == "started": started[d["key"]] = d
        elif d.get("type") == "result": results[d["key"]] = parse(d.get("result"))
    rows = [(started.get(k, {}).get("phase", "?"), started.get(k, {}).get("label", "?"), results[k]) for k in results]
    # sources and claims
    sources, claims, verdicts, scope, report = [], [], {}, None, None
    for phase, label, r in rows:
        if not isinstance(r, dict): continue
        if phase == "Scope": scope = r
        elif phase == "Search":
            for x in r.get("results", []): x["angle"] = label.replace("search:", ""); sources.append(dict(x, stage="search"))
        elif phase == "Fetch":
            host = label.replace("fetch:", "")
            for c in r.get("claims", []):
                claims.append(dict(c, source_label=host, sourceQuality=r.get("sourceQuality"), publishDate=r.get("publishDate")))
            sources.append(dict(label=host, quality=r.get("sourceQuality"), publishDate=r.get("publishDate"), claims=len(r.get("claims", [])), stage="fetch"))
        elif phase == "Verify":
            key = label.split(":", 1)[1].strip('"') if ":" in label else label
            verdicts.setdefault(key, []).append(r)
        elif phase == "Synthesize": report = r
    # attach votes to claims by the first 40 characters of the claim (the verifier labels are capped there)
    for c in claims:
        k = c.get("claim", "")[:40].strip()
        for vk, vs in verdicts.items():
            if vk.rstrip("…") and k.startswith(vk.rstrip("…")[:30]):
                c["votes"] = vs; c["refuted_votes"] = sum(1 for v in vs if v.get("refuted")); break
    with open(os.path.join(out, "claims.jsonl"), "w") as f:
        for c in claims: f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with open(os.path.join(out, "sources.md"), "w") as f:
        f.write("# Sources\n\n")
        if question: f.write("**Question:** " + question + "\n\n")
        if scope: f.write("## Search angles\n\n" + "".join(f"- **{a.get('label')}** — `{a.get('query')}`\n" for a in scope.get("angles", [])) + "\n")
        f.write("## Search results\n\n| Angle | Title | URL | Relevance |\n|---|---|---|---|\n")
        for s in sources:
            if s.get("stage") == "search": f.write(f"| {s['angle']} | {s.get('title','')} | {s.get('url','')} | {s.get('relevance','')} |\n")
        f.write("\n## Fetched sources\n\n| Source | Quality | Date | Claims extracted |\n|---|---|---|---|\n")
        for s in sources:
            if s.get("stage") == "fetch": f.write(f"| {s['label']} | {s.get('quality','')} | {s.get('publishDate','') or ''} | {s.get('claims',0)} |\n")
    if report:
        json.dump(dict(question=question, **report), open(os.path.join(out, "findings.json"), "w"), ensure_ascii=False, indent=1)
        with open(os.path.join(out, "report.md"), "w") as f:
            f.write("# " + (question[:90] + ("…" if len(question) > 90 else "") if question else "Research report") + "\n\n")
            f.write(report.get("summary", "") + "\n\n## Findings\n\n")
            for i, x in enumerate(report.get("findings", []), 1):
                f.write(f"### {i}. [{x.get('confidence','?')}] {x.get('claim','')}\n\n")
                if x.get("evidence"): f.write("**Evidence:** " + x["evidence"] + "\n\n")
                if x.get("sources"): f.write("**Sources:** " + ", ".join(x["sources"]) + "\n\n")
            if report.get("caveats"): f.write("## Caveats\n\n" + report["caveats"] + "\n\n")
            if report.get("openQuestions"): f.write("## Open questions\n\n" + "".join(f"- {q}\n" for q in report["openQuestions"]))
    print(f"{out}: {len(sources)} source rows, {len(claims)} claims, report {'yes' if report else 'no'}")

if __name__ == "__main__":
    a = sys.argv[1:]; q = ""
    if "--question" in a: i = a.index("--question"); q = a[i + 1]; a = a[:i] + a[i + 2:]
    export(a[0], a[1], q)
