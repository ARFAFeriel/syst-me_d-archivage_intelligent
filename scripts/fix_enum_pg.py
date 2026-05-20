"""
scripts/fix_enum_pg.py
Recrée proprement l'enum PostgreSQL documenttype avec D&B Chart inclus,
en utilisant une migration SQL directe sans passer par SQLAlchemy ORM.
"""
import asyncio, sys
from pathlib import Path
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.database import AsyncSessionLocal
from sqlalchemy import text


async def main():
    async with AsyncSessionLocal() as db:
        # Vérifier les valeurs actuelles de l'enum
        r = await db.execute(text("""
            SELECT enumlabel FROM pg_enum 
            JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
            WHERE pg_type.typname = 'documenttype'
            ORDER BY enumsortorder
        """))
        values = [row[0] for row in r.fetchall()]
        logger.info(f"Valeurs actuelles de l'enum: {values}")

        if 'D&B Chart' in values:
            logger.success("'D&B Chart' déjà présent dans l'enum PostgreSQL")
        else:
            # Ajouter la valeur
            await db.execute(text(
                "ALTER TYPE documenttype ADD VALUE IF NOT EXISTS 'D&B Chart'"
            ))
            await db.commit()
            logger.success("'D&B Chart' ajouté à l'enum PostgreSQL")

        # Vérifier après
        r2 = await db.execute(text("""
            SELECT enumlabel FROM pg_enum 
            JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
            WHERE pg_type.typname = 'documenttype'
            ORDER BY enumsortorder
        """))
        values2 = [row[0] for row in r2.fetchall()]
        logger.info(f"Valeurs après: {values2}")

        # Compter les D&B Chart en base
        r3 = await db.execute(text(
            "SELECT COUNT(*) FROM documents WHERE doc_type = 'D&B Chart'"
        ))
        print(f"Documents D&B Chart en base: {r3.scalar()}")


if __name__ == "__main__":
    asyncio.run(main())