"""
Simulador de Telemetría / IoT y Avance de Kilometraje para la Flota de 27 Camiones.
Permite simular recorridos en ruta para uno o varios camiones (con `driver_id=None`
para representar telemetría IoT o con el conductor asignado) y dispara automáticamente
el motor de recálculo de estados preventivos (`OPTIMAL`, `WARNING_MAINTENANCE`, `OVERDUE`).

Uso:
    .\\env\\Scripts\\python.exe -m utils.simulate_odometer --plate GBA-7101 --km 450
    .\\env\\Scripts\\python.exe -m utils.simulate_odometer --all --km 250
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from pathlib import Path
from typing import List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import select

from scripts.core.logger import LoggerManager
from scripts.database.session import db_manager
from scripts.models.entities import OdometerLog, Truck
from scripts.services.maintenance_engine import MaintenanceEngineService

sim_logger = LoggerManager.get_logger("iot_simulator")


class TelemetryOdometerSimulator:
    """Simulador POO de incremento de kilometraje por telemetría IoT."""

    async def simulate(
        self,
        plate_number: Optional[str] = None,
        increment_km: Optional[float] = None,
    ) -> None:
        async with db_manager.session_factory() as session:
            stmt = select(Truck).order_by(Truck.plate_number.asc())
            if plate_number:
                stmt = stmt.where(Truck.plate_number == plate_number.strip().upper())

            trucks: List[Truck] = list((await session.execute(stmt)).scalars().all())
            if not trucks:
                sim_logger.error("No se encontraron camiones que coincidan con el criterio.")
                return

            for truck in trucks:
                delta = (
                    round(float(increment_km), 2)
                    if increment_km is not None
                    else round(random.uniform(120.0, 480.0), 2)
                )
                prev_odo = truck.current_odometer
                new_odo = round(prev_odo + delta, 2)
                truck.current_odometer = new_odo

                iot_log = OdometerLog(
                    truck_id=truck.id,
                    driver_id=None,  # Nulo porque proviene del simulador IoT
                    odometer_value=new_odo,
                    notes=f"Telemetría GPS/IoT automática (+{delta:,.1f} km)",
                )
                session.add(iot_log)
                await session.flush()

                new_status, _ = await MaintenanceEngineService.recalculate_truck_status(
                    session, truck
                )
                sim_logger.info(
                    f"[IoT] Camión {truck.plate_number}: {prev_odo:,.1f} -> {new_odo:,.1f} km "
                    f"(+{delta:,.1f} km) | Estado: {new_status}"
                )

            await session.commit()


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulador de telemetría IoT para avance de odómetros de la flota."
    )
    parser.add_argument(
        "--plate",
        type=str,
        default=None,
        help="Placa específica del camión a simular (ej. GBA-7123).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Simular incremento en las 27 unidades de la flota.",
    )
    parser.add_argument(
        "--km",
        type=float,
        default=250.0,
        help="Kilómetros a incrementar en la simulación (por defecto 250 km).",
    )
    args = parser.parse_args()

    simulator = TelemetryOdometerSimulator()
    target_plate = args.plate.strip().upper() if args.plate else None
    await simulator.simulate(plate_number=target_plate, increment_km=args.km)
    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
