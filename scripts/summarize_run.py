import json, sys, collections
f = sys.argv[1]
batches, ticks = [], 0
for l in open(f):
    if l.startswith("data: {\"cards\""):
        batches.append(json.loads(l[6:]))
    elif l.startswith("data: {\"event\""):
        ticks += 1
print("ticks", ticks, "batches", len(batches))
u = batches[-1]["usage"]; print(json.dumps(u, indent=1))
rej = sum(len(t.get("factcheck_rejected") or []) if isinstance(t.get("factcheck_rejected"), list) else (t.get("factcheck_rejected") or 0) for b in batches for t in b["trace"])
skips = collections.Counter(t.get("llm") for b in batches for t in b["trace"] if t.get("llm"))
print("fact-check rejections", rej, "llm states", dict(skips))
lat = collections.defaultdict(list)
for b in batches:
    for t in b["trace"]:
        lat[t["agent"]].append(t["ms"])
print({k: (round(sum(v)/len(v)), max(v)) for k, v in lat.items()})
print("anomalies", sum(len(b["report"].get("anomalies", [])) for b in batches), "dups", sum(b["report"].get("duplicates", 0) for b in batches))
for b in batches:
    for c in b["cards"]:
        print(f"{c['minute']:>3}' [{c['type']:<12}] p{c['priority']} {c['source']:<26} {c['title']} | {c['text']}")
for b in batches:
    for t in b["trace"]:
        if t.get("factcheck_rejected") or (t.get("factcheck") and t["factcheck"] != "pass"):
            print("REJECT", b["minute"], t["agent"], json.dumps(t.get("factcheck_rejected") or t.get("factcheck"), ensure_ascii=False)[:300])
