; Inno-Setup-Skript: erzeugt den Windows-Installer AICP-Research-Setup.exe
; Installiert PRO BENUTZER (nach %LOCALAPPDATA%\Programs\AICP Research), legt
; Start- und Desktop-Verknuepfung an und erscheint in "Apps & Features"
; (sauber deinstallierbar).
;
; Warum pro Benutzer und nicht nach "Programme":
; Eine Installation nach "Programme" braucht Administratorrechte. Windows
; zeigt dafuer bei JEDEM Update die UAC-Abfrage ("Moechten Sie zulassen ...") -
; auch dann, wenn der Installer mit /SILENT gestartet wird. Das automatische
; Update laeuft dadurch nicht wirklich still. Eine Installation im eigenen
; Benutzerprofil braucht keine Adminrechte; /SILENT laeuft dann tatsaechlich
; unsichtbar durch, genau wie das Update auf dem Mac.

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
; Pro-Benutzer-Installation -> KEINE Administratorrechte, also keine UAC-Abfrage.
; Zusammen mit PrivilegesRequired=lowest loest {autopf} auf
; %LOCALAPPDATA%\Programs auf, {group} und {autodesktop} ebenso auf die
; Verknuepfungen des angemeldeten Benutzers.
PrivilegesRequired=lowest
; Der Nutzer soll beim Update nicht gefragt werden, ob systemweit installiert
; werden soll - sonst kaeme die UAC-Abfrage durch die Hintertuer zurueck.
PrivilegesRequiredOverridesAllowed=
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
; Normale Installation: Ankreuzfeld "Anwendung starten" am Ende des Assistenten.
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: postinstall nowait skipifsilent
; Stilles Update (/SILENT): die App danach zuverlaessig wieder starten.
; RestartApplications allein genuegt nicht - die App beendet sich beim Update
; selbst, damit ihre Dateien ersetzt werden koennen, und ob der Windows-
; Restart-Manager sie vorher noch erfasst hat, ist Zufall. Ein doppelter Start
; ist unschaedlich: die Einzelinstanz-Sperre holt dann nur das vorhandene
; Fenster nach vorne (siehe main() in app/main.py).
Filename: "{app}\{#MyAppExe}"; Flags: nowait skipifnotsilent
