; Vedware — one-file installer (Inno Setup 6)
; Built by build.bat or the GitHub Actions workflow → dist\Installer-Vedware.exe
; Per-user install: no admin rights, no questions — double-click and it's done.

#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif

[Setup]
AppId={{5B7D2E41-9C3A-4F8E-A1D6-3E0F7B9C2A58}
AppName=Vedware
AppVersion={#AppVersion}
AppVerName=Vedware {#AppVersion}
AppPublisher=Sébastien Védrine
AppPublisherURL=https://github.com/sebastien-vedrine/Vedware
AppSupportURL=https://github.com/sebastien-vedrine/Vedware/issues
AppUpdatesURL=https://github.com/sebastien-vedrine/Vedware/releases
DefaultDirName={localappdata}\Programs\Vedware
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=Installer-Vedware
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\Vedware.exe
UninstallDisplayName=Vedware
VersionInfoVersion={#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=auto
CloseApplications=force
RestartApplications=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Messages]
en.WelcomeLabel2=This will install Vedware on your computer.%n%nVedware installs your Windows apps from GitHub and keeps them up to date.%n%nClick Next to continue.
fr.WelcomeLabel2=Ce programme va installer Vedware sur votre ordinateur.%n%nVedware installe vos logiciels Windows depuis GitHub et les garde à jour.%n%nCliquez sur « Suivant » pour continuer.

[CustomMessages]
en.DesktopIcon=Put a Vedware icon on the desktop
fr.DesktopIcon=Mettre une icône Vedware sur le Bureau
en.OpenNow=Open Vedware now
fr.OpenNow=Ouvrir Vedware maintenant

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"

[InstallDelete]
; clean update: remove the previous version's runtime files
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\Vedware\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Vedware"; Filename: "{app}\Vedware.exe"
Name: "{userdesktop}\Vedware"; Filename: "{app}\Vedware.exe"; Tasks: desktopicon

[Run]
; normal install: offer to open Vedware
Filename: "{app}\Vedware.exe"; Description: "{cm:OpenNow}"; Flags: nowait postinstall skipifsilent
; silent self-update from Vedware: restart it quietly in the tray
Filename: "{app}\Vedware.exe"; Parameters: "--minimized"; Flags: nowait; Check: WizardSilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM Vedware.exe /F"; Flags: runhidden; RunOnceId: "StopVedware"

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\Vedware\downloads"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { Vedware writes its own "start with Windows" entry; remove it on uninstall. }
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Vedware');
end;
