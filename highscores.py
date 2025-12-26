from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class HighScoreEntry:
    name: str
    score: int


def _sanitize_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return "PLAYER"
    name = "".join(ch for ch in name if ch.isprintable())
    name = name.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    return name[:16].strip() or "PLAYER"


def _safe_int(x, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _default_path() -> str:
    # Store alongside main.py so it persists for local runs.
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "highscores.json")


def load_highscores(path: str | None = None) -> List[HighScoreEntry]:
    path = path or _default_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError:
        return []
    except Exception:
        return []

    items = payload.get("scores", []) if isinstance(payload, dict) else []
    out: List[HighScoreEntry] = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        name = _sanitize_name(it.get("name", "PLAYER"))
        score = max(0, _safe_int(it.get("score", 0)))
        out.append(HighScoreEntry(name=name, score=score))
    out.sort(key=lambda e: e.score, reverse=True)
    return out


def save_highscore(name: str, score: int, path: str | None = None, keep_max: int = 50) -> List[HighScoreEntry]:
    path = path or _default_path()
    entries = load_highscores(path)
    entries.append(HighScoreEntry(name=_sanitize_name(name), score=max(0, int(score))))
    entries.sort(key=lambda e: e.score, reverse=True)
    entries = entries[: max(1, int(keep_max))]

    payload = {"scores": [{"name": e.name, "score": e.score} for e in entries]}
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        # If saving fails, just return the in-memory list.
        pass
    return entries


