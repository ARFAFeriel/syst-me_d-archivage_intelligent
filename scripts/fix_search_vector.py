"""
scripts/fix_search_vector.py
Régénère le search_vector en normalisant le filename (remplace _ - . par espace)
pour que chart_R001 soit indexé comme 'chart' + 'r001' séparément.
"""
import asyncio, sys
from pathlib import Path
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.database import AsyncSessionLocal
from sqlalchemy import text


async def main():
    async with AsyncSessionLocal() as db:
        # Normaliser filename : _ - . → espace pour séparer les tokens
        r = await db.execute(text("""
            UPDATE documents
            SET search_vector = to_tsvector(
                'simple',
                regexp_replace(
                    coalesce(lower(filename), ''),
                    '[_\\-\\.&]', ' ', 'g'
                ) || ' ' ||
                coalesce(lower(aircraft_registration), '') || ' ' ||
                coalesce(lower(es_reference), '') || ' ' ||
                coalesce(lower(cast(doc_type as text)), '') || ' ' ||
                coalesce(lower(category), '') || ' ' ||
                coalesce(ocr_text, '')
            )
            WHERE filename ILIKE '%d&b%chart%'
               OR filename ILIKE '%chart_r%'
        """))
        await db.commit()
        logger.success(f"search_vector régénéré pour {r.rowcount} documents")

        # Vérification
        r2 = await db.execute(text("""
            SELECT COUNT(*) FROM documents
            WHERE search_vector @@ to_tsquery('simple', 'chart & r001')
        """))
        print(f"Test 'chart & r001': {r2.scalar()} résultats")

        r3 = await db.execute(text("""
            SELECT COUNT(*) FROM documents
            WHERE search_vector @@ to_tsquery('simple', 'r001')
        """))
        print(f"Test 'r001': {r3.scalar()} résultats")


if __name__ == "__main__":
    asyncio.run(main())