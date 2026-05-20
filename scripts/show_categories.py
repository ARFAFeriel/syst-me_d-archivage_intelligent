import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.database import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("""
            SELECT category, doc_type, COUNT(*) as n
            FROM documents
            GROUP BY category, doc_type
            ORDER BY category NULLS FIRST, n DESC
        """))
        current_cat = None
        for row in r.fetchall():
            cat, dtype, n = row
            label = cat if cat else "Sans catégorie"
            if label != current_cat:
                print(f"\n[{label}]")
                current_cat = label
            print(f"  {dtype} ({n})")

asyncio.run(main())