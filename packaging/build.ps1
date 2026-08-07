# Builds the distributable WordMute folder (and installer, if Inno
# Setup is present). Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot
Set-Location $root

# 1. icon (kept in git; regenerate if missing)
if (-not (Test-Path "packaging\wordmute.ico")) {
    python scripts\make_icon.py
}

# 2. freeze
python -m PyInstaller packaging\wordmute.spec --noconfirm --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# 3. bundle ffmpeg (static build) from this machine so end users need
#    no separate install. GPL build — see docs/LICENSING.md.
$ffmpeg = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source
if ($ffmpeg) {
    $dest = "dist\WordMute\ffmpeg"
    New-Item -ItemType Directory -Force $dest | Out-Null
    Copy-Item $ffmpeg $dest
    $ffprobe = Join-Path (Split-Path $ffmpeg) "ffprobe.exe"
    if (Test-Path $ffprobe) { Copy-Item $ffprobe $dest }
    Write-Host "Bundled ffmpeg from $ffmpeg"
} else {
    Write-Warning "ffmpeg not found on PATH - dist will need a system ffmpeg"
}

# 4. installer (optional - needs Inno Setup 6 on PATH as iscc)
$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if ($iscc) {
    iscc packaging\installer.iss
} else {
    Write-Host "Inno Setup (iscc) not found - skipped installer compile."
    Write-Host "Install it (winget install JRSoftware.InnoSetup), then:"
    Write-Host "  iscc packaging\installer.iss"
}

Write-Host "`nDone. App folder: dist\WordMute\WordMute.exe"
