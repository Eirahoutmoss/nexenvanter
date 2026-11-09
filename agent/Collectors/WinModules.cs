using System.Management;
using System.Runtime.Versioning;
using Microsoft.Win32;

namespace NexAgent.Collectors;

[SupportedOSPlatform("windows")]
static class WinModules
{
    public static Func<object?>? Get(string name, AgentConfig cfg) => name switch
    {
        "system" => System_, "cpu" => Cpu, "memory" => Memory, "storage" => Storage, "gpu" => Gpu,
        "display" => Display, "software" => () => Software(cfg.SoftwareMax), "printers" => Printers,
        "security" => Security, "updates" => Updates, "usb" => Usb, "admins" => Admins, _ => null,
    };

    // ---- yardımcılar ----
    static object? N(object? v) => v switch
    {
        null => null,
        string s => string.IsNullOrWhiteSpace(s) ? null : s.Trim(),
        string[] a => a.Length == 0 ? null : a,
        _ => v,
    };

    static string? Dt(object? v)
    {
        try { return v is string s && s.Length >= 14 ? ManagementDateTimeConverter.ToDateTime(s).ToUniversalTime().ToString("o") : null; }
        catch { return null; }
    }

    static List<Dictionary<string, object?>> Rows(string scope, string wql, params string[] props)
    {
        var res = new List<Dictionary<string, object?>>();
        var opts = new System.Management.EnumerationOptions { Timeout = TimeSpan.FromSeconds(20), ReturnImmediately = false };
        using var s = new ManagementObjectSearcher(new ManagementScope(scope), new ObjectQuery(wql), opts);
        foreach (ManagementBaseObject o in s.Get())
        {
            using (o)
            {
                var d = new Dictionary<string, object?>();
                foreach (var p in props) { try { d[p] = N(o[p]); } catch { d[p] = null; } }
                res.Add(d);
            }
        }
        return res;
    }

    static List<Dictionary<string, object?>> Cim(string wql, params string[] props) => Rows(@"root\cimv2", wql, props);
    static T? Try<T>(Func<T> f) { try { return f(); } catch { return default; } }
    static string? Str(Dictionary<string, object?>? d, string k) => d != null && d.TryGetValue(k, out var v) ? v?.ToString() : null;

    // ---- modüller ----
    static object? System_()
    {
        var cs = Cim("SELECT Name,Domain,Manufacturer,Model,UserName,PartOfDomain FROM Win32_ComputerSystem", "Name", "Domain", "Manufacturer", "Model", "UserName", "PartOfDomain").FirstOrDefault();
        var bios = Cim("SELECT SerialNumber,SMBIOSBIOSVersion,ReleaseDate,Manufacturer FROM Win32_BIOS", "SerialNumber", "SMBIOSBIOSVersion", "ReleaseDate", "Manufacturer").FirstOrDefault();
        var prod = Cim("SELECT UUID FROM Win32_ComputerSystemProduct", "UUID").FirstOrDefault();
        var os = Cim("SELECT Caption,Version,BuildNumber,OSArchitecture,InstallDate,LastBootUpTime FROM Win32_OperatingSystem", "Caption", "Version", "BuildNumber", "OSArchitecture", "InstallDate", "LastBootUpTime").FirstOrDefault();
        var enc = Try(() => Rows(@"root\cimv2", "SELECT ChassisTypes FROM Win32_SystemEnclosure", "ChassisTypes").FirstOrDefault());
        int chassis = 0;
        if (enc != null && enc.TryGetValue("ChassisTypes", out var ct) && ct is ushort[] arr && arr.Length > 0) chassis = arr[0];
        return new Dictionary<string, object?>
        {
            ["hostname"] = Str(cs, "Name") ?? Environment.MachineName, ["domain"] = Str(cs, "Domain"), ["domainJoined"] = cs?["PartOfDomain"],
            ["manufacturer"] = Str(cs, "Manufacturer"), ["model"] = Str(cs, "Model"), ["lastUser"] = Str(cs, "UserName"),
            ["serial"] = Str(bios, "SerialNumber"), ["uuid"] = Str(prod, "UUID"),
            ["biosVersion"] = Str(bios, "SMBIOSBIOSVersion"), ["biosDate"] = Dt(bios?["ReleaseDate"]),
            ["formFactor"] = FormFactor(chassis), ["chassisType"] = chassis,
            ["os"] = new Dictionary<string, object?>
            {
                ["caption"] = Str(os, "Caption"), ["version"] = Str(os, "Version"), ["build"] = Str(os, "BuildNumber"),
                ["arch"] = Str(os, "OSArchitecture"), ["installDate"] = Dt(os?["InstallDate"]), ["lastBoot"] = Dt(os?["LastBootUpTime"]),
            },
        };
    }

