# Build script for Windows EXE
$venvPath = ".venv-win"
$python = "$venvPath\Scripts\python.exe"
$pyinstaller = "$venvPath\Scripts\pyinstaller.exe"

if (-not (Test-Path $python)) {
    Write-Host "Creating virtual environment..."
    python -m venv $venvPath
}

Write-Host "Installing dependencies..."
& $python -m pip install PyQt6 pyinstaller

Write-Host "Building EXE..."
& $pyinstaller --noconfirm --onefile --windowed `
    --name "StellarisTechTreeGenerator" `
    --add-data "src/gui/fonts/NotoSansSC-Regular.otf;gui/fonts" `
    --paths "src" `
    scripts/generate_tech_tree_gui.py

Write-Host "Build complete! Check the 'dist' folder."
