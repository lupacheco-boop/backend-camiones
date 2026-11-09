"""Controlador de servicio POO para el Módulo Conductor (/driver)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from scripts.core.exceptions import ResourceNotFoundException
from scripts.core.logger import LoggerManager
from scripts.models.entities import (
    MaintenanceRecord,
    MaintenanceStatus,
    Truck,
    User,
)
from scripts.schemas.driver_schemas import (
    CompletedMaintenanceHistoryItem,
    DriverMaintenanceHistoryResponse,
    DriverMyTruckResponse,
)
from scripts.services.maintenance_engine import MaintenanceEngineService

driver_logger = LoggerManager.get_logger("driver_service")


class DriverService:
    """Servicio POO exclusivo para conductores (`CONDUCTOR`) en la aplicación móvil."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_assigned_truck_or_raise(self, driver: User) -> Truck:
        """Verifica que el conductor tenga un camión asignado y lo retorna."""
        if not driver.assigned_truck_id:
            raise ResourceNotFoundException(
                "Actualmente no tiene ninguna unidad (camión) asignada a su perfil de conductor."
            )

        stmt = select(Truck).where(Truck.id == driver.assigned_truck_id)
        result = await self.session.execute(stmt)
        truck = result.scalar_one_or_none()
        if not truck:
            raise ResourceNotFoundException(
                "El camión asignado a su cuenta no fue encontrado en el sistema."
            )
        return truck

    async def get_my_truck_details(self, driver: User) -> DriverMyTruckResponse:
        """
        `GET /driver/my-truck`:
        Retorna los detalles del camión asignado, odómetro actual, estado de salud
        y lista de mantenimientos programados o próximos a vencer.
        """
        truck = await self._get_assigned_truck_or_raise(driver)
        updated_status, upcoming_items = (
            await MaintenanceEngineService.recalculate_truck_status(self.session, truck)
        )
        await self.session.commit()

        return DriverMyTruckResponse(
            truck_id=truck.id,
            plate_number=truck.plate_number,
            brand=truck.brand,
            model=truck.model,
            year=truck.year,
            current_odometer=truck.current_odometer,
            status=updated_status,
            driver_id=driver.id,
            driver_name=driver.full_name,
            driver_identifier=driver.identifier,
            scheduled_maintenances=upcoming_items,
        )

    async def get_driver_truck_history(
        self, driver: User, limit: int = 50
    ) -> DriverMaintenanceHistoryResponse:
        """
        `GET /driver/history`:
        Retorna únicamente el historial de todos los mantenimientos realizados (COMPLETED)
        hasta la fecha para el camión del conductor:
        - Nombre del mantenimiento
        - Kilometraje que constaba al momento de realizarlo
        - Costo del mantenimiento
        - Taller donde se le realizó
        - Fecha y observaciones
        """
        truck = await self._get_assigned_truck_or_raise(driver)

        maint_stmt = (
            select(MaintenanceRecord)
            .options(selectinload(MaintenanceRecord.plan))
            .where(
                MaintenanceRecord.truck_id == truck.id,
                MaintenanceRecord.status == MaintenanceStatus.COMPLETADO.value,
            )
            .order_by(MaintenanceRecord.performed_at.desc().nullslast())
            .limit(limit)
        )
        maint_res = await self.session.execute(maint_stmt)
        completed_records = list(maint_res.scalars().all())

        history_items = [
            CompletedMaintenanceHistoryItem(
                service_name=rec.plan.service_name,
                mileage_at_service=rec.mileage_at_service,
                cost=rec.cost,
                workshop=rec.workshop or "Taller Autorizado de Flota",
                performed_at=rec.performed_at,
                notes=rec.notes,
            )
            for rec in completed_records
        ]

        return DriverMaintenanceHistoryResponse(
            truck_id=truck.id,
            plate_number=truck.plate_number,
            current_odometer=truck.current_odometer,
            total_completed=len(history_items),
            completed_maintenances=history_items,
        )
