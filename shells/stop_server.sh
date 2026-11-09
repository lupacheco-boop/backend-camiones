#!/usr/bin/env bash
# ==============================================================================
# stop_server.sh: Detiene el servidor FastAPI / Uvicorn y sus túneles públicos (Ngrok / Cloudflared)
# ==============================================================================

echo "========================================================================"
echo "    Deteniendo Servidor FastAPI y Túneles Públicos (Puerto 8000)       "
echo "========================================================================"

STOPPED=false

# 1. Detener procesos escuchando en el puerto 8000 (FastAPI / Uvicorn) en Windows
if command -v netstat >/dev/null 2>&1 && command -v taskkill >/dev/null 2>&1; then
    PIDS=$(netstat -ano 2>/dev/null | grep -E "(:8000\s+.*LISTENING)" | awk '{print $5}' | sort -u)
    for PID in $PIDS; do
        if [ "$PID" -gt 0 ] 2>/dev/null; then
            echo "[INFO] Deteniendo FastAPI en puerto 8000 (PID Windows: $PID)..."
            taskkill //F //PID "$PID" >/dev/null 2>&1 || true
            STOPPED=true
        fi
    done
fi

# 2. Detener procesos Uvicorn vía pgrep (Linux / macOS / Git Bash)
if command -v pgrep >/dev/null 2>&1; then
    UVICORN_PIDS=$(pgrep -f "scripts.main:app" 2>/dev/null || true)
    for PID in $UVICORN_PIDS; do
        echo "[INFO] Deteniendo Uvicorn (PID: $PID)..."
        kill -9 "$PID" >/dev/null 2>&1 || true
        STOPPED=true
    done
fi

# 3. Detener procesos de túneles públicos (Ngrok / Cloudflared)
echo "[INFO] Deteniendo túneles públicos asociados (Ngrok / Cloudflared)..."
if command -v taskkill >/dev/null 2>&1; then
    taskkill //F //IM "cloudflared.exe" >/dev/null 2>&1 || true
    taskkill //F //IM "ngrok.exe" >/dev/null 2>&1 || true
fi

if command -v pkill >/dev/null 2>&1; then
    pkill -9 -f "cloudflared" >/dev/null 2>&1 || true
    pkill -9 -f "ngrok" >/dev/null 2>&1 || true
fi

# 4. Verificación y limpieza de respaldo mediante PowerShell
if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command "
        \$connections = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue;
        if (\$connections) {
            foreach (\$c in \$connections) {
                Write-Host \"[INFO] PowerShell finalizando PID: \$(\$c.OwningProcess)\";
                Stop-Process -Id \$c.OwningProcess -Force -ErrorAction SilentlyContinue;
            }
        }
        Stop-Process -Name 'cloudflared' -Force -ErrorAction SilentlyContinue;
        Stop-Process -Name 'ngrok' -Force -ErrorAction SilentlyContinue;
    " >/dev/null 2>&1 || true
    STOPPED=true
fi

echo "[OK] Servidor FastAPI y túneles detenidos exitosamente. Puerto 8000 liberado."
echo "========================================================================"
