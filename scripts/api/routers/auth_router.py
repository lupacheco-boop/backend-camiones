"""Controlador de rutas POO para Autenticación y Perfil (`/api/v1/auth`)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.api.dependencies import get_current_user
from scripts.database.session import get_db_session
from scripts.models.entities import User
from scripts.schemas.auth_schemas import (
    LoginRequest,
    TokenResponse,
    UserProfileResponse,
)
from scripts.services.auth_service import AuthService


class AuthRouterController:
    """Encapsula los endpoints de autenticación y perfil de sesión bajo POO."""

    def __init__(self) -> None:
        self.router = APIRouter(prefix="/auth", tags=["A. Autenticación y Perfil (/auth)"])
        self._register_routes()

    def _register_routes(self) -> None:
        @self.router.post(
            "/login",
            response_model=TokenResponse,
            status_code=status.HTTP_200_OK,
            summary="Iniciar sesión con validación estricta de rol y plataforma (WEB vs APP)",
        )
        async def login(
            payload: LoginRequest,
            x_client_type: Optional[str] = Header(
                default=None,
                alias="X-Client-Type",
                description="Cabecera opcional ('WEB' o 'APP') si no se envía en el body.",
            ),
            session: AsyncSession = Depends(get_db_session),
        ) -> TokenResponse:
            service = AuthService(session)
            return await service.authenticate_user(
                payload=payload,
                header_client_type=x_client_type,
            )

        @self.router.get(
            "/me",
            response_model=UserProfileResponse,
            status_code=status.HTTP_200_OK,
            summary="Obtener perfil del usuario en sesión a partir del Bearer Token",
        )
        async def get_me(
            current_user: User = Depends(get_current_user),
        ) -> UserProfileResponse:
            return AuthService.build_user_profile(current_user)


auth_router = AuthRouterController().router
