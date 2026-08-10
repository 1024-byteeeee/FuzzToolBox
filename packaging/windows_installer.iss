#ifndef MyAppVersion
  #define MyAppVersion "2.1.0"
#endif
#ifndef InstallerBaseName
  #define InstallerBaseName "FuzzToolBox-Setup"
#endif

[Setup]
AppId={{E1A69B91-D9E8-4869-8768-9303D47C07B5}
AppName=FuzzToolBox
AppVersion={#MyAppVersion}
AppPublisher=1024_byteeeee
AppPublisherURL=https://github.com/1024-byteeeee/FuzzToolBox
AppSupportURL=https://github.com/1024-byteeeee/FuzzToolBox/issues
DefaultDirName={localappdata}\Programs\FuzzToolBox
DefaultGroupName=FuzzToolBox
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\build\releases
OutputBaseFilename={#InstallerBaseName}
SetupIconFile=FuzzToolBox.ico
UninstallDisplayIcon={app}\FuzzToolBox.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany=1024_byteeeee
VersionInfoDescription=FuzzToolBox Windows Installer
VersionInfoProductName=FuzzToolBox

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："; Flags: unchecked

[Files]
Source: "..\build\FuzzToolBox\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\FuzzToolBox"; Filename: "{app}\FuzzToolBox.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\FuzzToolBox"; Filename: "{app}\FuzzToolBox.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\FuzzToolBox.exe"; Description: "启动 FuzzToolBox"; Flags: nowait postinstall skipifsilent
