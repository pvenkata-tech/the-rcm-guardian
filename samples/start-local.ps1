$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

New-Item -ItemType Directory -Force -Path (Join-Path $Root "samples\generated") | Out-Null

$envPath = Join-Path $Root ".env"
if (-not (Test-Path $envPath)) {
    Copy-Item (Join-Path $Root ".env.example") $envPath
    Write-Host "Created .env from .env.example — set OPENAI_API_KEY and LANGCHAIN_API_KEY (LangSmith is required). Optional: ANTHROPIC for vision fallback."
}

function Has-OpenAiKey {
    if ($env:OPENAI_API_KEY -match '\S') { return $true }
    if (-not (Test-Path $envPath)) { return $false }
    return Select-String -Path $envPath -Pattern '^\s*OPENAI_API_KEY\s*=\s*\S+' -Quiet
}

function Has-LangSmithKey {
    if ($env:LANGCHAIN_API_KEY -match '\S') { return $true }
    if (-not (Test-Path $envPath)) { return $false }
    return Select-String -Path $envPath -Pattern '^\s*LANGCHAIN_API_KEY\s*=\s*\S+' -Quiet
}

if (-not (Has-OpenAiKey)) {
    Write-Error "Set OPENAI_API_KEY in .env (see .env.example)."
    exit 1
}

if (-not (Has-LangSmithKey)) {
    Write-Error "Set LANGCHAIN_API_KEY in .env — LangSmith tracing is required (see .env.example)."
    exit 1
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "docker not found in PATH. Install Docker Desktop (or Docker Engine) and retry."
    exit 1
}
& docker compose version 2>&1 | Out-Null
if (-not $?) {
    Write-Error "docker compose is not available. Use Docker Compose V2 (docker compose, not legacy docker-compose)."
    exit 1
}

Write-Host "Starting stack (Postgres, LIMS mock, API, Prometheus, Grafana)..."
docker compose up --build
