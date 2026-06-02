"""
Connexion base de données
SQLAlchemy 2.0 async · asyncpg · PostgreSQL 16 + pgvector
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from loguru import logger
from backend.config import settings


# ── Engine async ──────────────────────────────────────────────────────────────
import os
import ssl

_db_url = settings.database_url
_connect_args = {}
if "neon.tech" in _db_url:
    _ssl_ctx = ssl.create_default_context()
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode = ssl.CERT_NONE
    _connect_args = {"ssl": _ssl_ctx}

engine = create_async_engine(
    _db_url,
    echo=settings.debug,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args=_connect_args,
)


AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# ── Base declarative ──────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Dependency FastAPI ────────────────────────────────────────────────────────
async def get_db() -> AsyncSession:
    """Dependency injection: session DB async par requête."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Initialisation extensions PostgreSQL ─────────────────────────────────────
async def init_extensions():
    """Active les extensions PostgreSQL nécessaires."""
    async with engine.begin() as conn:
        extensions = [
            "CREATE EXTENSION IF NOT EXISTS vector",
            "CREATE EXTENSION IF NOT EXISTS pg_trgm",
            "CREATE EXTENSION IF NOT EXISTS unaccent",
        ]
        for ext in extensions:
            try:
                await conn.execute(text(ext))
                logger.info(f"Extension activée: {ext.split()[-1]}")
            except Exception as e:
                logger.warning(f"Extension ignorée ({ext.split()[-1]}): {e}")


async def create_tables():
    """Crée toutes les tables si elles n'existent pas."""
    from backend.models import aircraft, document, check  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tables créées avec succès")


async def init_db():
    """Initialisation complète de la base de données."""
    logger.info("Initialisation de la base de données nouv...")
    await init_extensions()
    await create_tables()
    logger.info("Base de données prête.")
