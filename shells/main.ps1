# ==============================================================================
# main.ps1: Inicia el backend FastAPI y su túnel público Cloudflare en Windows PowerShell.
# Sincroniza automáticamente la URL en Supabase (system_config) para Vercel y la App.
# ==============================================================================
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
Set-Location $RootDir

# 1. Detectar ejecutable de Python en el entorno virtual
$PythonBin = Join-Path $RootDir "env\Scripts\python.exe"
if (-not (Test-Path $PythonBin)) {
    Write-Host "[ERROR] No se encontró el entorno virtual en $RootDir\env" -ForegroundColor Red
    Write-Host "Cree el entorno virtual con: python -m venv env" -ForegroundColor Yellow
    exit 1
}

# 2. Localizar binario de Cloudflared
$cfCmd = Get-Command cloudflared -ErrorAction SilentlyContinue
$cfBin = $null
if ($cfCmd) {
    $cfBin = $cfCmd.Source
} elseif (Test-Path "C:\Program Files (x86)\cloudflared\cloudflared.exe") {
    $cfBin = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
} elseif (Test-Path "C:\Program Files\cloudflared\cloudflared.exe") {
    $cfBin = "C:\Program Files\cloudflared\cloudflared.exe"
} elseif (Test-Path "$RootDir\env\Scripts\cloudflared.exe") {
    $cfBin = "$RootDir\env\Scripts\cloudflared.exe"
}

$cfProc = $null

# 3. Iniciar túnel si está disponible
if ($cfBin) {
    New-Item -ItemType Directory -Force -Path "$RootDir\logs" | Out-Null
    $cfLog = Join-Path $RootDir "logs\cloudflared.log"
    Remove-Item $cfLog -Force -ErrorAction SilentlyContinue

    Write-Host "[INFO] Iniciando Cloudflare Tunnel inmediato con $cfBin..." -ForegroundColor Cyan
    $cfProc = Start-Process -FilePath $cfBin -ArgumentList "tunnel", "--protocol", "http2", "--url", "http://localhost:8000" -RedirectStandardError $cfLog -PassThru -NoNewWindow

    $publicUrl = ""
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Path $cfLog) {
            $content = Get-Content $cfLog -ErrorAction SilentlyContinue
            $match = $content | Select-String -Pattern "https://[a-zA-Z0-9.-]+\.trycloudflare\.com" | Select-Object -First 1
            if ($match) {
                $publicUrl = $match.Matches[0].Value
                break
            }
        }
    }

    if ($publicUrl) {
        Write-Host "========================================================================" -ForegroundColor Cyan
        Write-Host " [ÉXITO] Túnel Cloudflare Activo:" -ForegroundColor Green
        Write-Host "  • URL Pública:  $publicUrl" -ForegroundColor Yellow
        Write-Host "  • Swagger Docs: $publicUrl/docs"
        Write-Host "  • Health Check: $publicUrl/health"
        Write-Host "========================================================================" -ForegroundColor Cyan

        Write-Host "[INFO] Sincronizando URL en Supabase (system_config)..." -ForegroundColor Gray
        & $PythonBin -m utils.sync_tunnel_url $publicUrl

        $frontEnv = Join-Path $RootDir "..\camiones_frontend\.env"
        if (Test-Path $frontEnv) {
            "VITE_API_BASE_URL=$publicUrl" | Set-Content -Path $frontEnv -Encoding UTF8
        }
    } else {
        Write-Host "[AVISO] No se pudo capturar la URL del túnel. Continuando solo en local." -ForegroundColor Yellow
    }
} else {
    Write-Host "[AVISO] cloudflared no encontrado. El servidor iniciará solo en local (http://127.0.0.1:8000)." -ForegroundColor Yellow
    Write-Host "Para instalarlo: winget install Cloudflare.cloudflared" -ForegroundColor Gray
}

# 4. Iniciar servidor FastAPI con Uvicorn
try {
    Write-Host "[INFO] Arrancando servidor Uvicorn en http://0.0.0.0:8000 ..." -ForegroundColor Green
    & $PythonBin -m uvicorn scripts.main:app --host 0.0.0.0 --port 8000 --reload
} finally {
    if ($cfProc -and -not $cfProc.HasExited) {
        Write-Host "`n[INFO] Deteniendo proceso de Cloudflare Tunnel..." -ForegroundColor Yellow
        Stop-Process -Id $cfProc.Id -Force -ErrorAction SilentlyContinue
    }
}
