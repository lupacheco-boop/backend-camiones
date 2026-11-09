"""Controlador de rutas POO para el Módulo Conductor (`/driver`) - Exclusivo Rol CONDUCTOR."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.api.dependencies import require_driver_role
from scripts.database.session import get_db_session
from scripts.models.entities import User
from scripts.schemas.driver_schemas import (
    DriverMaintenanceHistoryResponse,
    DriverMyTruckResponse,
)
from scripts.services.driver_service import DriverService


class DriverRouterController:
    """
    Controlador POO con endpoints reservados exclusivamente a usuarios con rol `CONDUCTOR`.
    El conductor solo puede visualizar la información de su camión asignado y el historial
    de mantenimientos efectuados.
    """

    def __init__(self) -> None:
        self.router = APIRouter(
            prefix="/driver",
            tags=["B. Módulo Conductor (/driver) - Exclusivo CONDUCTOR"],
        )
        self._register_routes()

    def _register_routes(self) -> None:
        @self.router.get(
            "/my-truck",
            response_model=DriverMyTruckResponse,
            status_code=status.HTTP_200_OK,
            summary="Consultar unidad asignada, odómetro actual, estado de salud y mantenimientos próximos",
        )
        async def get_my_truck(
            driver: User = Depends(require_driver_role),
            session: AsyncSession = Depends(get_db_session),
        ) -> DriverMyTruckResponse:
            service = DriverService(session)
            return await service.get_my_truck_details(driver)

        @self.router.get(
            "/history",
            response_model=DriverMaintenanceHistoryResponse,
            status_code=status.HTTP_200_OK,
            summary="Consultar historial de mantenimientos realizados a la fecha (nombre, kilometraje, costo y taller)",
        )
        async def get_history(
            limit: int = Query(
                default=50,
                ge=1,
                le=200,
                description="Cantidad máxima de registros de mantenimiento a retornar.",
            ),
            driver: User = Depends(require_driver_role),
            session: AsyncSession = Depends(get_db_session),
        ) -> DriverMaintenanceHistoryResponse:
            service = DriverService(session)
            return await service.get_driver_truck_history(driver, limit=limit)


driver_router = DriverRouterController().router
