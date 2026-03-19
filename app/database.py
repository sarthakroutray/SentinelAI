"""Async SQLAlchemy engine & session factory (Supabase PostgreSQL)."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def _db_connect_args() -> dict[str, bool]:
    """Enable SSL for managed providers like Supabase, disable for local Docker DB."""
    if "supabase.co" in settings.DATABASE_URL:
        return {"ssl": True}
    return {"ssl": False}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
    connect_args=_db_connect_args(),
)

async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


async def get_session() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency – yields an async DB session."""
    async with async_session() as session:
        yield session
