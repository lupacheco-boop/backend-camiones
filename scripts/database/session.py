"""Configuración del motor asíncrono SQLAlchemy 2.0 optimizado para Supabase Transaction Pooler (Puerto 6543)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import uuid4

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import AsyncAdaptedQueuePool

from scripts.core.config import settings
from scripts.core.logger import LoggerManager

db_logger = LoggerManager.get_logger("database")


class Base(DeclarativeBase):
    """Clase base declarativa de SQLAlchemy 2.0 para todas las entidades del dominio."""

    pass


class DatabaseSessionManager:
    """Gestor POO del ciclo de vida de conexiones asíncronas a PostgreSQL/Supabase."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        # Configuración optimizada para Supavisor / PgBouncer en modo Transaction Pooling (puerto 6543):
        # statement_cache_size=0 evita errores DuplicatePreparedStatementError en conexiones compartidas.
        self.engine: AsyncEngine = create_async_engine(
            self._database_url,
            echo=False,
            poolclass=AsyncAdaptedQueuePool,
            pool_size=10,
            max_overflow=10,
            pool_pre_ping=False,
            pool_recycle=1800,
            connect_args={
                "statement_cache_size": 0,
                "prepared_statement_cache_size": 0,
                "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
                "command_timeout": 45,
            },
        )
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Generador de dependencia FastAPI que provee una sesión transaccional por petición."""
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def close(self) -> None:
        """Cierra ordenadamente el pool de conexiones del motor asíncrono."""
        await self.engine.dispose()
        db_logger.info("Motor asíncrono de base de datos cerrado correctamente.")


db_manager = DatabaseSessionManager(settings.async_database_url)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependencia inyectable en rutas de FastAPI para obtener `AsyncSession`."""
    async for session in db_manager.get_session():
        yield session
