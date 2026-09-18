# Packaging MediFlow

Produces a standalone app and a double-click installer for each target
platform: Windows (PyInstaller + Inno Setup) and macOS (PyInstaller + `hdiutil`).

Both platforms drive the **same** `mediflow.spec`. It branches on `sys.platform`
for the icon and the macOS `.app` wrapper; everything that is easy to get
subtly wrong — hidden imports, bundled `.qm` files, excluded Qt modules — is
written once so the two cannot drift apart.

---

## Windows

### One command

From the project root:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

This: generates the app icon → ensures PyInstaller is installed → builds the
app → builds the installer (if Inno Setup is present).

### Prerequisites

- The project's Windows virtual environment (`.venv-win`) with dependencies
  installed (`pip install -e ".[dev]"`).
- **Inno Setup 6** for the installer step — install once:
  ```powershell
  winget install JRSoftware.InnoSetup
  ```
  (The standalone app builds without it; only the `.exe` installer needs it.)

### Steps individually

```powershell
# 1. App icon  ->  assets\mediflow.ico
.\.venv-win\Scripts\python.exe packaging\make_icon.py

# 2. Standalone app  ->  dist\MediFlow\MediFlow.exe   (one-dir, windowed)
.\.venv-win\Scripts\python.exe -m PyInstaller packaging\mediflow.spec --noconfirm --clean

# 3. Installer  ->  dist_installer\MediFlow-Setup-0.2.0.exe
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\mediflow.iss
```

---

## macOS

### One command

From the project root:

```bash
bash packaging/build-macos.sh
```

This: generates the `.icns` → ensures PyInstaller is installed → builds
`dist/MediFlow.app` → signs it → packs `dist_installer/MediFlow-<version>.dmg`
with a drag-to-`/Applications` symlink.

### Prerequisites

- macOS 11 or later and the Xcode command line tools (`xcode-select --install`)
  — `codesign`, `iconutil` and `hdiutil` come from there.
- A virtual environment at `.venv-mac` with dependencies installed
  (`pip install -e ".[dev]"`), or any `python3` on `PATH`.

### Steps individually

```bash
# 1. App icon  ->  assets/mediflow.icns
./.venv-mac/bin/python packaging/make_icns.py

# 2. Standalone app  ->  dist/MediFlow.app   (one-dir, windowed)
./.venv-mac/bin/python -m PyInstaller packaging/mediflow.spec --noconfirm --clean

# 3. Disk image  ->  dist_installer/MediFlow-0.2.0.dmg
bash packaging/build-macos.sh        # steps 1-3 together; there is no separate one
```

### Signing and notarisation

Apple Silicon refuses to start an unsigned binary at all, so the build always
signs. What it signs *with* decides whether the result can leave the build Mac.

**Team:** `27RXPRW77S` (Apple Developer Program, Individual). This is the default
in `build-macos.sh` and is not a secret — it is embedded in every signed binary
and `codesign -dv --verbose=4 MediFlow.app` prints it. Override with
`MEDIFLOW_TEAM_ID`. No Apple ID, password or address belongs in this repository.

#### One-time setup on the build Mac

