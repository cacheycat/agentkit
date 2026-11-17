"""Hybrid lexical retrieval: BM25 and TF-IDF cosine, fused by reciprocal rank.

No embedding service is required, which keeps retrieval deterministic and free
to run in tests. `Index.search` returns the fused ranking with both component
ranks so a caller can show why a passage was retrieved.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

_STOP = set("a an and are as at be but by for from has have if in into is it its of on or "
            "that the their then there these this to was were which while with not no".split())


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9_\-]*", text.lower())
    out = []
    for w in words:
        if w in _STOP or len(w) < 2:
            continue
        for suffix in ("ing", "ed", "es", "s"):
            if len(w) > len(suffix) + 3 and w.endswith(suffix):
                w = w[: -len(suffix)]
                break
        out.append(w)
    return out


class Index:
    def __init__(self, docs: list[dict], text_key: str = "text", k1: float = 1.4, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.tokens = [tokenize(d.get("title", "") + " " + d[text_key]) for d in docs]
        self.tf = [Counter(t) for t in self.tokens]
        self.lengths = [len(t) for t in self.tokens]
        self.avg_len = (sum(self.lengths) / len(docs)) if docs else 0.0
        df = Counter(term for tf in self.tf for term in tf)
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.norms = [math.sqrt(sum((f * self.idf[t]) ** 2 for t, f in tf.items())) or 1.0 for tf in self.tf]

    def _bm25(self, q: list[str], i: int) -> float:
        tf, score = self.tf[i], 0.0
        for term in q:
            f = tf.get(term, 0)
            if f:
                denom = f + self.k1 * (1 - self.b + self.b * self.lengths[i] / (self.avg_len or 1))
                score += self.idf.get(term, 0.0) * f * (self.k1 + 1) / denom
        return score

    def _cosine(self, q: list[str], i: int) -> float:
        qtf = Counter(q)
        qnorm = math.sqrt(sum((f * self.idf.get(t, 0.0)) ** 2 for t, f in qtf.items())) or 1.0
        dot = sum(f * self.idf.get(t, 0.0) * self.tf[i].get(t, 0) * self.idf.get(t, 0.0) for t, f in qtf.items())
        return dot / (qnorm * self.norms[i])

    def search(self, query: str, k: int = 4) -> list[dict]:
        q = tokenize(query)
        if not q or not self.docs:
            return []
        n = len(self.docs)
        bm = sorted(range(n), key=lambda i: -self._bm25(q, i))
        cs = sorted(range(n), key=lambda i: -self._cosine(q, i))
        bm_rank = {i: r for r, i in enumerate(bm)}
        cs_rank = {i: r for r, i in enumerate(cs)}
        fused = sorted(range(n), key=lambda i: -(1 / (60 + bm_rank[i]) + 1 / (60 + cs_rank[i])))
        hits = []
        for i in fused[:k]:
            if self._bm25(q, i) <= 0:
                continue
            hits.append({**self.docs[i], "score": round(1 / (60 + bm_rank[i]) + 1 / (60 + cs_rank[i]), 5),
                         "bm25_rank": bm_rank[i] + 1, "cosine_rank": cs_rank[i] + 1})
        return hits


def load_cards(directory: str | Path) -> list[dict]:
    """Read a folder of markdown cards. Each `## ` heading starts one passage."""
    docs: list[dict] = []

    def flush(card: str, card_title: str, title: str, buf: list[str]) -> None:
        body = "\n".join(buf).strip()
        if body:
            docs.append({"id": f"{card}#{len(docs)}", "card": card, "card_title": card_title,
                         "title": title, "text": body})

    for path in sorted(Path(directory).glob("*.md")):
        card = card_title = title = path.stem
        buf: list[str] = []
        for line in path.read_text().splitlines():
            if line.startswith("# "):
                card_title = title = line[2:].strip()
            elif line.startswith("## "):
                flush(card, card_title, title, buf)
                buf = []
                title = f"{card_title} / {line[3:].strip()}"
            else:
                buf.append(line)
        flush(card, card_title, title, buf)
    return docs