    static string FormFactor(int c) => c switch
    {
        8 or 9 or 10 or 11 or 12 or 14 or 18 or 21 or 31 or 32 => "laptop",
        3 or 4 or 5 or 6 or 7 or 15 or 16 or 24 or 35 or 36 => "desktop",
        13 => "all-in-one", 23 or 28 or 29 or 17 or 25 => "server", 30 => "tablet", _ => "other",
    };

    static object? Cpu()
    {
        var rows = Cim("SELECT Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed,SocketDesignation FROM Win32_Processor",
            "Name", "NumberOfCores", "NumberOfLogicalProcessors", "MaxClockSpeed", "SocketDesignation");
        if (rows.Count == 0) return null;
        return new Dictionary<string, object?>
        {
            ["name"] = rows[0]["Name"], ["sockets"] = rows.Count,
            ["cores"] = rows.Sum(r => Convert.ToInt32(r["NumberOfCores"] ?? 0)),
            ["threads"] = rows.Sum(r => Convert.ToInt32(r["NumberOfLogicalProcessors"] ?? 0)),
            ["maxMhz"] = rows[0]["MaxClockSpeed"],
        };
    }

    static object? Memory()
    {
        var total = Cim("SELECT TotalPhysicalMemory FROM Win32_ComputerSystem", "TotalPhysicalMemory").FirstOrDefault();
        var mods = Cim("SELECT BankLabel,DeviceLocator,Capacity,Speed,Manufacturer,PartNumber,SerialNumber,SMBIOSMemoryType FROM Win32_PhysicalMemory",
            "BankLabel", "DeviceLocator", "Capacity", "Speed", "Manufacturer", "PartNumber", "SerialNumber", "SMBIOSMemoryType");
        return new Dictionary<string, object?>
        {
            ["totalBytes"] = total?["TotalPhysicalMemory"],
            ["modules"] = mods.Select(m => new Dictionary<string, object?>
            {
                ["slot"] = m["DeviceLocator"] ?? m["BankLabel"], ["sizeBytes"] = m["Capacity"], ["speedMhz"] = m["Speed"],
                ["manufacturer"] = m["Manufacturer"], ["partNumber"] = m["PartNumber"], ["serial"] = m["SerialNumber"],
                ["type"] = MemType(m["SMBIOSMemoryType"]),
            }).ToList(),
        };
    }

    static string? MemType(object? v) => v is null ? null : Convert.ToInt32(v) switch { 20 => "DDR", 21 => "DDR2", 24 => "DDR3", 26 => "DDR4", 34 => "DDR5", var x => x.ToString() };

    static object? Storage()
    {
        var disks = Cim("SELECT Model,SerialNumber,Size,InterfaceType,MediaType,Index FROM Win32_DiskDrive", "Model", "SerialNumber", "Size", "InterfaceType", "MediaType", "Index");
        var phys = Try(() => Rows(@"root\Microsoft\Windows\Storage", "SELECT FriendlyName,SerialNumber,MediaType,BusType,HealthStatus FROM MSFT_PhysicalDisk",
            "FriendlyName", "SerialNumber", "MediaType", "BusType", "HealthStatus")) ?? new();
        var vols = Cim("SELECT DeviceID,FileSystem,Size,FreeSpace,VolumeName FROM Win32_LogicalDisk WHERE DriveType=3", "DeviceID", "FileSystem", "Size", "FreeSpace", "VolumeName");
        return new Dictionary<string, object?>
        {
            ["disks"] = disks.Select(d =>
            {
                var m = phys.FirstOrDefault(p => Str(p, "SerialNumber")?.Trim() is { } s && s == Str(d, "SerialNumber")?.Trim())
                        ?? phys.FirstOrDefault(p => Str(d, "Model")?.Contains(Str(p, "FriendlyName") ?? "\0", StringComparison.OrdinalIgnoreCase) == true);
                return new Dictionary<string, object?>
                {
                    ["model"] = d["Model"], ["serial"] = d["SerialNumber"], ["sizeBytes"] = d["Size"], ["interface"] = d["InterfaceType"],
                    ["mediaType"] = m == null ? null : m["MediaType"]?.ToString() switch { "3" or "HDD" => "HDD", "4" or "SSD" => "SSD", "5" or "SCM" => "SCM", var x => x?.ToString() },
                    ["health"] = m == null ? null : m["HealthStatus"]?.ToString() switch { "0" => "Sağlıklı", "1" => "Uyarı", "2" => "Sağlıksız", var x => x?.ToString() },
                };
            }).ToList(),
            ["volumes"] = vols.Select(v => new Dictionary<string, object?>
            { ["letter"] = v["DeviceID"], ["fs"] = v["FileSystem"], ["sizeBytes"] = v["Size"], ["freeBytes"] = v["FreeSpace"], ["label"] = v["VolumeName"] }).ToList(),
        };
    }

