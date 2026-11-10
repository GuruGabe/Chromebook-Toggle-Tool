; =============================================================================
; chromebooktoggle.iss - Inno Setup script that builds the Windows installer
; for the Chromebook Toggle Tool.
;
; What it produces:
;   ChromebookToggle-<version>-Setup.exe - a standard Windows installer that:
;     - installs the one-folder app (from dist\ChromebookToggle),
;     - asks "all users" or "just me" (all users = Program Files and needs
;       administrator approval; just me = no approval needed, and the app can
;       then update itself without any prompt),
;     - adds a Start Menu entry and (by default) a desktop shortcut,
;     - creates an uninstaller and an Add/Remove Programs entry, and
;     - writes HKLM or HKCU \SOFTWARE\ChromebookToggle (Version,
;       InstallLocation), which is how the app's self-updater recognises an
;       installed copy and updates it by running the new Setup.exe.
;
; Settings are never overwritten. settings.ini is installed only if there is
; not one already, so an upgrade keeps the administrator's gam_path, acting
; email, allow_deprovision and so on.
;
; Switches for IT (all optional, for silent installs):
;   /VERYSILENT /SUPPRESSMSGBOXES /NORESTART   no windows at all
;   /ALLUSERS or /CURRENTUSER                  choose the install scope
;   /TASKS="deprovision"  or  /ALLOWDEPROV=1   turn the PERMANENT Deprovision
;                                              action on (off by default)
;   /GAMPATH="C:\GAM7\gam.exe"                 write gam_path
;   /SHEETEMAIL="someone@your-domain"          write sheet_acting_email
;   /RELAUNCH=1                                start the app afterwards (the
;                                              self-updater passes this)
; The three settings switches only WRITE a value when given; leaving them off
; on an upgrade leaves whatever is already in settings.ini alone.
;
; The version is injected by the build:  iscc /DMyAppVersion=1.5 chromebooktoggle.iss
; The [Files] source is dist\ChromebookToggle, so run Build-EXE.bat (or the CI
; build) first. Compile from the repo root:
;   iscc /DMyAppVersion=1.5 installer\chromebooktoggle.iss
; =============================================================================

#ifndef MyAppVersion
  #define MyAppVersion "0.0"
#endif
#define MyAppName "Chromebook Toggle Tool"
#define MyAppPublisher "Gabriel Clifton"
#define MyAppURL "https://github.com/GuruGabe/Chromebook-Toggle-Tool"
#define MyAppExeName "ChromebookToggle.exe"

[Setup]
; A STABLE AppId so version upgrades replace the previous install in place and
; update the same Add/Remove Programs entry (never change this GUID).
AppId={{5A2A14CD-3974-4C88-954B-C7736875A7E5}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; {autopf} = Program Files for an all-users install, the person's own
; Programs folder for a just-me install.
DefaultDirName={autopf}\ChromebookToggle
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; The script lives in installer\ but the built app is at the repo root in
; dist\ChromebookToggle, so resolve sources and the output from the repo root
; (one level up). The Setup.exe therefore lands in the repo root.
SourceDir=..
OutputDir=.
OutputBaseFilename=ChromebookToggle-{#MyAppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Default to an all-users install (needs administrator approval) but let the
; person - or /CURRENTUSER - choose a just-me install, which needs none.
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog commandline
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
; Close a running copy so its files can be replaced during an upgrade.
CloseApplications=yes
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoProductName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "deprovision"; Description: "Allow the PERMANENT Deprovision action on this PC (leave unticked unless this PC is for IT staff who retire devices)"; GroupDescription: "Options:"; Flags: unchecked

[Files]
; Everything except settings.ini is replaced on every install/upgrade...
Source: "dist\ChromebookToggle\*"; DestDir: "{app}"; Excludes: "settings.ini"; Flags: recursesubdirs createallsubdirs ignoreversion
; ...but settings.ini is only installed if there is not one already.
Source: "dist\ChromebookToggle\settings.ini"; DestDir: "{app}"; Flags: onlyifdoesntexist

[INI]
; Written ONLY when asked for (see the switches above), so a plain upgrade
; never changes an administrator's settings.
Filename: "{app}\settings.ini"; Section: "Settings"; Key: "allow_deprovision"; String: "true"; Check: DeprovisionRequested
Filename: "{app}\settings.ini"; Section: "Settings"; Key: "gam_path"; String: "{param:GAMPATH|}"; Check: ParamGiven('GAMPATH')
Filename: "{app}\settings.ini"; Section: "Settings"; Key: "sheet_acting_email"; String: "{param:SHEETEMAIL|}"; Check: ParamGiven('SHEETEMAIL')

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; HKA = HKLM for an all-users install, HKCU for a just-me install. The app's
; self-updater reads these to recognise an installed copy.
Root: HKA; Subkey: "SOFTWARE\ChromebookToggle"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey
Root: HKA; Subkey: "SOFTWARE\ChromebookToggle"; ValueType: string; ValueName: "InstallLocation"; ValueData: "{app}"; Flags: uninsdeletevalue

[Run]
; After a normal interactive install: offer to start the app.
Filename: "{app}\{#MyAppExeName}"; Description: "Start {#MyAppName}"; Flags: nowait postinstall skipifsilent
; After a silent self-update (which passes /RELAUNCH=1): start it again for
; the person, as them (not with the installer's administrator rights).
Filename: "{app}\{#MyAppExeName}"; Flags: nowait runasoriginaluser; Check: RelaunchRequested

[Code]
{ Whether the permanent Deprovision action should be switched on: either the
  tick-box was ticked or /ALLOWDEPROV=1 was given. Never used to switch it OFF,
  so an upgrade cannot undo an administrator's choice. }
function DeprovisionRequested: Boolean;
begin
  Result := (ExpandConstant('{param:ALLOWDEPROV|0}') = '1') or WizardIsTaskSelected('deprovision');
end;

{ Whether a /NAME=value switch was given and is not empty. }
function ParamGiven(Name: String): Boolean;
begin
  Result := ExpandConstant('{param:' + Name + '|}') <> '';
end;

{ Whether to start the app when finished (the self-updater asks for this). }
function RelaunchRequested: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;
