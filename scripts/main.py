"""
Punto de entrada principal del servidor FastAPI bajo arquitectura POO.
Configura ciclo de vida (lifespan), CORS permisivo para desarrollo con Ngrok,
middlewares de auditoría y montaje de routers en `/api/v1`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.api.middlewares import NgrokAndAuditMiddleware
from scripts.api.routers.admin_router import admin_router
from scripts.api.routers.auth_router import auth_router
from scripts.api.routers.driver_router import driver_router
from scripts.core.config import settings
from scripts.core.exceptions import register_exception_handlers
from scripts.core.logger import LoggerManager
from scripts.database.session import db_manager, get_db_session

app_logger = LoggerManager.get_logger("main")


class FleetBackendServer:
    """Clase principal POO que construye y configura la aplicación ASGI FastAPI."""

    def __init__(self) -> None:
        LoggerManager.setup_logging()
        self.app = FastAPI(
            title=settings.APP_NAME,
            version=settings.APP_VERSION,
            debug=settings.DEBUG,
            description=(
                "API Backend Asíncrona para el Monitoreo de Kilometraje y Gestión de "
                "Mantenimiento Preventivo de una Flota de 27 Camiones.\n\n"
                "**Política de Acceso RBAC Estricta:**\n"
                "- **Plataforma Web (`/api/v1/admin`)**: Exclusivo para rol `ADMIN`.\n"
                "- **Aplicación Móvil (`/api/v1/driver`)**: Exclusivo para rol `DRIVER`.\n"
                "- Intentos de acceso cruzado se rechazan de inmediato con `403 Forbidden`."
            ),
            docs_url="/docs",
            redoc_url="/redoc",
            openapi_url="/openapi.json",
            lifespan=self._lifespan,
        )
        self._configure_middlewares()
        self._configure_exception_handlers()
        self._configure_routes()

    @staticmethod
    @asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        app_logger.info(
            f"Iniciando {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENVIRONMENT}]"
        )
        yield
        await db_manager.close()
        app_logger.info("Servidor FastAPI detenido limpiamente.")

    def _configure_middlewares(self) -> None:
        # Middleware de auditoría y soporte para túneles Ngrok
        self.app.add_middleware(NgrokAndAuditMiddleware)

        # Middleware CORS permisivo para desarrollo con Vercel, móvil 4G/5G y túneles Ngrok
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=[
                "*",
                "Authorization",
                "Content-Type",
                "X-Client-Type",
                "ngrok-skip-browser-warning",
            ],
            expose_headers=[
                "X-Process-Time-Ms",
                "ngrok-skip-browser-warning",
            ],
        )

    def _configure_exception_handlers(self) -> None:
        register_exception_handlers(self.app)

    def _configure_routes(self) -> None:
        @self.app.get(
            "/health",
            tags=["Health & Status"],
            summary="Estado de salud del servidor y metadatos de la API",
        )
        async def root_health() -> Dict[str, Any]:
            return {
                "status": "online",
                "service": settings.APP_NAME,
                "version": settings.APP_VERSION,
                "docs_url": "/docs",
                "rbac_policy": "STRICT_MUTUALLY_EXCLUSIVE (WEB=ADMIN, APP=DRIVER)",
            }

        @self.app.get(
            "/system/tunnel-url",
            tags=["Health & Status"],
            summary="Obtiene la URL pública activa del túnel desde Supabase (system_config)",
        )
        async def get_tunnel_url(
            session: AsyncSession = Depends(get_db_session),
        ) -> Dict[str, Any]:
            res = await session.execute(
                text(
                    'SELECT "VALOR", "ACTUALIZADO_EN" FROM public.system_config WHERE "CLAVE" = \'URL_BACKEND_ACTIVA\' LIMIT 1'
                )
            )
            row = res.first()
            if row and row[0]:
                return {
                    "success": True,
                    "backend_url": row[0],
                    "updated_at": row[1].isoformat() if row[1] else None,
                }
            return {
                "success": False,
                "backend_url": None,
            }

        self.app.include_router(auth_router, prefix=settings.API_PREFIX)
        self.app.include_router(driver_router, prefix=settings.API_PREFIX)
        self.app.include_router(admin_router, prefix=settings.API_PREFIX)

        # Compatibilidad dual con clientes que utilicen prefijo /api/v1 (ej. Flutter app)
        if settings.API_PREFIX != "/api/v1":
            self.app.include_router(auth_router, prefix="/api/v1", include_in_schema=False)
            self.app.include_router(driver_router, prefix="/api/v1", include_in_schema=False)
            self.app.include_router(admin_router, prefix="/api/v1", include_in_schema=False)


server_instance = FleetBackendServer()
app = server_instance.app
