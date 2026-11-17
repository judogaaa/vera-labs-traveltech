$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv-ml\Scripts\python.exe"
$frontPort = 5173
$apiPort = 8000

function Test-PortListening([int]$Port) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    return $null -ne $conn
}

function Wait-HttpOk([string]$Url, [int]$TimeoutSec = 60) {
    # Only 2xx counts as healthy. 404/3xx/5xx (and connection errors) are not success.
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300) {
                return $true
            }
        } catch {
            # Includes HTTP 4xx/5xx when -SkipHttpErrorCheck is unavailable.
            Start-Sleep -Milliseconds 500
            continue
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

if (-not (Test-Path $python)) {
    Write-Host @"
Missing .venv-ml\Scripts\python.exe

Create the project ML environment first (PowerShell):

  py -3.11 -m venv .venv-ml
  .\.venv-ml\Scripts\python.exe -m pip install -U pip
  .\.venv-ml\Scripts\python.exe -m pip install -r services\search_api\requirements.txt
  .\.venv-ml\Scripts\python.exe -m pip install pytest fastapi httpx python-dotenv pydantic reportlab python-multipart pillow "qrcode[pil]" arabic-reshaper python-bidi

Then copy .env.example to .env and set SEARCH_BACKEND=mock for local demo without Qdrant/indexer.
"@
    exit 1
}

if (Test-PortListening $frontPort) {
    Write-Host "Port $frontPort is already in use. Stop the process using it, then retry. Refusing to kill foreign processes."
    exit 1
}
if (Test-PortListening $apiPort) {
    Write-Host "Port $apiPort is already in use. Stop the process using it, then retry. Refusing to kill foreign processes."
    exit 1
}

Set-Location $projectRoot

$catalogDb = Join-Path $projectRoot "data\curated_hotels\catalog_db.json"
$hotelsJsonl = Join-Path $projectRoot "data\curated_hotels\hotels.jsonl"
if (-not (Test-Path $catalogDb)) {
    if (Test-Path $hotelsJsonl) {
        Write-Host "Building catalog_db.json from hotels.jsonl..."
        & $python -m services.catalog.import_curated_hotels
        if ($LASTEXITCODE -ne 0) {
            throw "Catalog bootstrap failed (exit $LASTEXITCODE)"
        }
    } else {
        Write-Warning "Catalog DB missing and data/curated_hotels/hotels.jsonl not found. /api/catalog will return 503 until import is possible."
    }
}

Write-Host "Starting API on 127.0.0.1:$apiPort ..."
$backend = Start-Process -FilePath $python -ArgumentList @(
    "-m", "uvicorn", "services.search_api.main:app",
    "--host", "127.0.0.1", "--port", "$apiPort"
) -WorkingDirectory $projectRoot -NoNewWindow -PassThru

try {
    if (-not (Wait-HttpOk "http://127.0.0.1:$apiPort/health" 60)) {
        throw "Backend did not become healthy on http://127.0.0.1:$apiPort/health within 60s"
    }
    Write-Host "Backend healthy. Starting Vite on 127.0.0.1:$frontPort ..."
    & npm run dev
    if ($LASTEXITCODE -ne 0) {
        throw "Vite exited with code $LASTEXITCODE"
    }
} finally {
    if ($backend -and -not $backend.HasExited) {
        # Stop the uvicorn process tree we started (not unrelated PIDs).
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$($backend.Id)" -ErrorAction SilentlyContinue |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    }
}
