"""Controlador de rutas POO para el Módulo Administrador (`/api/v1/admin`) - Exclusivo Rol ADMIN."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.api.dependencies import require_admin_role
from scripts.database.session import get_db_session
from scripts.models.entities import User
from scripts.schemas.admin_schemas import (
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
from scripts.services.admin_service import AdminService


class AdminRouterController:
    """
    Controlador POO con endpoints reservados exclusivamente a usuarios con rol `ADMIN`.
    Cualquier intento de acceso por parte de un `DRIVER` es rechazado con HTTP `403 Forbidden`.
    """

    def __init__(self) -> None:
        self.router = APIRouter(
            prefix="/admin",
            tags=["C. Módulo Administrador (/admin) - Exclusivo ADMIN"],
        )
        self._register_routes()

    def _register_routes(self) -> None:
        @self.router.get(
            "/metrics",
            response_model=FleetMetricsResponse,
            status_code=status.HTTP_200_OK,
            summary="Resumen ejecutivo de la flota (27 camiones, Óptimos, Alerta, Vencidos y km mensual)",
        )
        async def get_metrics(
            _admin: User = Depends(require_admin_role),
            session: AsyncSession = Depends(get_db_session),
        ) -> FleetMetricsResponse:
            service = AdminService(session)
            return await service.get_fleet_metrics()

        @self.router.get(
            "/trucks",
            response_model=PaginatedTrucksResponse,
            status_code=status.HTTP_200_OK,
            summary="Listar camiones con paginación, filtro por estado y búsqueda por placa",
        )
        async def list_trucks(
            page: int = Query(default=1, ge=1, description="Número de página"),
            page_size: int = Query(
                default=30, ge=1, le=100, description="Tamaño de página"
            ),
            status_filter: Optional[str] = Query(
                default=None,
                alias="status",
                description="Filtrar por estado: OPTIMO, ALERTA, VENCIDO",
            ),
            plate: Optional[str] = Query(
                default=None,
                description="Búsqueda parcial o exacta por número de placa (ej. GBA-7123)",
            ),
            _admin: User = Depends(require_admin_role),
            session: AsyncSession = Depends(get_db_session),
        ) -> PaginatedTrucksResponse:
            service = AdminService(session)
            return await service.list_trucks(
                page=page,
                page_size=page_size,
                status_filter=status_filter,
                plate_search=plate,
            )

        @self.router.post(
            "/trucks",
            response_model=TruckAdminItemResponse,
            status_code=status.HTTP_201_CREATED,
            summary="Registrar una nueva unidad en la flota",
        )
        async def create_truck(
            payload: TruckCreateRequest,
            _admin: User = Depends(require_admin_role),
            session: AsyncSession = Depends(get_db_session),
        ) -> TruckAdminItemResponse:
            service = AdminService(session)
            return await service.create_truck(payload)

        @self.router.put(
            "/trucks/{id}",
            response_model=TruckAdminItemResponse,
            status_code=status.HTTP_200_OK,
            summary="Actualizar datos de una unidad (placa, odómetro, asignación de conductor)",
        )
        async def update_truck(
            id: UUID,
            payload: TruckUpdateRequest,
            _admin: User = Depends(require_admin_role),
            session: AsyncSession = Depends(get_db_session),
        ) -> TruckAdminItemResponse:
            service = AdminService(session)
            return await service.update_truck(id, payload)

        @self.router.get(
            "/users",
            response_model=List[UserAdminResponse],
            status_code=status.HTTP_200_OK,
            summary="Listar todos los conductores y administradores registrados",
        )
        async def list_users(
            role: Optional[str] = Query(
                default=None, description="Filtro opcional por rol: ADMIN o DRIVER"
            ),
            _admin: User = Depends(require_admin_role),
            session: AsyncSession = Depends(get_db_session),
        ) -> List[UserAdminResponse]:
            service = AdminService(session)
            return await service.list_users(role_filter=role)

        @self.router.post(
            "/users",
            response_model=UserAdminResponse,
            status_code=status.HTTP_201_CREATED,
            summary="Dar de alta un nuevo conductor (DRIVER) o administrador (ADMIN)",
        )
        async def create_user(
            payload: UserCreateRequest,
            _admin: User = Depends(require_admin_role),
            session: AsyncSession = Depends(get_db_session),
        ) -> UserAdminResponse:
            service = AdminService(session)
            return await service.create_user(payload)

        @self.router.put(
            "/users/{id}",
            response_model=UserAdminResponse,
            status_code=status.HTTP_200_OK,
            summary="Actualizar datos, estado activo o asignación de camión de un usuario",
        )
        async def update_user(
            id: UUID,
            payload: UserUpdateRequest,
            _admin: User = Depends(require_admin_role),
            session: AsyncSession = Depends(get_db_session),
        ) -> UserAdminResponse:
            service = AdminService(session)
            return await service.update_user(id, payload)

        @self.router.get(
            "/maintenance/plans",
            response_model=List[MaintenancePlanResponse],
            status_code=status.HTTP_200_OK,
            summary="Listar catálogo de planes de mantenimiento preventivo",
        )
        async def list_maintenance_plans(
            _admin: User = Depends(require_admin_role),
            session: AsyncSession = Depends(get_db_session),
        ) -> List[MaintenancePlanResponse]:
            service = AdminService(session)
            return await service.list_maintenance_plans()

        @self.router.post(
            "/maintenance/plans",
            response_model=MaintenancePlanResponse,
            status_code=status.HTTP_201_CREATED,
            summary="Crear un nuevo plan de mantenimiento preventivo",
        )
        async def create_maintenance_plan(
            payload: MaintenancePlanCreateRequest,
            _admin: User = Depends(require_admin_role),
            session: AsyncSession = Depends(get_db_session),
        ) -> MaintenancePlanResponse:
            service = AdminService(session)
            return await service.create_maintenance_plan(payload)

        @self.router.post(
            "/maintenance",
            response_model=MaintenancePerformResponse,
            status_code=status.HTTP_201_CREATED,
            summary="Registrar un mantenimiento efectuado (COMPLETED) y calcular próximo next_due_mileage",
        )
        async def register_maintenance(
            payload: MaintenancePerformRequest,
            _admin: User = Depends(require_admin_role),
            session: AsyncSession = Depends(get_db_session),
        ) -> MaintenancePerformResponse:
            service = AdminService(session)
            return await service.register_performed_maintenance(payload)

        @self.router.get(
            "/maintenance/schedule",
            response_model=List[MaintenanceRecordAdminResponse],
            status_code=status.HTTP_200_OK,
            summary="Calendario/lista de servicios pendientes y vencidos ordenados por urgencia de kilometraje",
        )
        async def get_maintenance_schedule(
            urgency: Optional[str] = Query(
                default=None,
                description="Filtrar por urgencia: VENCIDO, ALERTA, OPTIMO",
            ),
            _admin: User = Depends(require_admin_role),
            session: AsyncSession = Depends(get_db_session),
        ) -> List[MaintenanceRecordAdminResponse]:
            service = AdminService(session)
            return await service.get_maintenance_schedule(urgency_filter=urgency)


admin_router = AdminRouterController().router
