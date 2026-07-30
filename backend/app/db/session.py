from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(settings: Settings) -> None:
    global _engine, _session_factory
    # Supabase's pooled connection runs pgbouncer in transaction mode, which is
    # incompatible with asyncpg's server-side prepared statement cache.
    _engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        # pgbouncer (transaction mode) can silently drop idle connections
        # server-side without the client knowing — pool_pre_ping catches most
        # of that, but not every case. Recycling connections well before any
        # realistic idle-close window is cheap insurance against a
        # long-running process holding a connection the pooler has already
        # killed, which is exactly the kind of failure that would hang or
        # silently fail with nothing useful logged.
        pool_recycle=300,
        connect_args={"statement_cache_size": 0},
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def dispose_engine() -> None:
    if _engine is not None:
        await _engine.dispose()


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database engine not initialized — call init_engine() first")
    async with _session_factory() as session:
        yield session
