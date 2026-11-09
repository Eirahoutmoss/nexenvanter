; NexEnvanter kurulum sihirbazı (Inno Setup 6). Derleme: ISCC /DAppVersion=0.7.0 installer\windows\NexEnvanter.iss
; Önce dist\NexEnvanter.exe derlenmiş olmalı (build.bat).
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{B7E1C5A2-4D0E-4C7A-9E54-6E7B2F5A1C11}
AppName=NexEnvanter
AppVersion={#AppVersion}
AppVerName=NexEnvanter {#AppVersion}
AppPublisher=Hasan Güler
AppPublisherURL=https://github.com/Eirahoutmoss/NexEnvanter
DefaultDirName={autopf}\NexEnvanter
DefaultGroupName=NexEnvanter
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=NexEnvanter-Setup-{#AppVersion}
SetupIconFile=..\..\build\out\nexenvanter.ico
UninstallDisplayIcon={app}\NexEnvanter.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes
VersionInfoVersion={#AppVersion}

[Languages]
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "service"; Description: "Arka plan hizmeti olarak kur (bilgisayar açıldığında oturum açılmasa da çalışır) — önerilen"
Name: "firewall"; Description: "Güvenlik duvarında portu aç (yalnızca etki alanı ve özel ağlar)"
Name: "desktopicon"; Description: "Masaüstü kısayolu oluştur"; Flags: unchecked

[Dirs]
; Veri klasörü: güncelleme ve kaldırmada korunur
Name: "{commonappdata}\NexEnvanter"; Permissions: users-modify; Flags: uninsneveruninstall

[Files]
Source: "..\..\dist\NexEnvanter.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\NexEnvanter"; Filename: "{app}\NexEnvanter.exe"; Parameters: "--data ""{commonappdata}\NexEnvanter"" --port {code:GetPort}"
Name: "{group}\NexEnvanter veri klasörü"; Filename: "{commonappdata}\NexEnvanter"
Name: "{group}\NexEnvanter'i kaldır"; Filename: "{uninstallexe}"
Name: "{commondesktop}\NexEnvanter"; Filename: "{app}\NexEnvanter.exe"; Parameters: "--data ""{commonappdata}\NexEnvanter"" --port {code:GetPort}"; Tasks: desktopicon

[Registry]
Root: HKLM; Subkey: "Software\NexEnvanter"; ValueType: string; ValueName: "Port"; ValueData: "{code:GetPort}"; Flags: uninsdeletekey

[Run]
Filename: "{app}\NexEnvanter.exe"; Parameters: "--install-service --quiet --port {code:GetPort} --data ""{commonappdata}\NexEnvanter"""; Tasks: service; Flags: runhidden waituntilterminated; StatusMsg: "Arka plan hizmeti kuruluyor..."
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=NexEnvanter"; Tasks: firewall; Flags: runhidden waituntilterminated
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=NexEnvanter dir=in action=allow protocol=TCP localport={code:GetPort} profile=domain,private program=""{app}\NexEnvanter.exe"""; Tasks: firewall; Flags: runhidden waituntilterminated; StatusMsg: "Güvenlik duvarı kuralı ekleniyor..."
Filename: "{app}\NexEnvanter.exe"; Parameters: "--data ""{commonappdata}\NexEnvanter"" --port {code:GetPort}"; Description: "NexEnvanter'i aç"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\NexEnvanter.exe"; Parameters: "--uninstall-service --quiet"; Flags: runhidden waituntilterminated; RunOnceId: "NexSvc"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=NexEnvanter"; Flags: runhidden waituntilterminated; RunOnceId: "NexFw"

[Code]
var
  PortPage: TInputQueryWizardPage;

function GetPort(Param: String): String;
begin
  Result := PortPage.Values[0];
end;

procedure InitializeWizard;
var
  P: String;
begin
  PortPage := CreateInputQueryPage(wpSelectTasks, 'Ağ ayarı', 'NexEnvanter hangi portta çalışsın?',
    'Tarayıcıdan http://sunucu-adı:PORT adresiyle erişilir. Varsayılan 8750. Bu porta başka bir program bağlıysa kurulum durur; farklı bir port seçin.');
  PortPage.Add('Port (1024-65535):', False);
  if not RegQueryStringValue(HKLM, 'Software\NexEnvanter', 'Port', P) then P := '8750';
  PortPage.Values[0] := ExpandConstant('{param:PORT|' + P + '}');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  N: Integer;
begin
  Result := True;
  if CurPageID = PortPage.ID then
  begin
    N := StrToIntDef(PortPage.Values[0], 0);
    if (N < 1024) or (N > 65535) then
    begin
      MsgBox('Port 1024 ile 65535 arasında olmalı.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  RC: Integer;
begin
  Result := '';
  { Çalışan eski sürümü durdur (hizmet ve tepsi) }
  Exec(ExpandConstant('{sys}\schtasks.exe'), '/End /TN NexEnvanter', '', SW_HIDE, ewWaitUntilTerminated, RC);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM NexEnvanter.exe', '', SW_HIDE, ewWaitUntilTerminated, RC);
  Sleep(1500);
  { Port başka bir programda mı? }
  if Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -Command "if (Get-NetTCPConnection -State Listen -LocalPort ' + PortPage.Values[0] + ' -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"', '', SW_HIDE, ewWaitUntilTerminated, RC) then
    if RC = 1 then
      Result := 'Port ' + PortPage.Values[0] + ' başka bir program tarafından kullanılıyor. Geri dönüp farklı bir port seçin.';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if (not UninstallSilent) and (MsgBox('Veri klasörü (veritabanı, yedekler, ajan imza anahtarı) de silinsin mi?' + #13#10 + 'Emin değilseniz HAYIR deyin; veriler korunur.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) then
      DelTree(ExpandConstant('{commonappdata}\NexEnvanter'), True, True, True);
end;
