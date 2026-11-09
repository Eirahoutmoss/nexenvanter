using System.Collections.Concurrent;
using System.Net;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Authentication;
using System.Security.Cryptography.X509Certificates;
using System.Text;

namespace NexAgent;

public sealed class HttpReq
{
    public string Method = "", Target = "", Path = "";
    public Dictionary<string, string> Headers = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, string> Query = new(StringComparer.OrdinalIgnoreCase);
    public byte[] Body = Array.Empty<byte>();
    public IPAddress Remote = IPAddress.None;
    public string? Q(string k) => Query.TryGetValue(k, out var v) ? v : null;
}

public sealed class HttpResp
{
    public int Status = 200;
    public string Body = "";
    public string? ETag;
    public static HttpResp Json(object o, int status = 200) =>
        new() { Status = status, Body = System.Text.Json.JsonSerializer.Serialize(o, Cfg.Compact) };
    public static HttpResp Err(int status, string msg) => Json(new { error = msg }, status);
}

/// <summary>Minimal TLS/HTTP-1.1 sunucusu: sınırlı eşzamanlılık, küçük istek sınırları, kaynak IP denetimi.</summary>
public sealed class HttpServer
{
    readonly SemaphoreSlim _slots = new(6);
    readonly ConcurrentDictionary<string, (int n, long t)> _rate = new();
    X509Certificate2? _cert;
    public string Fingerprint { get; private set; } = "";
    TcpListener? _l;

    public async Task RunAsync(CancellationToken ct)
    {
        var cfg = Cfg.Current;
        _cert = Tls.LoadOrCreate();
        Fingerprint = Tls.Fingerprint(_cert);
        try { _l = new TcpListener(IPAddress.IPv6Any, cfg.Port); _l.Server.DualMode = true; _l.Start(16); }
        catch { _l = new TcpListener(IPAddress.Any, cfg.Port); _l.Start(16); }
        Log.Info($"Dinleniyor: {cfg.Port}/tcp, sertifika {Fingerprint[..16]}…");
        using var _ = ct.Register(() => { try { _l!.Stop(); } catch { } });
        while (!ct.IsCancellationRequested)
        {
            TcpClient c;
            try { c = await _l!.AcceptTcpClientAsync(ct); }
            catch { break; }
            var ip = (c.Client.RemoteEndPoint as IPEndPoint)?.Address ?? IPAddress.None;
            if (!Net4.Allowed(ip, Cfg.Current.AllowedSources) || RateLimited(ip) || !_slots.Wait(0))
            { try { c.Dispose(); } catch { } continue; }
            _ = Task.Run(() => HandleAsync(c, Net4.Norm(ip), ct), ct);
        }
        _cert?.Dispose();
    }

    bool RateLimited(IPAddress ip)
    {
        var k = ip.ToString(); var now = Environment.TickCount64;
        var e = _rate.AddOrUpdate(k, (1, now), (_, o) => now - o.t > 10_000 ? (1, now) : (o.n + 1, o.t));
        if (_rate.Count > 4096) _rate.Clear();
        return e.n > 40;
    }

    async Task HandleAsync(TcpClient c, IPAddress ip, CancellationToken ct)
    {
        try
        {
            using (c)
            {
                c.NoDelay = true;
                using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
                cts.CancelAfter(TimeSpan.FromSeconds(25));
                await using var ssl = new SslStream(c.GetStream(), false);
                await ssl.AuthenticateAsServerAsync(new SslServerAuthenticationOptions
                {
                    ServerCertificate = _cert,
                    EnabledSslProtocols = SslProtocols.Tls12 | SslProtocols.Tls13,
                    ClientCertificateRequired = false,
                }, cts.Token);
                var req = await ReadAsync(ssl, ip, cts.Token);
                var resp = req == null ? HttpResp.Err(400, "geçersiz istek") : await Routes.HandleAsync(req, this, cts.Token);
                await WriteAsync(ssl, resp, cts.Token);
            }
        }
        catch (Exception e) { Log.Warn($"{ip}: {e.GetType().Name}"); }
        finally { _slots.Release(); }
    }

    static async Task<HttpReq?> ReadAsync(Stream s, IPAddress ip, CancellationToken ct)
    {
        var buf = new byte[16 * 1024]; int len = 0, hdrEnd = -1;
        while (hdrEnd < 0)
        {
            if (len == buf.Length) return null;
            var n = await s.ReadAsync(buf.AsMemory(len), ct);
            if (n == 0) return null;
            len += n;
            hdrEnd = Find(buf, len);
        }
        var head = Encoding.ASCII.GetString(buf, 0, hdrEnd).Split("\r\n");
        var rl = head[0].Split(' ');
        if (rl.Length != 3 || !rl[2].StartsWith("HTTP/")) return null;
        var r = new HttpReq { Method = rl[0].ToUpperInvariant(), Target = rl[1], Remote = ip };
        var qi = r.Target.IndexOf('?');
        r.Path = qi < 0 ? r.Target : r.Target[..qi];
        if (qi >= 0)
            foreach (var kv in r.Target[(qi + 1)..].Split('&', StringSplitOptions.RemoveEmptyEntries))
            {
                var p = kv.Split('=', 2);
                r.Query[Uri.UnescapeDataString(p[0])] = p.Length > 1 ? Uri.UnescapeDataString(p[1]) : "";
            }
        foreach (var h in head.Skip(1)) { var i = h.IndexOf(':'); if (i > 0) r.Headers[h[..i].Trim()] = h[(i + 1)..].Trim(); }
        var need = r.Headers.TryGetValue("content-length", out var cl) && int.TryParse(cl, out var x) ? x : 0;
        if (need < 0 || need > 64 * 1024) return null;
        var body = new byte[need]; var have = Math.Min(need, len - (hdrEnd + 4));
        if (have > 0) Array.Copy(buf, hdrEnd + 4, body, 0, have);
        while (have < need) { var n = await s.ReadAsync(body.AsMemory(have, need - have), ct); if (n == 0) return null; have += n; }
        r.Body = body;
        return r;
    }

    static int Find(byte[] b, int len)
    {
        for (var i = 3; i < len; i++) if (b[i] == '\n' && b[i - 1] == '\r' && b[i - 2] == '\n' && b[i - 3] == '\r') return i - 3;
        return -1;
    }

    static async Task WriteAsync(Stream s, HttpResp r, CancellationToken ct)
    {
        var body = Encoding.UTF8.GetBytes(r.Body);
        var reason = r.Status switch { 200 => "OK", 202 => "Accepted", 304 => "Not Modified", 400 => "Bad Request", 401 => "Unauthorized",
            403 => "Forbidden", 404 => "Not Found", 409 => "Conflict", 429 => "Too Many Requests", _ => "Error" };
        var sb = new StringBuilder($"HTTP/1.1 {r.Status} {reason}\r\nContent-Type: application/json; charset=utf-8\r\n" +
                                   $"Content-Length: {(r.Status == 304 ? 0 : body.Length)}\r\nConnection: close\r\nCache-Control: no-store\r\n");
        if (r.ETag != null) sb.Append($"ETag: {r.ETag}\r\n");
        sb.Append("\r\n");
        await s.WriteAsync(Encoding.ASCII.GetBytes(sb.ToString()), ct);
        if (r.Status != 304) await s.WriteAsync(body, ct);
        await s.FlushAsync(ct);
    }
}
