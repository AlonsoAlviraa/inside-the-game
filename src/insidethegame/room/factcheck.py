"""Grounding check: every number in generated text must exist in the facts the agent was given."""
from __future__ import annotations
import re

_NUM = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)?")


def _flatten(obj) -> list[float]:
    out: list[float] = []
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            out += _flatten(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out += _flatten(v)
    elif isinstance(obj, str):
        out += [float(n.replace(",", ".")) for n in _NUM.findall(obj)]
    return out


def allowed_numbers(*facts) -> set[str]:
    allowed = {"1", "2", "0"}  # "one-two", "1v1", ordinal halves
    for v in _flatten(list(facts)):
        for cand in (v, round(v), round(v, 1), round(v, 2), round(v * 100), round(v * 100, 1)):
            allowed.add(_norm(cand))
    return allowed


def _norm(v) -> str:
    v = float(v)
    return str(int(v)) if v == int(v) else f"{v:.2f}".rstrip("0").rstrip(".")


def numbers_in(text: str) -> list[str]:
    return [_norm(n.replace(",", ".")) for n in _NUM.findall(text)]


def check(text: str, *facts) -> tuple[bool, list[str]]:
    """Return (ok, unsupported_numbers)."""
    ok_set = allowed_numbers(*facts)
    bad = [n for n in numbers_in(text) if n not in ok_set]
    return (not bad, bad)
