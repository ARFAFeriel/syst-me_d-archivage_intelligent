import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.database import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("""
            SELECT id, aircraft_registration, filename, category, doc_type
            FROM documents
            WHERE aircraft_registration NOT IN ('TS-INP', 'TS-INQ')
            ORDER BY aircraft_registration, filename
        """))
        for row in r.fetchall():
            print(f"#{row[0]} [{row[1]}] {row[4]} / {row[3]}")
            print(f"  {row[2]}")

asyncio.run(main())