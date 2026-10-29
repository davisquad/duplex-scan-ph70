#define AppVersion "1.8.0"

[Setup]
AppId={{5C89DA60-DB27-4C03-AEE7-BEC6E6BD4EC7}
AppName=Duplex Scan
AppVersion={#AppVersion}
AppPublisher=davisquad
AppPublisherURL=https://github.com/davisquad/duplex-scan-ph70
DefaultDirName={localappdata}\Programs\Duplex Scan
DefaultGroupName=Duplex Scan
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
DisableWelcomePage=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=no
DisableFinishedPage=yes
OutputDir=..\installer-output
OutputBaseFilename=DuplexScan-Setup-{#AppVersion}-x64
SetupIconFile=..\DuplexScan-Neon.ico
UninstallDisplayIcon={app}\Duplex Scan.exe
Compression=lzma2/fast
SolidCompression=yes
ArchiveExtraction=full
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Messages]
ReadyLabel1=Ready to install Duplex Scan
ReadyLabel2a=Click Install to set up Duplex Scan for your Windows account. Setup automatically downloads the NAPS2 scanner engine (about 70 MB); an internet connection is required.%n%nInstall Visioneer's PH70 driver separately if it is not already installed. Your scans and settings are kept when upgrading or uninstalling.

[Files]
Source: "..\dist\Duplex Scan\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "https://github.com/cyanfish/naps2/releases/download/v8.6.0/naps2-8.6.0-win-x64.zip"; DestDir: "{app}\scanner-engine"; DestName: "naps2-8.6.0-win-x64.zip"; ExternalSize: 69430988; Hash: "5337339764a948722a7b1d3286116ad486a633c13ec006c81eee3a99b9af12e2"; Flags: external download extractarchive ignoreversion recursesubdirs createallsubdirs
Source: "FIRST-RUN.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Duplex Scan"; Filename: "{app}\Duplex Scan.exe"; WorkingDir: "{app}"; AppUserModelID: "DuplexScan.PH70.Gallery"
Name: "{group}\PH70 driver downloads"; Filename: "https://www.visioneer.com/drivers-and-manuals/"
Name: "{group}\Uninstall Duplex Scan"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Duplex Scan"; Filename: "{app}\Duplex Scan.exe"; WorkingDir: "{app}"; AppUserModelID: "DuplexScan.PH70.Gallery"

[Run]
Filename: "{app}\Duplex Scan.exe"; Flags: nowait skipifsilent
