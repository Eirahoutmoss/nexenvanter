using System.Collections.Concurrent;
using System.Net;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;

namespace NexAgent;

public static class Pwd
{
    const int Iter = 200_000;

    public static string Hash(string password)
    {
        var salt = RandomNumberGenerator.GetBytes(16);
        var h = Rfc2898DeriveBytes.Pbkdf2(password, salt, Iter, HashAlgorithmName.SHA256, 32);
        return $"pbkdf2-sha256${Iter}${Convert.ToBase64String(salt)}${Convert.ToBase64String(h)}";
    }

    public static bool Verify(string password, string? stored)
    {
        if (string.IsNullOrEmpty(stored)) return true;      // parola tanımlı değilse serbest
        try
        {
            var p = stored.Split('$');
            if (p.Length != 4 || p[0] != "pbkdf2-sha256") return false;
            var h = Rfc2898DeriveBytes.Pbkdf2(password, Convert.FromBase64String(p[2]), int.Parse(p[1]),
                HashAlgorithmName.SHA256, 32);
            return CryptographicOperations.FixedTimeEquals(h, Convert.FromBase64String(p[3]));
        }
        catch { return false; }
    }
}

public static class Tls
{
    public static X509Certificate2 LoadOrCreate()
    {
        var flags = OperatingSystem.IsWindows() ? X509KeyStorageFlags.MachineKeySet : X509KeyStorageFlags.DefaultKeySet;
        if (File.Exists(Paths.CertFile))
        {
            try { return X509CertificateLoader.LoadPkcs12FromFile(Paths.CertFile, null, flags); }
            catch (Exception e) { Log.Warn("Sertifika okunamadı, yenileniyor: " + e.Message); }
        }
        using var key = ECDsa.Create(ECCurve.NamedCurves.nistP256);
        var host = Environment.MachineName;
        var req = new CertificateRequest($"CN=NexAgent-{host}", key, HashAlgorithmName.SHA256);
        var san = new SubjectAlternativeNameBuilder();
        san.AddDnsName(host);
        req.CertificateExtensions.Add(san.Build());
        req.CertificateExtensions.Add(new X509KeyUsageExtension(X509KeyUsageFlags.DigitalSignature, true));
        req.CertificateExtensions.Add(new X509EnhancedKeyUsageExtension(
            new OidCollection { new Oid("1.3.6.1.5.5.7.3.1") }, false));
        using var self = req.CreateSelfSigned(DateTimeOffset.UtcNow.AddDays(-1), DateTimeOffset.UtcNow.AddYears(15));
        var pfx = self.Export(X509ContentType.Pfx);
        Directory.CreateDirectory(Paths.DataDir);
        File.WriteAllBytes(Paths.CertFile, pfx);
        Perms.Restrict(Paths.CertFile);
        return X509CertificateLoader.LoadPkcs12(pfx, null, flags);
    }

    public static string Fingerprint(X509Certificate2 c) => Convert.ToHexString(SHA256.HashData(c.RawData)).ToLowerInvariant();
}

/// <summary>İsteğin Envanter tarafından imzalandığını doğrular (ECDSA P-256 / SHA-256).</summary>
public static class Auth
{
    static readonly ConcurrentDictionary<string, long> Nonces = new();
    static readonly object PruneLock = new();
    static long _lastPrune;

    public static bool Verify(HttpReq r, out string err)
    {
        err = "";
        var cfg = Cfg.Current;
        if (!r.Headers.TryGetValue("x-nex-ts", out var tsS) || !long.TryParse(tsS, out var ts) ||
            !r.Headers.TryGetValue("x-nex-nonce", out var nonce) || nonce.Length is < 12 or > 64 ||
            !r.Headers.TryGetValue("x-nex-agent", out var agent) ||
            !r.Headers.TryGetValue("x-nex-sig", out var sigS))
        { err = "imza başlıkları eksik"; return false; }

        var now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        if (Math.Abs(now - ts) > 300) { err = "zaman damgası geçersiz (saat farkı?)"; return false; }
        if (!string.Equals(agent, cfg.AgentId, StringComparison.OrdinalIgnoreCase)) { err = "ajan kimliği uyuşmuyor"; return false; }
        if (string.IsNullOrEmpty(cfg.PublicKey)) { err = "ajan yapılandırılmamış"; return false; }
        if (Nonces.ContainsKey(nonce)) { err = "tekrarlanan istek"; return false; }

        var msg = $"NEX1\n{r.Method}\n{r.Target}\n{cfg.AgentId}\n{ts}\n{nonce}\n" +
                  Convert.ToHexString(SHA256.HashData(r.Body)).ToLowerInvariant();
        try
        {
            using var ec = ECDsa.Create();
            ec.ImportSubjectPublicKeyInfo(Convert.FromBase64String(cfg.PublicKey), out _);
            var ok = ec.VerifyData(Encoding.UTF8.GetBytes(msg), Convert.FromBase64String(sigS),
                HashAlgorithmName.SHA256, DSASignatureFormat.Rfc3279DerSequence);
            if (!ok) { err = "imza geçersiz"; return false; }
        }
        catch { err = "imza doğrulanamadı"; return false; }

        Nonces[nonce] = now;
        Prune(now);
        return true;
    }

    static void Prune(long now)
    {
        if (now - _lastPrune < 60) return;
        lock (PruneLock)
        {
            _lastPrune = now;
            foreach (var kv in Nonces) if (now - kv.Value > 700) Nonces.TryRemove(kv.Key, out _);
        }
    }
}

public static class Net4
{
    public static IPAddress Norm(IPAddress ip) => ip.IsIPv4MappedToIPv6 ? ip.MapToIPv4() : ip;

    public static bool TryNet(string s, out IPNetwork net)
    {
        s = s.Trim();
        if (!s.Contains('/'))
            s += IPAddress.TryParse(s, out var a) && a.AddressFamily == System.Net.Sockets.AddressFamily.InterNetworkV6 ? "/128" : "/32";
        return IPNetwork.TryParse(s, out net);
    }

    public static bool Allowed(IPAddress ip, IEnumerable<string> sources)
    {
        ip = Norm(ip);
        if (IPAddress.IsLoopback(ip)) return true;
        foreach (var s in sources) if (TryNet(s, out var n) && n.Contains(ip)) return true;
        return false;
    }
}

public static class Perms
{
    /// <summary>Dosya/klasörü yalnızca SYSTEM ve yöneticilere (Windows) / root'a (Linux) açar.</summary>
    public static void Restrict(string path)
    {
        try
        {
            if (OperatingSystem.IsWindows())
            {
                var isDir = Directory.Exists(path);
                Proc.Run("icacls.exe", new[] { path, "/inheritance:r", "/grant:r",
                    isDir ? "*S-1-5-18:(OI)(CI)F" : "*S-1-5-18:F", isDir ? "*S-1-5-32-544:(OI)(CI)F" : "*S-1-5-32-544:F" }, 15000);
            }
            else File.SetUnixFileMode(path, Directory.Exists(path)
                ? UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute
                : UnixFileMode.UserRead | UnixFileMode.UserWrite);
        }
        catch (Exception e) { Log.Warn("İzin kısıtlanamadı: " + e.Message); }
    }
}
