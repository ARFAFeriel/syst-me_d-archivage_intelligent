import asyncio
import asyncpg
from sentence_transformers import SentenceTransformer


async def check():
    model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
    query = 'ordre de travail ES156802 ATA 05 TS-INO'
    vec = model.encode(query).tolist()
    vec_str = '[' + ','.join(str(x) for x in vec) + ']'

    conn = await asyncpg.connect(
        host='localhost', port=5434, database='nouv_db',
        user='postgres', password='Nouv26',
    )

    row = await conn.fetchrow(
        "SELECT id, 1 - (embedding <=> CAST($1 AS vector)) as sim "
        "FROM documents WHERE id = 3997",
        vec_str,
    )
    print('Similarite avec le document cible (id=3997):', dict(row))

    rows = await conn.fetch(
        "SELECT id, filename, 1 - (embedding <=> CAST($1 AS vector)) as sim "
        "FROM documents WHERE embedding IS NOT NULL "
        "ORDER BY embedding <=> CAST($1 AS vector) LIMIT 5",
        vec_str,
    )
    print()
    print('Top 5 documents les plus proches semantiquement (sans filtre):')
    for r in rows:
        print(dict(r))

    await conn.close()


asyncio.run(check())