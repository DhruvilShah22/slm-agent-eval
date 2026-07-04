"""search_docs tool — BM25 keyword retrieval over the local corpus.

Hand-rolled BM25 (Robertson/Sparck-Jones, k1=1.5, b=0.75): zero dependencies,
deterministic (ties broken by doc id), tiny corpus so no index persistence.
"""

import math
import re
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "corpus"
_K1, _B = 1.5, 0.75

SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_docs",
        "description": "Keyword-search Zephyra Outfitters' internal documents "
                       "(policies on returns, shipping, warranty, discounts, "
                       "delivery times, and product guides). Returns the most "
                       "relevant documents.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keywords"},
                "top_k": {"type": "integer",
                          "description": "Number of documents to return (default 3)"},
            },
            "required": ["query"],
        },
    },
}

_index = None  # lazy singleton: (docs, doc_freq, avg_len)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _build():
    docs = []
    for path in sorted(CORPUS_DIR.glob("*.txt")):
        body = path.read_text(encoding="utf-8")
        toks = _tokens(body)
        tf = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        docs.append({"id": path.stem, "body": body, "tf": tf, "len": len(toks)})
    df = {}
    for d in docs:
        for t in d["tf"]:
            df[t] = df.get(t, 0) + 1
    avg = sum(d["len"] for d in docs) / max(len(docs), 1)
    return docs, df, avg


def run(query: str, top_k: int = 3) -> dict:
    global _index
    if _index is None:
        _index = _build()
    docs, df, avg = _index
    n = len(docs)
    if n == 0:
        return {"error": "document corpus is empty — run data/generate.py"}
    q = _tokens(str(query))
    scored = []
    for d in docs:
        s = 0.0
        for t in q:
            if t not in d["tf"]:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            tf = d["tf"][t]
            s += idf * tf * (_K1 + 1) / (tf + _K1 * (1 - _B + _B * d["len"] / avg))
        if s > 0:
            scored.append((s, d))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    k = max(1, min(int(top_k or 3), 10))
    return {"results": [{"doc_id": d["id"], "score": round(s, 3),
                         "content": d["body"]} for s, d in scored[:k]]}
