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

; --- WebView2-Laufzeit -------------------------------------------------------
; Das Programmfenster ist ein Browser-Fenster (pywebview). Unter Windows nutzt
; pywebview dafuer die "WebView2"-Laufzeit von Microsoft. Fehlt sie, faellt
; pywebview stillschweigend auf die uralte Internet-Explorer-Engine zurueck -
; die Oberflaeche der App laeuft darauf nicht, der Nutzer sieht ein WEISSES
; FENSTER ohne jede Meldung und kann nichts tun. Das ist der schlimmste Fall:
; kaputt, ohne dass irgendwo steht warum.
;
; Auf Windows 11 und aktuellen Windows-10-Installationen ist die Laufzeit
; vorhanden. Auf frisch aufgesetzten oder abgespeckten Systemen (LTSC,
; Windows Server, entfernte Edge-Installation) fehlt sie.
;
; Deshalb liefern wir Microsofts offiziellen Bootstrapper mit (ca. 2 MB) und
; starten ihn NUR, wenn die Laufzeit wirklich fehlt. Er laedt die Laufzeit dann
; von Microsoft und installiert sie ohne Adminrechte fuer den angemeldeten
; Benutzer - passt also zu PrivilegesRequired=lowest.
;
; Die Datei wird vom Build besorgt (siehe .github/workflows/build-windows.yml
; und Build-Windows.bat). Fehlt sie, laesst sich der Installer trotzdem bauen -
; dann nur eben ohne diese Absicherung.
#define WebView2Setup "MicrosoftEdgeWebview2Setup.exe"
#if FileExists(AddBackslash(SourcePath) + WebView2Setup)
  #define HatWebView2
#endif

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
#ifdef HatWebView2
; Bewusst als ERSTER Eintrag: "dontcopy" heisst, die Datei wird nicht
; installiert, sondern bei Bedarf in den Temp-Ordner ausgepackt. Wegen
; SolidCompression=yes muss zum Auspacken alles davor mit entpackt werden -
; ganz vorne kostet es also praktisch nichts.
Source: "{#WebView2Setup}"; Flags: dontcopy
#endif
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

[Code]
// --- WebView2-Laufzeit pruefen und notfalls nachinstallieren -----------------
// Microsoft legt die installierte Laufzeit unter einer festen Kennung in der
// Registrierung ab. Es gibt mehrere moegliche Orte: systemweit (dort im
// 32-Bit-Zweig WOW6432Node, so legt Microsoft es auf 64-Bit-Windows ab) und
// nur fuer den angemeldeten Benutzer. Wir pruefen alle - eine per Benutzer
// installierte Laufzeit ist genauso gut wie eine systemweite.
// Der Wert "pv" ist die Versionsnummer; "0.0.0.0" bedeutet "Eintrag da, aber
// nicht wirklich installiert" und zaehlt deshalb nicht.
const
  WebView2Kennung = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function WebView2ImSchluessel(Wurzel: Integer; Pfad: String): Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(Wurzel, Pfad + WebView2Kennung, 'pv', Version)
            and (Version <> '') and (Version <> '0.0.0.0');
end;

function WebView2Vorhanden(): Boolean;
begin
  Result := WebView2ImSchluessel(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\');
  if not Result then
    Result := WebView2ImSchluessel(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\');
  if not Result then
    Result := WebView2ImSchluessel(HKCU, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\');
  if not Result then
    Result := WebView2ImSchluessel(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\');
end;

procedure WebView2Sicherstellen();
var
  Ergebnis: Integer;
begin
  if WebView2Vorhanden() then
    exit;
#ifdef HatWebView2
  if not WizardSilent then
    WizardForm.StatusLabel.Caption := 'Installiere die WebView2-Laufzeit (einmalig) ...';
  ExtractTemporaryFile('{#WebView2Setup}');
  // Ein Fehlschlag (z. B. kein Internet) wird bewusst NICHT als Fehler
  // gemeldet: die Installation soll trotzdem durchlaufen. Ohne Laufzeit
  // bleibt es beim weissen Fenster - aber ein abgebrochener Installer waere
  // auch keine Hilfe, und beim naechsten Update wird es erneut versucht.
  Exec(ExpandConstant('{tmp}\{#WebView2Setup}'), '/silent /install', '',
       SW_HIDE, ewWaitUntilTerminated, Ergebnis);
#endif
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    WebView2Sicherstellen();
end;
