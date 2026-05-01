$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

New-Item -ItemType Directory -Force -Path (Join-Path $Root "uploads") | Out-Null

$envPath = Join-Path $Root ".env"
if (-not (Test-Path $envPath)) {
    Copy-Item (Join-Path $Root ".env.example") $envPath
    Write-Host "Created .env from .env.example — set OPENAI_API_KEY (optional ANTHROPIC_API_KEY for vision fallback)."
}

function Has-OpenAiKey {
    if ($env:OPENAI_API_KEY -match '\S') { return $true }
    if (-not (Test-Path $envPath)) { return $false }
    return Select-String -Path $envPath -Pattern '^\s*OPENAI_API_KEY\s*=\s*\S+' -Quiet
}

if (-not (Has-OpenAiKey)) {
    Write-Error "Set OPENAI_API_KEY in .env (see .env.example)."
    exit 1
}

Write-Host "Starting stack (Postgres + pgvector, LIMS mock, API)..."
docker compose up --build
