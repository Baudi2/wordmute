; Inno Setup 6 script for WordMute.
; Build dist\WordMute first (packaging\build.ps1), then: iscc packaging\installer.iss

#define MyAppName "WordMute"
; the version comes from wordmute_app/__init__.py via build.ps1
; (/DMyAppVersion=…); a bare `iscc installer.iss` used to fall back to
; a stale number and ship a mislabelled installer
#ifndef MyAppVersion
  #error Pass the version: iscc /DMyAppVersion=<wordmute_app.__version__> installer.iss (or run packaging\build.ps1)
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

[CustomMessages]
english.RemoveDataQuestion=Also delete the downloaded components, settings, word lists and history?%n%n%1  (components, 1–2.5 GB)%n%2  (settings, word lists, history)%n%nThe recognition models in %3 are kept either way — delete that folder by hand if you no longer need them.
russian.RemoveDataQuestion=Удалить также загруженные компоненты, настройки, списки слов и историю?%n%n%1  (компоненты, 1–2,5 ГБ)%n%2  (настройки, списки слов, история)%n%nМодели распознавания в %3 в любом случае остаются — удалите эту папку вручную, если они больше не нужны.

[Code]
// The uninstaller only removes {app} (~160 MB); the app's own
// downloads live elsewhere and used to stay behind silently — several
// gigabytes with no visible owner. Ask, default to keeping.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Runtime, Data, Models: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Runtime := ExpandConstant('{localappdata}\WordMute');
    Data := ExpandConstant('{userappdata}\WordMute');
    Models := ExpandConstant('{%USERPROFILE}\.cache\huggingface');
    // (the array stays on the call line: a line that BEGINS with '['
    //  is read as a section tag by the Inno parser, even inside [Code])
    if DirExists(Runtime) or DirExists(Data) then
      if MsgBox(FmtMessage(CustomMessage('RemoveDataQuestion'), [Runtime, Data, Models]),
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(Runtime, True, True, True);
        DelTree(Data, True, True, True);
      end;
  end;
end;
