; ============================================================================
; AMBER — Inno Setup installer script
; ============================================================================
; Compile with: iscc amber-installer.iss
; Requires Inno Setup 6+ (https://jrsoftware.org/isdl.php)
; ============================================================================

#define MyAppName        "AMBER"
#define MyAppVersion     "1.0.0"
#define MyAppPublisher   "Agency Internal"
#define MyAppExeName     "start-amber.bat"

[Setup]
AppId={{B5C1F3F2-AAA1-4F77-9F2C-A1B2C3D4E5F6}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\AMBER
DefaultGroupName=AMBER
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=AMBER_Setup_v{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
UninstallDisplayName={#MyAppName}
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional icons:"; Flags: checkedonce
Name: "autostart"; Description: "Install AMBER as a Windows Service (auto-start on boot)"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; --- Application files ---
Source: "staging\AMBER\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; --- Sample data folder (only the structure, never any case files) ---
; Created at runtime if absent — nothing to bundle.

[Dirs]
; Persistent data directory — NOT in Program Files so it survives upgrades.
Name: "{code:GetDataDir}";          Permissions: users-modify
Name: "{code:GetDataDir}\mongo";    Permissions: users-modify
Name: "{code:GetDataDir}\logs";     Permissions: users-modify

[Icons]
Name: "{group}\AMBER";              Filename: "{app}\start-amber.bat"; WorkingDir: "{app}"; IconFilename: "{app}\backend\amber-backend.exe"
Name: "{group}\Stop AMBER";         Filename: "{app}\stop-amber.bat";  WorkingDir: "{app}"
Name: "{group}\Backup AMBER";       Filename: "{app}\BACKUP-amber.bat"; WorkingDir: "{app}"
Name: "{group}\Open Data Folder";   Filename: "{code:GetDataDir}"
Name: "{group}\Read Me";            Filename: "{app}\README.txt"
Name: "{group}\Uninstall AMBER";    Filename: "{uninstallexe}"
Name: "{commondesktop}\AMBER";      Filename: "{app}\start-amber.bat"; WorkingDir: "{app}"; IconFilename: "{app}\backend\amber-backend.exe"; Tasks: desktopicon

[Run]
; --- If user opted in, register Windows Services ---
Filename: "{app}\install-service.bat"; Description: "Register AMBER as a Windows Service"; Flags: postinstall runascurrentuser skipifsilent; Tasks: autostart

; --- Add firewall rules restricting Mongo + backend to 127.0.0.1 only ---
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""AMBER-MongoDB-Block-External"" dir=in action=block protocol=TCP localport=27017 remoteip=""!127.0.0.1"""; Flags: runhidden
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""AMBER-Backend-Block-External"" dir=in action=block protocol=TCP localport=8001  remoteip=""!127.0.0.1"""; Flags: runhidden

; --- Open the README in Notepad post-install ---
Filename: "notepad.exe"; Parameters: """{app}\README.txt"""; Description: "View Read Me"; Flags: postinstall skipifsilent unchecked

[UninstallRun]
Filename: "{app}\uninstall-service.bat"; Flags: runhidden; RunOnceId: "RemoveAmberServices"
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""AMBER-MongoDB-Block-External"""; Flags: runhidden; RunOnceId: "RemoveAmberFirewallMongo"
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""AMBER-Backend-Block-External"""; Flags: runhidden; RunOnceId: "RemoveAmberFirewallBackend"

[Code]
var
  DataDirPage: TInputDirWizardPage;

procedure InitializeWizard;
begin
  DataDirPage := CreateInputDirPage(
    wpSelectDir,
    'Data Folder',
    'Where should AMBER store cases, the database, and logs?',
    'AMBER stores all investigation data here. This folder is NOT touched by future upgrades. ' +
    'Pick a drive the agency backs up regularly.',
    False, '');
  DataDirPage.Add('Data folder:');
  DataDirPage.Values[0] := 'C:\AMBER-Data';
end;

function GetDataDir(Param: String): String;
begin
  if Assigned(DataDirPage) then
    Result := DataDirPage.Values[0]
  else
    Result := 'C:\AMBER-Data';
end;
