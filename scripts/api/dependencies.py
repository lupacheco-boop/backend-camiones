"""Dependencias de inyección de sesión y guardias RBAC mutuamente excluyentes (ADMIN vs CONDUCTOR)."""

from __future__ import annotations

import time
from typing import Dict, Optional, Tuple
from uuid import UUID

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.core.exceptions import (
    AuthenticationException,
    StrictRBACForbiddenException,
)
from scripts.core.logger import LoggerManager
from scripts.core.security import SecurityManager
from scripts.database.session import get_db_session
from scripts.models.entities import User, UserRole
from scripts.services.auth_service import AuthService

rbac_logger = LoggerManager.get_logger("rbac_guard")

bearer_scheme = HTTPBearer(auto_error=False)

# Caché en memoria para validación rápida de usuarios autenticados (reduce latencia a Supabase)
_USER_AUTH_CACHE: Dict[UUID, Tuple[User, float]] = {}
_USER_AUTH_CACHE_TTL_SECONDS = 60.0


class RBACAccessGuard:
    """
    Guardia POO de control de acceso basado en roles (RBAC) con validación de plataforma.
    Aplica la regla de seguridad estricta:
    - Si un usuario con rol `CONDUCTOR` intenta consumir endpoints de la plataforma web (`/admin`)
      o envía `X-Client-Type: WEB`, rechaza de inmediato con `403 Forbidden`.
    - Si un usuario con rol `ADMIN` intenta consumir endpoints de la app móvil (`/driver`)
      o envía `X-Client-Type: APP`, rechaza de inmediato con `403 Forbidden`.
    """

    def __init__(self, required_role: Optional[UserRole] = None) -> None:
        self.required_role = required_role

    async def __call__(
        self,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
        x_client_type: Optional[str] = Header(
            default=None,
            alias="X-Client-Type",
            description="Plataforma cliente opcional ('WEB' o 'APP') para validación cruzada RBAC.",
        ),
        session: AsyncSession = Depends(get_db_session),
    ) -> User:
        if not credentials or not credentials.credentials:
            raise AuthenticationException(
                "No se proporcionó un Bearer Token de autenticación válido."
            )

        payload = SecurityManager.decode_access_token(credentials.credentials)
        try:
            user_id = UUID(str(payload["sub"]))
        except ValueError as exc:
            raise AuthenticationException("Identificador de usuario en token inválido.") from exc

        token_role = str(payload.get("role", "")).upper()
        token_client_type = payload.get("client_type")

        now = time.time()
        cached_entry = _USER_AUTH_CACHE.get(user_id)
        if cached_entry and (now - cached_entry[1]) < _USER_AUTH_CACHE_TTL_SECONDS:
            user = cached_entry[0]
        else:
            auth_service = AuthService(session)
            user = await auth_service.get_user_by_id(user_id)
            _USER_AUTH_CACHE[user_id] = (user, now)

        # Validar consistencia entre el rol en BD y el rol del JWT
        if user.role.upper() != token_role:
            rbac_logger.error(
                f"Discrepancia de rol en token para usuario {user.identifier}. Sesión revocada."
            )
            raise StrictRBACForbiddenException(
                "Los privilegios de su sesión han cambiado. Sesión revocada."
            )

        # Si el cliente envía cabecera X-Client-Type, validar que coincida con su rol
        if x_client_type:
            SecurityManager.validate_client_role_exclusivity(
                user_role=user.role,
                client_type=x_client_type,
            )

        # Validar también el client_type embebido en el JWT cuando fue emitido
        if token_client_type:
            SecurityManager.validate_client_role_exclusivity(
                user_role=user.role,
                client_type=str(token_client_type),
            )

        # Validar rol requerido por el módulo de endpoints (/admin vs /driver)
        if self.required_role is not None and user.role != self.required_role.value:
            attempted_module = (
                "Plataforma Web Administrativa (/admin)"
                if self.required_role == UserRole.ADMIN
                else "Aplicación Móvil de Conductores (/driver)"
            )
            rbac_logger.error(
                f"ACCESO PROHIBIDO (403): Usuario '{user.identifier}' con rol '{user.role}' "
                f"intentó consumir un endpoint de {attempted_module}. Sesión revocada."
            )
            raise StrictRBACForbiddenException(
                message=(
                    f"Acceso denegado (403 Forbidden): Su rol '{user.role}' tiene estrictamente "
                    f"prohibido consumir recursos de {attempted_module}. Sesión revocada."
                ),
                details={
                    "user_role": user.role,
                    "required_role": self.required_role.value,
                    "session_revoked": True,
                },
            )

        return user


get_current_user = RBACAccessGuard(required_role=None)
require_admin_role = RBACAccessGuard(required_role=UserRole.ADMIN)
require_driver_role = RBACAccessGuard(required_role=UserRole.CONDUCTOR)
