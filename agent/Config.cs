using System.Text.Json;
using System.Text.Json.Serialization;

namespace NexAgent;

public static class Paths
{
    public static string DataDir => OperatingSystem.IsWindows()
        ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "NexAgent")
        : "/etc/nexagent";
    public static string InstallDir => OperatingSystem.IsWindows()
        ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "NexAgent")
        : "/opt/nexagent";
    public static string ExeName => OperatingSystem.IsWindows() ? "NexAgent.exe" : "nexagent";
    public static string InstalledExe => Path.Combine(InstallDir, ExeName);
    public static string ConfigFile => Path.Combine(DataDir, "agent.json");
    public static string CacheFile => Path.Combine(DataDir, "cache.json");
    public static string CertFile => Path.Combine(DataDir, "server.pfx");
    public static string LogDir => Path.Combine(DataDir, "logs");
}

/// <summary>Ajan ayarları. Envanter imzalı istekle (PUT /v1/config) değiştirebilir; port ve açık anahtar hariç.</summary>
public sealed class AgentConfig
{
    public int Version { get; set; } = 1;
    public string AgentId { get; set; } = "";
    public int Port { get; set; } = 47820;
    public string PublicKey { get; set; } = "";                 // Envanter ECDSA P-256 açık anahtarı (SPKI, base64)
    public List<string> AllowedSources { get; set; } = new();   // CIDR / IP
    public string? UninstallHash { get; set; }                  // pbkdf2-sha256$iter$salt$hash
    public string ServerName { get; set; } = "";
    public int IntervalMinutes { get; set; } = 360;
    public int SoftwareMax { get; set; } = 800;
    public Dictionary<string, bool> Modules { get; set; } = DefaultModules();

    public static Dictionary<string, bool> DefaultModules() => new()
    {
        ["system"] = true, ["cpu"] = true, ["memory"] = true, ["storage"] = true, ["gpu"] = true,
        ["display"] = true, ["network"] = true, ["software"] = true, ["printers"] = true,
        ["security"] = true, ["updates"] = true, ["usb"] = false, ["admins"] = false,
    };

    public IEnumerable<string> EnabledModules() =>
        Modules.Where(kv => kv.Value).Select(kv => kv.Key).Where(Collectors.Registry.Known);
}

public static class Cfg
{
    static readonly object Lock = new();
    static AgentConfig? _cur;
    public static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    };

    public static readonly JsonSerializerOptions Compact = new(Json) { WriteIndented = false };

    public static AgentConfig Current
    {
        get { lock (Lock) return _cur ??= Load(); }
    }

    public static bool Exists() => File.Exists(Paths.ConfigFile);

    static AgentConfig Load()
    {
        var c = JsonSerializer.Deserialize<AgentConfig>(File.ReadAllText(Paths.ConfigFile), Json) ?? new AgentConfig();
        foreach (var kv in AgentConfig.DefaultModules()) c.Modules.TryAdd(kv.Key, kv.Value);
        return c;
    }

    public static void Save(AgentConfig c)
    {
        lock (Lock)
        {
            Directory.CreateDirectory(Paths.DataDir);
            var tmp = Paths.ConfigFile + ".tmp";
            File.WriteAllText(tmp, JsonSerializer.Serialize(c, Json));
            File.Move(tmp, Paths.ConfigFile, true);
            _cur = c;
        }
    }
}

public static class Log
{
    static readonly object Lock = new();
    public static void Info(string m) => Write("INFO", m);
    public static void Warn(string m) => Write("WARN", m);
    public static void Error(string m) => Write("ERR ", m);

    static void Write(string lvl, string m)
    {
        try
        {
            lock (Lock)
            {
                Directory.CreateDirectory(Paths.LogDir);
                var f = Path.Combine(Paths.LogDir, "agent.log");
                if (File.Exists(f) && new FileInfo(f).Length > 512 * 1024)
                    File.Move(f, Path.Combine(Paths.LogDir, "agent.1.log"), true);
                File.AppendAllText(f, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} {lvl} {m}{Environment.NewLine}");
            }
        }
        catch { /* günlük yazılamıyorsa sessizce geç */ }
    }
}
