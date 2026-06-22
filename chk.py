import asyncio, sys
sys.path.insert(0, '.')
async def check():
    from backend.database import engine
    from sqlalchemy import text
    async with engine.begin() as conn:
        r = await conn.execute(text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'model_benchmarks')"))
        exists = r.scalar()
        print('Table existe:', exists)
        if exists:
            r2 = await conn.execute(text('SELECT COUNT(*) FROM model_benchmarks'))
            print('Lignes:', r2.scalar())
asyncio.run(check())
