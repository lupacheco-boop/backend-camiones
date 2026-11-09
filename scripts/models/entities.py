"""Definición de las 5 entidades relacionales del dominio mapeadas a PostgreSQL (Columnas en Mayúsculas en Español)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from scripts.database.session import Base


class UserRole(str, enum.Enum):
    """Roles del sistema con políticas de acceso mutuamente excluyentes."""

    ADMIN = "ADMIN"
    CONDUCTOR = "CONDUCTOR"


class ClientPlatform(str, enum.Enum):
    """Plataformas cliente soportadas por la arquitectura."""

    WEB = "WEB"
    APP = "APP"


class TruckStatus(str, enum.Enum):
    """Estados de salud operativa y preventiva de un camión."""

    OPTIMO = "OPTIMO"
    ALERTA = "ALERTA"
    VENCIDO = "VENCIDO"


class MaintenanceStatus(str, enum.Enum):
    """Estados posibles de un registro en la hoja de vida de mantenimiento."""

    PROGRAMADO = "PROGRAMADO"
    COMPLETADO = "COMPLETADO"
    CANCELADO = "CANCELADO"


class Truck(Base):
    """Entidad `trucks`: Unidades de la flota de 27 camiones."""

    __tablename__ = "trucks"
    __table_args__ = (
        CheckConstraint(
            "\"ESTADO\" IN ('OPTIMO', 'ALERTA', 'VENCIDO')",
            name="ck_camiones_estado",
        ),
        CheckConstraint('"KILOMETRAJE_ACTUAL" >= 0', name="ck_camiones_km_positivo"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        "ID",
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    plate_number: Mapped[str] = mapped_column(
        "PLACA", String(20), unique=True, nullable=False, index=True
    )
    brand: Mapped[str] = mapped_column("MARCA", String(50), nullable=False)
    model: Mapped[str] = mapped_column("MODELO", String(50), nullable=False)
    year: Mapped[int] = mapped_column("AÑO", Integer, nullable=False)
    current_odometer: Mapped[float] = mapped_column(
        "KILOMETRAJE_ACTUAL",
        Double,
        nullable=False,
        default=0.0,
        server_default=text("0"),
    )
    status: Mapped[str] = mapped_column(
        "ESTADO",
        String(30),
        nullable=False,
        default=TruckStatus.OPTIMO.value,
        server_default=text("'OPTIMO'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        "CREADO_EN",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relaciones
    assigned_drivers: Mapped[List["User"]] = relationship(
        "User",
        back_populates="assigned_truck",
        foreign_keys="User.assigned_truck_id",
        lazy="selectin",
    )
    odometer_logs: Mapped[List["OdometerLog"]] = relationship(
        "OdometerLog",
        back_populates="truck",
        cascade="all, delete-orphan",
        order_by="desc(OdometerLog.registered_at)",
    )
    maintenance_records: Mapped[List["MaintenanceRecord"]] = relationship(
        "MaintenanceRecord",
        back_populates="truck",
        cascade="all, delete-orphan",
        order_by="asc(MaintenanceRecord.next_due_mileage)",
    )


class User(Base):
    """Entidad `users`: Administradores (Web) y Conductores (App Móvil)."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("\"ROL\" IN ('ADMIN', 'CONDUCTOR')", name="ck_usuarios_rol"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        "ID",
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    identifier: Mapped[str] = mapped_column(
        "IDENTIFICADOR", String(50), unique=True, nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column("NOMBRE_COMPLETO", String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column("CONTRASENA_HASH", String(255), nullable=False)
    role: Mapped[str] = mapped_column("ROL", String(20), nullable=False)
    assigned_truck_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        "ID_CAMION_ASIGNADO",
        UUID(as_uuid=True),
        ForeignKey("trucks.ID", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        "ACTIVO", Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        "CREADO_EN",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relaciones
    assigned_truck: Mapped[Optional["Truck"]] = relationship(
        "Truck",
        back_populates="assigned_drivers",
        foreign_keys=[assigned_truck_id],
        lazy="selectin",
    )
    odometer_logs: Mapped[List["OdometerLog"]] = relationship(
        "OdometerLog",
        back_populates="driver",
    )


class OdometerLog(Base):
    """Entidad `odometer_logs`: Bitácora histórica de lecturas de kilometraje."""

    __tablename__ = "odometer_logs"
    __table_args__ = (
        CheckConstraint('"VALOR_ODOMETRO" >= 0', name="ck_odometros_valor_positivo"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        "ID",
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    truck_id: Mapped[uuid.UUID] = mapped_column(
        "ID_CAMION",
        UUID(as_uuid=True),
        ForeignKey("trucks.ID", ondelete="CASCADE"),
        nullable=False,
    )
    driver_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        "ID_CONDUCTOR",
        UUID(as_uuid=True),
        ForeignKey("users.ID", ondelete="SET NULL"),
        nullable=True,
    )
    odometer_value: Mapped[float] = mapped_column(
        "VALOR_ODOMETRO", Double, nullable=False
    )
    registered_at: Mapped[datetime] = mapped_column(
        "REGISTRADO_EN",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    notes: Mapped[Optional[str]] = mapped_column("NOTAS", Text, nullable=True)

    # Relaciones
    truck: Mapped["Truck"] = relationship("Truck", back_populates="odometer_logs")
    driver: Mapped[Optional["User"]] = relationship(
        "User", back_populates="odometer_logs", lazy="selectin"
    )


class MaintenancePlan(Base):
    """Entidad `maintenance_plans`: Catálogo de parámetros preventivos de rutina."""

    __tablename__ = "maintenance_plans"
    __table_args__ = (
        CheckConstraint('"INTERVALO_KM" > 0', name="ck_planes_intervalo"),
        CheckConstraint('"TOLERANCIA_KM" >= 0', name="ck_planes_tolerancia"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        "ID",
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    service_name: Mapped[str] = mapped_column(
        "NOMBRE_SERVICIO", String(100), unique=True, nullable=False
    )
    interval_km: Mapped[int] = mapped_column("INTERVALO_KM", Integer, nullable=False)
    tolerance_km: Mapped[int] = mapped_column(
        "TOLERANCIA_KM",
        Integer,
        nullable=False,
        default=500,
        server_default=text("500"),
    )

    # Relaciones
    maintenance_records: Mapped[List["MaintenanceRecord"]] = relationship(
        "MaintenanceRecord",
        back_populates="plan",
    )


class MaintenanceRecord(Base):
    """Entidad `maintenance_records`: Hoja de vida, programación e historial de servicios."""

    __tablename__ = "maintenance_records"
    __table_args__ = (
        CheckConstraint(
            "\"ESTADO\" IN ('PROGRAMADO', 'COMPLETADO', 'CANCELADO')",
            name="ck_mantenimientos_estado",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        "ID",
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    truck_id: Mapped[uuid.UUID] = mapped_column(
        "ID_CAMION",
        UUID(as_uuid=True),
        ForeignKey("trucks.ID", ondelete="CASCADE"),
        nullable=False,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        "ID_PLAN",
        UUID(as_uuid=True),
        ForeignKey("maintenance_plans.ID", ondelete="RESTRICT"),
        nullable=False,
    )
    mileage_at_service: Mapped[float] = mapped_column(
        "KILOMETRAJE_SERVICIO", Double, nullable=False
    )
    next_due_mileage: Mapped[float] = mapped_column(
        "PROXIMO_KILOMETRAJE", Double, nullable=False
    )
    cost: Mapped[Optional[Decimal]] = mapped_column(
        "COSTO", Numeric(10, 2), nullable=True
    )
    status: Mapped[str] = mapped_column(
        "ESTADO",
        String(20),
        nullable=False,
        default=MaintenanceStatus.PROGRAMADO.value,
        server_default=text("'PROGRAMADO'"),
    )
    performed_at: Mapped[Optional[datetime]] = mapped_column(
        "REALIZADO_EN", DateTime(timezone=True), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column("NOTAS", Text, nullable=True)
    workshop: Mapped[Optional[str]] = mapped_column("TALLER", String(150), nullable=True)

    # Relaciones
    truck: Mapped["Truck"] = relationship(
        "Truck", back_populates="maintenance_records", lazy="selectin"
    )
    plan: Mapped["MaintenancePlan"] = relationship(
        "MaintenancePlan", back_populates="maintenance_records", lazy="selectin"
    )


class SystemConfig(Base):
    """Entidad `system_config`: Configuración global y descubrimiento dinámico de URL del túnel."""

    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(
        "CLAVE", String(100), primary_key=True, nullable=False
    )
    value: Mapped[str] = mapped_column("VALOR", Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        "ACTUALIZADO_EN",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
