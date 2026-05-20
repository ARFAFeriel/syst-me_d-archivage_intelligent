import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.database import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as db:
        # Tokens du filename
        r = await db.execute(text(
            "SELECT to_tsvector('simple', 'TS-INP_D&B chart_R001.pdf')::text"
        ))
        print("Tokens filename:", r.scalar())

        # Est-ce que chart est dans le vecteur du doc 747 ?
        r2 = await db.execute(text(
            "SELECT search_vector @@ to_tsquery('simple', 'chart') FROM documents WHERE id = 747"
        ))
        print("has 'chart':", r2.scalar())

        # Est-ce que r001 est dans le vecteur ?
        r3 = await db.execute(text(
            "SELECT search_vector @@ to_tsquery('simple', 'r001') FROM documents WHERE id = 747"
        ))
        print("has 'r001':", r3.scalar())

asyncio.run(main())