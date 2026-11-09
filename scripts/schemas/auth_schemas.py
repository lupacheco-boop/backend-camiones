"""Esquemas Pydantic v2 para Autenticación y Perfil (/auth)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """Petición de inicio de sesión con validación de plataforma cliente."""

    identifier: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Identificador del usuario: 'admin' para ADMIN o número de cédula (10 dígitos que empiece en 09) para CONDUCTOR.",
        examples=["admin", "0987654321"],
    )
    password: str = Field(
        ...,
        min_length=4,
        max_length=128,
        description="Contraseña del usuario en texto plano.",
    )
    client_type: Optional[Literal["WEB", "APP"]] = Field(
        default=None,
        description="Plataforma cliente desde la cual se autentica: 'WEB' (solo ADMIN) o 'APP' (solo CONDUCTOR).",
    )


class AssignedTruckBrief(BaseModel):
    """Resumen compacto del camión asignado al usuario."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plate_number: str
    brand: str
    model: str
    year: int
    current_odometer: float
    status: str


class UserProfileResponse(BaseModel):
    """Información pública del usuario autenticado."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    identifier: str
    full_name: str
    role: Literal["ADMIN", "CONDUCTOR"]
    assigned_truck_id: Optional[UUID] = None
    assigned_truck: Optional[AssignedTruckBrief] = None
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    """Respuesta de autenticación exitosa con JWT firmado (HS256)."""

    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    role: Literal["ADMIN", "CONDUCTOR"]
    client_type: Optional[str] = None
    user: UserProfileResponse
