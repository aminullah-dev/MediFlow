# Build the MediFlow Windows installer.
# Run from the project root:  powershell -ExecutionPolicy Bypass -File packaging\build.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = Join-Path $root ".venv-win\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Write-Host "==> Generating application icon" -ForegroundColor Cyan
& $py packaging\make_icon.py

Write-Host "==> Ensuring PyInstaller is installed" -ForegroundColor Cyan
& $py -m pip install --quiet pyinstaller

Write-Host "==> Building the app with PyInstaller (one-dir, windowed)" -ForegroundColor Cyan
& $py -m PyInstaller packaging\mediflow.spec --noconfirm --clean --distpath dist --workpath build

$exe = Join-Path $root "dist\MediFlow\MediFlow.exe"
if (-not (Test-Path $exe)) { throw "PyInstaller build did not produce $exe" }
Write-Host "==> App built: $exe" -ForegroundColor Green

Write-Host "==> Building the installer with Inno Setup" -ForegroundColor Cyan
# winget installs Inno Setup per-user (LOCALAPPDATA); also cover machine installs.
$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    $iscc = (Get-ChildItem -Path "$env:ProgramFiles", "${env:ProgramFiles(x86)}", "$env:LOCALAPPDATA\Programs" `
        -Recurse -Filter ISCC.exe -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
}

if ($iscc) {
    & $iscc packaging\mediflow.iss
    Write-Host "==> Installer written to dist_installer\" -ForegroundColor Green
} else {
    Write-Host "Inno Setup 6 not found." -ForegroundColor Yellow
    Write-Host "Install it from https://jrsoftware.org/isdl.php then run:" -ForegroundColor Yellow
    Write-Host '  & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\mediflow.iss' -ForegroundColor Yellow
    Write-Host "(The standalone app already works: dist\MediFlow\MediFlow.exe)" -ForegroundColor Yellow
}
