"""Small BM25 lexical index. Access filtering happens in SQL BEFORE scoring."""
import math
import re
from collections import Counter
from .db import connect

STOP = set("a an the is are was were be to of in on for from and or with by as at can do does how what which who when my our your me tell please about give much many documents document policy policies company business employee employees find show information based uploaded summarize summary".split())
STOP.update("provide provided provides receive receives received required require need needs".split())
ALIASES = {"vacation": "leave", "revenues": "revenue", "sales": "revenue", "profits": "profit", "costs": "cost", "expenses": "expense", "working": "work", "remotely": "remote"}


def tokens(text):
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [ALIASES.get(w, w) for w in words if w not in STOP and len(w) > 1]


def retrieve(settings, question, role, category=None, limit=6):
    with connect(settings) as con:
        rows = con.execute("SELECT c.id,c.document_id,c.location,c.text,d.name,d.category "
                           "FROM chunks c JOIN documents d ON c.document_id=d.id "
                           "WHERE (d.access='public' OR ?='admin') AND (? IS NULL OR d.category=?)",
                           (role, category, category)).fetchall()
    if not rows:
        return []
    query = set(tokens(question))
    if not query:
        return []
    corpus = [Counter(tokens(row["text"] + " " + row["name"])) for row in rows]
    lengths = [sum(c.values()) for c in corpus]
    average = max(sum(lengths) / len(lengths), 1)
    frequencies = {term: sum(term in c for c in corpus) for term in query}
    hits = []
    for row, counts, length in zip(rows, corpus, lengths):
        matched = query.intersection(counts)
        # Do not answer a specific multi-term question from a single generic overlap.
        if len(matched) < min(2, len(query)) or len(matched) / len(query) < 0.28:
            continue
        score = 0
        for term in matched:
            tf = counts[term]
            idf = math.log(1 + (len(rows) - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
            score += idf * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * length / average))
        hit = dict(row)
        hit["score"] = round(score, 4)
        hits.append(hit)
    return sorted(hits, key=lambda row: row["score"], reverse=True)[:limit]


def evidence_sentences(question, hits):
    query = set(tokens(question))
    # Company names repeated across every report must not outrank a specific topic.
    present = {term: sum(term in set(tokens(h["text"])) for h in hits) for term in query}
    focused = {term for term, count in present.items() if 0 < count <= max(1, len(hits) // 2)}
    query = focused or query
    selections = []
    for hit in hits:
        lines = [s.strip() for s in re.split(r"\n+|(?<=[.!?])\s+", hit["text"]) if s.strip()]
        ranked = sorted(lines, key=lambda s: len(query.intersection(tokens(s))), reverse=True)
        if ranked and query.intersection(tokens(ranked[0])):
            selections.append({"chunk_id": hit["id"], "quote": ranked[0][:700]})
    return selections[:4]
