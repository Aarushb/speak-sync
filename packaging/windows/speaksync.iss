; SpeakSync Inno Setup Compiler Script
; Generates a clean, accessible, modern Windows installer for SpeakSync

#define MyAppName "SpeakSync"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Aarush Bhatnagar"
#define MyAppURL "https://github.com/Aarushb/speak-sync"
#define MyAppExeName "speaksync.exe"
#define MyAppSourceDir "..\..\dist\speaksync"

[Setup]
; App identification
AppId={{E58BAE42-66C7-4A19-94F3-88225CDD2E2B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases

; Modern per-user installation (no admin elevation required)
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Output settings
OutputDir=..\..\dist
OutputBaseFilename=SpeakSync-v{#MyAppVersion}-windows-setup
SetupIconFile=..\..\assets\speaksync.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; Installation options
ShowLanguageDialog=no
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "&Start SpeakSync when Windows starts"; GroupDescription: "Windows Startup:"

[Files]
Source: "{#MyAppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\speaksync.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\speaksync.ico"; Tasks: desktopicon

[Registry]
; Interoperable with SpeakSync's in-app autostart toggle:
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "SpeakSync"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
