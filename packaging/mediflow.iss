; Inno Setup script for MediFlow — builds a Windows installer from the
; PyInstaller one-dir output (dist\MediFlow). Compile with:
;     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\mediflow.iss
; (paths below are relative to this .iss file, i.e. the packaging\ folder).

#define MyAppName "MediFlow"
#define MyAppVersion "0.2.0"
#define MyAppPublisher "MediFlow"
#define MyAppExeName "MediFlow.exe"

[Setup]
; A stable, unique application id (do not reuse for other apps).
AppId={{7C2F1E64-9A3B-4E2D-8F5A-2B6D1C9A4E10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\MediFlow
DefaultGroupName=MediFlow
DisableProgramGroupPage=yes
OutputDir=..\dist_installer
OutputBaseFilename=MediFlow-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\mediflow.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The entire PyInstaller one-dir output.
Source: "..\dist\MediFlow\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\MediFlow"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall MediFlow"; Filename: "{uninstallexe}"
Name: "{autodesktop}\MediFlow"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,MediFlow}"; Flags: nowait postinstall skipifsilent
