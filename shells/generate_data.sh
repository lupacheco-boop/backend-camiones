#!/usr/bin/env bash
# ==============================================================================
# generate_data.sh: Ejecuta el script encargado de la data sintética
# de los 27 camiones y usuarios (a excepción de admin) y sube la info a la DB.
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

echo "[INFO] Generando y sincronizando data sintética de 27 camiones y usuarios (a excepción de admin)..."
exec "$PYTHON_BIN" -m utils.seed_fleet --reset "$@"
