using System.Net.NetworkInformation;

namespace NexAgent.Collectors;

public static class Registry
{
    public static readonly string[] All = { "system", "cpu", "memory", "storage", "gpu", "display", "network", "software", "printers", "security", "updates", "usb", "admins" };
    public static bool Known(string n) => All.Contains(n);

    public static Func<object?>? Get(string name, AgentConfig cfg)
    {
        if (name == "network") return Net.Collect;
        if (OperatingSystem.IsWindows()) return WinModules.Get(name, cfg);
        return LinuxModules.Get(name, cfg);
    }
}

static class Net
{
    public static object? Collect()
    {
        var list = new List<Dictionary<string, object?>>();
        foreach (var ni in NetworkInterface.GetAllNetworkInterfaces())
        {
            if (ni.NetworkInterfaceType is NetworkInterfaceType.Loopback or NetworkInterfaceType.Tunnel) continue;
            if (ni.OperationalStatus != OperationalStatus.Up) continue;
            var p = ni.GetIPProperties();
            var v4 = p.UnicastAddresses.Where(a => a.Address.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork).ToList();
            if (v4.Count == 0) continue;
            var mac = ni.GetPhysicalAddress().GetAddressBytes();
            var d = new Dictionary<string, object?>
            {
                ["name"] = ni.Name, ["description"] = ni.Description,
                ["mac"] = mac.Length == 6 ? string.Join(":", mac.Select(b => b.ToString("X2"))) : null,
                ["type"] = ni.NetworkInterfaceType.ToString(),
                ["ips"] = v4.Select(a => a.Address.ToString()).ToArray(),
                ["prefix"] = v4.Select(a => a.PrefixLength).ToArray(),
                ["gateways"] = p.GatewayAddresses.Where(g => g.Address.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork).Select(g => g.Address.ToString()).ToArray(),
                ["dns"] = p.DnsAddresses.Where(a => a.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork).Select(a => a.ToString()).ToArray(),
                ["dnsSuffix"] = string.IsNullOrWhiteSpace(p.DnsSuffix) ? null : p.DnsSuffix,
                ["virtual"] = IsVirtual(ni),
            };
            try { d["dhcp"] = p.GetIPv4Properties().IsDhcpEnabled; } catch { }
            try { if (ni.Speed > 0) d["speedMbps"] = ni.Speed / 1_000_000; } catch { }
            list.Add(d);
        }
        return list;
    }

    static bool IsVirtual(NetworkInterface n)
    {
        var s = (n.Name + " " + n.Description).ToLowerInvariant();
        return new[] { "virtual", "vmware", "hyper-v", "vethernet", "docker", "veth", "br-", "tap", "vpn", "loopback", "bluetooth" }.Any(s.Contains);
    }
}
