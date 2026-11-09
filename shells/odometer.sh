#!/usr/bin/env bash
# ==============================================================================
# odometer.sh: Aumenta los kilometrajes según el script destinado para este fin
# ==============================================================================
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f "$ROOT_DIR/env/Scripts/python.exe" ]; then
    PYTHON_BIN="$ROOT_DIR/env/Scripts/python.exe"
elif [ -f "$ROOT_DIR/env/bin/python" ]; then
    PYTHON_BIN="$ROOT_DIR/env/bin/python"
elif [ -f "$ROOT_DIR/env/Scripts/python" ]; then
    PYTHON_BIN="$ROOT_DIR/env/Scripts/python"
else
    echo "[ERROR] No se encontró el entorno virtual en $ROOT_DIR/env"
    exit 1
fi

echo "[INFO] Incrementando kilometrajes de la flota con $PYTHON_BIN ..."
exec "$PYTHON_BIN" -m utils.simulate_odometer "$@"
