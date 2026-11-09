"""Gestor criptográfico de contraseñas (Bcrypt) y tokens JWT (HS256) con política RBAC."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt

from scripts.core.config import settings
from scripts.core.exceptions import AuthenticationException, StrictRBACForbiddenException


class SecurityManager:
    """Clase utilitaria bajo POO para hashing de contraseñas, firma de JWT y validación RBAC."""

    @staticmethod
    def hash_password(plain_password: str) -> str:
        """Genera un hash seguro Bcrypt a partir de una contraseña en texto plano."""
        password_bytes = plain_password.encode("utf-8")
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password_bytes, salt)
        return hashed.decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, password_hash: str) -> bool:
        """Verifica de forma segura si la contraseña coincide con el hash almacenado."""
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                password_hash.encode("utf-8"),
            )
        except Exception:
            return False

    @staticmethod
    def create_access_token(
        subject: str,
        role: str,
        client_type: Optional[str] = None,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Crea un JSON Web Token firmado con HS256 incluyendo claims `sub`, `role` y `exp`."""
        now = datetime.now(timezone.utc)
        expire = now + (
            expires_delta
            if expires_delta is not None
            else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        payload: Dict[str, Any] = {
            "sub": str(subject),
            "role": role,
            "iat": int(now.timestamp()),
            "exp": int(expire.timestamp()),
        }
        if client_type:
            payload["client_type"] = client_type.upper()

        return jwt.encode(
            payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )

    @staticmethod
    def decode_access_token(token: str) -> Dict[str, Any]:
        """Decodifica y verifica la firma y expiración de un token JWT."""
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
            if "sub" not in payload or "role" not in payload:
                raise AuthenticationException("Token malformado: faltan claims obligatorios.")
            return payload
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationException(
                "La sesión ha expirado. Por favor, inicie sesión nuevamente."
            ) from exc
        except jwt.InvalidTokenError as exc:
            raise AuthenticationException(
                "Token de acceso inválido o corrupto."
            ) from exc

    @staticmethod
    def validate_client_role_exclusivity(
        user_role: str, client_type: Optional[str]
    ) -> None:
        """
        Regla de seguridad estricta RBAC:
        - Plataforma Web (`client_type == 'WEB'`): Exclusivo para rol `ADMIN`.
        - Aplicación Móvil (`client_type == 'APP'`): Exclusivo para rol `CONDUCTOR`.
        Si un usuario intenta autenticarse o usar el cliente equivocado, rechaza con 403 Forbidden.
        """
        if not client_type:
            return

        normalized_client = client_type.strip().upper()
        normalized_role = user_role.strip().upper()

        if normalized_client == "WEB" and normalized_role != "ADMIN":
            raise StrictRBACForbiddenException(
                message=(
                    "Acceso denegado (403 Forbidden): Los usuarios con rol CONDUCTOR tienen "
                    "estrictamente prohibido el acceso a la Plataforma Web Administrativa. "
                    "Sesión revocada."
                ),
                details={"role": normalized_role, "attempted_client": "WEB", "session_revoked": True},
            )

        if normalized_client == "APP" and normalized_role != "CONDUCTOR":
            raise StrictRBACForbiddenException(
                message=(
                    "Acceso denegado (403 Forbidden): Los usuarios con rol ADMIN tienen "
                    "estrictamente prohibido el acceso a la Aplicación Móvil de Conductores. "
                    "Sesión revocada."
                ),
                details={"role": normalized_role, "attempted_client": "APP", "session_revoked": True},
            )
