using System.Diagnostics;
using System.Text.Json;

namespace NexAgent;

public sealed class Snapshot
{
    public DateTime At { get; set; }
    public int DurationMs { get; set; }
    public Dictionary<string, JsonElement> Modules { get; set; } = new();
    public Dictionary<string, string> Errors { get; set; } = new();
}

/// <summary>Sakin toplama: gecikmeli ilk çalışma, jitter'lı aralık, düşük öncelik, modüller arası bekleme, bellek budama.</summary>
public static class Collector
{
    static readonly SemaphoreSlim KickSignal = new(0);
    static Task<Snapshot>? _running;
    public static Snapshot? Current { get; private set; }

    public static void Invalidate() => Current = null;

    public static void Kick() { if (KickSignal.CurrentCount == 0) KickSignal.Release(); }

    public static void LoadCache()
    {
        try { if (File.Exists(Paths.CacheFile)) Current = JsonSerializer.Deserialize<Snapshot>(File.ReadAllText(Paths.CacheFile), Cfg.Json); }
        catch { Current = null; }
    }

    public static async Task LoopAsync(CancellationToken ct)
    {
        Native.LowPriority();
        LoadCache();
        var rnd = new Random();
        try
        {
            var age = Current == null ? double.MaxValue : (DateTime.UtcNow - Current.At).TotalMinutes;
            var first = age >= Cfg.Current.IntervalMinutes ? TimeSpan.FromSeconds(rnd.Next(90, 240)) : TimeSpan.FromMinutes(Cfg.Current.IntervalMinutes - age);
            await KickSignal.WaitAsync(first, ct);   // açılış fırtınasını önlemek için rastgele gecikme
            while (!ct.IsCancellationRequested)
            {
                for (var i = 0; i < 6 && await Native.CpuBusyAsync() > 85; i++) await Task.Delay(TimeSpan.FromMinutes(2), ct); // meşgulse ertele
                try { await CollectNowAsync(ct); } catch (Exception e) when (e is not OperationCanceledException) { Log.Error("Toplama hatası: " + e.Message); }
                Watchdog();
                var wait = TimeSpan.FromMinutes(Cfg.Current.IntervalMinutes * (0.85 + rnd.NextDouble() * 0.3));
                await KickSignal.WaitAsync(wait, ct);
            }
        }
        catch (OperationCanceledException) { }
    }

    static void Watchdog()
    {
        var mb = Process.GetCurrentProcess().WorkingSet64 / 1048576;
        if (mb > 220) { Log.Error($"Bellek sınırı aşıldı ({mb} MB), servis yeniden başlatılıyor"); Environment.Exit(3); }
    }

    static readonly object _lock = new();

    public static Task<Snapshot> CollectNowAsync(CancellationToken ct)
    {
        lock (_lock)
        {
            _running ??= Task.Run(async () =>
            {
                try { return await RunAsync(); }
                finally { lock (_lock) _running = null; }
            });
            return _running.WaitAsync(ct);
        }
    }

    static async Task<Snapshot> RunAsync()
    {
        var sw = Stopwatch.StartNew(); var cfg = Cfg.Current;
        var snap = new Snapshot { At = DateTime.UtcNow };
        Native.BackgroundBegin();
        try
        {
            foreach (var name in cfg.EnabledModules().ToList())
            {
                var fn = Collectors.Registry.Get(name, cfg);
                if (fn == null) continue;
                try
                {
                    var job = Task.Run(fn);
                    if (await Task.WhenAny(job, Task.Delay(TimeSpan.FromSeconds(25))) != job) { snap.Errors[name] = "zaman aşımı"; continue; }
                    var v = await job;
                    if (v != null) snap.Modules[name] = JsonSerializer.SerializeToElement(v, Cfg.Compact);
                }
                catch (Exception e) { snap.Errors[name] = e.GetBaseException().Message; }
                await Task.Delay(200);   // modüller arasında nefes payı
            }
        }
        finally { Native.BackgroundEnd(); }
        snap.DurationMs = (int)sw.ElapsedMilliseconds;
        Current = snap;
        try { Directory.CreateDirectory(Paths.DataDir); File.WriteAllText(Paths.CacheFile + ".tmp", JsonSerializer.Serialize(snap, Cfg.Compact)); File.Move(Paths.CacheFile + ".tmp", Paths.CacheFile, true); }
        catch (Exception e) { Log.Warn("Önbellek yazılamadı: " + e.Message); }
        Log.Info($"Toplama tamam: {snap.Modules.Count} modül, {snap.DurationMs} ms, {snap.Errors.Count} hata");
        Native.TrimMemory();
        return snap;
    }
}
