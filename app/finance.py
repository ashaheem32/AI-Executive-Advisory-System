"""Strict labelled-report extraction and Decimal calculations, never eval/LLM arithmetic."""
import re
from decimal import Decimal, ROUND_HALF_UP
from .db import connect

LABELS = {
    "revenue": "revenue", "cost of goods sold": "cogs", "cogs": "cogs",
    "operating expenses": "opex", "cash balance": "cash", "monthly net burn": "burn",
    "reported gross margin": "reported_margin",
}
NUMBER = re.compile(r"^-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?%?$")


def money(value):
    return f"{value:,.2f}"


def rounded(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate(operation, values):
    """Pure, explicit operation allowlist. Invariants guard invalid denominators."""
    if any(not isinstance(v, Decimal) or not v.is_finite() or abs(v) > Decimal("1e15") for v in values.values()):
        raise ValueError("Inputs must be finite Decimal values within the supported range.")
    if operation == "gross_profit":
        result = values["revenue"] - values["cogs"]
    elif operation == "gross_margin":
        if values["revenue"] <= 0:
            raise ValueError("Gross margin requires positive revenue.")
        result = (values["revenue"] - values["cogs"]) / values["revenue"] * 100
    elif operation == "operating_profit":
        result = values["revenue"] - values["cogs"] - values["opex"]
    elif operation == "operating_margin":
        if values["revenue"] <= 0:
            raise ValueError("Operating margin requires positive revenue.")
        result = (values["revenue"] - values["cogs"] - values["opex"]) / values["revenue"] * 100
    elif operation == "growth":
        if values["prior"] <= 0:
            raise ValueError("Growth requires a positive prior-period revenue.")
        result = (values["current"] - values["prior"]) / values["prior"] * 100
    elif operation == "runway":
        if values["burn"] <= 0 or values["cash"] < 0:
            raise ValueError("Runway requires nonnegative cash and a positive monthly net burn.")
        result = values["cash"] / values["burn"]
    else:
        raise ValueError("Unsupported calculation")
    return rounded(result)


def parse_reports(settings, role):
    with connect(settings) as con:
        docs = con.execute("SELECT * FROM documents WHERE category='finance' AND (access='public' OR ?='admin')", (role,)).fetchall()
        chunks = con.execute("SELECT c.* FROM chunks c JOIN documents d ON c.document_id=d.id "
                             "WHERE d.category='finance' AND (d.access='public' OR ?='admin')", (role,)).fetchall()
    reports = []
    for doc in docs:
        # Exactly one period and currency per report; ambiguity is never silently resolved.
        periods = set(re.findall(r"(?im)^Period:\s*(20\d{2}-Q[1-4])\s*$", doc["text"]))
        currencies = set(re.findall(r"(?im)^Currency:\s*([A-Z]{3})\s*$", doc["text"]))
        if len(periods) != 1 or len(currencies) != 1:
            continue
        scopes = set(re.findall(r"(?im)^Scope:\s*(.+)$", doc["text"]))
        report = {"period": next(iter(periods)).upper(), "currency": next(iter(currencies)).upper(), "scope": next(iter(scopes)).strip().lower() if len(scopes) == 1 else None, "values": {}, "invalid": [], "doc": dict(doc)}
        for line in doc["text"].splitlines():
            if ":" not in line:
                continue
            label, raw = line.split(":", 1)
            key = LABELS.get(label.strip().lower())
            if not key:
                continue
            raw = raw.strip()
            if not NUMBER.fullmatch(raw) or ("%" in raw) != (key == "reported_margin"):
                report["invalid"].append(key)
                continue
            value = Decimal(raw.replace(",", "").replace("%", ""))
            if abs(value) > Decimal("1e15") or (key != "reported_margin" and value < 0):
                report["invalid"].append(key)
                continue
            source = next((dict(c) for c in chunks if c["document_id"] == doc["id"] and line.strip() in c["text"]), None)
            if not source:
                report["invalid"].append(key)
                continue
            entry = {"value": value, "quote": line.strip(), "source": source, "name": doc["name"]}
            # Duplicate labels with different numbers are conflicts even inside one file.
            if key in report["values"] and report["values"][key]["value"] != value:
                report["invalid"].append(key)
            report["values"][key] = entry
        reports.append(report)
    return reports


def finance_answer(settings, question, role):
    q = question.lower()
    operation = ("growth" if any(t in q for t in ("growth", "increase", "compare")) else
                 "runway" if any(t in q for t in ("runway", "burn")) else
                 "operating_margin" if "operating" in q and "margin" in q else
                 "operating_profit" if "operating" in q and "profit" in q else
                 "gross_margin" if "margin" in q else "gross_profit" if "gross profit" in q else None)
    if operation is None:
        return None
    result = {"advisor": "finance", "mode": "code", "status": "insufficient", "citations": [], "calculations": [], "warnings": [],
              "answer": "I cannot find sufficient evidence in documents you can access. Upload a labelled financial report with Period, Currency and the required metrics."}
    reports = parse_reports(settings, role)
    periods = sorted(set(r["period"] for r in reports))
    requested = sorted(set(p.upper() for p in re.findall(r"20\d{2}-q[1-4]", q)))
    if operation == "growth":
        selected = requested if len(requested) == 2 else [p for p in periods if not requested or p <= requested[-1]][-2:]
        if len(requested) > 2 or len(selected) != 2:
            result["answer"] = "Revenue growth needs two distinct periods with comparable revenue and currency. Specify two periods such as 2026-Q2 and 2026-Q3."
            return result
    else:
        if len(requested) > 1:
            result["answer"] = "Please select one period for this calculation. Revenue growth supports two periods."
            return result
        selected = requested or periods[-1:]
    selected_reports = [r for r in reports if r["period"] in selected]
    if any(r["scope"] is None for r in selected_reports) or len({r["scope"] for r in selected_reports}) > 1:
        result.update(status="conflict", answer="A consistent reporting Scope is required. Confirm these reports cover the same entity, accounting basis and period duration before combining inputs.")
        return result
    required = {"gross_profit": ["revenue", "cogs"], "gross_margin": ["revenue", "cogs"],
                "operating_profit": ["revenue", "cogs", "opex"], "operating_margin": ["revenue", "cogs", "opex"],
                "growth": ["revenue"], "runway": ["cash", "burn"]}[operation]
    inputs, citations, currencies, all_values = {}, [], set(), {}
    for period in selected:
        matching = [r for r in reports if r["period"] == period]
        if not matching:
            result["answer"] = f"I cannot find sufficient evidence for {period} in documents you can access."
            return result
        for key in required:
            if any(key in r["invalid"] for r in matching):
                result.update(status="invalid", answer=f"Cannot calculate: {key} in {period} has an invalid or ambiguous numeric format. Correct the report first.")
                return result
            entries = [r["values"][key] for r in matching if key in r["values"]]
            if not entries:
                result["answer"] = f"I cannot find sufficient evidence: {key} is missing for {period}."
                return result
            # Currency belongs to each source amount, not to the model's interpretation.
            signatures = {(e["value"], r["currency"]) for r in matching for e in [r["values"].get(key)] if e}
            if len(signatures) > 1:
                result.update(status="conflict", answer=f"Conflicting {key} values or currencies for {period}. Reconcile the source reports before calculating.",
                              citations=[citation(e, i + 1) for i, e in enumerate(entries)])
                return result
            value, currency = next(iter(signatures))
            currencies.add(currency)
            all_values[(period, key)] = value
            entry = entries[0]
            citations.append(citation(entry, len(citations) + 1))
            inputs[f"{period} · {key}"] = money(value)
    if not selected:
        return result
    if len(currencies) != 1:
        result.update(status="conflict", answer="The reports use different currencies. I cannot combine these amounts without an approved exchange rate.", citations=citations)
        return result
    currency = next(iter(currencies))
    values = ({"prior": all_values[(selected[0], "revenue")], "current": all_values[(selected[1], "revenue")]} if operation == "growth"
              else {key: all_values[(selected[0], key)] for key in required})
    try:
        value = calculate(operation, values)
    except ValueError as exc:
        result.update(status="invalid", answer=str(exc), citations=citations)
        return result
    formula = {
        "gross_profit": "Revenue − cost of goods sold", "gross_margin": "(Revenue − cost of goods sold) ÷ revenue × 100",
        "operating_profit": "Revenue − cost of goods sold − operating expenses",
        "operating_margin": "(Revenue − cost of goods sold − operating expenses) ÷ revenue × 100",
        "growth": "(Current revenue − prior revenue) ÷ prior revenue × 100", "runway": "Cash balance ÷ monthly net burn",
    }[operation]
    unit = "%" if operation in ("growth", "gross_margin", "operating_margin") else " months" if operation == "runway" else f" {currency}"
    label = operation.replace("_", " ").capitalize()
    result.update(status="answered", citations=citations,
                  answer=f"{label} is {money(value)}{unit} for {' → '.join(selected)}. " + {
                      "gross_margin": f"This leaves {money(value)}% of revenue after direct costs, before operating expenses.",
                      "gross_profit": "This is the amount remaining after direct costs, before operating expenses.",
                      "operating_profit": "This excludes tax, interest and any costs not listed as operating expenses.",
                      "operating_margin": "This measures the share of revenue remaining after the listed operating costs.",
                      "growth": "This compares reported revenue; it does not establish the cause of the change.",
                      "runway": "This assumes the stated monthly net burn stays constant.",
                  }[operation],
                  calculations=[{"label": label, "value": money(value) + unit, "formula": formula, "inputs": inputs,
                                 "period": " → ".join(selected), "currency": currency, "rounding": "Decimal · half up · 2 places"}])
    if operation == "gross_margin":
        for report in reports:
            claimed = report["values"].get("reported_margin")
            if report["period"] in selected and claimed and rounded(claimed["value"]) != value:
                result["warnings"].append(f"Source arithmetic mismatch: {report['doc']['name']} reports {claimed['value']}%, but the code recomputes {value}%. Use the recomputed value and review the report.")
                result["citations"].append(citation(claimed, len(result["citations"]) + 1))
    return result


def citation(entry, number):
    return {"ref": f"S{number}", "document_id": entry["source"]["document_id"], "chunk_id": entry["source"]["id"],
            "name": entry["name"], "location": entry["source"]["location"], "quote": entry["quote"]}
