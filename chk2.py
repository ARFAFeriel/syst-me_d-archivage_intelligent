import asyncio, sys
sys.path.insert(0, '.')
async def check():
    from backend.database import engine
    from sqlalchemy import text
    async with engine.begin() as conn:
        r = await conn.execute(text('SELECT model_name, model_type, accuracy, f1_macro, status, notes FROM model_benchmarks ORDER BY accuracy DESC'))
        for row in r.fetchall():
            print(dict(row._mapping))
asyncio.run(check())
