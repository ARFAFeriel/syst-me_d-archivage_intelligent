# -*- coding: utf-8 -*-
import asyncio, sys
sys.path.insert(0, ".")
async def fix():
    from backend.database import engine
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE model_benchmarks SET status = 'deprecie' WHERE status = 'deprecated'"))
        await conn.execute(text("UPDATE model_benchmarks SET status = 'experimental' WHERE status = 'experimental'"))
        r = await conn.execute(text("SELECT model_name, status FROM model_benchmarks"))
        for row in r.fetchall():
            print(dict(row._mapping))
asyncio.run(fix())
