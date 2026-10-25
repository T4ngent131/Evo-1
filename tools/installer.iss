; Evo Windows 安装器。先运行 tools/build.py，再运行 tools/build_installer.py。
; 数据目录由 paths.py 决定，位于安装目录之外；卸载时保留战绩、截图和高光。

#ifndef AppVersion
  #error AppVersion must be passed by build_installer.py
#endif

#define ProjectRoot AddBackslash(SourcePath) + ".."

[Setup]
AppId={{d71df750-fb81-41fc-8a80-4282aa72cebb}
AppName=Evo Tracker
AppVersion={#AppVersion}
AppVerName=Evo Tracker {#AppVersion}
AppPublisher=Evo Tracker
AppPublisherURL=https://evotracker.cn
AppSupportURL=https://github.com/T4ngent131/Evo-1/issues
DefaultDirName={localappdata}\Programs\Evo Tracker
DefaultGroupName=Evo Tracker
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\Evo.exe
SetupIconFile={#ProjectRoot}\build\icon\evo.ico
LicenseFile={#ProjectRoot}\LICENSE
OutputDir={#ProjectRoot}\dist
OutputBaseFilename=Evo-{#AppVersion}-Setup-win64
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "chinesetraditional"; MessagesFile: "compiler:Languages\ChineseTraditional.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#ProjectRoot}\dist\Evo\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Evo Tracker"; Filename: "{app}\Evo.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Evo Tracker"; Filename: "{app}\Evo.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Evo.exe"; Description: "启动 Evo Tracker"; Flags: nowait postinstall skipifsilent
