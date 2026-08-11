; Inno Setup 6 script for WordMute.
; Build dist\WordMute first (packaging\build.ps1), then: iscc packaging\installer.iss

#define MyAppName "WordMute"
; fallback for a bare `iscc installer.iss` run — build.ps1 overrides
; this with /DMyAppVersion=<wordmute_app.__version__>
#ifndef MyAppVersion
  #define MyAppVersion "0.5.0"
#endif
#define MyAppExeName "WordMute.exe"

[Setup]
AppId={{8B1F2C9D-53A4-4E1B-9C11-WORDMUTE0001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
; per-user install: no admin prompt, models/settings stay per-user anyway
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=WordMute-Setup-{#MyAppVersion}
; payload is ~3 GB (CUDA DLLs); /max compression would take very long
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
SetupIconFile=wordmute.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\WordMute\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\docs\INSTALL_GUIDE.md"; DestDir: "{app}"; \
    Flags: ignoreversion

[Icons]
; AppUserModelID must match main.py's APP_USER_MODEL_ID — Windows
; resolves the notification name/icon through this shortcut
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    AppUserModelID: "Baudi2.WordMute"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    AppUserModelID: "Baudi2.WordMute"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; \
    Description: "{cm:LaunchProgram,{#MyAppName}}"; \
    Flags: nowait postinstall skipifsilent
