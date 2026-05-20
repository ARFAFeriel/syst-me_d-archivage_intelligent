"""
scripts/fix_db_charts.py
1. Ajoute 'D&B Chart' au type ENUM PostgreSQL
2. Corrige les 108 documents D&B Chart mal classifiés
"""
import asyncio, sys
from pathlib import Path
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.database import AsyncSessionLocal
from sqlalchemy import text


async def main():
    async with AsyncSessionLocal() as db:

        # ── 1. Ajouter la valeur au type ENUM PostgreSQL ──────────────────────
        await db.execute(text(
            "ALTER TYPE documenttype ADD VALUE IF NOT EXISTS 'D&B Chart'"
        ))
        await db.commit()
        logger.info("Enum documenttype mis à jour : 'D&B Chart' ajouté")

        # ── 2. Corriger les documents via SQL direct ──────────────────────────
        result = await db.execute(text("""
            UPDATE documents
            SET doc_type          = 'D&B Chart',
                category          = 'Structural_Repair',
                manually_corrected = TRUE,
                updated_at         = NOW()
            WHERE filename ILIKE :p1
               OR filename ILIKE :p2
               OR filename ILIKE :p3
        """), {"p1": "%d&b%chart%", "p2": "%dent%buckle%", "p3": "%chart_r0%"})
        await db.commit()
        logger.success(f"{result.rowcount} documents corrigés → D&B Chart / Structural_Repair")


if __name__ == "__main__":
    asyncio.run(main())