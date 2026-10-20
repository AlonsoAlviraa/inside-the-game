"""Rebuild the deterministic season cache: python scripts/build_season.py"""
import json
from insidethegame import season
data = season.build()
season.CACHE.write_text(json.dumps(data, separators=(",", ":")))
print(len(data["matches"]), "matches ->", season.CACHE)
