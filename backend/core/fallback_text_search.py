import re
from sqlalchemy import text

async def fallback_text_search(db, question, limit=5):
    stopwords = {
        "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "est",
        "qu", "qui", "que", "dans", "sur", "pour", "avec", "ce", "cette",
        "il", "y", "a", "t", "the", "is", "in", "on", "of", "an",
    }
    mots = re.findall(r"[a-zA-Z0-9À-ÿ]+", question.lower())
    mots_significatifs = [m for m in mots if m not in stopwords and len(m) > 2]

    if not mots_significatifs:
        return []

    where_parts = []
    params = {}
    for i, mot in enumerate(mots_significatifs[:6]):
        param_name = f"mot{i}"
        where_parts.append(
            f"(filename ILIKE :{param_name} OR ocr_text ILIKE :{param_name} "
            f"OR es_reference ILIKE :{param_name} OR doc_type::text ILIKE :{param_name} "
            f"OR aircraft_registration ILIKE :{param_name})"
        )
        params[param_name] = f"%{mot}%"

    where_sql = " OR ".join(where_parts)
    params["limit_n"] = limit

    sql_query = f"""
        SELECT id, filename, doc_type, aircraft_registration, category,
               es_reference, ata_chapter, ocr_confidence,
               LEFT(ocr_text, 500) as ocr_preview
        FROM documents
        WHERE status = 'ARCHIVED' AND ({where_sql})
        LIMIT :limit_n
    """
    result = await db.execute(text(sql_query), params)
    return result.fetchall()
