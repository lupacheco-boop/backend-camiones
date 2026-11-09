"""Configuración centralizada y tipada mediante Pydantic Settings v2."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class AppSettings(BaseSettings):
    """Parámetros de configuración global cargados desde el archivo .env."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Metadatos de aplicación
    APP_NAME: str = Field(
        default="Sistema de Monitoreo y Mantenimiento Preventivo de Flota (27 Camiones)"
    )
    APP_VERSION: str = Field(default="1.0.0")
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=True)
    API_PREFIX: str = Field(default="")

    # Base de datos relacional (Supabase PostgreSQL Transaction Pooler - Puerto 6543)
    DATABASE_URL: str = Field(
        ...,
        description="Cadena de conexión asíncrona a Supabase PostgreSQL",
    )

    # Seguridad y Tokens JWT (HS256)
    JWT_SECRET_KEY: str = Field(
        ...,
        description="Llave secreta para firma criptográfica de tokens JWT",
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=720)  # 12 horas por turno

    # Servidor y CORS / Ngrok
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    CORS_ORIGINS: str = Field(default="*")

    @property
    def async_database_url(self) -> str:
        """Retorna la URL asíncrona para SQLAlchemy + asyncpg."""
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def cors_origins_list(self) -> List[str]:
        """Convierte la cadena de orígenes CORS en una lista."""
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> AppSettings:
    """Retorna una instancia singleton en caché de la configuración."""
    return AppSettings()


settings = get_settings()
