using System.Diagnostics;

namespace NexAgent;

public static class Proc
{
    public sealed record Result(int Code, string Out, string Err);

    public static Result Run(string file, IEnumerable<string> args, int timeoutMs = 10000)
    {
        try
        {
            var psi = new ProcessStartInfo(file)
            { RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false, CreateNoWindow = true };
            foreach (var a in args) psi.ArgumentList.Add(a);
            using var p = Process.Start(psi);
            if (p == null) return new(-1, "", "başlatılamadı");
            var o = p.StandardOutput.ReadToEndAsync();
            var e = p.StandardError.ReadToEndAsync();
            if (!p.WaitForExit(timeoutMs)) { try { p.Kill(true); } catch { } return new(-2, "", "zaman aşımı"); }
            o.Wait(2000); e.Wait(2000);
            return new(p.ExitCode, o.IsCompletedSuccessfully ? o.Result : "", e.IsCompletedSuccessfully ? e.Result : "");
        }
        catch (Exception ex) { return new(-1, "", ex.Message); }
    }

    public static string? Text(string file, string args, int timeoutMs = 8000)
    {
        var r = Run(file, args.Split(' ', StringSplitOptions.RemoveEmptyEntries), timeoutMs);
        return r.Code == 0 ? r.Out : null;
    }
}
