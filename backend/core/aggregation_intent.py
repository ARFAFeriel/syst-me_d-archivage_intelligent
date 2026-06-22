import re
from sqlalchemy import text

EXISTENCE_PATTERNS = [
    r"\by\s*a[\s-]*t[\s-]*il\b",
    r"\best[\s-]*ce\s*qu[' ]?[ei]?\s*il\s*y\s*a\b",
    r"\bexiste[\s-]*t[\s-]*il\b",
]

COUNT_PATTERNS = [
    r"\bcombien\b",
    r"\bnombre\s+de\b",
]

FIELD_KEYWORDS = {
    "aircraft_registration": ["immatriculation", "avion", "aéronef", "appareil"],
    "doc_type": ["type de document", "work order", "jobcard", "job card",
                 "airworthiness", "service bulletin", "certificate", "rct", "defect"],
    "ata_chapter": ["ata", "chapitre"],
    "category": ["categorie", "catégorie", "check"],
}

DOC_TYPE_VALUE_MAP = {
    "work order": "WORK_ORDER",
    "jobcard": "JOBCARD",
    "job card": "JOBCARD",
    "airworthiness": "AD",
    "service bulletin": "SB",
    "certificate": "CERTIFICATE",
    "rct": "RCT",
    "defect": "DEFECT_REPORT",
}


def detect_aggregation_intent(question: str):
    q_lower = question.lower()

    intent = None
    if any(re.search(p, q_lower) for p in EXISTENCE_PATTERNS):
        intent = "existence"
    elif any(re.search(p, q_lower) for p in COUNT_PATTERNS):
        intent = "count"

    if intent is None:
        return None

    field = None
    for field_name, keywords in FIELD_KEYWORDS.items():
        if any(kw in q_lower for kw in keywords):
            field = field_name
            break

    if field is None:
        return None

    is_negation = any(neg in q_lower for neg in ["sans ", "pas de ", "aucun", "n'a pas", "non rattaché"])

    doc_type_value = None
    if field == "doc_type":
        for kw, val in DOC_TYPE_VALUE_MAP.items():
            if kw in q_lower:
                doc_type_value = val
                break

    return {
        "intent": intent,
        "field": field,
        "is_negation": is_negation,
        "doc_type_value": doc_type_value,
    }


async def handle_aggregation_query(db, intent_info, aircraft_filter):
    field = intent_info["field"]
    is_negation = intent_info["is_negation"]
    doc_type_value = intent_info.get("doc_type_value")

    where_clauses = ["status = 'ARCHIVED'"]
    params = {}

    if is_negation:
        where_clauses.append(f"({field} IS NULL OR {field} = '')")
    elif doc_type_value:
        where_clauses.append("doc_type::text = :doc_type_value")
        params["doc_type_value"] = doc_type_value

    if aircraft_filter and field != "aircraft_registration":
        where_clauses.append("aircraft_registration ILIKE :aircraft")
        params["aircraft"] = f"%{aircraft_filter}%"

    where_sql = " AND ".join(where_clauses)

    count_sql = f"SELECT COUNT(*) as total FROM documents WHERE {where_sql}"
    result = await db.execute(text(count_sql), params)
    total = result.scalar() or 0

    examples = []
    if total > 0:
        ex_sql = f"""
            SELECT filename, aircraft_registration, doc_type, category, es_reference
            FROM documents WHERE {where_sql} LIMIT 10
        """
        ex_result = await db.execute(text(ex_sql), params)
        examples = [dict(row._mapping) for row in ex_result.fetchall()]

    return {
        "field": field,
        "is_negation": is_negation,
        "total": total,
        "examples": examples,
    }


