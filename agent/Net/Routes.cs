using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text.Json;

namespace NexAgent;

public static class Routes
{
    static readonly ConcurrentDictionary<string, (int n, long t)> Fails = new();

    public static async Task<HttpResp> HandleAsync(HttpReq r, HttpServer srv, CancellationToken ct)
    {
        if (r.Method == "GET" && r.Path == "/v1/hello")
            return HttpResp.Json(new { proto = 1, agentId = Cfg.Current.AgentId, version = AppInfo.Version, os = AppInfo.OsName });

        if (!Auth.Verify(r, out var err))
        {
            var k = r.Remote.ToString(); var now = Environment.TickCount64;
            var f = Fails.AddOrUpdate(k, (1, now), (_, o) => now - o.t > 60_000 ? (1, now) : (o.n + 1, o.t));
            if (Fails.Count > 1024) Fails.Clear();
            Log.Warn($"Yetkisiz istek {r.Remote} {r.Method} {r.Path}: {err}");
            if (f.n > 5) await Task.Delay(2000, ct);
            return HttpResp.Err(401, err);
        }
        Log.Info($"{r.Remote} {r.Method} {r.Target}");

        return (r.Method, r.Path) switch
        {
            ("GET", "/v1/status") => Status(srv),
            ("GET", "/v1/inventory") => await InventoryAsync(r, ct),
            ("PUT", "/v1/config") => PutConfig(r),
            ("POST", "/v1/uninstall") => Uninstall(r),
            _ => HttpResp.Err(404, "bulunamadı"),
        };
    }

    static HttpResp Status(HttpServer srv)
    {
        var c = Cfg.Current; var s = Collector.Current; var p = Process.GetCurrentProcess();
        return HttpResp.Json(new
        {
            agentId = c.AgentId, version = AppInfo.Version, os = AppInfo.OsName, hostname = Environment.MachineName,
            uptimeSec = (long)(DateTime.Now - p.StartTime).TotalSeconds, port = c.Port, fingerprint = srv.Fingerprint,
            config = new { version = c.Version, c.IntervalMinutes, c.SoftwareMax, modules = c.Modules, c.AllowedSources, c.ServerName,
                           uninstallProtected = !string.IsNullOrEmpty(c.UninstallHash) },
            lastCollect = s == null ? null : new { at = s.At, s.DurationMs, s.Errors, modules = s.Modules.Keys },
            process = new { workingSetMb = p.WorkingSet64 / 1048576, cpuSec = Math.Round(p.TotalProcessorTime.TotalSeconds, 1) },
        });
    }

    static async Task<HttpResp> InventoryAsync(HttpReq r, CancellationToken ct)
    {
        var want = r.Q("modules")?.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToHashSet();
        var snap = Collector.Current;
        if (snap == null || (r.Q("fresh") == "1" && (DateTime.UtcNow - snap.At).TotalSeconds > 60))
            snap = await Collector.CollectNowAsync(ct);
        var etag = $"\"{snap.At.Ticks:x}-{(want == null ? "all" : string.Join('+', want.OrderBy(x => x)))}-{Cfg.Current.Version}\"";
        if (r.Headers.TryGetValue("if-none-match", out var inm) && inm == etag) return new HttpResp { Status = 304, ETag = etag };
        var mods = snap.Modules.Where(kv => want == null || want.Contains(kv.Key)).ToDictionary(kv => kv.Key, kv => kv.Value);
        var missing = want?.Where(w => !snap.Modules.ContainsKey(w)).ToArray() ?? Array.Empty<string>();
        var resp = HttpResp.Json(new
        {
            agentId = Cfg.Current.AgentId, agentVersion = AppInfo.Version, hostname = Environment.MachineName,
            collectedAt = snap.At, durationMs = snap.DurationMs, configVersion = Cfg.Current.Version,
            modules = mods, errors = snap.Errors, missing,
        });
        resp.ETag = etag;
        return resp;
    }

    sealed class Patch
    {
        public int? Version { get; set; }
        public Dictionary<string, bool>? Modules { get; set; }
        public int? IntervalMinutes { get; set; }
        public int? SoftwareMax { get; set; }
        public List<string>? AllowedSources { get; set; }
        public string? UninstallHash { get; set; }
        public bool? ClearUninstallHash { get; set; }
        public string? ServerName { get; set; }
    }

    static HttpResp PutConfig(HttpReq r)
    {
        Patch? p;
        try { p = JsonSerializer.Deserialize<Patch>(r.Body, Cfg.Json); } catch { return HttpResp.Err(400, "geçersiz JSON"); }
        if (p == null) return HttpResp.Err(400, "boş istek");
        var cur = Cfg.Current;
        if (p.Version is int v && v < cur.Version) return HttpResp.Json(new { error = "eski sürüm", current = cur.Version }, 409);
        if (p.IntervalMinutes is < 15 or > 10080) return HttpResp.Err(400, "aralık 15–10080 dk olmalı");
        if (p.SoftwareMax is < 0 or > 5000) return HttpResp.Err(400, "yazılım sınırı 0–5000");
        if (p.UninstallHash != null && !p.UninstallHash.StartsWith("pbkdf2-sha256$")) return HttpResp.Err(400, "parola özeti geçersiz");
        if (p.AllowedSources != null)
        {
            if (p.AllowedSources.Count == 0 || p.AllowedSources.Any(s => !Net4.TryNet(s, out _))) return HttpResp.Err(400, "izinli kaynak listesi geçersiz");
            if (!Net4.Allowed(r.Remote, p.AllowedSources)) return HttpResp.Err(400, "yeni liste isteği yapan adresi dışarıda bırakıyor");
        }
        var n = new AgentConfig
        {
            Version = (p.Version ?? cur.Version) + (p.Version == null ? 1 : 0), AgentId = cur.AgentId, Port = cur.Port, PublicKey = cur.PublicKey,
            AllowedSources = p.AllowedSources ?? cur.AllowedSources, ServerName = p.ServerName ?? cur.ServerName,
            UninstallHash = p.ClearUninstallHash == true ? null : p.UninstallHash ?? cur.UninstallHash,
            IntervalMinutes = p.IntervalMinutes ?? cur.IntervalMinutes, SoftwareMax = p.SoftwareMax ?? cur.SoftwareMax,
            Modules = new Dictionary<string, bool>(cur.Modules),
        };
        if (p.Modules != null)
            foreach (var kv in p.Modules) if (Collectors.Registry.Known(kv.Key)) n.Modules[kv.Key] = kv.Value;
        Cfg.Save(n);
        Collector.Invalidate();
        Collector.Kick();
        Log.Info($"Yapılandırma güncellendi (sürüm {n.Version})");
        return HttpResp.Json(new { ok = true, version = n.Version });
    }

    static HttpResp Uninstall(HttpReq r)
    {
        string? confirm = null;
        try { confirm = JsonDocument.Parse(r.Body).RootElement.GetProperty("confirm").GetString(); } catch { }
        if (!string.Equals(confirm, Cfg.Current.AgentId, StringComparison.OrdinalIgnoreCase)) return HttpResp.Err(400, "onay kodu (agentId) gerekli");
        Log.Warn($"Uzaktan kaldırma isteği: {r.Remote}");
        _ = Task.Run(async () => { await Task.Delay(1500); Installer.RemoveSelf(); });
        return HttpResp.Json(new { ok = true, message = "kaldırma başlatıldı" }, 202);
    }
}
