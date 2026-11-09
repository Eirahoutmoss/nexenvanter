using System.Runtime.Versioning;
using System.ServiceProcess;
using System.Text;

namespace NexAgent;

public static class Program
{
    public static int Main(string[] a)
    {
        try { Console.OutputEncoding = Encoding.UTF8; } catch { }
        var cmd = a.Length > 0 ? a[0].ToLowerInvariant() : "help";
        switch (cmd)
        {
            case "--service":
                if (!OperatingSystem.IsWindows()) return 1;
                RunService();
                return 0;
            case "run": return Host.RunForeground();
            case "install": return Installer.Install(a[1..]);
            case "uninstall": return Installer.Uninstall(a[1..]);
            case "status": return Installer.Status();
            case "version": Console.WriteLine(AppInfo.Version); return 0;
            default:
                Console.WriteLine($"NexAgent {AppInfo.Version} — NexEnvanter envanter ajanı\n\n" +
                                  "  install [--enroll enroll.json] [--password PAROLA] [--old-password ESKİ]\n" +
                                  "  uninstall [--password PAROLA] [--keep-data]\n  status\n  run        (ön planda çalıştır)\n  version\n");
                return 0;
        }
    }

    [SupportedOSPlatform("windows")]
    static void RunService() => ServiceBase.Run(new NexService());
}

[SupportedOSPlatform("windows")]
sealed class NexService : ServiceBase
{
    public NexService() { ServiceName = "NexAgent"; CanStop = true; CanShutdown = true; AutoLog = false; }
    protected override void OnStart(string[] args) => Host.Start();
    protected override void OnStop() => Host.Stop();
    protected override void OnShutdown() => Host.Stop();
}

public static class Host
{
    static CancellationTokenSource? _cts;
    static Task? _srv, _col;
    public static readonly HttpServer Server = new();

    public static void Start()
    {
        _cts = new CancellationTokenSource();
        Log.Info($"NexAgent {AppInfo.Version} başlıyor");
        _srv = Task.Run(async () =>
        {
            try { await Server.RunAsync(_cts.Token); }
            catch (Exception e) { Log.Error("Sunucu başlatılamadı: " + e.Message); Environment.Exit(2); }
        });
        _col = Task.Run(() => Collector.LoopAsync(_cts.Token));
    }

    public static void Stop()
    {
        try { _cts?.Cancel(); Task.WaitAll(new[] { _srv, _col }.Where(t => t != null).ToArray()!, 5000); } catch { }
        Log.Info("Durduruldu");
    }

    public static int RunForeground()
    {
        if (!Cfg.Exists()) { Console.Error.WriteLine("Yapılandırma yok. Önce 'install' çalıştırın."); return 1; }
        var done = new ManualResetEventSlim();
        Console.CancelKeyPress += (_, e) => { e.Cancel = true; done.Set(); };
        System.Runtime.InteropServices.PosixSignalRegistration.Create(System.Runtime.InteropServices.PosixSignal.SIGTERM, c => { c.Cancel = true; done.Set(); });
        Start();
        done.Wait();
        Stop();
        return 0;
    }
}
