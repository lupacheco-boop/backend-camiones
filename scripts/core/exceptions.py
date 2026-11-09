"""Jerarquía de excepciones de dominio y manejadores globales de errores HTTP."""

from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from scripts.core.logger import LoggerManager

exc_logger = LoggerManager.get_logger("exceptions")


class FleetBaseException(Exception):
    """Excepción base de negocio para el sistema de gestión de flota."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_code: str = "FLEET_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}


class AuthenticationException(FleetBaseException):
    """Credenciales inválidas o sesión expirada (401 Unauthorized)."""

    def __init__(self, message: str = "Credenciales de autenticación inválidas.") -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="AUTH_UNAUTHORIZED",
        )


class StrictRBACForbiddenException(FleetBaseException):
    """Violación de política de acceso mutuamente excluyente entre WEB (ADMIN) y APP (DRIVER) (403 Forbidden)."""

    def __init__(
        self,
        message: str = (
            "Acceso denegado (403 Forbidden): Su rol no tiene permisos para acceder a esta "
            "plataforma o recurso. Sesión revocada por política de seguridad RBAC."
        ),
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="RBAC_STRICT_FORBIDDEN",
            details=details,
        )


class ResourceNotFoundException(FleetBaseException):
    """Entidad solicitada no existe en la base de datos (404 Not Found)."""

    def __init__(self, message: str = "El recurso solicitado no fue encontrado.") -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="RESOURCE_NOT_FOUND",
        )


class BusinessRuleViolationException(FleetBaseException):
    """Incumplimiento de una regla de negocio o integridad (422 / 400)."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_code: str = "BUSINESS_RULE_VIOLATION",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status_code,
            error_code=error_code,
            details=details,
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Registra manejadores globales en la instancia de FastAPI."""

    @app.exception_handler(FleetBaseException)
    async def fleet_exception_handler(
        request: Request, exc: FleetBaseException
    ) -> JSONResponse:
        exc_logger.warning(
            f"[{exc.error_code}] {request.method} {request.url.path} -> {exc.message}"
        )
        headers = {}
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(
            status_code=exc.status_code,
            headers=headers,
            content={
                "success": False,
                "error_code": exc.error_code,
                "detail": exc.message,
                "details": exc.details,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = []
        for err in exc.errors():
            loc = " -> ".join(str(part) for part in err.get("loc", []))
            errors.append({"field": loc, "message": err.get("msg", "Valor inválido")})
        exc_logger.warning(
            f"[VALIDATION_ERROR] {request.method} {request.url.path} -> {errors}"
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "error_code": "VALIDATION_ERROR",
                "detail": "Error de validación en los datos enviados.",
                "errors": errors,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        exc_logger.exception(
            f"[INTERNAL_ERROR] Excepción no controlada en {request.method} {request.url.path}: {exc}"
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error_code": "INTERNAL_SERVER_ERROR",
                "detail": "Error interno en el servidor. Consulte los registros de auditoría.",
            },
        )
