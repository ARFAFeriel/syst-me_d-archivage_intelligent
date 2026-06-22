import asyncio, sys
sys.path.insert(0, ".")
async def run():
    from backend.database import engine
    from sqlalchemy import text
    async with engine.begin() as conn:
        r = await conn.execute(text("""
            SELECT doc_type, ata_chapter, aircraft_registration,
                   COUNT(*) as nb
            FROM documents
            WHERE status = 'ARCHIVED'
              AND ata_chapter IS NOT NULL
            GROUP BY doc_type, ata_chapter, aircraft_registration
            ORDER BY nb DESC
            LIMIT 20
        """))
        for row in r.fetchall():
            print(dict(row._mapping))
asyncio.run(run())
