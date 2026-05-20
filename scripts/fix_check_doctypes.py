import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.database import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as db:
        # Compter
        r = await db.execute(text("""
            SELECT
                SUM(CASE WHEN filename ILIKE '%EAD%' THEN 1 ELSE 0 END) as ead_count,
                SUM(CASE WHEN filename ILIKE '%ADSB%' THEN 1 ELSE 0 END) as adsb_count,
                SUM(CASE WHEN filename ILIKE '%SB%' AND filename NOT ILIKE '%ADSB%' AND filename NOT ILIKE '%EAD%' THEN 1 ELSE 0 END) as sb_count
            FROM documents
            WHERE category IN ('Check A', 'Check C', 'Check D')
            AND doc_type = 'SPECS'
            AND (filename ILIKE '%EAD%' OR filename ILIKE '%ADSB%' OR filename ILIKE '%SB%')
        """))
        row = r.fetchone()
        print(f"EAD → AD  : {row[0]} documents")
        print(f"ADSB → SB : {row[1]} documents")
        print(f"SB → SB   : {row[2]} documents")

        # Corriger EAD → AD
        r1 = await db.execute(text("""
            UPDATE documents
            SET doc_type = 'AD', manually_corrected = TRUE, updated_at = NOW()
            WHERE category IN ('Check A', 'Check C', 'Check D')
            AND doc_type = 'SPECS'
            AND filename ILIKE '%EAD%'
        """))

        # Corriger ADSB → SB
        r2 = await db.execute(text("""
            UPDATE documents
            SET doc_type = 'SB', manually_corrected = TRUE, updated_at = NOW()
            WHERE category IN ('Check A', 'Check C', 'Check D')
            AND doc_type = 'SPECS'
            AND filename ILIKE '%ADSB%'
        """))

        # Corriger SB... → SB
        r3 = await db.execute(text("""
            UPDATE documents
            SET doc_type = 'SB', manually_corrected = TRUE, updated_at = NOW()
            WHERE category IN ('Check A', 'Check C', 'Check D')
            AND doc_type = 'SPECS'
            AND filename ILIKE 'SB%'
        """))

        await db.commit()
        print(f"\nCorrigés:")
        print(f"  EAD → AD  : {r1.rowcount}")
        print(f"  ADSB → SB : {r2.rowcount}")
        print(f"  SB → SB   : {r3.rowcount}")

asyncio.run(main())