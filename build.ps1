Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$dist = Join-Path $root "dist"
$build = Join-Path $root "build"

if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }
if (Test-Path $build) { Remove-Item $build -Recurse -Force }

python -m PyInstaller `
  --noconfirm `
  --onefile `
  --windowed `
  --icon "assets\ui\app_icon.ico" `
  --name FocusDawn `
  --add-data "README.md;." `
  --add-data "requirements.txt;." `
  --add-data "assets;assets" `
  main.py
