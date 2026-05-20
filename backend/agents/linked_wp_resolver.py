"""
linked_wp_resolver.py
─────────────────────
Module à intégrer dans le pipeline pour résoudre automatiquement
la catégorie d'un Work Order via son champ "Linked WP".

Intégration dans pipeline.py :
  from backend.agents.linked_wp_resolver import resolve_linked_wp_category

  # Après classification, avant archivage :
  if doc.doc_type == "WORK_ORDER":
      resolved = await resolve_linked_wp_category(db, doc.ocr_text)
      if resolved:
          doc.category = resolved
"""

import re
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


def normalize_es(ref: str) -> str:
    """
    Normalise une référence ES pour comparaison insensible aux zéros et préfixes.
    ES00001778 → 1778  |  ES001392 → 1392  |  00203601 → 203601
    """
    if not ref:
        return ""
    cleaned = re.sub(r'^ES\s*', '', ref.strip(), flags=re.IGNORECASE)
    return cleaned.lstrip('0') or '0'


def extract_linked_wp_es(ocr_text: str) -> list[str]:
    """
    Extrait les références ES du champ "Linked WP" dans le texte OCR.

    Patterns reconnus :
      "linked wp     ES001234     MSN2158"
      "LINKED WP : ES 001234"
      "wp linked ES152410"
    """
    if not ocr_text:
        return []

    results = []

    # Pattern principal
    pattern = re.compile(
        r'(?:linked\s+wp|wp\s+linked)\s*[:\-]?\s*((?:ES\s*\d{4,8}\s*[/,]?\s*)+)',
        re.IGNORECASE
    )
    for match in pattern.finditer(ocr_text):
        refs_str = match.group(1)
        for es_match in re.finditer(r'ES\s*(\d{4,8})', refs_str, re.IGNORECASE):
            results.append(es_match.group(0).replace(' ', ''))

    # Fallback
    if not results:
        fallback = re.compile(r'(?:linked|wp)\s+.*?(ES\s*\d{4,8})', re.IGNORECASE)
        for match in fallback.finditer(ocr_text):
            results.append(match.group(1).replace(' ', ''))

    return list(dict.fromkeys(results))


async def resolve_linked_wp_category(
    db: AsyncSession,
    ocr_text: str,
    filename: str = "",
) -> str | None:
    """
    Résout la catégorie d'un Work Order en cherchant son ES "Linked WP" en base.

    Retourne la catégorie trouvée ('Check A', 'Check C', 'Check D', ...)
    ou None si non résolu.

    Utilisation dans pipeline.py :
    ───────────────────────────────
    from backend.agents.linked_wp_resolver import resolve_linked_wp_category

    # Dans la fonction _process_document(), après _classify() :
    if result.doc_type == DocumentTypeEnum.WORK_ORDER:
        resolved_cat = await resolve_linked_wp_category(
            db, ocr_result.text, filename=filename
        )
        if resolved_cat:
            result.category = resolved_cat
            logger.info(f"[LinkedWP] {filename} → {resolved_cat}")
    """
    linked_refs = extract_linked_wp_es(ocr_text)
    if not linked_refs:
        logger.debug(f"[LinkedWP] {filename} — aucun Linked WP dans OCR")
        return None

    logger.info(f"[LinkedWP] {filename} — Linked WP trouvés : {linked_refs}")

    for ref in linked_refs:
        norm = normalize_es(ref)
        if not norm:
            continue

        # Chercher cet ES en base parmi les Work Orders avec catégorie connue
        # On cherche par la partie numérique normalisée (insensible aux zéros)
        row = (await db.execute(text("""
            SELECT category FROM documents
            WHERE doc_type = 'WORK_ORDER'
              AND category IN ('Check A', 'Check B', 'Check C', 'Check D')
              AND (
                -- Exact match avec préfixe ES variable
                es_reference ILIKE :ref
                -- Match sur la partie numérique (ignore zéros de padding)
                OR REGEXP_REPLACE(
                    LOWER(es_reference),
                    '^es\\s*0*', ''
                ) = :norm
              )
            LIMIT 1
        """), {"ref": f"%{norm}%", "norm": norm})
        ).fetchone()

        if row and row.category:
            logger.info(
                f"[LinkedWP] {filename} → {row.category} "
                f"(via Linked WP {ref})"
            )
            return row.category

    logger.info(f"[LinkedWP] {filename} — Linked WP {linked_refs} non trouvés en base")
    return None