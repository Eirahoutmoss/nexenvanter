using System.Reflection;
using System.Runtime.InteropServices;

namespace NexAgent;

public static class AppInfo
{
    public static readonly string Version = Assembly.GetExecutingAssembly().GetName().Version is { } v ? $"{v.Major}.{v.Minor}.{v.Build}" : "1.0.0";
    public static string OsName => OperatingSystem.IsWindows() ? "windows" : "linux";
    public static string Arch => RuntimeInformation.OSArchitecture.ToString().ToLowerInvariant();

    public const string Manifest = """
        NexAgent — NexEnvanter envanter ajanı (Hasan Güler)

        NE YAPAR: Bu bilgisayarın donanım ve yazılım bilgisini (model, seri no, işlemci, bellek, disk, ağ kartı,
        monitör, kurulu programlar, yazıcılar, güvenlik durumu) yalnızca kurumun envanter sunucusuna sorulduğunda iletir.
        NE YAPMAZ: Dosya içeriği, belge, e-posta, tarayıcı geçmişi, parola, ekran görüntüsü, tuş kaydı toplamaz;
        uzaktan komut çalıştırmaz; kendiliğinden internete bağlanmaz.
        NASIL ÇALIŞIR: Düşük öncelikli arka plan servisi; yalnızca yetkili sunucudan gelen imzalı istekleri yanıtlar.
        """;
}

internal static class Native
{
    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll")] static extern bool SetPriorityClass(IntPtr h, uint c);
    [DllImport("kernel32.dll")] static extern bool SetProcessWorkingSetSize(IntPtr h, IntPtr min, IntPtr max);
    [DllImport("kernel32.dll")] static extern bool GetSystemTimes(out long idle, out long kernel, out long user);

    const uint BELOW_NORMAL = 0x4000, BG_BEGIN = 0x00100000, BG_END = 0x00200000;

    public static void LowPriority()
    {
        try
        {
            if (OperatingSystem.IsWindows()) SetPriorityClass(GetCurrentProcess(), BELOW_NORMAL);
            else System.Diagnostics.Process.GetCurrentProcess().PriorityClass = System.Diagnostics.ProcessPriorityClass.BelowNormal;
        }
        catch { }
    }

    public static void BackgroundBegin() { if (OperatingSystem.IsWindows()) try { SetPriorityClass(GetCurrentProcess(), BG_BEGIN); } catch { } }
    public static void BackgroundEnd() { if (OperatingSystem.IsWindows()) try { SetPriorityClass(GetCurrentProcess(), BG_END); } catch { } }

    public static void TrimMemory()
    {
        GC.Collect(2, GCCollectionMode.Aggressive, true, true);
        if (OperatingSystem.IsWindows()) try { SetProcessWorkingSetSize(GetCurrentProcess(), (IntPtr)(-1), (IntPtr)(-1)); } catch { }
    }

    /// <summary>Sistem genel CPU kullanımı (%), ~1 sn örnekler. Ölçülemezse 0.</summary>
    public static async Task<int> CpuBusyAsync()
    {
        try
        {
            if (OperatingSystem.IsWindows())
            {
                GetSystemTimes(out var i1, out var k1, out var u1); await Task.Delay(1000);
                GetSystemTimes(out var i2, out var k2, out var u2);
                var tot = (k2 - k1) + (u2 - u1); var idle = i2 - i1;
                return tot <= 0 ? 0 : (int)(100 - idle * 100 / tot);
            }
            static (long idle, long total) Read()
            {
                var f = File.ReadLines("/proc/stat").First().Split(' ', StringSplitOptions.RemoveEmptyEntries).Skip(1).Select(long.Parse).ToArray();
                return (f[3] + (f.Length > 4 ? f[4] : 0), f.Sum());
            }
            var a = Read(); await Task.Delay(1000); var b = Read();
            var dt = b.total - a.total; return dt <= 0 ? 0 : (int)(100 - (b.idle - a.idle) * 100 / dt);
        }
        catch { return 0; }
    }
}
