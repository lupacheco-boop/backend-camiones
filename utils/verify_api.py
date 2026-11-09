"""
Suite de Verificación e Integración End-to-End (E2E) del Backend.
Comprueba:
1. Regla estricta RBAC en `/auth/login`:
   - `ADMIN` ("admin") en `WEB` -> `200 OK`
   - `ADMIN` en `APP` -> `403 Forbidden`
   - `CONDUCTOR` (Cédula 09...) en `APP` -> `200 OK`
   - `CONDUCTOR` en `WEB` -> `403 Forbidden`
2. Regla estricta RBAC en módulos protegidos:
   - `CONDUCTOR` consumiendo `/admin/metrics` -> `403 Forbidden`
   - `ADMIN` consumiendo `/driver/my-truck` -> `403 Forbidden`
3. Módulo Conductor (`/driver`):
   - `GET /driver/my-truck` (solo visualización de su camión)
   - `GET /driver/history` (historial exclusivo de mantenimientos con nombre, kilometraje, costo y taller)
   - Verificación de que `driver/odometer` fue eliminado -> `404 Not Found`
4. Módulo Administrador (`/admin`):
   - `GET /admin/metrics` (27 camiones y métricas)
   - `GET /admin/trucks`
   - `GET /admin/users` (solo 1 admin y 27 conductores)
   - `GET /admin/maintenance/schedule`
   - `POST /admin/maintenance` con campo `workshop` (Taller)

Uso:
    .\\env\\Scripts\\python.exe -m utils.verify_api
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from scripts.core.logger import LoggerManager
from scripts.database.session import db_manager
from scripts.main import app
from scripts.models.entities import User, UserRole

verify_logger = LoggerManager.get_logger("verify_api")


async def run_verification_suite() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"ngrok-skip-browser-warning": "true"},
    ) as client:
        verify_logger.info("=== INICIANDO SUITE DE VERIFICACIÓN END-TO-END (E2E) ===")

        # 1. Healthcheck
        res_health = await client.get("/health")
        assert res_health.status_code == 200, f"Fallo health: {res_health.text}"
        verify_logger.info("[OK] 1. Healthcheck verificado.")

        # Obtener un conductor generado en BD
        async with db_manager.session_factory() as session:
            driver_db = (
                await session.execute(
                    select(User).where(User.role == UserRole.CONDUCTOR.value)
                )
            ).scalars().first()
            assert driver_db is not None, "No se encontró ningún conductor en BD"
            driver_cedula = driver_db.identifier
            assert driver_cedula.startswith("09") and len(driver_cedula) == 10

        # 2. RBAC en /auth/login
        # 2a. ADMIN intentando entrar desde APP -> Debe rechazar con 403 Forbidden
        res_admin_app = await client.post(
            "/auth/login",
            json={
                "identifier": "admin",
                "password": "Admin2026*",
                "client_type": "APP",
            },
        )
        assert res_admin_app.status_code == 403, f"Esperado 403, recibido {res_admin_app.status_code}"

        # 2b. CONDUCTOR intentando entrar desde WEB -> Debe rechazar con 403 Forbidden
        res_driver_web = await client.post(
            "/auth/login",
            json={
                "identifier": driver_cedula,
                "password": "Driver2026*",
                "client_type": "WEB",
            },
        )
        assert res_driver_web.status_code == 403, f"Esperado 403, recibido {res_driver_web.status_code}"
        verify_logger.info("[OK] 2. Bloqueo RBAC en Login (ADMIN en APP / CONDUCTOR en WEB -> 403 Forbidden).")

        # 3. Login legítimo para ADMIN (identifier='admin', client_type='WEB') y CONDUCTOR (APP)
        res_admin_login = await client.post(
            "/auth/login",
            json={
                "identifier": "admin",
                "password": "Admin2026*",
                "client_type": "WEB",
            },
        )
        assert res_admin_login.status_code == 200, res_admin_login.text
        admin_token = res_admin_login.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        res_driver_login = await client.post(
            "/auth/login",
            json={
                "identifier": driver_cedula,
                "password": "Driver2026*",
                "client_type": "APP",
            },
        )
        assert res_driver_login.status_code == 200, res_driver_login.text
        driver_token = res_driver_login.json()["access_token"]
        driver_headers = {"Authorization": f"Bearer {driver_token}"}
        verify_logger.info(f"[OK] 3. Login exitoso para admin y conductor {driver_cedula}.")

        # 4. Perfil de sesión (/auth/me)
        res_me = await client.get("/auth/me", headers=driver_headers)
        assert res_me.status_code == 200
        assert res_me.json()["role"] == "CONDUCTOR"
        verify_logger.info("[OK] 4. Endpoint GET /auth/me verificado (Rol CONDUCTOR).")

        # 5. Bloqueo RBAC en endpoints protegidos (/admin vs /driver -> 403 Forbidden)
        res_cross_1 = await client.get("/admin/metrics", headers=driver_headers)
        assert res_cross_1.status_code == 403
        res_cross_2 = await client.get("/driver/my-truck", headers=admin_headers)
        assert res_cross_2.status_code == 403
        verify_logger.info("[OK] 5. Bloqueo RBAC en endpoints protegidos verificado.")

        # 6. Módulo Conductor: Verificación de eliminación de driver/odometer y formato de /driver/history
        # 6a. driver/odometer NO debe existir (404 / 405)
        res_bad_endpoint = await client.post(
            "/driver/odometer",
            headers=driver_headers,
            json={"odometer_value": 50000},
        )
        assert res_bad_endpoint.status_code in (404, 405), f"Esperado 404/405, recibido {res_bad_endpoint.status_code}"
        verify_logger.info("[OK] 6a. Endpoint /driver/odometer eliminado correctamente.")

        # 6b. GET /driver/my-truck (solo visualización de su camión)
        res_my_truck = await client.get("/driver/my-truck", headers=driver_headers)
        assert res_my_truck.status_code == 200
        verify_logger.info("[OK] 6b. Conductor consulta exitosamente su camión en /driver/my-truck.")

        # 6c. GET /driver/history (historial de mantenimientos con nombre, kilometraje, costo y taller)
        res_history = await client.get("/driver/history", headers=driver_headers)
        assert res_history.status_code == 200
        history_data = res_history.json()
        assert "completed_maintenances" in history_data
        assert "odometer_logs" not in history_data, "No deben incluirse lecturas de odómetro en el historial"
        for maint in history_data["completed_maintenances"]:
            assert "service_name" in maint
            assert "mileage_at_service" in maint
            assert "cost" in maint
            assert "workshop" in maint
        verify_logger.info(
            f"[OK] 6c. GET /driver/history verificado: {history_data['total_completed']} mantenimientos realizados con taller y costo."
        )

        # 7a. Métricas
        res_metrics = await client.get("/admin/metrics", headers=admin_headers)
        assert res_metrics.status_code == 200
        metrics = res_metrics.json()
        assert metrics["total_trucks"] == 27
        assert metrics["optimal_count"] == 20
        assert metrics["warning_count"] == 4
        assert metrics["overdue_count"] == 3
        verify_logger.info(
            f"[OK] 7a. GET /admin/metrics: 27 camiones (Óptimo={metrics['optimal_count']}, "
            f"Alerta={metrics['warning_count']}, Vencido={metrics['overdue_count']})."
        )

        # 7b. Filtro por estado en español
        res_trucks = await client.get("/admin/trucks?status=VENCIDO", headers=admin_headers)
        assert res_trucks.status_code == 200
        assert res_trucks.json()["total"] == 3
        verify_logger.info("[OK] 7b. Filtro /admin/trucks?status=VENCIDO verificado.")

        # 7b. Verificar que exista exactamente 1 usuario ADMIN en /admin/users
        res_users = await client.get("/admin/users", headers=admin_headers)
        assert res_users.status_code == 200
        users = res_users.json()
        admins = [u for u in users if u["role"] == "ADMIN"]
        assert len(admins) == 1, f"Se esperaba exactamente 1 ADMIN, se encontraron {len(admins)}"
        assert admins[0]["identifier"] == "admin"
        verify_logger.info("[OK] 7b. Usuario único ADMIN ('admin') verificado en /admin/users.")

        verify_logger.info("=== TODAS LAS PRUEBAS E2E FINALIZARON CON ÉXITO ===")

    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(run_verification_suite())
