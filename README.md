# Sistema de Monitoreo de Kilometraje y Gestión de Mantenimiento Preventivo de Flota (27 Camiones)

Backend modular, asíncrono y de alto rendimiento desarrollado con **Python (3.12 - 3.14)**, **FastAPI**, **SQLAlchemy 2.0 (asyncpg)** y **Supabase (PostgreSQL Cloud)**.

Centraliza toda la lógica de negocio, reglas matemáticas de evaluación preventiva, persistencia relacional y control de acceso basado en roles (**RBAC estricto y mutuamente excluyente**) para dos plataformas cliente:

1. **Plataforma Web (Dashboard Administrativo):** Exclusivo para el rol `ADMIN`. Gestiona unidades, conductores, analítica global de la flota, catálogo de planes preventivos y registro de mantenimientos con costos y talleres. Desplegado en producción en **Vercel**: [https://camionesfrontend.vercel.app](https://camionesfrontend.vercel.app).
2. **Aplicación Móvil (App de Conductores):** Exclusivo para el rol `CONDUCTOR`. Desarrollada en **Flutter**, diseñada para uso táctil ergonómico en cabina (Claymorphism). Permite al conductor consultar en tiempo real el odómetro de su unidad asignada, alertas de salud y su historial de servicios completados.

---

## ⚡ Novedad: Handshake y Descubrimiento Dinámico Cloudflare ⇄ Supabase

Este proyecto implementa una **arquitectura de descubrimiento dinámico en tiempo real**:
- Cada vez que se arranca el backend con [`shells/main.sh`](file:///shells/main.sh) o [`shells/main.ps1`](file:///shells/main.ps1), se levanta automáticamente un túnel seguro **Cloudflare** (`https://xxxx.trycloudflare.com`).
- El script registra esa URL inmediatamente en la tabla `system_config` de **Supabase PostgreSQL**.
- **Tanto el Frontend en Vercel como la App Móvil Flutter detectan automáticamente la nueva URL al iniciar.**
- **No es necesario crear cuentas, configurar tokens de Ngrok ni modificar manualmente variables de entorno (`.env`) en ningún cliente al reiniciar el servidor.**

---

## 1. Requisitos Previos del Sistema

Para ejecutar este backend en cualquier equipo se requiere:

1. **Python 3.14:**
   - Compruebe su versión con:
     ```bash
     python --version
     ```
   - Si no lo tiene instalado, descárguelo desde [python.org](https://www.python.org/downloads/) asegurándose de marcar la casilla **"Add Python to PATH"**.

2. **Cloudflare Tunnel (`cloudflared`):**
   - Es la herramienta que publica el backend local en internet de forma segura para que la App móvil y Vercel puedan conectarse desde cualquier red externa (4G/5G/Wi-Fi).
   - **Es 100% gratuito y no requiere registrar tarjetas ni crear cuentas.**
   - **Instalación en Windows:**
     ```powershell
     winget install Cloudflare.cloudflared
     ```
     *(O descargue directamente `cloudflared-windows-amd64.exe` desde [Cloudflare GitHub Releases](https://github.com/cloudflare/cloudflared/releases) y colóquelo en su PATH o dentro de `env/Scripts/`).*
   - **Instalación en macOS:**
     ```bash
     brew install cloudflare/cloudflare/cloudflared
     ```
   - **Instalación en Linux (Ubuntu/Debian):**
     ```bash
     sudo apt-get install cloudflared
     ```

3. **Git y Terminal:**
   - En Windows: **PowerShell** o **Git Bash**.
   - En Linux / macOS: Terminal estándar Bash / Zsh.

---

## 2. Instalación y Puesta en Marcha Paso a Paso

### Paso 1: Posicionarse en la carpeta del backend
```bash
cd camiones_backend
```

### Paso 2: Crear el entorno virtual (`env/`)
- **Windows (PowerShell / CMD):**
  ```powershell
  python -m venv env
  ```
- **Linux / macOS / Git Bash:**
  ```bash
  python3 -m venv env
  ```

### Paso 3: Activar el entorno virtual
- **En Windows PowerShell:**
  ```powershell
  .\env\Scripts\Activate.ps1
  ```
  *(Si PowerShell muestra error de permisos de ejecución, habilítelo para la sesión actual con: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` y vuelva a ejecutar el comando).*
- **En Windows CMD:**
  ```cmd
  .\env\Scripts\activate.bat
  ```
- **En Git Bash / Linux / macOS:**
  ```bash
  source env/Scripts/activate    # En Windows Git Bash
  # o
  source env/bin/activate        # En Linux / macOS
  ```

### Paso 4: Instalar librerías requeridas
Con el entorno virtual activo, actualice `pip` e instale las dependencias de [`requirements.txt`](file:///requirements.txt):
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Paso 5: Configurar variables de entorno (`.env`)
Copie la plantilla de ejemplo [`.env.example`](file:///.env.example) o configure su archivo `.env` en la raíz del proyecto con las credenciales de su base de datos y entorno:

```env
# Base de Datos PostgreSQL Cloud (Supabase Transaction Pooler - Puerto 6543)
DATABASE_URL="postgresql+asyncpg://<USUARIO_DB>:<PASSWORD_DB>@<HOST_SUPABASE>:6543/postgres"

# Seguridad y Criptografía JWT (Algoritmo HS256)
JWT_SECRET_KEY="<TU_CLAVE_SECRETA_CRIPTOGRAFICA_DE_256_BITS>"
JWT_ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=720

# Servidor ASGI Uvicorn y CORS
HOST="0.0.0.0"
PORT=8000
CORS_ORIGINS="*"
ENVIRONMENT="development"
DEBUG=True
```

---

## 3. Ejecución del Servidor Backend

El backend cuenta con scripts inteligentes que levantan la API, inician Cloudflare y publican la URL en Supabase automáticamente:

### Opción A: Desde Windows PowerShell (Recomendado en Windows)
Ejecute directamente:
```powershell
.\shells\main.ps1
```

### Opción B: Desde Git Bash / Linux / macOS
```bash
bash shells/main.sh
```

#### ¿Qué hace este comando automáticamente?
1. Detecta y usa el intérprete de Python dentro de `env/`.
2. Inicia el proceso de Cloudflare Tunnel en segundo plano hacia `http://localhost:8000`.
3. Extrae la URL pública HTTPS asignada (ejemplo: `https://xxxx.trycloudflare.com`).
4. Sincroniza la URL en la tabla `system_config` de Supabase para que el Frontend web y la App móvil se conecten inmediatamente.
5. Inicia el servidor **Uvicorn** en `http://0.0.0.0:8000` con recarga automática en caliente (*hot-reload*).
6. Al presionar `Ctrl + C`, finaliza limpiamente tanto el servidor como el proceso del túnel.

*Opciones avanzadas para Bash:*
- `bash shells/main.sh --no-tunnel`: Inicia solo el servidor local en `http://127.0.0.1:8000` sin levantar túneles externos.

---

### Detener el servidor y liberar puertos
Si el servidor quedó corriendo en segundo plano o el puerto `8000` quedó ocupado:
- **En Git Bash / Linux:**
  ```bash
  bash shells/stop_server.sh
  ```
- **En PowerShell:**
  ```powershell
  Stop-Process -Name python, cloudflared -Force -ErrorAction SilentlyContinue
  ```

---

## 4. Credenciales de Acceso al Sistema

El sistema implementa una estricta política de **Control de Acceso Basado en Roles (RBAC)** definida en [`utils\seed_fleet.py`](file:///utils/seed_fleet.py):

| Rol | Usuario / Identificador | Contraseña | Plataforma Permitida | Acción ante Acceso Cruzado |
| :--- | :--- | :--- | :--- | :--- |
| **`ADMIN`** | `admin` | `Admin2026*` | **Exclusivo Plataforma Web** | Si intenta entrar en la App móvil, se bloquea con **403 Forbidden**. |
| **`CONDUCTOR`** | Cédula ecuatoriana de 10 dígitos (ej. `0997663476`) | `Driver2026*` | **Exclusivo App Móvil** | Si intenta entrar en la Web, se bloquea con **403 Forbidden**. |

### Ejemplos de cédulas de conductores disponibles:
- `0997663476` (Conductor del camión GBA-7101)
- `0929926773` (Conductor del camión GBA-7102)
- `0988788330` (Conductor del camión GBA-7103)
- *(O cualquiera de los 27 conductores registrados en el dashboard)*

---

## 5. Plataformas Clientes Disponibles

### 1. Plataforma Web (Vercel)
- **URL Pública:** [https://camionesfrontend.vercel.app](https://camionesfrontend.vercel.app)
- **Acceso:** Inicie sesión con `admin` y `Admin2026*`.
- **Handshake automático:** La web consulta su función serverless `/api/backend-url`, la cual lee en tiempo real la URL de Cloudflare desde Supabase.

### 2. Aplicación Móvil (Android APK)
- **Instalador APK listo para instalar:** Ubicado en [`camiones_app/build/app/outputs/flutter-apk/app-release.apk`](file:///C:/Users/ntole/OneDrive/Desktop/camiones_app/build/app/outputs/flutter-apk/app-release.apk).
- **Acceso:** Inicie sesión con una cédula de conductor y la contraseña `Driver2026*`.
- **Autodescubrimiento:** Al abrirse, autodetecta la URL del túnel. También cuenta con un botón superior **`☁️ Servidor`** para probar o cambiar la URL manualmente en caso de emergencia.

### 3. Documentación Interactiva Swagger / OpenAPI
Con el backend encendido, puede probar y consultar todos los contratos REST de la API en:
- Local: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Vía túnel: `https://<tu-subdominio>.trycloudflare.com/docs`
- Health check: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

---

## 6. Scripts Auxiliares y Herramientas (`utils/` y `shells/`)

| Script | Propósito | Cuándo usarlo |
| :--- | :--- | :--- |
| [`shells/main.ps1`](file:///shells/main.ps1) | Arranca API + Cloudflare + Supabase Sync en PowerShell. | Uso diario en Windows. |
| [`shells/main.sh`](file:///shells/main.sh) | Arranca API + Cloudflare + Supabase Sync en Bash. | Uso diario en Linux, Mac o Git Bash. |
| [`shells/stop_server.sh`](file:///shells/stop_server.sh) | Apaga procesos y libera el puerto 8000. | Cuando se requiera detener el backend por completo. |
| [`utils/sync_tunnel_url.py`](file:///utils/sync_tunnel_url.py) | Registra la URL del túnel en la tabla `system_config`. | Invocado automáticamente por `main.sh`/`main.ps1`. |
| [`utils/verify_api.py`](file:///utils/verify_api.py) | Suite de pruebas automatizadas E2E de roles y endpoints. | Para validar que todos los endpoints respondan con 200/403 según su rol: `python -m utils.verify_api`. |
| [`utils/seed_fleet.py`](file:///utils/seed_fleet.py) | Borra y reconstruye la data de prueba en Supabase. | **Opcional:** Solo si se desea reiniciar la base de datos de cero (`python -m utils.seed_fleet --reset`). |
| [`utils/simulate_odometer.py`](file:///utils/simulate_odometer.py) | Simula el avance de kilometraje en tiempo real (IoT). | **Opcional:** Para demos de odómetro en vivo (`bash shells/odometer.sh`). |

---

## 7. Estructura Arquitectónica del Backend (`scripts/`)

```text
camiones_backend/
├── .env                              # Configuración activa de entorno y secretos
├── requirements.txt                  # Librerías Python versionadas
├── shells/
│   ├── main.ps1                      # Ejecutor integral para Windows PowerShell
│   ├── main.sh                       # Ejecutor integral para Bash (Linux / Git Bash)
│   ├── stop_server.sh                # Detención de procesos del backend
│   ├── generate_data.sh              # Disparador de semilla de base de datos
│   ├── odometer.sh                   # Disparador de simulación de kilometraje
│   └── stop_odometer.sh              # Detención de simulador de kilometraje
├── utils/
│   ├── sync_tunnel_url.py            # Puente de sincronización Cloudflare -> Supabase
│   ├── verify_api.py                 # Suite de validación y pruebas E2E
│   ├── seed_fleet.py                 # Generador de datos relacionales sintéticos
│   └── simulate_odometer.py          # Simulador de telemetría IoT de kilometraje
└── scripts/                          # Código fuente en arquitectura limpia POO
    ├── main.py                       # Fábrica FastAPI, lifespan y registro de routers
    ├── api/
    │   ├── dependencies.py           # Guardias de seguridad RBAC y caché de sesión
    │   ├── middlewares.py            # Auditoría de tiempos de respuesta y headers
    │   └── routers/
    │       ├── auth_router.py        # /auth/login, /auth/me
    │       ├── driver_router.py      # /driver/my-truck, /driver/history
    │       └── admin_router.py       # /admin/metrics, /admin/trucks, /admin/maintenance
    ├── core/
    │   ├── config.py                 # Pydantic Settings tipado desde .env
    │   ├── security.py               # Bcrypt y JWT (HS256)
    │   ├── logger.py                 # Logger unificado diario rotativo
    │   └── exceptions.py             # Excepciones de negocio y mapeo HTTP
    ├── database/
    │   └── session.py                # Motor SQLAlchemy asyncpg optimizado para Supavisor
    ├── models/
    │   └── entities.py               # Entidades ORM (Truck, User, MaintenanceRecord, etc.)
    ├── schemas/
    │   ├── auth_schemas.py           # DTOs de autenticación
    │   ├── driver_schemas.py         # DTOs para la app de conductor
    │   └── admin_schemas.py          # DTOs para el panel administrativo
    └── services/
        ├── auth_service.py           # Lógica de login y verificación de credenciales
        ├── driver_service.py         # Consultas de conductor
        ├── admin_service.py          # Lógica administrativa (camiones, métricas, taller)
        └── maintenance_engine.py     # Motor matemático de cálculo de estados preventivos
```

---

## 8. Estados del Negocio en Español

El sistema clasifica la salud de cada unidad evaluando su odómetro actual frente al kilometraje programado y la tolerancia de cada plan:

- **`OPTIMO`:** El camión opera dentro del kilometraje normal y sin proximidad a mantenimientos.
- **`ALERTA`:** El odómetro ingresó en el umbral de anticipación (`tolerancia_km`) antes del vencimiento. Requiere agendamiento de taller.
- **`VENCIDO`:** El odómetro igualó o superó el kilometraje programado. La unidad requiere atención correctiva inmediata.

Estados de órdenes de trabajo (`maintenance_records`):
- **`PROGRAMADO`:** Servicio preventivo pendiente asignado a un kilometraje futuro.
- **`COMPLETADO`:** Servicio efectuado con fecha, costo y taller registrados.

---

## 9. Preguntas Frecuentes y Solución de Problemas

#### ¿Qué hago si al ejecutar `.\shells\main.ps1` PowerShell dice que está deshabilitada la ejecución de scripts?
Abra PowerShell y ejecute:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```
Luego vuelva a ejecutar `.\shells\main.ps1`.

#### ¿Por qué no necesito configurar ninguna IP en la app móvil ni en Vercel?
Porque `main.ps1` / `main.sh` actualiza la URL del túnel en Supabase automáticamente. La web en Vercel y la App móvil leen esa tabla en tiempo real en cada inicio.

#### ¿Cómo verifico que la base de datos está respondiendo?
Ejecute la verificación de salud en el navegador:
`http://localhost:8000/health` o consulte la tabla de camiones desde `http://localhost:8000/docs`.
