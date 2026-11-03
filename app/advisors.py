import re
from . import provider
from .db import audit, connect
from .retrieval import retrieve, evidence_sentences
from .finance import finance_answer

TOPICS = {
    "annual leave": ["annual leave", "vacation", "holiday allowance"],
    "remote work": ["remote", "work from home", "hybrid"],
    "notice period": ["notice period", "resign", "termination notice"],
    "sick leave": ["sick leave", "illness"], "parental leave": ["parental", "maternity", "paternity"],
    "probation": ["probation"], "working hours": ["working hours", "work hours"],
}


def route(question):
    q = question.lower()
    hr = any(term in q for terms in TOPICS.values() for term in terms) or bool(re.search(r"\b(hr|employee|salary|salaries|bonus|compensation|benefits|handbook|policy|policies|training)\b", q))
    finance = bool(re.search(r"\b(revenue|margin|profit|financial|finance|cash|burn|runway|growth|cogs|budget|expenses)\b", q))
    if hr and finance and not ("training budget" in q and not re.search(r"\b(revenue|margin|profit|cash|growth)\b", q)):
        return "mixed"
    return "hr" if hr else "finance" if finance else "knowledge"


def respond(settings, question, user):
    advisor = route(question)
    base = {"advisor": advisor, "mode": "evidence", "status": "insufficient", "calculations": [], "warnings": [], "citations": [],
            "answer": "I cannot find sufficient evidence in documents you can access. Try a more specific question or ask an administrator to upload the relevant source."}
    if advisor == "mixed":
        base.update(status="clarify", answer="This question spans Finance and HR. Please ask each advisor question separately so the evidence and calculations stay clear.")
        return base
    if advisor == "finance":
        calculated = finance_answer(settings, question, user["role"])
        if calculated:
            audit(settings, user["id"], "advisor_answer", detail=f"finance; {calculated['status']}; code")
            return calculated
        if any(term in question.lower() for term in ("net profit", "ebitda", "calculate")):
            base.update(status="clarify", answer="Supported calculations are gross profit, gross margin, operating profit, operating margin, revenue growth and cash runway. Net profit and EBITDA require additional accounting inputs and are not implemented.")
            return base
    topics = [topic for topic, terms in TOPICS.items() if any(term in question.lower() for term in terms)] if advisor == "hr" else []
    retrieval_question = " ".join(topics) if topics else question
    hits = retrieve(settings, retrieval_question, user["role"], advisor if advisor in ("finance", "hr") else None)
    # Check known HR topics against relevant source lines, not a document title or generic 'leave'.
    if topics:
        missing = [topic for topic in topics if not any(any(term in h["text"].lower() for term in TOPICS[topic]) for h in hits)]
        if missing:
            base["answer"] = "I cannot find sufficient evidence for " + ", ".join(missing) + " in documents you can access. Ask HR to provide the relevant policy."
            return base
        conflict = policy_conflict(settings, topics, user["role"])
        if conflict:
            base.update(status="conflict", answer="Conflicting policy evidence found. " + conflict["message"] + " No precedence rule is configured; ask HR to confirm which policy applies.", citations=conflict["citations"])
            audit(settings, user["id"], "advisor_answer", detail="hr; conflict")
            return base
    if not hits:
        audit(settings, user["id"], "advisor_answer", detail=f"{advisor}; insufficient")
        return base
    if settings.api_key:
        try:
            selections = provider.select_evidence(settings, question, hits)
            base["mode"] = "ai"
        except provider.ProviderError:
            selections = evidence_sentences(retrieval_question, hits)
            base["mode"] = "fallback"
            base["warnings"].append("The AI service could not return verified evidence. Showing local source excerpts instead.")
            audit(settings, user["id"], "provider_failure", detail="Evidence-only fallback used")
    else:
        selections = evidence_sentences(retrieval_question, hits)
    by_id = {h["id"]: h for h in hits}
    citations = []
    for selection in selections:
        hit = by_id[selection["chunk_id"]]
        citations.append({"ref": f"S{len(citations) + 1}", "document_id": hit["document_id"], "chunk_id": hit["id"],
                          "name": hit["name"], "location": hit["location"], "quote": selection["quote"]})
    if citations:
        base.update(status="answered", answer="Relevant evidence from the documents you can access:\n\n" + "\n\n".join(
            f"[{c['ref']}] {c['quote']}" for c in citations), citations=citations)
    audit(settings, user["id"], "advisor_answer", detail=f"{advisor}; {base['status']}; {base['mode']}")
    return base


def policy_conflict(settings, topics, role):
    with connect(settings) as con:
        rows = con.execute("SELECT c.*,d.name FROM chunks c JOIN documents d ON c.document_id=d.id "
                           "WHERE d.category='hr' AND (d.access='public' OR ?='admin')", (role,)).fetchall()
    # Bounded conflict detector for labelled policy facts. No automatic date precedence.
    for topic in topics:
        facts = []
        for row in rows:
            for line in row["text"].splitlines():
                if re.match(r"^" + re.escape(topic) + r"\s*:", line, re.I):
                    value = line.split(":", 1)[1].strip().rstrip(".").lower()
                    facts.append((value, dict(row), line.strip()))
        unique = {value for value, _, _ in facts}
        if len(unique) > 1:
            citations = [{"ref": f"S{i + 1}", "document_id": row["document_id"], "chunk_id": row["id"], "name": row["name"],
                          "location": row["location"], "quote": quote} for i, (_, row, quote) in enumerate(facts[:6])]
            return {"message": f"The accessible documents give different values for {topic}.", "citations": citations}
    return None
