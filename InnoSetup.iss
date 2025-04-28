[Setup]
AppName=IP-Scanner
AppVersion=1.3.0
VersionInfoVersion=0.0.0.2
DefaultDirName={autopf}\IPScanner
OutputDir=E:\Users\Desktop
OutputBaseFilename=IP-Scanner v1.3.0 For Windows Setup
SetupIconFile=src\main\resources\icon\IPScannerIcon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "build\image\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\IP-Scanner"; Filename: "{app}\bin\IP-Scanner.exe"; IconFilename: "{app}\img\IPScannerIcon.ico"
Name: "{autodesktop}\IP-Scanner"; Filename: "{app}\bin\IP-Scanner.exe"; IconFilename: "{app}\img\IPScannerIcon.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Run]
Filename: "{app}\bin\IP-Scanner.exe"; Description: "{cm:LaunchProgram,IPScanner}"; Flags: nowait postinstall skipifsilent
