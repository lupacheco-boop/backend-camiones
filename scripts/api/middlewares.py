"""Middlewares HTTP para compatibilidad con túneles Ngrok, CORS y auditoría de tiempos."""

from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from scripts.core.logger import LoggerManager

mw_logger = LoggerManager.get_logger("middleware")


class NgrokAndAuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware encargado de:
    1. Aceptar y propagar la cabecera `ngrok-skip-browser-warning: true` para evitar
       la pantalla intersticial de advertencia de Ngrok en clientes Web (Vercel) y App Móvil (4G/5G).
    2. Medir el tiempo de respuesta de cada endpoint y registrarlo en `logs/app.log`.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # Cabeceras de soporte para Ngrok y trazabilidad
        response.headers["ngrok-skip-browser-warning"] = "true"
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"

        mw_logger.info(
            f"{request.method} {request.url.path} -> HTTP {response.status_code} ({elapsed_ms:.2f} ms)"
        )
        return response
