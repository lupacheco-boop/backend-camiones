"""Esquemas Pydantic v2 para el Módulo Administrador (/admin)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FleetMetricsResponse(BaseModel):
    """Resumen ejecutivo de la flota (`GET /admin/metrics`)."""

    total_trucks: int
    optimal_count: int
    warning_count: int
    overdue_count: int
    monthly_accumulated_km: float
    active_drivers_count: int
    scheduled_maintenances_count: int
    generated_at: datetime


class DriverBriefInfo(BaseModel):
    """Información resumida del conductor asignado a un camión."""

    id: UUID
    identifier: str
    full_name: str
    is_active: bool


class TruckAdminItemResponse(BaseModel):
    """Detalle completo de un camión para el listado y gestión administrativa."""

    id: UUID
    plate_number: str
    brand: str
    model: str
    year: int
    current_odometer: float
    status: str
    created_at: datetime
    assigned_driver: Optional[DriverBriefInfo] = None


class PaginatedTrucksResponse(BaseModel):
    """Respuesta paginada de `GET /admin/trucks`."""

    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[TruckAdminItemResponse]


class TruckCreateRequest(BaseModel):
    """Solicitud de alta de una nueva unidad (`POST /admin/trucks`)."""

    plate_number: str = Field(
        ...,
        min_length=5,
        max_length=20,
        description="Número de placa único (ej. 'GBA-7123').",
        examples=["GBA-7123"],
    )
    brand: str = Field(..., min_length=2, max_length=50, examples=["Hino"])
    model: str = Field(..., min_length=1, max_length=50, examples=["GH 1828"])
    year: int = Field(..., ge=1990, le=2100, examples=[2023])
    current_odometer: float = Field(default=0.0, ge=0.0, examples=[15000.0])
    assigned_driver_id: Optional[UUID] = Field(
        default=None,
        description="ID opcional del conductor a asignar e inicializar planes preventivos.",
    )
    initialize_default_plans: bool = Field(
        default=True,
        description="Si es True, programa automáticamente los planes de mantenimiento activos para este camión.",
    )

    @field_validator("plate_number")
    @classmethod
    def normalize_plate(cls, v: str) -> str:
        return v.strip().upper()


class TruckUpdateRequest(BaseModel):
    """Solicitud de actualización de una unidad (`PUT /admin/trucks/{id}`)."""

    plate_number: Optional[str] = Field(default=None, min_length=5, max_length=20)
    brand: Optional[str] = Field(default=None, min_length=2, max_length=50)
    model: Optional[str] = Field(default=None, min_length=1, max_length=50)
    year: Optional[int] = Field(default=None, ge=1990, le=2100)
    current_odometer: Optional[float] = Field(default=None, ge=0.0)
    status: Optional[Literal["OPTIMO", "ALERTA", "VENCIDO"]] = None
    assigned_driver_id: Optional[UUID] = Field(
        default=None,
        description="ID del conductor a asignar a esta unidad.",
    )
    unassign_driver: bool = Field(
        default=False,
        description="Si es True, desvincula cualquier conductor actualmente asignado a este camión.",
    )

    @field_validator("plate_number")
    @classmethod
    def normalize_plate(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().upper() if v is not None else None


class UserAdminResponse(BaseModel):
    """Representación de usuario para el panel administrativo."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    identifier: str
    full_name: str
    role: Literal["ADMIN", "CONDUCTOR"]
    assigned_truck_id: Optional[UUID] = None
    assigned_truck_plate: Optional[str] = None
    is_active: bool
    created_at: datetime


class UserCreateRequest(BaseModel):
    """Solicitud de creación de usuario (`POST /admin/users`)."""

    identifier: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="'admin' para ADMIN, o cédula de 10 dígitos (iniciando en 09) para CONDUCTOR.",
    )
    full_name: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=4, max_length=128)
    role: Literal["ADMIN", "CONDUCTOR"]
    assigned_truck_id: Optional[UUID] = None
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    """Solicitud de actualización de usuario (`PUT /admin/users/{id}`)."""

    full_name: Optional[str] = Field(default=None, min_length=3, max_length=100)
    password: Optional[str] = Field(default=None, min_length=4, max_length=128)
    assigned_truck_id: Optional[UUID] = None
    unassign_truck: bool = False
    is_active: Optional[bool] = None


class MaintenancePlanResponse(BaseModel):
    """Respuesta de un plan de mantenimiento preventivo (`maintenance_plans`)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    service_name: str
    interval_km: int
    tolerance_km: int


class MaintenancePlanCreateRequest(BaseModel):
    """Creación de un nuevo plan de mantenimiento preventivo."""

    service_name: str = Field(..., min_length=3, max_length=100)
    interval_km: int = Field(..., gt=0, examples=[10000])
    tolerance_km: int = Field(default=500, ge=0, examples=[500])


class MaintenancePerformRequest(BaseModel):
    """
    Solicitud de registro de mantenimiento efectuado (`POST /admin/maintenance`).
    Marca el servicio como COMPLETED, registra el costo, taller, calcula automáticamente
    el siguiente `next_due_mileage` según el plan y genera el nuevo ciclo `SCHEDULED`.
    """

    truck_id: UUID
    plan_id: UUID
    mileage_at_service: Optional[float] = Field(
        default=None,
        ge=0,
        description="Kilometraje al momento del servicio. Si se omite, usa el `current_odometer` del camión.",
    )
    cost: Optional[Decimal] = Field(
        default=None,
        ge=0,
        description="Costo económico del servicio efectuado (USD).",
        examples=[185.50],
    )
    workshop: Optional[str] = Field(
        default="Taller Central de Flota",
        max_length=150,
        description="Nombre del taller donde se realizó el mantenimiento.",
        examples=["Taller Central Autorizado Hino"],
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=500,
        examples=["Cambio de aceite sintético 15W40 y filtros originales."],
    )
    performed_at: Optional[datetime] = None


class MaintenanceRecordAdminResponse(BaseModel):
    """Detalle de un registro de mantenimiento para el administrador."""

    id: UUID
    truck_id: UUID
    plate_number: str
    plan_id: UUID
    service_name: str
    interval_km: int
    tolerance_km: int
    mileage_at_service: float
    next_due_mileage: float
    current_odometer: float
    remaining_km: float
    urgency_status: str  # OPTIMO, ALERTA, VENCIDO
    cost: Optional[Decimal] = None
    workshop: Optional[str] = None
    status: str
    performed_at: Optional[datetime] = None
    notes: Optional[str] = None


class MaintenancePerformResponse(BaseModel):
    """Respuesta tras registrar un mantenimiento completado y programar el siguiente ciclo."""

    message: str
    completed_record: MaintenanceRecordAdminResponse
    next_scheduled_record: MaintenanceRecordAdminResponse
    updated_truck_status: str