    static object? Gpu() => Cim("SELECT Name,DriverVersion,AdapterRAM FROM Win32_VideoController", "Name", "DriverVersion", "AdapterRAM")
        .Where(g => Str(g, "Name") is { } n && !n.Contains("Remote Display", StringComparison.OrdinalIgnoreCase))
        .Select(g => new Dictionary<string, object?> { ["name"] = g["Name"], ["driver"] = g["DriverVersion"], ["vramBytes"] = g["AdapterRAM"] }).ToList();

    static string? Txt(object? v) => v is ushort[] a ? new string(a.TakeWhile(c => c != 0).Select(c => (char)c).ToArray()).Trim() is { Length: > 0 } s ? s : null : null;

    static object? Display()
    {
        var res = new List<Dictionary<string, object?>>();
        var q = new ObjectQuery("SELECT ManufacturerName,ProductCodeID,SerialNumberID,UserFriendlyName,YearOfManufacture,WeekOfManufacture FROM WmiMonitorID");
        using var s = new ManagementObjectSearcher(new ManagementScope(@"root\wmi"), q);
        foreach (ManagementBaseObject o in s.Get())
            using (o)
                res.Add(new Dictionary<string, object?>
                {
                    ["manufacturer"] = Txt(o["ManufacturerName"]), ["model"] = Txt(o["UserFriendlyName"]) ?? Txt(o["ProductCodeID"]),
                    ["serial"] = Txt(o["SerialNumberID"]), ["year"] = o["YearOfManufacture"], ["week"] = o["WeekOfManufacture"],
                });
        return res;
    }

