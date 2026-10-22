"""Precompute replay commentary: python scripts/build_replay.py [seed ...] (needs ITG_LLM_PROVIDER=azure + endpoint).
Skips combinations already cached unless --force."""
import asyncio, json, sys, time
from insidethegame import replay
from insidethegame.room import localise

async def main(argv):
    force = "--force" in argv
    only = {tuple(a.split(":")) for a in argv if a.count(":") == 2}  # e.g. 7:fan:en rebuilds just that run
    seeds = sorted({int(o[0]) for o in only}) or [int(a) for a in argv if a.isdigit()] or list(replay.SHOWCASE)
    for s in seeds:
        for m in replay.MODES:
            for l in replay.LANGS:
                p = replay.path(s, m, l)
                if only and (str(s), m, l) not in only:
                    continue
                if p.exists() and not force and not only:
                    continue
                t = time.time()
                r = await replay.record(s, m, l)
                for b in r["batches"]:
                    b["payload"]["cards"] = localise.ensure(b["payload"]["cards"], l, m)
                p.write_text(json.dumps(r, default=str, ensure_ascii=False))
                n = sum(len(b["payload"]["cards"]) for b in r["batches"])
                llm = sum("llm" in str(c.get("source")) for b in r["batches"] for c in b["payload"]["cards"])
                pers = sum("personalised" in str(c.get("source")) for b in r["batches"] for c in b["payload"]["cards"])
                print(f"{s} {m} {l}: {n} cards, {llm} llm, {pers} personalised, {r['usage']['calls']} calls, "
                      f"${r['usage']['usd']}, {time.time()-t:.0f}s", flush=True)

asyncio.run(main(sys.argv[1:]))
