#!/usr/bin/env bash
# ==============================================================================
# main.sh: Inicia el servidor backend FastAPI y su túnel público (Ngrok / Cloudflared),
# sincronizando automáticamente la URL pública en ../camiones_frontend/.env
# ==============================================================================
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# 1. Detectar intérprete de Python en el entorno virtual
if [ -f "$ROOT_DIR/env/Scripts/python.exe" ]; then
    PYTHON_BIN="$ROOT_DIR/env/Scripts/python.exe"
elif [ -f "$ROOT_DIR/env/bin/python" ]; then
    PYTHON_BIN="$ROOT_DIR/env/bin/python"
elif [ -f "$ROOT_DIR/env/Scripts/python" ]; then
    PYTHON_BIN="$ROOT_DIR/env/Scripts/python"
else
    echo "[ERROR] No se encontró el entorno virtual en $ROOT_DIR/env"
    echo "Cree el entorno virtual con: python -m venv env"
    exit 1
fi

# 2. Procesar opciones de túnel
ENABLE_TUNNEL=true
PREFER_NGROK=false
FILTERED_ARGS=()

for arg in "$@"; do
    case "$arg" in
        --no-tunnel)
            ENABLE_TUNNEL=false
            ;;
        --ngrok)
            PREFER_NGROK=true
            ;;
        *)
            FILTERED_ARGS+=("$arg")
            ;;
    esac
done

# 3. Detectar binarios de túneles
NGROK_BIN=""
CF_BIN=""

if [ -f "$ROOT_DIR/env/Scripts/ngrok.exe" ]; then
    NGROK_BIN="$ROOT_DIR/env/Scripts/ngrok.exe"
elif command -v ngrok >/dev/null 2>&1; then
    NGROK_BIN="ngrok"
fi

if [ -f "$ROOT_DIR/env/Scripts/cloudflared.exe" ]; then
    CF_BIN="$ROOT_DIR/env/Scripts/cloudflared.exe"
elif [ -f "/c/Program Files (x86)/cloudflared/cloudflared.exe" ]; then
    CF_BIN="/c/Program Files (x86)/cloudflared/cloudflared.exe"
elif command -v cloudflared >/dev/null 2>&1; then
    CF_BIN="cloudflared"
fi

TUNNEL_PID=""
cleanup() {
    if [ -n "$TUNNEL_PID" ]; then
        echo ""
        echo "[INFO] Finalizando túnel público (PID: $TUNNEL_PID)..."
        kill -9 "$TUNNEL_PID" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT INT TERM

PUBLIC_URL=""

if [ "$ENABLE_TUNNEL" = true ]; then
    mkdir -p "$ROOT_DIR/logs"
    echo "========================================================================"
    echo "    Iniciando Túnel Público para Acceso Externo (4G/5G / Celular)      "
    echo "========================================================================"

    # Determinar si Ngrok tiene un token configurado
    NGROK_CONFIGURED=false
    if [ -n "$NGROK_BIN" ]; then
        if [ -f "$LOCALAPPDATA/ngrok/ngrok.yml" ] || [ -f "$HOME/.config/ngrok/ngrok.yml" ]; then
            if grep -q "authtoken:" "$LOCALAPPDATA/ngrok/ngrok.yml" 2>/dev/null || grep -q "authtoken:" "$HOME/.config/ngrok/ngrok.yml" 2>/dev/null; then
                NGROK_CONFIGURED=true
            fi
        fi
    fi

    if [ "$PREFER_NGROK" = true ] && [ "$NGROK_CONFIGURED" = true ]; then
        echo "[INFO] Utilizando túnel Ngrok..."
        "$NGROK_BIN" http 8000 --log=stdout > "$ROOT_DIR/logs/ngrok.log" 2>&1 &
        TUNNEL_PID=$!
        for i in {1..10}; do
            PUBLIC_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | grep -o 'https://[^"]*ngrok-free.app' | head -n 1 || true)
            [ -n "$PUBLIC_URL" ] && break
            sleep 1
        done
    elif [ -n "$CF_BIN" ]; then
        echo "[INFO] Utilizando Cloudflare Tunnel inmediato (protocolo TCP HTTP/2)..."
        CF_LOG="$ROOT_DIR/logs/cloudflared.log"
        rm -f "$CF_LOG"
        "$CF_BIN" tunnel --protocol http2 --url http://localhost:8000 > "$CF_LOG" 2>&1 &
        TUNNEL_PID=$!
        for i in {1..15}; do
            if [ -f "$CF_LOG" ]; then
                PUBLIC_URL=$(grep -o 'https://[a-zA-Z0-9.-]*\.trycloudflare\.com' "$CF_LOG" | head -n 1 || true)
                [ -n "$PUBLIC_URL" ] && break
            fi
            sleep 1
        done
    elif [ "$NGROK_CONFIGURED" = true ]; then
        echo "[INFO] Utilizando túnel Ngrok..."
        "$NGROK_BIN" http 8000 --log=stdout > "$ROOT_DIR/logs/ngrok.log" 2>&1 &
        TUNNEL_PID=$!
        for i in {1..10}; do
            PUBLIC_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | grep -o 'https://[^"]*ngrok-free.app' | head -n 1 || true)
            [ -n "$PUBLIC_URL" ] && break
            sleep 1
        done
    else
        echo "[AVISO] No se pudo iniciar el túnel automáticamente. Asegúrese de tener 'cloudflared' o 'ngrok' instalado."
    fi

    # Sincronizar automáticamente la URL pública con Supabase y con el frontend
    if [ -n "$PUBLIC_URL" ]; then
        echo "[INFO] Registrando URL del túnel en Supabase (system_config) para descubrimiento automático en Vercel..."
        "$PYTHON_BIN" -m utils.sync_tunnel_url "$PUBLIC_URL" || echo "[AVISO] No se pudo registrar la URL en Supabase."

        FRONTEND_ENV="$ROOT_DIR/../camiones_frontend/.env"
        if [ -f "$FRONTEND_ENV" ]; then
            echo "VITE_API_BASE_URL=$PUBLIC_URL" > "$FRONTEND_ENV"
            echo "[OK] Sincronizado automáticamente en: $FRONTEND_ENV"
        fi
        echo "------------------------------------------------------------------------"
        echo " [ÉXITO] Túnel Activo y Sincronizado en Supabase:"
        echo "  • URL Pública:  $PUBLIC_URL"
        echo "  • Swagger Docs: $PUBLIC_URL/docs"
        echo "  • Health Check: $PUBLIC_URL/health"
        echo "========================================================================"
    fi
fi

echo "[INFO] Arrancando servidor Uvicorn en http://0.0.0.0:8000 ..."
"$PYTHON_BIN" -m uvicorn scripts.main:app --host 0.0.0.0 --port 8000 --reload "${FILTERED_ARGS[@]}"
