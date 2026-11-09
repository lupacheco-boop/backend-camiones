#!/usr/bin/env bash
# ==============================================================================
# stop_odometer.sh: Detiene el proceso del simulador de kilometraje (simulate_odometer)
# ==============================================================================

echo "[INFO] Buscando procesos activos del simulador de odómetro..."

STOPPED=false

# 1. En entornos POSIX / Git Bash / Linux / Mac con pgrep
if command -v pgrep >/dev/null 2>&1; then
    ODO_PIDS=$(pgrep -f "utils.simulate_odometer" 2>/dev/null || true)
    for PID in $ODO_PIDS; do
        echo "[INFO] Deteniendo proceso simulador PID: $PID"
        kill -9 "$PID" >/dev/null 2>&1 || true
        STOPPED=true
    done
fi

# 2. En Windows vía WMIC / PowerShell buscando comandos que contengan simulate_odometer
if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command "
        \$procs = Get-CimInstance Win32_Process | Where-Object { \$_.CommandLine -like '*simulate_odometer*' };
        if (\$procs) {
            foreach (\$p in \$procs) {
                Write-Host \"Deteniendo simulador PID:\$($p.ProcessId)\";
                Stop-Process -Id \$p.ProcessId -Force -ErrorAction SilentlyContinue;
            }
        }
    " >/dev/null 2>&1 || true
    STOPPED=true
fi

echo "[OK] Procesos de simulación de odómetro finalizados."