1. Create a **Developer ID Application** certificate at
   [developer.apple.com](https://developer.apple.com/account/resources/certificates)
   and install it in the login keychain. Confirm it is there:
   ```bash
   security find-identity -v -p codesigning | grep "Developer ID Application"
   ```
   `build-macos.sh` finds it by team id on its own — the certificate's name is
   the account holder's legal name on an Individual account, so there is nothing
   stable to hardcode.

2. Create an **app-specific password** at
   [account.apple.com](https://account.apple.com) → Sign-In and Security, then
   store the notarisation credentials in the keychain **once**:
   ```bash
   xcrun notarytool store-credentials "MediFlow" \
       --apple-id "<your-apple-id>" --team-id 27RXPRW77S --password "<app-specific-password>"
   ```
   From then on the build refers to the profile by name. The password lives in
   the build Mac's keychain — never in the repository, the environment, or a CI
   log. Override the profile name with `MEDIFLOW_NOTARY_PROFILE`.

After that, `bash packaging/build-macos.sh` produces a notarised, stapled `.dmg`
with no further arguments.

#### Why the stapling step is the one that matters here

MediFlow is deployed to clinics with no internet. Gatekeeper, on first launch of
a notarised app, will try to ask Apple's servers whether the app is notarised —
unless the ticket is **stapled** into the bundle, in which case it checks
locally. So the build staples the `.app` *before* packing it into the `.dmg`,
and staples the `.dmg` afterwards. Notarising only the disk image would leave
the installed app depending on a network call the clinic cannot make.

#### Why not `codesign --deep`

PyInstaller signs every collected Qt framework and C extension individually,
inside-out, using the identity and entitlements the spec hands it. That is the
only ordering notarisation accepts. `--deep` re-signs all of that nested code
with the *outer* entitlements and gets the submission rejected, which is why the
script signs only the bundle itself once a real identity is present. `--deep` is
still used for the ad-hoc path, where there is no certificate and nothing to
lose.

#### Hardened Runtime entitlements

Notarisation requires the Hardened Runtime, which stops a PyInstaller + PySide6
app from starting unless three exceptions are granted — CPython executes memory
it generates itself, and the bundle loads Qt frameworks signed by Apple rather
than by this team. They are in `packaging/entitlements.plist`, each with the
reason it is there. If the notarised app fails to launch, that file is the first
place to look, not the signing command.

#### Without a certificate

The build falls back to an ad-hoc signature. It runs on the build Mac. On any
other Mac it is refused, and a downloaded copy is quarantined outright:

```bash
xattr -dr com.apple.quarantine /Applications/MediFlow.app
```

That is a development workaround, not a distribution method — asking a clinic to
run `xattr` is asking them to disable the check that protects them.

### Architecture

The build is single-architecture — whatever the build Mac is. PySide6 publishes
no universal2 wheels, so an Apple Silicon build **will not launch on an Intel
Mac**. Build on each machine, or ship arm64 only and make that explicit to the
clinic.

---

## Files

| File | Purpose |
|------|---------|
| `mediflow.spec` | PyInstaller build for **both** platforms (one-dir, windowed, bundles `.qm`, collects all `mediflow` submodules — needed because models are imported dynamically). Adds `BUNDLE` on macOS. |
| `mediflow_launcher.py` | Frozen-app entry point → `mediflow.__main__:main`. |
| `make_icon.py` | Generates the multi-resolution `.ico` (teal medical cross). `render()` is the shared artwork. |
| `make_icns.py` | Generates the macOS `.icns` from the same `render()`, via `iconutil` (Pillow fallback). |
| `mediflow.iss` | Inno Setup: Program Files install, Start-menu + optional desktop shortcut, uninstaller. |
| `build.ps1` | Orchestrates the Windows build. |
| `build-macos.sh` | Orchestrates the macOS build, signing, notarisation and `.dmg`. |
| `entitlements.plist` | Hardened Runtime exceptions the notarised build needs to start. |

---

## Notes

- **One-dir, not one-file:** more reliable for Qt and much faster to start.
- **Per-user data:** the app stores its database, encryption key, logs and
  backups under `%APPDATA%\MediFlow` (Windows) or
  `~/Library/Application Support/MediFlow` (macOS), so a single machine-wide
  install serves every account with isolated data.
- **The encryption key is sealed to the account**, with DPAPI on Windows and the
  Keychain on macOS. On macOS this has a packaging consequence: a Keychain ACL is
  bound to the calling binary, so the first launch after an update — a different
  binary, as far as macOS is concerned — can prompt "MediFlow wants to use your
  confidential information". "Always Allow" settles it for that build. A
  consistent Developer ID signature avoids the prompt across updates entirely.
- **Output size:** ~140 MB (PySide6). The spec excludes unused Qt modules
  (WebEngine, Quick/QML, 3D, Multimedia) to keep it down.
- **Versioning:** bump the version in `mediflow/__init__.py` and `pyproject.toml`
  and `mediflow.iss` (`MyAppVersion`) together. The spec and `build-macos.sh`
  read it from `mediflow/__init__.py`, so they never need touching.
- `dist/`, `build/` and `dist_installer/` are build artifacts — safe to delete.
