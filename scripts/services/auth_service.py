"""Controlador de servicio POO para Autenticación, Sesión y Control de Acceso RBAC."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from scripts.core.config import settings
from scripts.core.exceptions import (
    AuthenticationException,
    ResourceNotFoundException,
    StrictRBACForbiddenException,
)
from scripts.core.logger import LoggerManager
from scripts.core.security import SecurityManager
from scripts.models.entities import User
from scripts.schemas.auth_schemas import (
    AssignedTruckBrief,
    LoginRequest,
    TokenResponse,
    UserProfileResponse,
)

auth_logger = LoggerManager.get_logger("auth_service")


class AuthService:
    """Servicio POO para gestión de inicio de sesión, emisión de JWT y perfil de sesión."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def authenticate_user(
        self, payload: LoginRequest, header_client_type: Optional[str] = None
    ) -> TokenResponse:
        """
        Valida credenciales, verifica estado activo del usuario y aplica la regla estricta
        mutuamente excluyente entre WEB (`ADMIN`) y APP (`DRIVER`).
        """
        identifier_clean = payload.identifier.strip()
        stmt = (
            select(User)
            .options(selectinload(User.assigned_truck))
            .where(User.identifier == identifier_clean)
        )
        result = await self.session.execute(stmt)
        user: Optional[User] = result.scalar_one_or_none()

        if not user or not SecurityManager.verify_password(
            payload.password, user.password_hash
        ):
            auth_logger.warning(
                f"Intento de inicio de sesión fallido para identificador: '{identifier_clean}'"
            )
            raise AuthenticationException(
                "Credenciales inválidas. Verifique su identificador y contraseña."
            )

        if not user.is_active:
            auth_logger.warning(
                f"Usuario inactivo '{identifier_clean}' intentó iniciar sesión."
            )
            raise StrictRBACForbiddenException(
                message="Su cuenta de usuario se encuentra deshabilitada por el administrador."
            )

        # Determinar client_type efectivo (prioridad al body o cabecera X-Client-Type)
        effective_client_type = (
            payload.client_type
            or (header_client_type.strip().upper() if header_client_type else None)
        )

        # Validar regla estricta RBAC: ADMIN <-> WEB y DRIVER <-> APP
        try:
            SecurityManager.validate_client_role_exclusivity(
                user_role=user.role,
                client_type=effective_client_type,
            )
        except StrictRBACForbiddenException as exc:
            auth_logger.error(
                f"VIOLACIÓN RBAC en Login: Usuario '{user.identifier}' (rol={user.role}) "
                f"intentó autenticarse en cliente '{effective_client_type}'. Sesión rechazada con 403."
            )
            raise exc

        # Si no se envió client_type explícito, inferir el cliente legítimo según el rol
        issued_client = effective_client_type or (
            "WEB" if user.role == "ADMIN" else "APP"
        )

        access_token = SecurityManager.create_access_token(
            subject=str(user.id),
            role=user.role,
            client_type=issued_client,
        )

        auth_logger.info(
            f"Inicio de sesión exitoso: '{user.identifier}' (rol={user.role}, cliente={issued_client})"
        )

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
            role=user.role,  # type: ignore[arg-type]
            client_type=issued_client,
            user=self.build_user_profile(user),
        )

    async def get_user_by_id(self, user_id: UUID) -> User:
        """Recupera un usuario activo por su UUID con su camión asignado precargado."""
        stmt = (
            select(User)
            .options(selectinload(User.assigned_truck))
            .where(User.id == user_id)
        )
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            raise ResourceNotFoundException("El usuario de la sesión ya no existe.")
        if not user.is_active:
            raise StrictRBACForbiddenException(
                "Su cuenta ha sido desactivada. Sesión revocada."
            )
        return user

    @staticmethod
    def build_user_profile(user: User) -> UserProfileResponse:
        """Transforma la entidad ORM `User` al DTO `UserProfileResponse`."""
        truck_brief = None
        if user.assigned_truck is not None:
            truck_brief = AssignedTruckBrief.model_validate(user.assigned_truck)

        return UserProfileResponse(
            id=user.id,
            identifier=user.identifier,
            full_name=user.full_name,
            role=user.role,  # type: ignore[arg-type]
            assigned_truck_id=user.assigned_truck_id,
            assigned_truck=truck_brief,
            is_active=user.is_active,
            created_at=user.created_at,
        )
