Param(
    [switch]$Clean,
    [string]$Python = "python"
)

$ErrorActionPreference = 'Stop'

Write-Host "== DynamicTechnologyTree Build Script ==" -ForegroundColor Cyan

if ($Clean) {
    Write-Host "Cleaning build, dist, __pycache__ ..." -ForegroundColor Yellow
    if (Test-Path build) { Remove-Item build -Recurse -Force }
    if (Test-Path dist) { Remove-Item dist -Recurse -Force }
    Get-ChildItem -Recurse -Include '__pycache__' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Checking PyInstaller..." -ForegroundColor Cyan
$piVersion = & $Python -c "import importlib, pkgutil, sys; print('yes' if importlib.util.find_spec('PyInstaller') else 'no')"
if ($piVersion -ne 'yes') {
    Write-Host "Installing PyInstaller..." -ForegroundColor Yellow
    & $Python -m pip install --upgrade pip
    & $Python -m pip install pyinstaller
}

Write-Host "Running PyInstaller..." -ForegroundColor Cyan
& $Python -m PyInstaller generate_tech_tree.spec

if (!$?) { throw "PyInstaller failed" }

Write-Host "Build complete. Output: dist\\generate_tech_tree.exe" -ForegroundColor Green
Write-Host "Remember: Place an editable config.ini next to the exe when running." -ForegroundColor Green
