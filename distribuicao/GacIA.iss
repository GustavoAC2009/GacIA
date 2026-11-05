#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef StageDir
  #define StageDir "..\dist\stage\Gac.IA"
#endif

[Setup]
AppId={{7A4C388A-A51D-48D0-A2C1-EED2742FEA42}
AppName=Gac.IA
AppVersion={#AppVersion}
AppPublisher=Gac.IA
DefaultDirName={code:GetDefaultInstallDir}
DefaultGroupName=Gac.IA
UninstallDisplayName=Gac.IA
OutputDir=..\dist
OutputBaseFilename=GacIA-Setup
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64
CloseApplications=yes
RestartApplications=no
Uninstallable=yes
SetupLogging=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Dirs]
Name: "{app}\data"; Flags: uninsneveruninstall
Name: "{app}\data\backups"; Flags: uninsneveruninstall

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Gac.IA"; Filename: "{app}\iniciar.bat"; WorkingDir: "{app}"
Name: "{group}\Gerenciador da Gac.IA"; Filename: "{app}\gerenciador.bat"; WorkingDir: "{app}"
Name: "{autodesktop}\Gac.IA"; Filename: "{app}\iniciar.bat"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoLogo -NoProfile -ExecutionPolicy Bypass -File ""{app}\instalador.ps1"" -Mode {code:GetInstallMode}"; WorkingDir: "{app}"; Description: "Preparar ou atualizar Python e os componentes instalados"; Flags: postinstall skipifsilent waituntilterminated

[Code]
function GetDefaultInstallDir(Param: String): String;
var
  PreviousDir, LegacyDir: String;
begin
  if RegQueryStringValue(HKCU, 'Software\GacIA', 'InstallDir', PreviousDir) and
     FileExists(PreviousDir + '\main.py') then
    Result := PreviousDir
  else begin
    LegacyDir := ExpandConstant('{userdocs}\GacIA');
    if FileExists(LegacyDir + '\main.py') then
      Result := LegacyDir
    else
      Result := ExpandConstant('{localappdata}\Programs\Gac.IA');
  end;
end;

function GetInstallMode(Param: String): String;
begin
  if FileExists(ExpandConstant('{app}\.gacia-components.json')) then
    Result := 'Update'
  else
    Result := 'Install';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    RegWriteStringValue(HKCU, 'Software\GacIA', 'InstallDir', ExpandConstant('{app}'));
end;
