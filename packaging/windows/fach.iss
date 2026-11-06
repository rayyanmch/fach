; Inno-Setup-Skript für Fach (Windows).
; Installiert pro Benutzer – keine Administratorrechte, keine UAC-Abfrage.
; Bauen:  iscc /DAppVersion=0.1.0 packaging\windows\fach.iss   (nach pyinstaller packaging\fach.spec)

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6F0D9C2E-7B1A-4C55-9C1E-3F5A1C000001}
AppName=Fach
AppVersion={#AppVersion}
AppPublisher=Fach (inoffizielles Studierendenprojekt)
AppComments=Holt deine ILIAS-Unterlagen automatisch auf deinen Rechner.
DefaultDirName={localappdata}\Programs\Fach
DefaultGroupName=Fach
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=Fach-Setup-{#AppVersion}
SetupIconFile=..\assets\fach.ico
UninstallDisplayIcon={app}\Fach.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Verknüpfung auf dem Desktop"; Flags: unchecked

[Files]
Source: "..\..\dist\Fach\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "..\assets\fach.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Die AppUserModelID verbindet Fenster, Taskleiste und Mitteilungen mit „Fach“.
Name: "{userprograms}\Fach"; Filename: "{app}\Fach.exe"; AppUserModelID: "Fach.Desktop"; IconFilename: "{app}\fach.ico"
Name: "{userdesktop}\Fach"; Filename: "{app}\Fach.exe"; AppUserModelID: "Fach.Desktop"; IconFilename: "{app}\fach.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\Fach.exe"; Description: "Fach jetzt starten"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Zeitplan aus der Aufgabenplanung entfernen. Uni-Dateien und Einstellungen bleiben.
Filename: "{app}\Fach.exe"; Parameters: "--remove-schedule"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveSchedule"
