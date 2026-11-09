using System.Text;
using System.Text.Json;

namespace NexAgent.Collectors;

static class LinuxModules
{
    public static Func<object?>? Get(string name, AgentConfig cfg) => name switch
    {
        "system" => System_, "cpu" => Cpu, "memory" => Memory, "storage" => Storage, "gpu" => Gpu,
        "display" => Display, "software" => () => Software(cfg.SoftwareMax), "security" => Security,
        "updates" => Updates, "usb" => Usb, "admins" => Admins, _ => null,
    };

    static string? Rd(string path) { try { var s = File.ReadAllText(path).Trim(); return s.Length == 0 ? null : s; } catch { return null; } }
    static string? Dmi(string f) { var v = Rd("/sys/class/dmi/id/" + f); return v is "To Be Filled By O.E.M." or "Default string" or "None" or "Not Specified" ? null : v; }

    static object? System_()
    {
        var os = new Dictionary<string, string>();
        foreach (var l in File.Exists("/etc/os-release") ? File.ReadAllLines("/etc/os-release") : Array.Empty<string>())
        { var i = l.IndexOf('='); if (i > 0) os[l[..i]] = l[(i + 1)..].Trim('"'); }
        double up = 0; double.TryParse(Rd("/proc/uptime")?.Split(' ')[0], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out up);
        int.TryParse(Dmi("chassis_type"), out var ch);
        return new Dictionary<string, object?>
        {
            ["hostname"] = Environment.MachineName, ["manufacturer"] = Dmi("sys_vendor"), ["model"] = Dmi("product_name"),
            ["serial"] = Dmi("product_serial"), ["uuid"] = Dmi("product_uuid"), ["biosVersion"] = Dmi("bios_version"), ["biosDate"] = Dmi("bios_date"),
            ["formFactor"] = ch switch { 8 or 9 or 10 or 14 or 31 or 32 => "laptop", 3 or 4 or 6 or 7 or 15 or 16 => "desktop", 23 or 28 or 17 or 25 => "server", 13 => "all-in-one", _ => "other" },
            ["chassisType"] = ch,
            ["os"] = new Dictionary<string, object?>
            {
                ["caption"] = os.GetValueOrDefault("PRETTY_NAME"), ["version"] = os.GetValueOrDefault("VERSION_ID"), ["build"] = Rd("/proc/sys/kernel/osrelease"),
                ["arch"] = AppInfo.Arch, ["lastBoot"] = up > 0 ? DateTime.UtcNow.AddSeconds(-up).ToString("o") : null,
            },
        };
    }

    static object? Cpu()
    {
        var lines = File.ReadAllLines("/proc/cpuinfo");
        var name = lines.FirstOrDefault(l => l.StartsWith("model name"))?.Split(':', 2)[1].Trim()
                   ?? lines.FirstOrDefault(l => l.StartsWith("Hardware") || l.StartsWith("Model"))?.Split(':', 2)[1].Trim();
        var threads = lines.Count(l => l.StartsWith("processor"));
        var cores = lines.Where(l => l.StartsWith("core id")).Distinct().Count();
        var sockets = Math.Max(1, lines.Where(l => l.StartsWith("physical id")).Distinct().Count());
        var max = Rd("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq");
        return new Dictionary<string, object?>
        { ["name"] = name, ["sockets"] = sockets, ["cores"] = cores > 0 ? cores * sockets : threads, ["threads"] = threads, ["maxMhz"] = long.TryParse(max, out var m) ? m / 1000 : null };
    }

    static object? Memory()
    {
        long total = 0;
        var l = File.ReadLines("/proc/meminfo").FirstOrDefault(x => x.StartsWith("MemTotal"));
        if (l != null) long.TryParse(new string(l.Where(char.IsDigit).ToArray()), out total);
        var mods = new List<Dictionary<string, object?>>();
        var dm = Proc.Text("dmidecode", "-t memory", 8000);
        if (dm != null)
            foreach (var blk in dm.Split("\n\n").Where(b => b.Contains("Memory Device") && !b.Contains("No Module Installed")))
            {
                string? F(string k) => blk.Split('\n').Select(x => x.Trim()).FirstOrDefault(x => x.StartsWith(k + ":"))?.Split(':', 2)[1].Trim();
                var size = F("Size");
                if (size == null || size.StartsWith("Not")) continue;
                mods.Add(new Dictionary<string, object?> { ["slot"] = F("Locator"), ["size"] = size, ["speed"] = F("Speed"), ["manufacturer"] = F("Manufacturer"), ["partNumber"] = F("Part Number"), ["serial"] = F("Serial Number"), ["type"] = F("Type") });
            }
        return new Dictionary<string, object?> { ["totalBytes"] = total * 1024, ["modules"] = mods };
    }

    static object? Storage()
    {
        var disks = new List<Dictionary<string, object?>>(); var vols = new List<Dictionary<string, object?>>();
        var js = Proc.Text("lsblk", "-J -b -o NAME,MODEL,SERIAL,SIZE,TYPE,ROTA,TRAN,MOUNTPOINT,FSTYPE,LABEL", 8000);
        if (js != null)
        {
            using var doc = JsonDocument.Parse(js);
            foreach (var d in doc.RootElement.GetProperty("blockdevices").EnumerateArray())
            {
                string? S(JsonElement e, string k) => e.TryGetProperty(k, out var v) && v.ValueKind != JsonValueKind.Null ? v.ToString() : null;
                if (S(d, "type") == "disk" && S(d, "name") is { } nm && !nm.StartsWith("loop") && !nm.StartsWith("ram"))
                    disks.Add(new Dictionary<string, object?> { ["model"] = S(d, "model")?.Trim(), ["serial"] = S(d, "serial"), ["sizeBytes"] = long.TryParse(S(d, "size"), out var z) ? z : null,
                        ["interface"] = S(d, "tran"), ["mediaType"] = S(d, "rota") is "0" or "false" ? "SSD" : "HDD" });
                void Walk(JsonElement e)
                {
                    if (S(e, "mountpoint") is { } mp && mp.StartsWith('/') && !mp.StartsWith("/snap") && !mp.StartsWith("/boot/efi"))
                        try { var di = new DriveInfo(mp); vols.Add(new Dictionary<string, object?> { ["letter"] = mp, ["fs"] = S(e, "fstype"), ["sizeBytes"] = di.TotalSize, ["freeBytes"] = di.AvailableFreeSpace, ["label"] = S(e, "label") }); } catch { }
                    if (e.TryGetProperty("children", out var ch)) foreach (var c in ch.EnumerateArray()) Walk(c);
                }
                Walk(d);
            }
        }
        return new Dictionary<string, object?> { ["disks"] = disks, ["volumes"] = vols };
    }

