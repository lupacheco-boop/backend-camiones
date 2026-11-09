"""Motor de reglas de negocio para cálculo de estados de mantenimiento preventivo."""

from __future__ import annotations

from typing import List, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from scripts.core.logger import LoggerManager
from scripts.models.entities import (
    MaintenancePlan,
    MaintenanceRecord,
    MaintenanceStatus,
    Truck,
    TruckStatus,
)
from scripts.schemas.driver_schemas import UpcomingMaintenanceItem

engine_logger = LoggerManager.get_logger("maintenance_engine")


class MaintenanceEngineService:
    """
    Controlador POO responsable de evaluar la salud preventiva de cada unidad
    en función de su `current_odometer`, los `maintenance_records` en estado `SCHEDULED`
    y la `tolerance_km` definida en cada `MaintenancePlan`.
    """

    @staticmethod
    def evaluate_single_record_urgency(
        current_odometer: float,
        next_due_mileage: float,
        tolerance_km: int,
    ) -> Tuple[str, float]:
        """
        Determina la urgencia de un mantenimiento programado y los kilómetros restantes.
        Retorna `(urgency_status, remaining_km)`:
        - `VENCIDO`: `current_odometer >= next_due_mileage` (`remaining_km <= 0`)
        - `ALERTA`: `current_odometer >= (next_due_mileage - tolerance_km)`
        - `OPTIMO`: `current_odometer < (next_due_mileage - tolerance_km)`
        """
        remaining_km = round(next_due_mileage - current_odometer, 2)
        if current_odometer >= next_due_mileage:
            return TruckStatus.VENCIDO.value, remaining_km
        if current_odometer >= (next_due_mileage - tolerance_km):
            return TruckStatus.ALERTA.value, remaining_km
        return TruckStatus.OPTIMO.value, remaining_km

    @classmethod
    async def recalculate_truck_status(
        cls, session: AsyncSession, truck: Truck
    ) -> Tuple[str, List[UpcomingMaintenanceItem]]:
        """
        Evalúa todos los mantenimientos en estado `PROGRAMADO` del camión, actualiza
        `truck.status` en caso de cambio y retorna la lista ordenada por urgencia.
        """
        stmt = (
            select(MaintenanceRecord)
            .options(joinedload(MaintenanceRecord.plan))
            .where(
                MaintenanceRecord.truck_id == truck.id,
                MaintenanceRecord.status == MaintenanceStatus.PROGRAMADO.value,
            )
            .order_by(MaintenanceRecord.next_due_mileage.asc())
        )
        result = await session.execute(stmt)
        scheduled_records = list(result.scalars().unique().all())

        has_overdue = False
        has_warning = False
        upcoming_items: List[UpcomingMaintenanceItem] = []

        for record in scheduled_records:
            plan: MaintenancePlan = record.plan
            urgency, remaining_km = cls.evaluate_single_record_urgency(
                current_odometer=truck.current_odometer,
                next_due_mileage=record.next_due_mileage,
                tolerance_km=plan.tolerance_km,
            )
            if urgency == TruckStatus.VENCIDO.value:
                has_overdue = True
            elif urgency == TruckStatus.ALERTA.value:
                has_warning = True

            upcoming_items.append(
                UpcomingMaintenanceItem(
                    record_id=record.id,
                    plan_id=plan.id,
                    service_name=plan.service_name,
                    interval_km=plan.interval_km,
                    tolerance_km=plan.tolerance_km,
                    mileage_at_service=record.mileage_at_service,
                    next_due_mileage=record.next_due_mileage,
                    remaining_km=remaining_km,
                    urgency_status=urgency,
                    status=record.status,
                    notes=record.notes,
                    workshop=record.workshop,
                )
            )

        if has_overdue:
            new_status = TruckStatus.VENCIDO.value
        elif has_warning:
            new_status = TruckStatus.ALERTA.value
        else:
            new_status = TruckStatus.OPTIMO.value

        if truck.status != new_status:
            engine_logger.info(
                f"Camión {truck.plate_number} ({truck.id}) cambió de estado: "
                f"{truck.status} -> {new_status} (Odómetro: {truck.current_odometer} km)"
            )
            truck.status = new_status

        # Ordenar por menor kilometraje restante (más urgente primero)
        upcoming_items.sort(key=lambda item: item.remaining_km)
        return new_status, upcoming_items

    @classmethod
    async def initialize_truck_schedules(
        cls, session: AsyncSession, truck: Truck
    ) -> None:
        """
        Crea registros iniciales `PROGRAMADO` para un camión nuevo basándose en todos
        los planes preventivos existentes en `maintenance_plans`.
        """
        plans_result = await session.execute(select(MaintenancePlan))
        plans = list(plans_result.scalars().all())

        for plan in plans:
            next_due = round(truck.current_odometer + plan.interval_km, 2)
            record = MaintenanceRecord(
                truck_id=truck.id,
                plan_id=plan.id,
                mileage_at_service=truck.current_odometer,
                next_due_mileage=next_due,
                status=MaintenanceStatus.PROGRAMADO.value,
                notes=f"Programación preventiva inicial ({plan.service_name})",
            )
            session.add(record)
        await session.flush()
        await cls.recalculate_truck_status(session, truck)
