[CmdletBinding()]
param(
    [string]$Python = "python",
    [switch]$SkipInstall,
    [string]$ResticVersion = "latest"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not $SkipInstall) {
    & $Python -m pip install -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw "빌드 의존성 설치에 실패했습니다." }
}

$vendorDirectory = Join-Path $projectRoot "build-vendor\restic"
$resticExecutable = Join-Path $vendorDirectory "restic.exe"
New-Item -ItemType Directory -Force -Path $vendorDirectory | Out-Null

if ($ResticVersion -eq "latest") {
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/restic/restic/releases/latest"
    $ResticVersion = $release.tag_name.TrimStart("v")
}

$archive = Join-Path $vendorDirectory "restic.zip"
$downloadUrl = "https://github.com/restic/restic/releases/download/v$ResticVersion/restic_${ResticVersion}_windows_amd64.zip"
Write-Host "restic v$ResticVersion 다운로드 중..."
Invoke-WebRequest -Uri $downloadUrl -OutFile $archive
Expand-Archive -Path $archive -DestinationPath $vendorDirectory -Force
$downloadedExecutable = Join-Path $vendorDirectory "restic_${ResticVersion}_windows_amd64.exe"
if (-not (Test-Path $downloadedExecutable)) { throw "다운로드한 restic.exe를 찾을 수 없습니다." }
Copy-Item -Force $downloadedExecutable $resticExecutable

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name restic-gui `
    --add-data "frontend;frontend" `
    --add-binary "$resticExecutable;restic" `
    src/main.py

if ($LASTEXITCODE -ne 0) { throw "실행 파일 빌드에 실패했습니다." }

Write-Host "빌드 완료: $projectRoot\dist\restic-gui.exe"