    static object? Software(int max)
    {
        var seen = new HashSet<string>(); var list = new List<Dictionary<string, object?>>();
        foreach (var view in new[] { RegistryView.Registry64, RegistryView.Registry32 })
        {
            using var bk = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, view);
            using var k = bk.OpenSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall");
            if (k == null) continue;
            foreach (var n in k.GetSubKeyNames())
            {
                using var s = k.OpenSubKey(n);
                if (s?.GetValue("DisplayName") is not string name || string.IsNullOrWhiteSpace(name)) continue;
                if (s.GetValue("SystemComponent") is int sc && sc == 1) continue;
                if (s.GetValue("ParentKeyName") != null) continue;
                var ver = s.GetValue("DisplayVersion") as string;
                if (!seen.Add(name.Trim() + "|" + ver)) continue;
                list.Add(new Dictionary<string, object?>
                { ["name"] = name.Trim(), ["version"] = ver, ["publisher"] = s.GetValue("Publisher") as string, ["installDate"] = s.GetValue("InstallDate") as string });
            }
        }
        list = list.OrderBy(x => x["name"]?.ToString(), StringComparer.OrdinalIgnoreCase).ToList();
        return new Dictionary<string, object?> { ["count"] = list.Count, ["truncated"] = list.Count > max, ["items"] = max <= 0 ? new() : list.Take(max).ToList() };
    }

    static object? Printers() => Cim("SELECT Name,DriverName,PortName,Local,Network,Default FROM Win32_Printer", "Name", "DriverName", "PortName", "Local", "Network", "Default")
        .Where(p => Str(p, "Name") is { } n && !new[] { "PDF", "XPS", "OneNote", "Fax", "Microsoft Print" }.Any(x => n.Contains(x, StringComparison.OrdinalIgnoreCase)))
        .Select(p => new Dictionary<string, object?> { ["name"] = p["Name"], ["driver"] = p["DriverName"], ["port"] = p["PortName"], ["local"] = p["Local"], ["network"] = p["Network"], ["default"] = p["Default"] }).ToList();

    static object? Security()
    {
        var d = new Dictionary<string, object?>();
        d["antivirus"] = Try(() => Rows(@"root\SecurityCenter2", "SELECT displayName,productState FROM AntiVirusProduct", "displayName", "productState")
            .Select(a => { var ps = Convert.ToUInt32(a["productState"] ?? 0u); return new Dictionary<string, object?>
            { ["name"] = a["displayName"], ["enabled"] = ((ps >> 12) & 0xF) == 1, ["signaturesUpToDate"] = ((ps >> 4) & 0xF) == 0 }; }).ToList());
        d["firewall"] = Try(() =>
        {
            var o = new Dictionary<string, object?>();
            using var k = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy");
            foreach (var p in new[] { "DomainProfile", "StandardProfile", "PublicProfile" })
                using (var s = k?.OpenSubKey(p)) o[p.Replace("Profile", "")] = s?.GetValue("EnableFirewall") is int i ? i == 1 : null;
            return o;
        });
        d["bitlocker"] = Try(() => Rows(@"root\CIMV2\Security\MicrosoftVolumeEncryption", "SELECT DriveLetter,ProtectionStatus FROM Win32_EncryptableVolume", "DriveLetter", "ProtectionStatus")
            .Select(b => new Dictionary<string, object?> { ["drive"] = b["DriveLetter"], ["protected"] = Convert.ToInt32(b["ProtectionStatus"] ?? 0) == 1 }).ToList());
        d["tpm"] = Try(() => Rows(@"root\CIMV2\Security\MicrosoftTpm", "SELECT IsEnabled_InitialValue,SpecVersion FROM Win32_Tpm", "IsEnabled_InitialValue", "SpecVersion")
            .Select(t => new Dictionary<string, object?> { ["enabled"] = t["IsEnabled_InitialValue"], ["spec"] = t["SpecVersion"] }).FirstOrDefault());
        d["secureBoot"] = Try(() =>
        {
            using var k = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Control\SecureBoot\State");
            return k?.GetValue("UEFISecureBootEnabled") is int i ? (bool?)(i == 1) : null;
        });
        return d;
    }

    static readonly string[] DateFormats = { "d.M.yyyy", "dd.MM.yyyy", "d/M/yyyy", "M/d/yyyy", "yyyy-MM-dd", "yyyyMMdd", "d.M.yyyy HH:mm:ss", "M/d/yyyy h:mm:ss tt" };

    static DateTime? ParseDate(string? t)
    {
        if (string.IsNullOrWhiteSpace(t)) return null;
        var ic = System.Globalization.CultureInfo.InvariantCulture;
        if (DateTime.TryParseExact(t.Trim(), DateFormats, ic, System.Globalization.DateTimeStyles.None, out var x)) return x;
        return DateTime.TryParse(t, ic, System.Globalization.DateTimeStyles.None, out x) ? x : null;
    }

    static object? Updates()
    {
        var rows = Cim("SELECT HotFixID,InstalledOn,Description FROM Win32_QuickFixEngineering", "HotFixID", "InstalledOn", "Description");
        var items = rows.Select(r =>
        {
            var dt = ParseDate(Str(r, "InstalledOn"));
            return (id: Str(r, "HotFixID"), kind: Str(r, "Description"), dt);
        }).OrderByDescending(x => x.dt).ToList();
        return new Dictionary<string, object?>
        {
            ["count"] = items.Count, ["lastInstalled"] = items.FirstOrDefault().dt?.ToString("yyyy-MM-dd"),
            ["recent"] = items.Take(15).Select(x => new Dictionary<string, object?> { ["id"] = x.id, ["type"] = x.kind, ["date"] = x.dt?.ToString("yyyy-MM-dd") }).ToList(),
        };
    }

    static object? Usb() => Cim(@"SELECT Name,Manufacturer,PNPDeviceID FROM Win32_PnPEntity WHERE PNPDeviceID LIKE 'USB\\VID%' AND PNPClass<>'USB'", "Name", "Manufacturer", "PNPDeviceID")
        .Take(60).Select(u => new Dictionary<string, object?> { ["name"] = u["Name"], ["manufacturer"] = u["Manufacturer"], ["id"] = u["PNPDeviceID"] }).ToList();

    static object? Admins()
    {
        var g = Cim("SELECT Name,Domain FROM Win32_Group WHERE SID='S-1-5-32-544'", "Name", "Domain").FirstOrDefault();
        if (g == null) return null;
        var q = $"ASSOCIATORS OF {{Win32_Group.Domain='{g["Domain"]}',Name='{g["Name"]}'}} WHERE AssocClass=Win32_GroupUser";
        var res = new List<string>();
        using var s = new ManagementObjectSearcher(new ManagementScope(@"root\cimv2"), new ObjectQuery(q), new System.Management.EnumerationOptions { Timeout = TimeSpan.FromSeconds(20) });
        foreach (ManagementBaseObject o in s.Get()) using (o) res.Add($"{o["Domain"]}\\{o["Name"]}");
        return res;
    }
}
