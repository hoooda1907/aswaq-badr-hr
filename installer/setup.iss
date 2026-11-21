; Inno Setup script — يبني ملف التثبيت (نسخة ويندوز 11 أو نسخة Win10-Legacy)
; نسخة ويندوز 11 (افتراضي)  |  /DLEGACY = نسخة ويندوز 10 وما قبله (Qt 5)
#ifdef LEGACY
  #define OutName "RMT_HR-Win10-Legacy-Setup"
  #define MinVer "6.1.7601"
#else
  #define OutName "RMT_HR-Win11-Setup"
  #define MinVer "10.0.22000"
#endif

[Setup]
AppName=RMT HR
AppVersion=1.0.0
AppPublisher=Mahmoud Thabet
DefaultDirName={autopf}\RMT_HR
DefaultGroupName=RMT HR
OutputDir=..\dist_installer
OutputBaseFilename={#OutName}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\RMT_HR.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion={#MinVer}

[Tasks]
Name: "desktopicon"; Description: "إنشاء اختصار على سطح المكتب"; GroupDescription: "اختصارات:"

[Files]
Source: "..\dist\RMT_HR.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\RMT HR"; Filename: "{app}\RMT_HR.exe"
Name: "{autodesktop}\RMT HR"; Filename: "{app}\RMT_HR.exe"; Tasks: desktopicon

[Run]
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "تثبيت مكتبات ويندوز المطلوبة (Visual C++)..."; Flags: waituntilterminated
Filename: "{app}\RMT_HR.exe"; Description: "تشغيل البرنامج"; Flags: nowait postinstall skipifsilent