    static object? Gpu() => (Proc.Text("lspci", "-mm", 6000) ?? "").Split('\n')
        .Where(l => l.Contains("VGA") || l.Contains("3D controller") || l.Contains("Display controller"))
        .Select(l => { var q = l.Split('"'); return new Dictionary<string, object?> { ["name"] = q.Length > 5 ? $"{q[3]} {q[5]}".Trim() : l.Trim() }; }).ToList();

    static object? Display()
    {
        var res = new List<Dictionary<string, object?>>();
        if (!Directory.Exists("/sys/class/drm")) return res;
        foreach (var f in Directory.GetFiles("/sys/class/drm", "edid", SearchOption.AllDirectories).Concat(Directory.GetDirectories("/sys/class/drm").Select(d => Path.Combine(d, "edid")).Where(File.Exists)).Distinct())
        {
            try
            {
                var b = File.ReadAllBytes(f); if (b.Length < 128) continue;
                var m = (b[8] << 8) | b[9];
                var mf = new string(new[] { (char)('@' + ((m >> 10) & 31)), (char)('@' + ((m >> 5) & 31)), (char)('@' + (m & 31)) });
                string? name = null, ser = null;
                for (var o = 54; o <= 108; o += 18)
                    if (b[o] == 0 && b[o + 1] == 0 && b[o + 2] == 0)
                    {
                        var t = Encoding.ASCII.GetString(b, o + 5, 13).Split('\n')[0].Trim();
                        if (b[o + 3] == 0xFC) name = t; else if (b[o + 3] == 0xFF) ser = t;
                    }
                res.Add(new Dictionary<string, object?> { ["manufacturer"] = mf, ["model"] = name, ["serial"] = ser ?? BitConverter.ToUInt32(b, 12).ToString(), ["year"] = 1990 + b[17], ["week"] = (int)b[16] });
            }
            catch { }
        }
        return res;
    }

    static object? Software(int max)
    {
        var items = new List<Dictionary<string, object?>>();
        var dp = Proc.Text("dpkg-query", "-W -f=${Package}\\t${Version}\\t${Status}\\n", 15000);
        if (dp != null)
            foreach (var l in dp.Split('\n')) { var p = l.Split('\t'); if (p.Length >= 3 && p[2].EndsWith("installed")) items.Add(new() { ["name"] = p[0], ["version"] = p[1] }); }
        else if (Proc.Text("rpm", "-qa --qf %{NAME}\\t%{VERSION}-%{RELEASE}\\n", 15000) is { } rp)
            foreach (var l in rp.Split('\n')) { var p = l.Split('\t'); if (p.Length >= 2) items.Add(new() { ["name"] = p[0], ["version"] = p[1] }); }
        items = items.OrderBy(x => x["name"]?.ToString(), StringComparer.OrdinalIgnoreCase).ToList();
        return new Dictionary<string, object?> { ["count"] = items.Count, ["truncated"] = items.Count > max, ["items"] = max <= 0 ? new() : items.Take(max).ToList() };
    }

    static bool Active(string svc) => Proc.Text("systemctl", "is-active " + svc, 4000)?.Trim() == "active";

    static object? Security()
    {
        bool? sb = null;
        try { var f = Directory.GetFiles("/sys/firmware/efi/efivars", "SecureBoot-*").FirstOrDefault(); if (f != null) { var b = File.ReadAllBytes(f); sb = b[^1] == 1; } } catch { }
        return new Dictionary<string, object?>
        {
            ["firewall"] = new { ufw = Active("ufw"), firewalld = Active("firewalld") }, ["secureBoot"] = sb,
            ["selinux"] = Proc.Text("getenforce", "", 3000)?.Trim(), ["apparmor"] = Directory.Exists("/sys/kernel/security/apparmor"),
        };
    }

    static object? Updates()
    {
        var st = "/var/lib/apt/periodic/update-success-stamp";
        return new Dictionary<string, object?>
        { ["lastInstalled"] = File.Exists(st) ? File.GetLastWriteTimeUtc(st).ToString("yyyy-MM-dd") : null, ["rebootRequired"] = File.Exists("/var/run/reboot-required") };
    }

    static object? Usb() => (Proc.Text("lsusb", "", 5000) ?? "").Split('\n').Where(l => l.Length > 0 && !l.Contains("root hub")).Take(60)
        .Select(l => new Dictionary<string, object?> { ["name"] = l.Contains("ID ") ? l[(l.IndexOf("ID ") + 3)..] : l }).ToList();

    static object? Admins() => File.ReadAllLines("/etc/group").Where(l => l.StartsWith("sudo:") || l.StartsWith("wheel:"))
        .SelectMany(l => l.Split(':').Last().Split(',', StringSplitOptions.RemoveEmptyEntries)).Distinct().ToList();
}
