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

# 3. slim build: ffmpeg is NOT bundled — the app downloads it into the
#    managed runtime on first run (also sidesteps GPL redistribution).

# 4. installer (optional - needs Inno Setup 6)
$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    foreach ($candidate in @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $candidate) { $iscc = $candidate; break }
    }
}
if ($iscc) {
    & $iscc packaging\installer.iss
} else {
    Write-Host "Inno Setup (iscc) not found - skipped installer compile."
    Write-Host "Install it (winget install JRSoftware.InnoSetup), then:"
    Write-Host "  iscc packaging\installer.iss"
}

Write-Host "`nDone. App folder: dist\WordMute\WordMute.exe"
