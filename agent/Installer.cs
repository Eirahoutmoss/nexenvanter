using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text.Json;

namespace NexAgent;

/// <summary>Kurulum/kaldırma. Yalnızca yönetici (Windows) / root (Linux). Kaldırma parola ile korunabilir.</summary>
public static class Installer
{
    const string Svc = "NexAgent";
    [DllImport("libc")] static extern uint geteuid();

    static bool IsAdmin() => OperatingSystem.IsWindows()
        ? new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator)
        : geteuid() == 0;

    static string? Arg(string[] a, string n) { var i = Array.IndexOf(a, n); return i >= 0 && i + 1 < a.Length ? a[i + 1] : null; }

    static int Elevate(string verb, string[] a)
    {
        if (!OperatingSystem.IsWindows()) { Console.Error.WriteLine("root yetkisi gerekli (sudo ile çalıştırın)."); return 5; }
        Console.WriteLine("Yönetici yetkisi isteniyor…");
        try
        {
            var psi = new ProcessStartInfo(Environment.ProcessPath!) { UseShellExecute = true, Verb = "runas" };
            psi.ArgumentList.Add(verb); foreach (var x in a) psi.ArgumentList.Add(x); psi.ArgumentList.Add("--pause");
            using var p = Process.Start(psi)!; p.WaitForExit(); return p.ExitCode;
        }
        catch { Console.Error.WriteLine("Yönetici onayı verilmedi."); return 5; }
    }

    static string ReadSecret(string prompt)
    {
        Console.Write(prompt);
        if (Console.IsInputRedirected) return Console.ReadLine() ?? "";
        var sb = new System.Text.StringBuilder();
        while (true)
        {
            var k = Console.ReadKey(true);
            if (k.Key == ConsoleKey.Enter) { Console.WriteLine(); return sb.ToString(); }
            if (k.Key == ConsoleKey.Backspace) { if (sb.Length > 0) sb.Length--; }
            else if (!char.IsControl(k.KeyChar)) sb.Append(k.KeyChar);
        }
    }

    static bool CheckPassword(AgentConfig? cfg, string? given, string what)
    {
        if (cfg == null || string.IsNullOrEmpty(cfg.UninstallHash)) return true;
        given ??= ReadSecret($"{what} için parola: ");
        if (Pwd.Verify(given, cfg.UninstallHash)) return true;
        Thread.Sleep(2000);
        Log.Warn($"Hatalı parola ({what}) — kullanıcı: {Environment.UserName}");
        Console.Error.WriteLine("Parola hatalı.");
        return false;
    }

    sealed class Enroll
    {
        public string? ServerName { get; set; }
        public string PublicKey { get; set; } = "";
        public int Port { get; set; } = 47820;
        public List<string> AllowedSources { get; set; } = new();
        public string? UninstallHash { get; set; }
        public int? IntervalMinutes { get; set; }
        public Dictionary<string, bool>? Modules { get; set; }
    }

    static bool PortFree(int port)
    {
        try { var l = new TcpListener(IPAddress.Any, port); l.Start(); l.Stop(); return true; } catch { return false; }
    }

    // ---------------------------------------------------------------- install
    public static int Install(string[] a)
    {
        if (!IsAdmin()) return Elevate("install", a);
        var enrollPath = Arg(a, "--enroll") ?? Path.Combine(AppContext.BaseDirectory, "enroll.json");
        if (!File.Exists(enrollPath)) { Console.Error.WriteLine($"enroll.json bulunamadı: {enrollPath}"); return 2; }
        Enroll en;
        try { en = JsonSerializer.Deserialize<Enroll>(File.ReadAllText(enrollPath), Cfg.Json) ?? new(); }
        catch (Exception e) { Console.Error.WriteLine("enroll.json okunamadı: " + e.Message); return 2; }
        if (string.IsNullOrEmpty(en.PublicKey) || en.AllowedSources.Count == 0 || en.AllowedSources.Any(s => !Net4.TryNet(s, out _)))
        { Console.Error.WriteLine("enroll.json eksik/geçersiz (publicKey, allowedSources)."); return 2; }
        if (Arg(a, "--port") is { } ps && int.TryParse(ps, out var pp)) en.Port = pp;

        AgentConfig? old = Cfg.Exists() ? Cfg.Current : null;
        if (!CheckPassword(old, Arg(a, "--old-password"), "güncelleme")) return 5;

        if (OperatingSystem.IsWindows()) StopWindowsService(); else Proc.Run("systemctl", new[] { "stop", "nexagent" }, 20000);
        if (!PortFree(en.Port)) { Console.Error.WriteLine($"HATA: {en.Port}/tcp portu başka bir program tarafından kullanılıyor. enroll.json'da başka bir port belirleyin. Kurulum yapılmadı."); return 3; }

        var cfg = old ?? new AgentConfig { AgentId = Guid.NewGuid().ToString() };
        cfg.Version = (old?.Version ?? 0) + 1; cfg.Port = en.Port; cfg.PublicKey = en.PublicKey; cfg.AllowedSources = en.AllowedSources;
        cfg.ServerName = en.ServerName ?? cfg.ServerName;
        if (en.IntervalMinutes is >= 15 and <= 10080) cfg.IntervalMinutes = en.IntervalMinutes.Value;
        if (en.Modules != null) foreach (var kv in en.Modules) if (Collectors.Registry.Known(kv.Key)) cfg.Modules[kv.Key] = kv.Value;
        var pw = Arg(a, "--password");
        if (!string.IsNullOrEmpty(pw)) cfg.UninstallHash = Pwd.Hash(pw);
        else if (!string.IsNullOrEmpty(en.UninstallHash)) cfg.UninstallHash = en.UninstallHash;

        try
        {
            Directory.CreateDirectory(Paths.InstallDir); Directory.CreateDirectory(Paths.DataDir);
            if (!string.Equals(Path.GetFullPath(Environment.ProcessPath!), Path.GetFullPath(Paths.InstalledExe), StringComparison.OrdinalIgnoreCase)) File.Copy(Environment.ProcessPath!, Paths.InstalledExe, true);
            Perms.Restrict(Paths.DataDir);
            Cfg.Save(cfg);
            Perms.Restrict(Paths.ConfigFile);
            if (OperatingSystem.IsWindows()) InstallWindows(cfg); else InstallLinux(cfg);
        }
        catch (Exception e) { Console.Error.WriteLine("Kurulum hatası: " + e.Message); Log.Error("Kurulum hatası: " + e); return 4; }

        Thread.Sleep(2500);
        var ok = SelfCheck(cfg.Port);
        Console.WriteLine(ok ? $"Kuruldu ve çalışıyor. Ajan kimliği: {cfg.AgentId}  Port: {cfg.Port}" : "Kuruldu ancak servis yanıt vermedi; günlük: " + Path.Combine(Paths.LogDir, "agent.log"));
        return ok ? 0 : 6;
    }

    static bool SelfCheck(int port)
    {
        try
        {
            using var c = new TcpClient(); c.Connect(IPAddress.Loopback, port);
            using var ssl = new System.Net.Security.SslStream(c.GetStream(), false, (_, _, _, _) => true);
            ssl.AuthenticateAsClient("localhost");
            ssl.Write(System.Text.Encoding.ASCII.GetBytes("GET /v1/hello HTTP/1.1\r\nHost: x\r\n\r\n")); ssl.Flush();
            var buf = new byte[256]; return ssl.Read(buf, 0, buf.Length) > 0;
        }
        catch { return false; }
    }

    static void Sc(params string[] a) => Proc.Run("sc.exe", a, 20000);

    static void StopWindowsService()
    {
        Sc("stop", Svc);
        for (var i = 0; i < 20; i++) { Thread.Sleep(500); var r = Proc.Run("sc.exe", new[] { "query", Svc }, 5000); if (!r.Out.Contains("RUNNING") && !r.Out.Contains("STOP_PENDING")) break; }
    }

    static void InstallWindows(AgentConfig cfg)
    {
        var bin = $"\"{Paths.InstalledExe}\" --service";
        var exists = Proc.Run("sc.exe", new[] { "query", Svc }, 5000).Code == 0;
        Sc(exists ? "config" : "create", Svc, "binPath=", bin, "start=", "delayed-auto", "DisplayName=", "NexAgent Envanter Ajanı", "obj=", "LocalSystem");
        Sc("description", Svc, "NexEnvanter için donanım/yazılım envanter ajanı. Yalnızca yetkili sunucudan gelen imzalı isteklere yanıt verir.");
        Sc("failure", Svc, "reset=", "86400", "actions=", "restart/60000/restart/120000/restart/300000");
        Sc("sdset", Svc, "D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;CCLCSWLOCRRC;;;IU)(A;;CCLCSWLOCRRC;;;SU)");
        Proc.Run("netsh.exe", new[] { "advfirewall", "firewall", "delete", "rule", "name=NexAgent" }, 15000);
        Proc.Run("netsh.exe", new[] { "advfirewall", "firewall", "add", "rule", "name=NexAgent", "dir=in", "action=allow", "protocol=TCP",
            $"localport={cfg.Port}", $"remoteip={string.Join(",", cfg.AllowedSources)}", $"program={Paths.InstalledExe}", "enable=yes", "profile=any" }, 15000);
        using (var k = Microsoft.Win32.Registry.LocalMachine.CreateSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\NexAgent"))
        {
            k.SetValue("DisplayName", "NexAgent (Envanter Ajanı)"); k.SetValue("DisplayVersion", AppInfo.Version);
            k.SetValue("Publisher", "Hasan Güler"); k.SetValue("DisplayIcon", Paths.InstalledExe);
            k.SetValue("InstallLocation", Paths.InstallDir); k.SetValue("UninstallString", $"\"{Paths.InstalledExe}\" uninstall");
            k.SetValue("Comments", "NexEnvanter için envanter ajanı. Dosya, e-posta, tarayıcı geçmişi toplamaz; yalnızca yetkili sunucuya donanım/yazılım bilgisi iletir.");
            k.SetValue("NoModify", 1, Microsoft.Win32.RegistryValueKind.DWord); k.SetValue("NoRepair", 1, Microsoft.Win32.RegistryValueKind.DWord);
        }
        Sc("start", Svc);
    }

    const string Unit = "/etc/systemd/system/nexagent.service";

    static void InstallLinux(AgentConfig cfg)
    {
        File.SetUnixFileMode(Paths.InstalledExe, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute | UnixFileMode.GroupRead | UnixFileMode.GroupExecute | UnixFileMode.OtherRead | UnixFileMode.OtherExecute);
        File.WriteAllText(Unit, $"""
            [Unit]
            Description=NexAgent envanter ajanı
            After=network-online.target
            Wants=network-online.target

            [Service]
            Type=simple
            ExecStart={Paths.InstalledExe} run
            Restart=on-failure
            RestartSec=30
            Nice=10
            IOSchedulingClass=idle
            CPUQuota=20%
            MemoryMax=250M
            ProtectHome=true
            PrivateTmp=true

            [Install]
            WantedBy=multi-user.target
            """);
        Proc.Run("systemctl", new[] { "daemon-reload" }, 15000);
        Proc.Run("systemctl", new[] { "enable", "--now", "nexagent" }, 30000);
        if (Active("ufw"))
            foreach (var s in cfg.AllowedSources) Proc.Run("ufw", new[] { "allow", "from", s, "to", "any", "port", cfg.Port.ToString(), "proto", "tcp" }, 15000);
        else if (Active("firewalld"))
        {
            foreach (var s in cfg.AllowedSources) Proc.Run("firewall-cmd", new[] { "--permanent", $"--add-rich-rule=rule family=ipv4 source address={s} port port={cfg.Port} protocol=tcp accept" }, 15000);
            Proc.Run("firewall-cmd", new[] { "--reload" }, 15000);
        }
    }

    static bool Active(string s) => Proc.Text("systemctl", "is-active " + s, 4000)?.Trim() == "active";

    // -------------------------------------------------------------- uninstall
    public static int Uninstall(string[] a)
    {
        if (!IsAdmin()) return Elevate("uninstall", a);
        var cfg = Cfg.Exists() ? Cfg.Current : null;
        if (!CheckPassword(cfg, Arg(a, "--password"), "kaldırma")) return 5;
        Teardown(cfg, !a.Contains("--keep-data"), waitForCleanup: true);
        Console.WriteLine("NexAgent kaldırıldı.");
        return 0;
    }

    /// <summary>Envanter'den gelen imzalı komutla (parola gerekmez; yetki özel anahtardadır).</summary>
    public static void RemoveSelf()
    {
        Log.Warn("Uzaktan kaldırma uygulanıyor");
        try { Teardown(Cfg.Current, true, false); } catch (Exception e) { Log.Error("Kaldırma hatası: " + e.Message); }
        Thread.Sleep(8000);
        Environment.Exit(0);
    }

    static void Teardown(AgentConfig? cfg, bool removeData, bool waitForCleanup)
    {
        if (OperatingSystem.IsWindows())
        {
            Proc.Run("netsh.exe", new[] { "advfirewall", "firewall", "delete", "rule", "name=NexAgent" }, 15000);
            try { Microsoft.Win32.Registry.LocalMachine.DeleteSubKeyTree(@"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\NexAgent", false); } catch { }
            Sc("failure", Svc, "reset=", "0", "actions=", "none/0");
            Sc("delete", Svc);
            var data = removeData ? $" & rmdir /s /q \"{Paths.DataDir}\"" : "";
            Process.Start(new ProcessStartInfo("cmd.exe", $"/c ping -n 6 127.0.0.1 >nul & rmdir /s /q \"{Paths.InstallDir}\"{data}") { CreateNoWindow = true, UseShellExecute = false });
            if (waitForCleanup) StopWindowsService(); else Process.Start(new ProcessStartInfo("sc.exe", $"stop {Svc}") { CreateNoWindow = true, UseShellExecute = false });
        }
        else
        {
            if (cfg != null && Active("ufw")) foreach (var s in cfg.AllowedSources) Proc.Run("ufw", new[] { "delete", "allow", "from", s, "to", "any", "port", cfg.Port.ToString(), "proto", "tcp" }, 15000);
            var script = $"sleep 2; systemctl disable --now nexagent; rm -f {Unit}; systemctl daemon-reload; rm -rf {Paths.InstallDir}" + (removeData ? $" {Paths.DataDir}" : "");
            var r = Proc.Run("systemd-run", new[] { "--no-block", "--collect", "sh", "-c", script }, 10000);
            if (r.Code != 0) Process.Start(new ProcessStartInfo("sh", $"-c \"{script}\"") { UseShellExecute = false });
        }
    }

    // ----------------------------------------------------------------- status
    public static int Status()
    {
        Console.WriteLine(AppInfo.Manifest + "\n");
        if (!Cfg.Exists()) { Console.WriteLine("Durum: kurulu değil."); return 0; }
        var c = Cfg.Current;
        Console.WriteLine($"Sürüm: {AppInfo.Version}\nAjan kimliği: {c.AgentId}\nPort: {c.Port}/tcp\nİzinli kaynaklar: {string.Join(", ", c.AllowedSources)}");
        Console.WriteLine($"Toplama aralığı: {c.IntervalMinutes} dk\nEtkin modüller: {string.Join(", ", c.EnabledModules())}");
        Console.WriteLine($"Kaldırma parolası: {(string.IsNullOrEmpty(c.UninstallHash) ? "yok" : "var")}\nServis dinliyor: {(SelfCheck(c.Port) ? "evet" : "hayır")}");
        return 0;
    }
}
