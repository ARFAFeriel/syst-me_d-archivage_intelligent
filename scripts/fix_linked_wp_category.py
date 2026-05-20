"""
fix_linked_wp_category.py
─────────────────────────
Corrige la catégorie des Work Orders en lisant le champ "Linked WP"
dans le texte OCR, puis en cherchant la catégorie de cet ES parent
dans la base de données.

Logique métier :
  Work Order ES152410 (titre page 1)
    └── Linked WP : ES XXXXX  ← cet ES détermine le type de check
          ├── ES parent = Check A → ce WO est Check A
          ├── ES parent = Check C → ce WO est Check C
          └── ES parent = Check D → ce WO est Check D

Usage :
  py fix_linked_wp_category.py              # dry-run (affiche sans modifier)
  py fix_linked_wp_category.py --apply      # applique les corrections
  py fix_linked_wp_category.py --apply --id 3828  # un seul document
"""

import asyncio
import re
import sys
import argparse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text

# ── Config DB ─────────────────────────────────────────────────────────────────
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5434/nouv_db"

# ── Normalisation ES reference ────────────────────────────────────────────────
def normalize_es(ref: str) -> str:
    """
    Normalise une référence ES pour comparaison insensible aux zéros et préfixes.
    ES00001778 → 1778
    ES001392   → 1392
    152410     → 152410
    00203601   → 203601
    """
    if not ref:
        return ""
    # Supprimer préfixe ES (insensible à la casse) puis zéros
    cleaned = re.sub(r'^ES\s*', '', ref.strip(), flags=re.IGNORECASE)
    cleaned = cleaned.lstrip('0') or '0'
    return cleaned


def extract_linked_wp_es(ocr_text: str) -> list[str]:
    """
    Extrait les références ES depuis le champ "Linked WP" du texte OCR.
    Patterns reconnus :
      - "linked wp     ES001234     MSN2158"
      - "LINKED WP : ES 001234"
      - "Linked WP ES001234 / ES005678"
      - "wp linked ES152410"
    Retourne une liste de références ES normalisées.
    """
    if not ocr_text:
        return []

    results = []

    # Pattern principal : "linked wp" suivi d'une ou plusieurs refs ES
    pattern = re.compile(
        r'(?:linked\s+wp|wp\s+linked)\s*[:\-]?\s*((?:ES\s*\d{4,8}\s*[/,]?\s*)+)',
        re.IGNORECASE
    )
    for match in pattern.finditer(ocr_text):
        refs_str = match.group(1)
        # Extraire chaque ES individuellement
        for es_match in re.finditer(r'ES\s*(\d{4,8})', refs_str, re.IGNORECASE):
            results.append(es_match.group(0).replace(' ', ''))

    # Fallback : chercher "ES XXXXX MSN" (format NouvelAir courant)
    if not results:
        fallback = re.compile(
            r'(?:linked|wp)\s+.*?(ES\s*\d{4,8})',
            re.IGNORECASE
        )
        for match in fallback.finditer(ocr_text):
            results.append(match.group(1).replace(' ', ''))

    return list(dict.fromkeys(results))  # dédupliquer


async def fix_categories(apply: bool, doc_id: int | None):
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # ── Charger les Work Orders à corriger ────────────────────────────────
        stmt = text("""
            SELECT id, filename, es_reference, category, ocr_text
            FROM documents
            WHERE doc_type = 'WORK_ORDER'
              AND status = 'ARCHIVED'
              AND ocr_text IS NOT NULL
              AND ocr_text ILIKE '%linked%wp%'
        """ + (" AND id = :doc_id" if doc_id else ""))

        params = {"doc_id": doc_id} if doc_id else {}
        rows = (await db.execute(stmt, params)).fetchall()
        print(f"\n[Fix] {len(rows)} Work Orders avec 'linked wp' trouvés\n")

        # ── Charger le mapping ES_norm → category depuis la base ─────────────
        # On charge tous les docs qui ont une catégorie connue pour faire
        # le lookup local (évite N+1 queries)
        es_map_rows = (await db.execute(text("""
            SELECT es_reference, category FROM documents
            WHERE es_reference IS NOT NULL
              AND category IN ('Check A', 'Check C', 'Check D', 'Check B')
              AND doc_type = 'WORK_ORDER'
        """))).fetchall()

        # Construire le mapping norm → category
        es_category_map: dict[str, str] = {}
        for r in es_map_rows:
            norm = normalize_es(r.es_reference)
            if norm and r.category:
                es_category_map[norm] = r.category

        print(f"[Fix] {len(es_category_map)} ES references chargées pour lookup\n")

        # ── Traiter chaque Work Order ─────────────────────────────────────────
        corrections = []
        no_match = []

        for row in rows:
            linked_refs = extract_linked_wp_es(row.ocr_text or "")
            if not linked_refs:
                no_match.append((row.id, row.filename, "Aucun Linked WP trouvé dans OCR"))
                continue

            new_category = None
            matched_ref = None
            for ref in linked_refs:
                norm = normalize_es(ref)
                if norm in es_category_map:
                    new_category = es_category_map[norm]
                    matched_ref = ref
                    break

            if not new_category:
                no_match.append((
                    row.id, row.filename,
                    f"Linked WP {linked_refs} non trouvé en base"
                ))
                continue

            if new_category == row.category:
                print(f"  ✓ {row.filename:30s} → {new_category} (déjà correct)")
                continue

            corrections.append({
                "id": row.id,
                "filename": row.filename,
                "old_category": row.category,
                "new_category": new_category,
                "linked_ref": matched_ref,
            })

        # ── Afficher les corrections ──────────────────────────────────────────
        print(f"\n{'─'*65}")
        print(f"  CORRECTIONS DÉTECTÉES : {len(corrections)}")
        print(f"{'─'*65}")
        for c in corrections:
            flag = "→ APPLY" if apply else "→ DRY RUN"
            print(
                f"  [{c['id']:5d}] {c['filename']:25s} "
                f"{c['old_category']:12s} → {c['new_category']:12s} "
                f"(via {c['linked_ref']}) {flag}"
            )

        if no_match:
            print(f"\n  SANS CORRESPONDANCE : {len(no_match)}")
            for doc_id_nm, fname, reason in no_match[:20]:
                print(f"  [{doc_id_nm:5d}] {fname:25s} — {reason}")
            if len(no_match) > 20:
                print(f"  ... et {len(no_match)-20} autres")

        # ── Appliquer si --apply ──────────────────────────────────────────────
        if apply and corrections:
            print(f"\n[Fix] Application de {len(corrections)} corrections...")
            for c in corrections:
                await db.execute(
                    text("UPDATE documents SET category = :cat WHERE id = :id"),
                    {"cat": c["new_category"], "id": c["id"]}
                )
            await db.commit()
            print(f"[Fix] ✅ {len(corrections)} documents mis à jour.")
        elif not apply:
            print(f"\n[Fix] Mode dry-run — relance avec --apply pour appliquer.")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix Work Order categories via Linked WP")
    parser.add_argument("--apply", action="store_true", help="Appliquer les corrections")
    parser.add_argument("--id", type=int, default=None, help="Traiter un seul document")
    args = parser.parse_args()

    asyncio.run(fix_categories(apply=args.apply, doc_id=args.id))