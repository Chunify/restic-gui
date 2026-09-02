[CmdletBinding()]
param(
    [string]$Python = "python",
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$iconPath = Join-Path $PSScriptRoot "icon.ico"
Set-Location $projectRoot

if (-not (Test-Path -LiteralPath $iconPath -PathType Leaf)) {
    throw "앱 아이콘을 찾을 수 없습니다: $iconPath"
}

if (-not $SkipInstall) {
    & $Python -m pip install -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw "빌드 의존성 설치에 실패했습니다." }
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name restic-gui `
    --icon "$iconPath" `
    --hidden-import win32timezone `
    --add-data "frontend;frontend" `
    src/main.py

if ($LASTEXITCODE -ne 0) { throw "실행 파일 빌드에 실패했습니다." }

Write-Host "빌드 완료: $projectRoot\dist\restic-gui.exe"
