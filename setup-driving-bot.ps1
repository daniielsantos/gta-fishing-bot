# Cria C:\Users\daniel\gta-driving-bot e envia para o GitHub
# Rode na pasta do gta-fishing-bot:
#   .\setup-driving-bot.ps1

$ErrorActionPreference = "Stop"

$Source = Join-Path $PSScriptRoot "gta-driving-bot-planning"
$Target = "C:\Users\daniel\gta-driving-bot"
$Remote = "https://github.com/daniielsantos/gta-driving-bot.git"

if (-not (Test-Path $Source)) {
    Write-Error "Pasta nao encontrada: $Source`nAtualize o gta-fishing-bot (git pull) e tente de novo."
}

Write-Host "Origem:  $Source"
Write-Host "Destino: $Target"

New-Item -ItemType Directory -Force -Path $Target | Out-Null

Copy-Item -Path (Join-Path $Source "README.md") -Destination $Target -Force
Copy-Item -Path (Join-Path $Source "PLANNING.md") -Destination $Target -Force
Copy-Item -Path (Join-Path $Source "requirements.txt") -Destination $Target -Force
Copy-Item -Path (Join-Path $Source ".gitignore") -Destination $Target -Force

Set-Location $Target

if (-not (Test-Path .git)) {
    git init -b main
}

$hasOrigin = git remote 2>$null | Select-String -Pattern "^origin$" -Quiet
if (-not $hasOrigin) {
    git remote add origin $Remote
} else {
    git remote set-url origin $Remote
}

git add README.md PLANNING.md requirements.txt .gitignore
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m "docs: planejamento inicial do bot de direcao autonoma no GTA"
} else {
    Write-Host "Arquivos ja commitados."
}

git fetch origin main 2>$null
$hasRemote = git rev-parse --verify origin/main 2>$null
if ($LASTEXITCODE -eq 0) {
    git pull origin main --rebase --allow-unrelated-histories
}

git push -u origin main

Write-Host ""
Write-Host "Pronto! Projeto em: $Target"
Write-Host "GitHub: $Remote"
