"""
Script utilitario para poblar (Seed) la base de datos en Supabase con:
- 4 Planes de Mantenimiento Preventivo de rutina (`maintenance_plans`)
- 27 Camiones reales de flota (`trucks`) con distribución de estados:
  * 20 en estado `'OPTIMAL'`
  * 4 en estado `'WARNING_MAINTENANCE'` (dentro del rango de `tolerance_km`)
  * 3 en estado `'OVERDUE'` (kilometraje vencido)
- 1 Usuario ADMIN único con identificador "admin" (para Plataforma Web)
- 27 Usuarios CONDUCTOR con cédula aleatoria única de 10 dígitos que inicia en '09' y nombre completo:
  Apellidos y Nombres (ej. 'Mendoza Cevallos Carlos Andrés')
- Historial realista de mantenimientos completados con taller asignado y bitácoras de odómetro

Uso:
    .\\env\\Scripts\\python.exe -m utils.seed_fleet --reset
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import List, Set, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import delete, func, select, update

from scripts.core.logger import LoggerManager
from scripts.core.security import SecurityManager
from scripts.database.session import db_manager
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
from scripts.services.maintenance_engine import MaintenanceEngineService

seed_logger = LoggerManager.get_logger("seed_fleet")

FLEET_SPECS: List[Tuple[str, str, str, int, float]] = [
    # 20 Unidades en estado OPTIMAL
    ("GBA-7101", "Hino", "GH 1828", 2023, 42100.0),
    ("GBA-7102", "Hino", "GH 1828", 2023, 51200.0),
    ("GBA-7103", "Hino", "FM 2835", 2022, 83400.0),
    ("GBA-7104", "Hino", "FC 1121", 2024, 12300.0),
    ("GBA-7105", "Freightliner", "M2 106", 2022, 91500.0),
    ("GBA-7106", "Freightliner", "M2 106", 2023, 62400.0),
    ("GBA-7107", "Freightliner", "Cascadia 116", 2021, 141800.0),
    ("GBA-7108", "Kenworth", "T370", 2022, 73200.0),
    ("GBA-7109", "Kenworth", "T800", 2021, 162100.0),
    ("GBA-7110", "Chevrolet", "FVR 1826", 2023, 31900.0),
    ("GBA-7111", "Chevrolet", "FTR 1524", 2024, 14100.0),
    ("GBA-7112", "Chevrolet", "NQR 1019", 2023, 43500.0),
    ("GBA-7113", "Mercedes-Benz", "Atego 1726", 2022, 82700.0),
    ("GBA-7114", "Mercedes-Benz", "Actros 2645", 2021, 152300.0),
    ("GBA-7115", "Volkswagen", "Constellation 17.280", 2023, 53100.0),
    ("GBA-7116", "Volkswagen", "Constellation 24.280", 2022, 102400.0),
    ("GBA-7117", "Volvo", "VM 270", 2023, 61800.0),
    ("GBA-7118", "Volvo", "FH 460", 2021, 172900.0),
    ("GBA-7119", "Mack", "Anthem 6x4", 2022, 112600.0),
    ("GBA-7120", "Sinotruk", "HOWO T5G", 2024, 21400.0),
    # 4 Unidades en estado WARNING_MAINTENANCE (a menos de 500 km del próximo servicio de 10,000 km)
    ("GBA-7121", "Hino", "GH 1828", 2022, 79650.0),
    ("GBA-7122", "Freightliner", "M2 106", 2022, 89720.0),
    ("GBA-7123", "Kenworth", "T370", 2021, 119810.0),
    ("GBA-7124", "Chevrolet", "FVR 1826", 2023, 49580.0),
    # 3 Unidades en estado OVERDUE (superaron el límite de su servicio programado)
    ("GBA-7125", "Mercedes-Benz", "Atego 1726", 2021, 130450.0),
    ("GBA-7126", "Volvo", "VM 270", 2022, 90620.0),
    ("GBA-7127", "Mack", "Granite 6x4", 2020, 181240.0),
]

# 27 Nombres completos ecuatorianos con estructura: Primer Apellido, Segundo Apellido, Primer Nombre, Segundo Nombre
DRIVER_FULL_NAMES: List[str] = [
    "Mendoza Cevallos Carlos Andrés",
    "Zambrano Moreira Luis Fernando",
    "Pincay Loor Jorge Eduardo",
    "Macías Vera Miguel Ángel",
    "Alcívar Salazar Pedro Javier",
    "Intriago Quiñónez Roberto Carlos",
    "Villavicencio Peñafiel Diego Armando",
    "Carpio Bone José Antonio",
    "Bravo Solórzano Fernando Patricio",
    "Fajardo Caicedo Cristian David",
    "Morán Baque Héctor Gabriel",
    "Palacios Holguín Marco Vinicio",
    "Arboleda Chóez Édison Fabián",
    "Guerrero Cedeño Segundo Manuel",
    "Paredes Benítez Ángel Rodrigo",
    "Cárdenas Tello Raúl Alejandro",
    "Montalván Rosado Víctor Hugo",
    "Velasco Navarrete Darwin Geovanny",
    "Barreiro Murillo Kléber Oswaldo",
    "Santana Vera Washington René",
    "Bustamante Figueroa Byron Estuardo",
    "Carranza Delgado Wilmer Orlando",
    "Cornejo Mite Joffre Alexander",
    "Guzmán Yánez Galo Humberto",
    "Ortega Lucas Néstor Iván",
    "Sánchez Viteri Óscar Mauricio",
    "Peralta Quinde Fabián Enrique",
]

WORKSHOPS: List[str] = [
    "Taller Central Matriz Guayaquil",
    "Taller Autorizado Hino - Automekano",
    "Taller Mecánico Especializado Diesel Motors",
    "Centro de Servicio y Frenos Manta",
    "Taller Autorizado Freightliner - Divemotor",
]


def generate_unique_cedulas(count: int) -> List[str]:
    """Genera números aleatorios únicos de 10 dígitos que inician con '09'."""
    generated: Set[str] = set()
    while len(generated) < count:
        suffix = random.randint(10000000, 99999999)
        cedula = f"09{suffix}"
        generated.add(cedula)
    return list(generated)


class FleetDatabaseSeeder:
    """Controlador POO para inicialización determinista de las 27 unidades y usuarios."""

    def __init__(self, reset_existing: bool = False) -> None:
        self.reset_existing = reset_existing

    async def run(self) -> None:
        async with db_manager.session_factory() as session:
            if self.reset_existing:
                seed_logger.info("Limpiando data sintética previa (camiones y conductores, preservando admin)...")
                await session.execute(delete(MaintenanceRecord))
                await session.execute(delete(OdometerLog))
                # Desvincular camiones antes de eliminar para respetar foreign keys
                await session.execute(update(User).values(assigned_truck_id=None))
                # Eliminar únicamente los usuarios conductores sintéticos
                await session.execute(delete(User).where(User.role == UserRole.CONDUCTOR.value))
                # Eliminar cualquier usuario supervisor o duplicado, conservando solo el admin único
                await session.execute(delete(User).where(User.identifier != "admin"))
                await session.execute(delete(Truck))
                await session.execute(delete(MaintenancePlan))
                await session.commit()

            # 1. Asegurar la existencia del ÚNICO Administrador con identifier='admin'
            admin_stmt = select(User).where(User.role == UserRole.ADMIN.value)
            admin_user = (await session.execute(admin_stmt)).scalars().first()

            if not admin_user:
                admin_pw_hash = SecurityManager.hash_password("Admin2026*")
                admin_user = User(
                    identifier="admin",
                    full_name="Administrador General del Sistema",
                    password_hash=admin_pw_hash,
                    role=UserRole.ADMIN.value,
                    assigned_truck_id=None,
                    is_active=True,
                )
                session.add(admin_user)
                await session.flush()
                seed_logger.info("Usuario único ADMIN creado con identifier='admin'.")
            else:
                # Asegurar que su identifier sea 'admin'
                admin_user.identifier = "admin"
                admin_user.full_name = "Administrador General del Sistema"
                await session.flush()
                seed_logger.info("Usuario ADMIN único verificado con identifier='admin'.")

            # 2. Crear Planes de Mantenimiento Preventivo
            plans_data = [
                ("Cambio de Aceite y Filtro", 10000, 500),
                ("Revisión y Ajuste de Frenos", 15000, 500),
                ("Cambio de Filtros de Combustible y Aire", 20000, 600),
                ("Mantenimiento Mayor de Transmisión y Diferencial", 50000, 1000),
            ]
            plans: List[MaintenancePlan] = []
            for name, interval, tolerance in plans_data:
                plan = MaintenancePlan(
                    service_name=name,
                    interval_km=interval,
                    tolerance_km=tolerance,
                )
                session.add(plan)
                plans.append(plan)
            await session.flush()

            driver_pw_hash = SecurityManager.hash_password("Driver2026*")
            cedulas = generate_unique_cedulas(len(FLEET_SPECS))

            now = datetime.now(timezone.utc)
            oil_plan = plans[0]  # Cambio de Aceite y Filtro cada 10,000 km (tolerancia 500 km)
            brakes_plan = plans[1]  # Revisión de Frenos cada 15,000 km

            # 3. Crear los 27 Camiones, sus 27 Conductores, Bitácoras y Mantenimientos
            for idx, (plate, brand, model, year, current_odo) in enumerate(FLEET_SPECS):
                truck = Truck(
                    plate_number=plate,
                    brand=brand,
                    model=model,
                    year=year,
                    current_odometer=current_odo,
                    status=TruckStatus.OPTIMO.value,
                )
                session.add(truck)
                await session.flush()

                # Cédula única aleatoria de 10 dígitos que inicia en 09 y Nombre completo (Apellidos y Nombres)
                driver_identifier = cedulas[idx]
                driver_full_name = DRIVER_FULL_NAMES[idx]
                driver = User(
                    identifier=driver_identifier,
                    full_name=driver_full_name,
                    password_hash=driver_pw_hash,
                    role=UserRole.CONDUCTOR.value,
                    assigned_truck_id=truck.id,
                    is_active=True,
                )
                session.add(driver)
                await session.flush()

                # Generar 3 lecturas históricas de odómetro en el mes actual para métricas mensuales
                odo_step_1 = max(0.0, current_odo - 1450.0)
                odo_step_2 = max(0.0, current_odo - 680.0)

                session.add_all(
                    [
                        OdometerLog(
                            truck_id=truck.id,
                            driver_id=driver.id,
                            odometer_value=odo_step_1,
                            registered_at=now - timedelta(days=12, hours=idx % 6),
                            notes="Inicio de ciclo operativo mensual",
                        ),
                        OdometerLog(
                            truck_id=truck.id,
                            driver_id=driver.id,
                            odometer_value=odo_step_2,
                            registered_at=now - timedelta(days=5, hours=idx % 6),
                            notes="Reporte intermedio de ruta nacional",
                        ),
                        OdometerLog(
                            truck_id=truck.id,
                            driver_id=driver.id,
                            odometer_value=current_odo,
                            registered_at=now - timedelta(days=1, hours=idx % 4),
                            notes="Lectura más reciente verificada en garita",
                        ),
                    ]
                )

                # Hoja de vida de mantenimiento:
                # 0..19: OPTIMAL
                # 20..23: WARNING_MAINTENANCE
                # 24..26: OVERDUE
                if idx < 20:
                    last_service_km = (current_odo // 10000) * 10000.0
                    next_due_km = last_service_km + float(oil_plan.interval_km)
                elif idx < 24:
                    last_service_km = (current_odo // 10000) * 10000.0
                    next_due_km = last_service_km + float(oil_plan.interval_km)
                else:
                    last_service_km = ((current_odo // 10000) - 1) * 10000.0
                    next_due_km = last_service_km + float(oil_plan.interval_km)

                selected_workshop = WORKSHOPS[idx % len(WORKSHOPS)]

                # Registro histórico COMPLETADO previo
                completed_rec = MaintenanceRecord(
                    truck_id=truck.id,
                    plan_id=oil_plan.id,
                    mileage_at_service=last_service_km,
                    next_due_mileage=next_due_km,
                    cost=Decimal("185.00"),
                    workshop=selected_workshop,
                    status=MaintenanceStatus.COMPLETADO.value,
                    performed_at=now - timedelta(days=25),
                    notes="Mantenimiento preventivo completado según pauta de fabricante",
                )
                # Registro activo PROGRAMADO para Cambio de Aceite
                scheduled_oil = MaintenanceRecord(
                    truck_id=truck.id,
                    plan_id=oil_plan.id,
                    mileage_at_service=last_service_km,
                    next_due_mileage=next_due_km,
                    cost=None,
                    workshop=selected_workshop,
                    status=MaintenanceStatus.PROGRAMADO.value,
                    performed_at=None,
                    notes="Próximo cambio de aceite y filtro programado",
                )
                # Registro activo PROGRAMADO para Revisión de Frenos
                scheduled_brakes = MaintenanceRecord(
                    truck_id=truck.id,
                    plan_id=brakes_plan.id,
                    mileage_at_service=current_odo,
                    next_due_mileage=current_odo + float(brakes_plan.interval_km),
                    cost=None,
                    workshop=selected_workshop,
                    status=MaintenanceStatus.PROGRAMADO.value,
                    performed_at=None,
                    notes="Revisión preventiva programada de sistema de frenos",
                )
                session.add_all([completed_rec, scheduled_oil, scheduled_brakes])
                await session.flush()

                # Recalcular estado exacto de la unidad mediante el motor de reglas
                await MaintenanceEngineService.recalculate_truck_status(session, truck)

            await session.commit()
            seed_logger.info(
                "Semilla completada exitosamente: 27 camiones, 1 único administrador ('admin'), "
                "27 conductores con cédula única (09...) y dos apellidos + dos nombres, "
                "con taller asignado y bitácoras inicializadas."
            )


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Poblar base de datos con la flota de 27 camiones y usuarios."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Elimina la data sintética existente antes de insertar la semilla.",
    )
    args = parser.parse_args()
    seeder = FleetDatabaseSeeder(reset_existing=args.reset)
    await seeder.run()
    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
