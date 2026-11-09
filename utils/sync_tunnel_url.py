"""
Script utilitario para registrar y consultar en Supabase PostgreSQL (`system_config`)
la URL pública activa del túnel Cloudflare / Ngrok.
Permite que el Frontend en Vercel descubra dinámicamente la URL del Backend
sin depender de variables de entorno estáticas.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Asegurar que el directorio raíz esté en sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import text
from scripts.core.logger import LoggerManager
from scripts.database.session import db_manager

sync_logger = LoggerManager.get_logger("sync_tunnel")

CONFIG_KEY = "URL_BACKEND_ACTIVA"


async def ensure_table_and_upsert(url: str) -> str:
    """Crea la tabla `system_config` si no existe y actualiza la URL activa del backend."""
    cleaned_url = url.strip().rstrip("/")
    async for session in db_manager.get_session():
        await session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS public.system_config (
                    "CLAVE" VARCHAR(100) PRIMARY KEY,
                    "VALOR" TEXT NOT NULL,
                    "ACTUALIZADO_EN" TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        )
        await session.execute(
            text(
                """
                INSERT INTO public.system_config ("CLAVE", "VALOR", "ACTUALIZADO_EN")
                VALUES (:key, :val, NOW())
                ON CONFLICT ("CLAVE")
                DO UPDATE SET
                    "VALOR" = EXCLUDED."VALOR",
                    "ACTUALIZADO_EN" = NOW();
                """
            ),
            {"key": CONFIG_KEY, "val": cleaned_url},
        )
        await session.commit()
        sync_logger.info(f"URL de túnel sincronizada en Supabase (system_config): {cleaned_url}")
        break
    await db_manager.close()
    return cleaned_url


async def get_active_url() -> str | None:
    """Obtiene la URL pública activa almacenada en Supabase."""
    result_url: str | None = None
    async for session in db_manager.get_session():
        await session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS public.system_config (
                    "CLAVE" VARCHAR(100) PRIMARY KEY,
                    "VALOR" TEXT NOT NULL,
                    "ACTUALIZADO_EN" TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        )
        res = await session.execute(
            text('SELECT "VALOR" FROM public.system_config WHERE "CLAVE" = :key LIMIT 1'),
            {"key": CONFIG_KEY},
        )
        result_url = res.scalar()
        break
    await db_manager.close()
    return result_url


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sincroniza o consulta la URL pública del túnel en Supabase PostgreSQL."
    )
    parser.add_argument(
        "url",
        nargs="?",
        default=None,
        help="URL pública HTTPS del túnel (ej. https://xxxx.trycloudflare.com)",
    )
    parser.add_argument(
        "--get",
        action="store_true",
        help="Consulta e imprime la URL activa almacenada en Supabase.",
    )
    args = parser.parse_args()

    if args.get:
        current = asyncio.run(get_active_url())
        if current:
            print(current)
            sys.exit(0)
        sys.exit(1)

    if not args.url:
        print("[ERROR] Debe proporcionar una URL o usar --get", file=sys.stderr)
        sys.exit(1)

    saved = asyncio.run(ensure_table_and_upsert(args.url))
    print(f"[OK] Sincronizado en Supabase (system_config): {saved}")


if __name__ == "__main__":
    main()
