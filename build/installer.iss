; Inno-Setup-Skript: erzeugt den Windows-Installer AICP-Research-Setup.exe
; Installiert nach "Programme", legt Start- und Desktop-Verknuepfung an und
; erscheint in "Apps & Features" (sauber deinstallierbar).

#define MyAppName "AICP Research"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppExe "AICPResearch.exe"

[Setup]
AppId={{A7F3C2E1-9B4D-4E6A-8C1F-AICPRESEARCH01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=AICP Research
DefaultDirName={autopf}\AICP Research
DefaultGroupName={#MyAppName}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
OutputDir=..\dist
OutputBaseFilename=AICP-Research-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
; Installation nach "Programme" -> benoetigt Administrator (Standard bei Installern)
PrivilegesRequired=admin
; Beim Update automatisch die laufende App schliessen und danach neu starten
CloseApplications=yes
RestartApplications=yes

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\AICPResearch\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\{#MyAppName} deinstallieren"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: postinstall nowait skipifsilent
