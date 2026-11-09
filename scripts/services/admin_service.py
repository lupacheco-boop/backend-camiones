"""Controlador de servicio POO para el Módulo Administrador (/admin)."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from scripts.core.exceptions import (
    BusinessRuleViolationException,
    ResourceNotFoundException,
)
from scripts.core.logger import LoggerManager
from scripts.core.security import SecurityManager
from scripts.models.entities import (
    MaintenancePlan,
    MaintenanceRecord,
    MaintenanceStatus,
    OdometerLog,
    Truck,
    TruckStatus,
    User,
    UserRole,
)
from scripts.schemas.admin_schemas import (
    DriverBriefInfo,
    FleetMetricsResponse,
    MaintenancePerformRequest,
    MaintenancePerformResponse,
    MaintenancePlanCreateRequest,
    MaintenancePlanResponse,
    MaintenanceRecordAdminResponse,
    PaginatedTrucksResponse,
    TruckAdminItemResponse,
    TruckCreateRequest,
    TruckUpdateRequest,
    UserAdminResponse,
    UserCreateRequest,
    UserUpdateRequest,
)
from scripts.services.maintenance_engine import MaintenanceEngineService

admin_logger = LoggerManager.get_logger("admin_service")

# Caché en memoria para planes preventivos estáticos (reduce consultas remotas a Supabase)
_PLANS_CACHE: dict[UUID, MaintenancePlan] = {}


class AdminService:
    """Servicio POO exclusivo para administradores (`ADMIN`) en la Plataforma Web."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_fleet_metrics(self) -> FleetMetricsResponse:
        """
        `GET /admin/metrics`:
        Resumen ejecutivo de la flota (total de camiones, cantidad en estado Óptimo,
        cantidad en Alerta, cantidad Vencidos, kilometraje total acumulado en el mes).
        """
        # Conteo de camiones agrupado por estado
        status_stmt = select(Truck.status, func.count(Truck.id)).group_by(Truck.status)
        status_res = await self.session.execute(status_stmt)
        counts_by_status = {row[0]: int(row[1]) for row in status_res.all()}

        optimal_count = counts_by_status.get(TruckStatus.OPTIMO.value, 0)
        warning_count = counts_by_status.get(TruckStatus.ALERTA.value, 0)
        overdue_count = counts_by_status.get(TruckStatus.VENCIDO.value, 0)
        total_trucks = sum(counts_by_status.values())

        # Cálculo optimizado en 1 sola consulta SQL del kilometraje total acumulado en el mes actual
        now = datetime.now(timezone.utc)
        start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

        # Subconsulta: última lectura previa al inicio del mes por camión (si existe)
        prev_subq = (
            select(
                OdometerLog.truck_id,
                func.max(OdometerLog.odometer_value).label("prev_max_odo"),
            )
            .where(OdometerLog.registered_at < start_of_month)
            .group_by(OdometerLog.truck_id)
            .subquery()
        )

        # Consulta agregada mensual por camión unida con la línea base previa
        logs_month_stmt = (
            select(
                OdometerLog.truck_id,
                func.min(OdometerLog.odometer_value).label("min_odo"),
                func.max(OdometerLog.odometer_value).label("max_odo"),
                prev_subq.c.prev_max_odo,
            )
            .outerjoin(prev_subq, prev_subq.c.truck_id == OdometerLog.truck_id)
            .where(OdometerLog.registered_at >= start_of_month)
            .group_by(OdometerLog.truck_id, prev_subq.c.prev_max_odo)
        )
        logs_month_res = await self.session.execute(logs_month_stmt)
        monthly_rows = logs_month_res.all()

        monthly_accumulated_km = 0.0
        for _truck_id, min_odo, max_odo, prev_odo in monthly_rows:
            baseline = float(prev_odo) if prev_odo is not None else float(min_odo)
            delta = max(0.0, float(max_odo) - baseline)
            monthly_accumulated_km += delta

        monthly_accumulated_km = round(monthly_accumulated_km, 2)

        # Conteo de conductores activos
        drivers_stmt = select(func.count(User.id)).where(
            User.role == UserRole.CONDUCTOR.value, User.is_active.is_(True)
        )
        active_drivers_count = int((await self.session.execute(drivers_stmt)).scalar_one() or 0)

        # Conteo de mantenimientos programados pendientes
        sched_stmt = select(func.count(MaintenanceRecord.id)).where(
            MaintenanceRecord.status == MaintenanceStatus.PROGRAMADO.value
        )
        scheduled_maintenances_count = int(
            (await self.session.execute(sched_stmt)).scalar_one() or 0
        )

        return FleetMetricsResponse(
            total_trucks=total_trucks,
            optimal_count=optimal_count,
            warning_count=warning_count,
            overdue_count=overdue_count,
            monthly_accumulated_km=monthly_accumulated_km,
            active_drivers_count=active_drivers_count,
            scheduled_maintenances_count=scheduled_maintenances_count,
            generated_at=now,
        )

    async def list_trucks(
        self,
        page: int = 1,
        page_size: int = 30,
        status_filter: Optional[str] = None,
        plate_search: Optional[str] = None,
    ) -> PaginatedTrucksResponse:
        """
        `GET /admin/trucks`:
        Lista completa de camiones con paginación, filtros por estado (`status`)
        y búsqueda parcial por placa (`plate`).
        """
        base_stmt = select(Truck).options(joinedload(Truck.assigned_drivers))
        count_stmt = select(func.count(Truck.id))

        if status_filter:
            normalized_status = status_filter.strip().upper()
            base_stmt = base_stmt.where(Truck.status == normalized_status)
            count_stmt = count_stmt.where(Truck.status == normalized_status)

        if plate_search:
            pattern = f"%{plate_search.strip().upper()}%"
            base_stmt = base_stmt.where(Truck.plate_number.ilike(pattern))
            count_stmt = count_stmt.where(Truck.plate_number.ilike(pattern))

        total = int((await self.session.execute(count_stmt)).scalar_one() or 0)
        total_pages = max(1, math.ceil(total / page_size))
        offset = (page - 1) * page_size

        stmt = (
            base_stmt.order_by(Truck.plate_number.asc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.session.execute(stmt)
        trucks = list(result.scalars().unique().all())

        items: List[TruckAdminItemResponse] = [
            self._build_truck_admin_item(t) for t in trucks
        ]

        return PaginatedTrucksResponse(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            items=items,
        )

    async def create_truck(self, payload: TruckCreateRequest) -> TruckAdminItemResponse:
        """`POST /admin/trucks`: Registro de una nueva unidad en la flota."""
        dup_stmt = select(Truck).where(Truck.plate_number == payload.plate_number)
        if (await self.session.execute(dup_stmt)).scalar_one_or_none():
            raise BusinessRuleViolationException(
                message=f"Ya existe un camión registrado con la placa '{payload.plate_number}'.",
                error_code="DUPLICATE_PLATE_NUMBER",
            )

        truck = Truck(
            plate_number=payload.plate_number,
            brand=payload.brand.strip(),
            model=payload.model.strip(),
            year=payload.year,
            current_odometer=round(float(payload.current_odometer), 2),
            status=TruckStatus.OPTIMO.value,
        )
        self.session.add(truck)
        await self.session.flush()

        # Registrar lectura inicial en bitácora de odómetros
        initial_log = OdometerLog(
            truck_id=truck.id,
            driver_id=None,
            odometer_value=truck.current_odometer,
            notes="Kilometraje base de alta de unidad en el sistema",
        )
        self.session.add(initial_log)

        if payload.assigned_driver_id:
            await self._assign_driver_to_truck(payload.assigned_driver_id, truck.id)

        if payload.initialize_default_plans:
            await MaintenanceEngineService.initialize_truck_schedules(
                self.session, truck
            )

        await self.session.commit()

        # Recargar con relaciones
        refreshed = await self._get_truck_with_relations(truck.id)
        admin_logger.info(
            f"Nueva unidad registrada: {refreshed.plate_number} ({refreshed.brand} {refreshed.model})"
        )
        return self._build_truck_admin_item(refreshed)

    async def update_truck(
        self, truck_id: UUID, payload: TruckUpdateRequest
    ) -> TruckAdminItemResponse:
        """`PUT /admin/trucks/{id}`: Actualización de datos y asignación de conductor."""
        truck = await self._get_truck_with_relations(truck_id)

        if payload.plate_number and payload.plate_number != truck.plate_number:
            dup_stmt = select(Truck).where(
                Truck.plate_number == payload.plate_number,
                Truck.id != truck_id,
            )
            if (await self.session.execute(dup_stmt)).scalar_one_or_none():
                raise BusinessRuleViolationException(
                    message=f"La placa '{payload.plate_number}' ya pertenece a otra unidad.",
                    error_code="DUPLICATE_PLATE_NUMBER",
                )
            truck.plate_number = payload.plate_number

        if payload.brand is not None:
            truck.brand = payload.brand.strip()
        if payload.model is not None:
            truck.model = payload.model.strip()
        if payload.year is not None:
            truck.year = payload.year

        if payload.current_odometer is not None:
            new_odo = round(float(payload.current_odometer), 2)
            if new_odo < truck.current_odometer:
                raise BusinessRuleViolationException(
                    message=(
                        f"El nuevo odómetro ({new_odo:,.2f} km) no puede ser inferior al "
                        f"odómetro actual ({truck.current_odometer:,.2f} km)."
                    ),
                    error_code="INVALID_ODOMETER_DECREASE",
                )
            if new_odo > truck.current_odometer:
                truck.current_odometer = new_odo
                self.session.add(
                    OdometerLog(
                        truck_id=truck.id,
                        driver_id=None,
                        odometer_value=new_odo,
                        notes="Ajuste administrativo de odómetro desde Panel Web",
                    )
                )

        if payload.unassign_driver:
            await self.session.execute(
                update(User)
                .where(User.assigned_truck_id == truck.id)
                .values(assigned_truck_id=None)
            )
        elif payload.assigned_driver_id is not None:
            await self._assign_driver_to_truck(payload.assigned_driver_id, truck.id)

        if payload.status is not None:
            truck.status = payload.status
        else:
            await MaintenanceEngineService.recalculate_truck_status(
                self.session, truck
            )

        await self.session.commit()
        refreshed = await self._get_truck_with_relations(truck.id)
        admin_logger.info(f"Unidad actualizada por ADMIN: {refreshed.plate_number}")
        return self._build_truck_admin_item(refreshed)

    async def list_users(
        self, role_filter: Optional[str] = None
    ) -> List[UserAdminResponse]:
        """`GET /admin/users`: Listado completo de conductores y administradores."""
        stmt = (
            select(User)
            .options(joinedload(User.assigned_truck))
            .order_by(User.role.asc(), User.full_name.asc())
        )
        if role_filter:
            stmt = stmt.where(User.role == role_filter.strip().upper())

        result = await self.session.execute(stmt)
        users = list(result.scalars().unique().all())

        return [
            UserAdminResponse(
                id=u.id,
                identifier=u.identifier,
                full_name=u.full_name,
                role=u.role,  # type: ignore[arg-type]
                assigned_truck_id=u.assigned_truck_id,
                assigned_truck_plate=(
                    u.assigned_truck.plate_number if u.assigned_truck else None
                ),
                is_active=u.is_active,
                created_at=u.created_at,
            )
            for u in users
        ]

    async def create_user(self, payload: UserCreateRequest) -> UserAdminResponse:
        """`POST /admin/users`: Creación de conductores (`DRIVER`) o administradores (`ADMIN`)."""
        identifier_clean = payload.identifier.strip()
        dup_stmt = select(User).where(User.identifier == identifier_clean)
        if (await self.session.execute(dup_stmt)).scalar_one_or_none():
            raise BusinessRuleViolationException(
                message=f"Ya existe un usuario con el identificador '{identifier_clean}'.",
                error_code="DUPLICATE_USER_IDENTIFIER",
            )

        if payload.role == UserRole.ADMIN.value and payload.assigned_truck_id is not None:
            raise BusinessRuleViolationException(
                message="Un usuario con rol ADMIN no puede tener un camión asignado.",
                error_code="ADMIN_CANNOT_HAVE_TRUCK",
            )

        assigned_truck: Optional[Truck] = None
        if payload.assigned_truck_id is not None:
            truck_res = await self.session.execute(
                select(Truck).where(Truck.id == payload.assigned_truck_id)
            )
            assigned_truck = truck_res.scalar_one_or_none()
            if not assigned_truck:
                raise ResourceNotFoundException(
                    f"El camión con ID '{payload.assigned_truck_id}' no existe."
                )
            # Desvincular conductor anterior si ese camión ya estaba ocupado
            await self.session.execute(
                update(User)
                .where(User.assigned_truck_id == assigned_truck.id)
                .values(assigned_truck_id=None)
            )

        new_user = User(
            identifier=identifier_clean,
            full_name=payload.full_name.strip(),
            password_hash=SecurityManager.hash_password(payload.password),
            role=payload.role,
            assigned_truck_id=payload.assigned_truck_id,
            is_active=payload.is_active,
        )
        self.session.add(new_user)
        await self.session.commit()
        await self.session.refresh(new_user)

        admin_logger.info(
            f"Nuevo usuario creado: {new_user.identifier} ({new_user.role})"
        )
        return UserAdminResponse(
            id=new_user.id,
            identifier=new_user.identifier,
            full_name=new_user.full_name,
            role=new_user.role,  # type: ignore[arg-type]
            assigned_truck_id=new_user.assigned_truck_id,
            assigned_truck_plate=assigned_truck.plate_number if assigned_truck else None,
            is_active=new_user.is_active,
            created_at=new_user.created_at,
        )

    async def update_user(
        self, user_id: UUID, payload: UserUpdateRequest
    ) -> UserAdminResponse:
        """`PUT /admin/users/{id}`: Actualización de estado, contraseña o asignación de unidad."""
        stmt = (
            select(User)
            .options(joinedload(User.assigned_truck))
            .where(User.id == user_id)
        )
        user = (await self.session.execute(stmt)).scalars().unique().one_or_none()
        if not user:
            raise ResourceNotFoundException("El usuario especificado no existe.")

        if payload.full_name is not None:
            user.full_name = payload.full_name.strip()
        if payload.password is not None:
            user.password_hash = SecurityManager.hash_password(payload.password)
        if payload.is_active is not None:
            user.is_active = payload.is_active

        if payload.unassign_truck:
            user.assigned_truck_id = None
        elif payload.assigned_truck_id is not None:
            if user.role != UserRole.CONDUCTOR.value:
                raise BusinessRuleViolationException(
                    "Solo los usuarios con rol CONDUCTOR pueden tener un camión asignado."
                )
            await self._assign_driver_to_truck(user.id, payload.assigned_truck_id)

        await self.session.commit()
        refreshed = (await self.session.execute(stmt)).scalar_one()
        return UserAdminResponse(
            id=refreshed.id,
            identifier=refreshed.identifier,
            full_name=refreshed.full_name,
            role=refreshed.role,  # type: ignore[arg-type]
            assigned_truck_id=refreshed.assigned_truck_id,
            assigned_truck_plate=(
                refreshed.assigned_truck.plate_number
                if refreshed.assigned_truck
                else None
            ),
            is_active=refreshed.is_active,
            created_at=refreshed.created_at,
        )

    async def list_maintenance_plans(self) -> List[MaintenancePlanResponse]:
        """`GET /admin/maintenance/plans`: Catálogo de planes preventivos de rutina."""
        stmt = select(MaintenancePlan).order_by(MaintenancePlan.interval_km.asc())
        plans = list((await self.session.execute(stmt)).scalars().all())
        return [MaintenancePlanResponse.model_validate(p) for p in plans]

    async def create_maintenance_plan(
        self, payload: MaintenancePlanCreateRequest
    ) -> MaintenancePlanResponse:
        """`POST /admin/maintenance/plans`: Crea un nuevo parámetro preventivo de rutina."""
        dup_stmt = select(MaintenancePlan).where(
            MaintenancePlan.service_name.ilike(payload.service_name.strip())
        )
        if (await self.session.execute(dup_stmt)).scalar_one_or_none():
            raise BusinessRuleViolationException(
                f"Ya existe un plan preventivo denominado '{payload.service_name}'."
            )
        plan = MaintenancePlan(
            service_name=payload.service_name.strip(),
            interval_km=payload.interval_km,
            tolerance_km=payload.tolerance_km,
        )
        self.session.add(plan)
        await self.session.commit()
        await self.session.refresh(plan)
        return MaintenancePlanResponse.model_validate(plan)

    async def register_performed_maintenance(
        self, payload: MaintenancePerformRequest
    ) -> MaintenancePerformResponse:
        """
        `POST /admin/maintenance`:
        Registra un mantenimiento efectuado:
        1. Pasa el servicio programado actual a `'COMPLETED'` (o crea el registro completado),
        2. Registra el costo (`cost`) y fecha de ejecución (`performed_at`),
        3. Calcula automáticamente el siguiente `next_due_mileage = mileage_at_service + plan.interval_km`,
        4. Crea la nueva orden `'SCHEDULED'` para el próximo ciclo preventivo,
        5. Recalcula el estado de salud (`status`) del camión.
        """
        truck_res = await self.session.execute(
            select(Truck).where(Truck.id == payload.truck_id)
        )
        truck = truck_res.scalar_one_or_none()
        if not truck:
            raise ResourceNotFoundException("El camión especificado no existe.")

        plan = _PLANS_CACHE.get(payload.plan_id)
        if not plan:
            plan_res = await self.session.execute(
                select(MaintenancePlan).where(MaintenancePlan.id == payload.plan_id)
            )
            plan = plan_res.scalar_one_or_none()
            if not plan:
                raise ResourceNotFoundException(
                    "El plan de mantenimiento especificado no existe."
                )
            _PLANS_CACHE[payload.plan_id] = plan

        effective_mileage = (
            round(float(payload.mileage_at_service), 2)
            if payload.mileage_at_service is not None
            else float(truck.current_odometer)
        )

        # Si el mantenimiento se efectuó a un kilometraje ligeramente superior al registrado, actualizar camión
        if effective_mileage > truck.current_odometer:
            truck.current_odometer = effective_mileage
            self.session.add(
                OdometerLog(
                    truck_id=truck.id,
                    driver_id=None,
                    odometer_value=effective_mileage,
                    notes=f"Actualización automática por servicio: {plan.service_name}",
                )
            )

        next_due_mileage = round(effective_mileage + float(plan.interval_km), 2)
        performed_time = payload.performed_at or datetime.now(timezone.utc)

        # Buscar si había un registro PROGRAMADO pendiente para este camión y plan
        sched_stmt = (
            select(MaintenanceRecord)
            .where(
                MaintenanceRecord.truck_id == truck.id,
                MaintenanceRecord.plan_id == plan.id,
                MaintenanceRecord.status == MaintenanceStatus.PROGRAMADO.value,
            )
            .order_by(MaintenanceRecord.next_due_mileage.asc())
            .limit(1)
        )
        existing_scheduled = (
            await self.session.execute(sched_stmt)
        ).scalar_one_or_none()

        if existing_scheduled:
            existing_scheduled.mileage_at_service = effective_mileage
            existing_scheduled.next_due_mileage = next_due_mileage
            existing_scheduled.cost = payload.cost
            existing_scheduled.workshop = payload.workshop or "Taller Central de Flota"
            existing_scheduled.status = MaintenanceStatus.COMPLETADO.value
            existing_scheduled.performed_at = performed_time
            existing_scheduled.notes = (
                payload.notes.strip()
                if payload.notes
                else f"Servicio completado ({plan.service_name})"
            )
            completed_record = existing_scheduled
        else:
            completed_record = MaintenanceRecord(
                truck_id=truck.id,
                plan_id=plan.id,
                mileage_at_service=effective_mileage,
                next_due_mileage=next_due_mileage,
                cost=payload.cost,
                workshop=payload.workshop or "Taller Central de Flota",
                status=MaintenanceStatus.COMPLETADO.value,
                performed_at=performed_time,
                notes=(
                    payload.notes.strip()
                    if payload.notes
                    else f"Servicio completado ({plan.service_name})"
                ),
            )
            self.session.add(completed_record)

        # Crear el siguiente ciclo preventivo programado (PROGRAMADO)
        next_scheduled = MaintenanceRecord(
            truck_id=truck.id,
            plan_id=plan.id,
            mileage_at_service=effective_mileage,
            next_due_mileage=next_due_mileage,
            cost=None,
            status=MaintenanceStatus.PROGRAMADO.value,
            performed_at=None,
            notes=f"Próximo servicio programado automáticamente tras mantenimiento a los {effective_mileage:,.0f} km",
        )
        self.session.add(next_scheduled)
        await self.session.flush()

        updated_status, _ = await MaintenanceEngineService.recalculate_truck_status(
            self.session, truck
        )
        await self.session.commit()

        admin_logger.info(
            f"Mantenimiento registrado en camión {truck.plate_number}: "
            f"Plan='{plan.service_name}' a los {effective_mileage} km -> Próximo: {next_due_mileage} km | "
            f"Nuevo estado unidad: {updated_status}"
        )

        return MaintenancePerformResponse(
            message="Mantenimiento preventivo registrado como COMPLETED y próximo ciclo programado exitosamente.",
            completed_record=self._build_maintenance_record_response(
                completed_record, truck, plan
            ),
            next_scheduled_record=self._build_maintenance_record_response(
                next_scheduled, truck, plan
            ),
            updated_truck_status=updated_status,
        )

    async def get_maintenance_schedule(
        self, urgency_filter: Optional[str] = None
    ) -> List[MaintenanceRecordAdminResponse]:
        """
        `GET /admin/maintenance/schedule`:
        Calendario/lista de servicios pendientes (`SCHEDULED`) y vencidos ordenados
        por urgencia de kilometraje (menor `remaining_km` primero).
        """
        stmt = (
            select(MaintenanceRecord)
            .options(
                joinedload(MaintenanceRecord.truck),
                joinedload(MaintenanceRecord.plan),
            )
            .where(MaintenanceRecord.status == MaintenanceStatus.PROGRAMADO.value)
        )
        records = list((await self.session.execute(stmt)).scalars().unique().all())

        response_items: List[MaintenanceRecordAdminResponse] = []
        for rec in records:
            item = self._build_maintenance_record_response(rec, rec.truck, rec.plan)
            if urgency_filter:
                if item.urgency_status != urgency_filter.strip().upper():
                    continue
            response_items.append(item)

        # Ordenar por menor kilometraje restante (los vencidos tienen remaining_km negativo y van primero)
        response_items.sort(key=lambda r: r.remaining_km)
        return response_items

    async def _assign_driver_to_truck(
        self, driver_id: UUID, truck_id: UUID
    ) -> None:
        """Asigna un conductor exclusivamente a un camión garantizando relación 1-a-1 activa."""
        driver_res = await self.session.execute(
            select(User).where(User.id == driver_id)
        )
        driver = driver_res.scalar_one_or_none()
        if not driver:
            raise ResourceNotFoundException(
                f"El conductor con ID '{driver_id}' no fue encontrado."
            )
        if driver.role != UserRole.CONDUCTOR.value:
            raise BusinessRuleViolationException(
                "El usuario seleccionado no posee el rol CONDUCTOR."
            )

        # Desvincular cualquier otro conductor que tuviera este camión asignado
        await self.session.execute(
            update(User)
            .where(User.assigned_truck_id == truck_id, User.id != driver_id)
            .values(assigned_truck_id=None)
        )
        driver.assigned_truck_id = truck_id
        await self.session.flush()

    async def _get_truck_with_relations(self, truck_id: UUID) -> Truck:
        stmt = (
            select(Truck)
            .options(joinedload(Truck.assigned_drivers))
            .where(Truck.id == truck_id)
        )
        result = await self.session.execute(stmt)
        truck = result.scalars().unique().one_or_none()
        if not truck:
            raise ResourceNotFoundException(
                f"El camión con ID '{truck_id}' no existe."
            )
        return truck

    @staticmethod
    def _build_truck_admin_item(truck: Truck) -> TruckAdminItemResponse:
        active_driver: Optional[DriverBriefInfo] = None
        if truck.assigned_drivers:
            drv = truck.assigned_drivers[0]
            active_driver = DriverBriefInfo(
                id=drv.id,
                identifier=drv.identifier,
                full_name=drv.full_name,
                is_active=drv.is_active,
            )

        return TruckAdminItemResponse(
            id=truck.id,
            plate_number=truck.plate_number,
            brand=truck.brand,
            model=truck.model,
            year=truck.year,
            current_odometer=truck.current_odometer,
            status=truck.status,
            created_at=truck.created_at,
            assigned_driver=active_driver,
        )

    @staticmethod
    def _build_maintenance_record_response(
        record: MaintenanceRecord, truck: Truck, plan: MaintenancePlan
    ) -> MaintenanceRecordAdminResponse:
        urgency, remaining_km = (
            MaintenanceEngineService.evaluate_single_record_urgency(
                current_odometer=truck.current_odometer,
                next_due_mileage=record.next_due_mileage,
                tolerance_km=plan.tolerance_km,
            )
        )
        return MaintenanceRecordAdminResponse(
            id=record.id,
            truck_id=truck.id,
            plate_number=truck.plate_number,
            plan_id=plan.id,
            service_name=plan.service_name,
            interval_km=plan.interval_km,
            tolerance_km=plan.tolerance_km,
            mileage_at_service=record.mileage_at_service,
            next_due_mileage=record.next_due_mileage,
            current_odometer=truck.current_odometer,
            remaining_km=remaining_km,
            urgency_status=urgency,
            cost=record.cost,
            workshop=record.workshop,
            status=record.status,
            performed_at=record.performed_at,
            notes=record.notes,
        )
