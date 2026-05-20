"""
scripts/fix_db_chart_name.py
Corrige le stockage de D&B Chart :
- Ajoute 'DB_CHART' comme label PostgreSQL enum (le nom, pas la valeur)
- Met à jour les 106 documents pour utiliser 'DB_CHART' au lieu de 'D&B Chart'
"""
import asyncio, sys
from pathlib import Path
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.database import AsyncSessionLocal
from sqlalchemy import text


async def main():
    async with AsyncSessionLocal() as db:

        # 1. Ajouter le bon label enum (nom Python = DB_CHART)
        await db.execute(text(
            "ALTER TYPE documenttype ADD VALUE IF NOT EXISTS 'DB_CHART'"
        ))
        await db.commit()
        logger.info("Label 'DB_CHART' ajouté à l'enum PostgreSQL")

        # 2. Mettre à jour les documents : 'D&B Chart' → 'DB_CHART'
        r = await db.execute(text("""
            UPDATE documents
            SET doc_type = 'DB_CHART'::documenttype,
                updated_at = NOW()
            WHERE doc_type = 'D&B Chart'::documenttype
        """))
        await db.commit()
        logger.success(f"{r.rowcount} documents mis à jour : D&B Chart → DB_CHART")

        # 3. Vérification
        r2 = await db.execute(text(
            "SELECT COUNT(*) FROM documents WHERE doc_type = 'DB_CHART'"
        ))
        print(f"Documents DB_CHART en base: {r2.scalar()}")

        r3 = await db.execute(text(
            "SELECT COUNT(*) FROM documents WHERE doc_type = 'D&B Chart'"
        ))
        print(f"Documents D&B Chart restants: {r3.scalar()}")


if __name__ == "__main__":
    asyncio.run(main())