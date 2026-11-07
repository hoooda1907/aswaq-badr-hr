; Inno Setup script — يبني ملف تثبيت AswaqBadrHR-Setup.exe
[Setup]
AppName=Aswaq Badr HR
AppVersion=1.0.0
AppPublisher=Mahmoud Thabet
DefaultDirName={autopf}\AswaqBadrHR
DefaultGroupName=Aswaq Badr HR
OutputDir=..\dist_installer
OutputBaseFilename=AswaqBadrHR-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\AswaqBadrHR.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763

[Tasks]
Name: "desktopicon"; Description: "إنشاء اختصار على سطح المكتب"; GroupDescription: "اختصارات:"

[Files]
Source: "..\dist\AswaqBadrHR.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\أسواق بدر HR"; Filename: "{app}\AswaqBadrHR.exe"
Name: "{autodesktop}\أسواق بدر HR"; Filename: "{app}\AswaqBadrHR.exe"; Tasks: desktopicon

[Run]
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; StatusMsg: "تثبيت مكتبات ويندوز المطلوبة (Visual C++)..."; Flags: waituntilterminated
Filename: "{app}\AswaqBadrHR.exe"; Description: "تشغيل البرنامج"; Flags: nowait postinstall skipifsilent
