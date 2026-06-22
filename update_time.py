import asyncio, sys
sys.path.insert(0, '.')
from sqlalchemy import text
from backend.database import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        await session.execute(text('ALTER TABLE model_benchmarks ADD COLUMN IF NOT EXISTS train_time_minutes FLOAT'))
        await session.execute(text('UPDATE model_benchmarks SET train_time_minutes = 0.02 WHERE id = 1'))
        await session.execute(text('UPDATE model_benchmarks SET train_time_minutes = 180 WHERE id = 2'))
        await session.execute(text('UPDATE model_benchmarks SET train_time_minutes = 480 WHERE id = 3'))
        await session.execute(text('UPDATE model_benchmarks SET train_time_minutes = 0.017 WHERE id = 5'))
        await session.commit()
        print('OK')

asyncio.run(main())
