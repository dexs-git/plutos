; Inno-Setup-Skript für den Windows-Installer (Qt-Version).
; Aufruf: iscc /DAppVersion=1.1.0 packaging\plutos.iss   (nach pyinstaller)
#ifndef AppVersion
  #define AppVersion "dev"
#endif

[Setup]
AppId={{6F0C7A52-3B1D-4E2A-9C55-0A1B2C3D4E5F}
AppName=Plutos
AppVersion={#AppVersion}
AppPublisher=Plutos
DefaultDirName={autopf}\Plutos
DefaultGroupName=Plutos
UninstallDisplayIcon={app}\Plutos.exe
SetupIconFile=icons\plutos.ico
OutputDir=..\dist
OutputBaseFilename=Plutos-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\Plutos\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Plutos"; Filename: "{app}\Plutos.exe"
Name: "{autodesktop}\Plutos"; Filename: "{app}\Plutos.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Run]
Filename: "{app}\Plutos.exe"; Description: "{cm:LaunchProgram,Plutos}"; Flags: nowait postinstall skipifsilent
