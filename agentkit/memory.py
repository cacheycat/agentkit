"""Long-term memory with a learned usefulness score.

A memory is a short text plus metadata. Retrieval ranks by lexical relevance
multiplied by a utility prior: the Laplace-smoothed share of past retrievals
that preceded a good outcome. Callers report outcomes with `feedback`, so
lessons that keep helping rise and lessons that mislead sink without being
deleted. That feedback loop is the self-improvement mechanism.
"""
from __future__ import annotations

import json
import time

from .rag import Index, tokenize
from .store import Store


def utility(wins: int, losses: int) -> float:
    return (wins + 1) / (wins + losses + 2)


class Memory:
    def __init__(self, store: Store):
        self.store = store

    def add(self, kind: str, text: str, meta: dict | None = None) -> int:
        text = " ".join(text.split())
        new = set(tokenize(text))
        for row in self.all(kind):
            old = set(tokenize(row["text"]))
            if new and len(new & old) / len(new | old) > 0.8:  # near-duplicate: keep the original
                return row["id"]
        return self.store.execute("INSERT INTO memories(kind,text,meta,created) VALUES(?,?,?,?)",
                                  (kind, text, json.dumps(meta or {}), time.time())).lastrowid

    def all(self, kind: str | None = None) -> list[dict]:
        if kind:
            rows = self.store.query("SELECT * FROM memories WHERE kind=? ORDER BY id DESC", (kind,))
        else:
            rows = self.store.query("SELECT * FROM memories ORDER BY id DESC")
        for r in rows:
            r["meta"] = json.loads(r["meta"] or "{}")
            r["utility"] = round(utility(r["wins"], r["losses"]), 3)
        return rows

    def search(self, query: str, k: int = 4, kind: str | None = None, touch: bool = True) -> list[dict]:
        rows = self.all(kind)
        if not rows:
            return []
        hits = Index(rows).search(query, k=max(k * 3, k))
        for h in hits:
            h["rank_score"] = round(h["score"] * (0.5 + h["utility"]), 5)
        hits = sorted(hits, key=lambda h: -h["rank_score"])[:k]
        if touch and hits:
            ids = ",".join(str(h["id"]) for h in hits)
            self.store.execute(f"UPDATE memories SET uses = uses + 1 WHERE id IN ({ids})")
        return hits

    def feedback(self, ids: list[int], good: bool) -> None:
        if ids:
            col = "wins" if good else "losses"
            marks = ",".join("?" * len(ids))
            self.store.execute(f"UPDATE memories SET {col} = {col} + 1 WHERE id IN ({marks})", tuple(ids))
