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

[Messages]
ButtonBack=上一步(&B)
ButtonNext=下一步(&N)
ButtonInstall=安装(&I)
ButtonCancel=取消
ButtonFinish=完成
ButtonYes=是
ButtonNo=否
WelcomeLabel1=欢迎使用 FuzzToolBox 安装向导
WelcomeLabel2=此向导将引导你完成 FuzzToolBox 的安装。
SelectDirLabel3=请选择 FuzzToolBox 的安装目录。
SelectTasksLabel2=请选择要执行的附加任务。
FinishedHeadingLabel=安装完成
FinishedLabel=FuzzToolBox 已成功安装。
UninstallAppFullTitle=卸载 FuzzToolBox
ConfirmUninstall=确定要卸载 FuzzToolBox 吗？

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："; Flags: unchecked

[Files]
Source: "..\build\FuzzToolBox\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\FuzzToolBox"; Filename: "{app}\FuzzToolBox.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\FuzzToolBox"; Filename: "{app}\FuzzToolBox.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\FuzzToolBox.exe"; Description: "启动 FuzzToolBox"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM FuzzToolBox.exe /T /F"; Flags: runhidden waituntilterminated

[UninstallDelete]
Type: filesandordirs; Name: "{app}\data"
Type: files; Name: "{app}\fuzztoolbox-*.lock"
