"""Esquemas Pydantic v2 para el Módulo Conductor (/driver)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UpcomingMaintenanceItem(BaseModel):
    """Detalle de un servicio preventivo programado o próximo a vencer para el camión."""

    record_id: UUID
    plan_id: UUID
    service_name: str
    interval_km: int
    tolerance_km: int
    mileage_at_service: float
    next_due_mileage: float
    remaining_km: float
    urgency_status: str  # OPTIMO, ALERTA, VENCIDO
    status: str
    notes: Optional[str] = None
    workshop: Optional[str] = None


class DriverMyTruckResponse(BaseModel):
    """Respuesta detallada de `GET /driver/my-truck`: Datos del camión asignado al conductor."""

    truck_id: UUID
    plate_number: str
    brand: str
    model: str
    year: int
    current_odometer: float
    status: str
    driver_id: UUID
    driver_name: str
    driver_identifier: str
    scheduled_maintenances: List[UpcomingMaintenanceItem]


class CompletedMaintenanceHistoryItem(BaseModel):
    """Registro histórico de un mantenimiento completado para la hoja de vida del camión."""

    service_name: str = Field(..., description="Nombre del servicio de mantenimiento realizado.")
    mileage_at_service: float = Field(..., description="Kilometraje que constaba al momento de realizar el mantenimiento.")
    cost: Optional[Decimal] = Field(default=None, description="Costo económico del mantenimiento.")
    workshop: Optional[str] = Field(default=None, description="Taller donde se le realizó el servicio.")
    performed_at: Optional[datetime] = Field(default=None, description="Fecha y hora de realización.")
    notes: Optional[str] = Field(default=None, description="Observaciones del mantenimiento.")


class DriverMaintenanceHistoryResponse(BaseModel):
    """Respuesta del endpoint `GET /driver/history`: Historial exclusivo de mantenimientos realizados hasta la fecha."""

    truck_id: UUID
    plate_number: str
    current_odometer: float
    total_completed: int
    completed_maintenances: List[CompletedMaintenanceHistoryItem]
