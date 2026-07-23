# Packaging MediFlow for Windows

Produces a standalone Windows app (PyInstaller) and a double-click installer
(Inno Setup).

## One command

From the project root:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

This: generates the app icon → ensures PyInstaller is installed → builds the
app → builds the installer (if Inno Setup is present).

## Prerequisites

- The project's Windows virtual environment (`.venv-win`) with dependencies
  installed (`pip install -e ".[dev]"`).
- **Inno Setup 6** for the installer step — install once:
  ```powershell
  winget install JRSoftware.InnoSetup
  ```
  (The standalone app builds without it; only the `.exe` installer needs it.)

## Steps individually

```powershell
# 1. App icon  ->  assets\mediflow.ico
.\.venv-win\Scripts\python.exe packaging\make_icon.py

# 2. Standalone app  ->  dist\MediFlow\MediFlow.exe   (one-dir, windowed)
.\.venv-win\Scripts\python.exe -m PyInstaller packaging\mediflow.spec --noconfirm --clean

# 3. Installer  ->  dist_installer\MediFlow-Setup-0.1.0.exe
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\mediflow.iss
```

## Files

| File | Purpose |
|------|---------|
| `make_icon.py` | Generates the multi-resolution `.ico` (teal medical cross). |
| `mediflow_launcher.py` | Frozen-app entry point → `mediflow.__main__:main`. |
| `mediflow.spec` | PyInstaller build (one-dir, windowed, bundles `.qm`, collects all `mediflow` submodules — needed because models are imported dynamically). |
| `mediflow.iss` | Inno Setup: Program Files install, Start-menu + optional desktop shortcut, uninstaller. |
| `build.ps1` | Orchestrates all of the above. |

## Notes

- **One-dir, not one-file:** more reliable for Qt and much faster to start.
- **Per-user data:** the app stores its database, encryption key, logs and
  backups under `%APPDATA%\MediFlow`, so a single machine-wide install serves
  every Windows user with isolated data.
- **Output size:** ~140 MB (PySide6). The spec excludes unused Qt modules
  (WebEngine, Quick/QML, 3D, Multimedia) to keep it down.
- **Versioning:** bump the version in `mediflow/__init__.py`, `pyproject.toml`
  and `mediflow.iss` (`MyAppVersion`) together.
- `dist\`, `build\` and `dist_installer\` are build artifacts — safe to delete.
