"""Ağ keşfi: ping taraması + ARP tablosu + SNMP (switch MAC tablosu → port, yönlendirici ARP → IP).
Bulunan MAC'ler envanterdeki MAC adresleriyle eşleştirilir."""
import ipaddress
import re
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from . import db, snmp
from .textnorm import fold

_NOWIN = 0x08000000 if sys.platform == "win32" else 0
STATE = {"running": False, "last_run": None, "last_result": None, "progress": ""}
_lock = threading.Lock()

OID_BRIDGE_IF = "1.3.6.1.2.1.17.1.4.1.2"
OID_IFNAME = "1.3.6.1.2.1.31.1.1.1.1"
OID_IFDESCR = "1.3.6.1.2.1.2.2.1.2"
OID_QFDB = "1.3.6.1.2.1.17.7.1.2.2.1.2"
OID_FDB = "1.3.6.1.2.1.17.4.3.1.2"
OID_ARP = "1.3.6.1.2.1.4.22.1.2"
OID_SYSNAME = "1.3.6.1.2.1.1.5"


def mac_str(b) -> str | None:
    if isinstance(b, (bytes, bytearray)) and len(b) == 6:
        return ":".join(f"{x:02X}" for x in b)
    if isinstance(b, (tuple, list)) and len(b) == 6:
        return ":".join(f"{x:02X}" for x in b)
    return None


def _ping(ip: str) -> bool:
    cmd = ["ping", "-n", "1", "-w", "500", ip] if sys.platform == "win32" else ["ping", "-c", "1", "-W", "1", ip]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=4, creationflags=_NOWIN)
        return r.returncode == 0 and (sys.platform != "win32" or b"TTL=" in r.stdout.upper())
    except Exception:
        return False


_ARP_WIN = re.compile(r"^\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})\s+", re.M)


def local_arp() -> dict:
    """IP → MAC (sunucunun kendi ARP tablosu)."""
    out = {}
    try:
        if sys.platform == "win32":
            txt = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=15, creationflags=_NOWIN).stdout
            for ip, mac in _ARP_WIN.findall(txt):
                out[ip] = mac.replace("-", ":").upper()
        else:
            for line in open("/proc/net/arp").read().splitlines()[1:]:
                p = line.split()
                if len(p) >= 4 and p[3] != "00:00:00:00:00:00":
                    out[p[0]] = p[3].upper()
    except Exception:
        pass
    return {ip: m for ip, m in out.items() if m not in ("FF:FF:FF:FF:FF:FF",) and not m.startswith("01:00:5E")}


def _rdns(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return None


MAX_HOSTS = 16384      # tek taramada en fazla adres (bilgisayarı yormamak için)
PROBE_PORTS = (445, 135, 80, 443, 22, 3389, 9100, 515, 631, 161)
_WORKERS = 48


def parse_targets(items: list[str]) -> list[dict]:
    """'Ad: hedef' biçimi isteğe bağlı. Hedef: 10.1.2.0/24 | 10.1.2.10-10.1.2.200 | 10.1.2.10-200 | 10.1.2.7"""
    out = []
    for raw in items or []:
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        name, _, tgt = raw.rpartition(":") if ":" in raw and not raw.count(":") > 1 else ("", "", raw)
        tgt = tgt.strip()
        name = name.strip() or tgt
        try:
            if "/" in tgt:
                net = ipaddress.ip_network(tgt, strict=False)
                if net.num_addresses > 65536:
                    raise ValueError
                hosts = [str(h) for h in (net.hosts() if net.num_addresses > 2 else net)]
            elif "-" in tgt:
                a, b = (x.strip() for x in tgt.split("-", 1))
                start = ipaddress.ip_address(a)
                end = ipaddress.ip_address(b) if "." in b else ipaddress.ip_address(a.rsplit(".", 1)[0] + "." + b)
                if int(end) < int(start) or int(end) - int(start) > 65535:
                    raise ValueError
                hosts = [str(ipaddress.ip_address(n)) for n in range(int(start), int(end) + 1)]
            else:
                hosts = [str(ipaddress.ip_address(tgt))]
        except ValueError:
            raise ValueError(f"Geçersiz hedef: {raw} (ör. 10.10.1.0/24, 10.10.1.10-10.10.1.200, 10.10.1.7)")
        out.append({"name": name, "target": tgt, "hosts": hosts})
    total = sum(len(t["hosts"]) for t in out)
    if total > MAX_HOSTS:
        raise ValueError(f"Toplam {total} adres; tek taramada en fazla {MAX_HOSTS} adres taranabilir")
    return out


def hosts_of(subnets: list[str]) -> list[str]:  # geriye uyumluluk
    return [h for t in parse_targets(subnets) for h in t["hosts"]]


def _tcp_probe(ip: str, timeout=0.4) -> list[int]:
    """ICMP kapalı cihazlar için: birkaç yaygın porta aynı anda bağlanmayı dener; açık portları döndürür."""
    import select
    socks = {}
    try:
        for port in PROBE_PORTS:
            if port == 161:
                continue
            s_ = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s_.setblocking(False)
            s_.connect_ex((ip, port))
            socks[s_] = port
        _, w, _ = select.select([], list(socks), [], timeout)
        return sorted(socks[x] for x in w if x.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) == 0)
    except OSError:
        return []
    finally:
        for x in socks:
            x.close()


def _nb_encode(name="*"):
    raw = name.encode().ljust(16, b"\0")
    return bytes([32]) + bytes(c for b in raw for c in (0x41 + (b >> 4), 0x41 + (b & 0xF))) + b"\0"


def nbstat(ip: str, timeout=0.8) -> tuple[str | None, str | None]:
    """NetBIOS düğüm durumu (UDP 137): Windows cihazlarda yönlendirilmiş ağlarda da ad ve MAC verir."""
    import os
    tid = os.urandom(2)
    pkt = tid + b"\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00" + _nb_encode() + b"\x00\x21\x00\x01"
    s_ = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s_.settimeout(timeout)
    try:
        s_.sendto(pkt, (ip, 137))
        data, _ = s_.recvfrom(2048)
        return parse_nbstat(data, tid)
    except OSError:
        return None, None
    finally:
        s_.close()


def parse_nbstat(data: bytes, tid: bytes | None = None):
    if len(data) < 57 or (tid and data[:2] != tid):
        return None, None
    o = 12
    if data[o] & 0xC0 == 0xC0:
        o += 2
    else:
        while data[o]:
            o += data[o] + 1
        o += 1
    o += 10  # type, class, ttl, rdlength
    n = data[o]
    o += 1
    name = None
    for k in range(n):
        ent = data[o + 18 * k: o + 18 * (k + 1)]
        nm, suffix, flags = ent[:15].decode("ascii", "replace").strip(), ent[15], int.from_bytes(ent[16:18], "big")
        if suffix == 0 and not flags & 0x8000 and nm:
            name = nm
            break
    mac_b = data[o + 18 * n: o + 18 * n + 6]
    mac = mac_str(mac_b) if len(mac_b) == 6 and any(mac_b) else None
    return name, mac


def _probe_host(ip: str) -> dict | None:
    alive_ping = _ping(ip)
    ports = _tcp_probe(ip)
    if not alive_ping and not ports:
        return None
    nb_name, nb_mac = nbstat(ip) if (445 in ports or 135 in ports or not ports) else (None, None)
    return {"ip": ip, "ports": ports, "netbios": nb_name, "mac": nb_mac,
            "method": "+".join(x for x, ok in (("ping", alive_ping), ("tcp", bool(ports)), ("netbios", bool(nb_name))) if ok)}


def poll_switch(host, community) -> tuple[list[dict], dict]:
    """→ (gözlemler [{mac, port, vlan}], arp {ip: mac}) ."""
    name = None
    try:
        sn = snmp.walk(host, community, OID_SYSNAME)
        name = sn[0][1].decode(errors="replace") if sn and isinstance(sn[0][1], bytes) else None
    except TimeoutError:
        raise
    bif = {idx[0]: v for idx, v in snmp.walk(host, community, OID_BRIDGE_IF)}
    names = {idx[0]: v.decode(errors="replace") for idx, v in snmp.walk(host, community, OID_IFNAME) if isinstance(v, bytes)}
    if not names:
        names = {idx[0]: v.decode(errors="replace") for idx, v in snmp.walk(host, community, OID_IFDESCR) if isinstance(v, bytes)}
    obs = []
    q = snmp.walk(host, community, OID_QFDB)
    if q:
        for idx, bport in q:
            m = mac_str(idx[1:7])
            if m and bport:
                obs.append({"mac": m, "bport": bport, "vlan": str(idx[0])})
    else:
        for idx, bport in snmp.walk(host, community, OID_FDB):
            m = mac_str(idx[:6])
            if m and bport:
                obs.append({"mac": m, "bport": bport, "vlan": None})
    for o in obs:
        ifi = bif.get(o["bport"], o["bport"])
        o["port"] = names.get(ifi, str(ifi))
    arp = {}
    for idx, v in snmp.walk(host, community, OID_ARP):
        m = mac_str(v)
        if m and len(idx) >= 5:
            arp[".".join(str(x) for x in idx[-4:])] = m
    return obs, arp, name or host


def scan(user="sistem") -> dict:
    if not _lock.acquire(blocking=False):
        raise RuntimeError("Tarama zaten sürüyor")
    STATE.update(running=True, progress="Başlıyor")
    t0 = time.time()
    try:
        cfg = db.get_setting("net_scan") or {}
        seen: dict[str, dict] = {}   # mac → kayıt
        ip_mac: dict[str, str] = {}
        errors = []
        targets = parse_targets(cfg.get("subnets") or [])
        block_of = {h: t["name"] for t in targets for h in t["hosts"]}
        hosts = list(block_of)
        found: list[dict] = []
        if hosts:
            done = [0]

            def job(ip):
                r = _probe_host(ip)
                done[0] += 1
                if done[0] % 32 == 0:
                    STATE["progress"] = f"Taranıyor {done[0]}/{len(hosts)}"
                return r
            with ThreadPoolExecutor(_WORKERS) as ex:
                found = [r for r in ex.map(job, hosts) if r]
        alive = [r["ip"] for r in found]
        ip_mac.update(local_arp())
        for r in found:
            if r["mac"]:
                ip_mac.setdefault(r["ip"], r["mac"])
        sw_rows = [dict(r) for r in db.conn().execute("SELECT * FROM net_switches WHERE active=1")]
        port_load: dict[tuple, int] = {}
        observations = []
        for sw in sw_rows:
            STATE["progress"] = f"SNMP: {sw['host']}"
            try:
                obs, arp, sysname = poll_switch(sw["host"], sw["community"])
                ip_mac.update(arp)
                for o in obs:
                    o["switch"] = sw["name"] or sysname
                    port_load[(o["switch"], o["port"])] = port_load.get((o["switch"], o["port"]), 0) + 1
                observations += obs
                db.conn().execute("UPDATE net_switches SET last_poll=?, last_error=NULL WHERE id=?", (db.now(), sw["id"]))
            except Exception as e:
                errors.append(f"{sw['host']}: {e}")
                db.conn().execute("UPDATE net_switches SET last_poll=?, last_error=? WHERE id=?", (db.now(), str(e)[:300], sw["id"]))
        # Her MAC için en az MAC barındıran portu seç (uplink/trunk portlarını ele)
        for o in observations:
            load = port_load[(o["switch"], o["port"])]
            cur = seen.get(o["mac"])
            if cur is None or load < cur["_load"]:
                seen[o["mac"]] = {"mac": o["mac"], "switch": o["switch"], "port": o["port"], "vlan": o["vlan"], "_load": load}
        for ip, mac in ip_mac.items():
            seen.setdefault(mac, {"mac": mac, "_load": 0})["ip"] = ip
        STATE["progress"] = "Ad çözümleme"
        ips = [v["ip"] for v in seen.values() if v.get("ip")]
        with ThreadPoolExecutor(32) as ex:
            names = dict(zip(ips, ex.map(_rdns, ips)))
        rd = {}
        if alive:
            with ThreadPoolExecutor(32) as ex:
                rd = dict(zip(alive, ex.map(_rdns, alive)))
        ts = db.now()
        with db.tx() as t:
            for r in found:
                t.execute("""INSERT INTO net_hosts(ip,mac,hostname,netbios,block,ports,method,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(ip) DO UPDATE SET mac=coalesce(excluded.mac,mac), hostname=coalesce(excluded.hostname,hostname),
                    netbios=coalesce(excluded.netbios,netbios), block=excluded.block, ports=excluded.ports, method=excluded.method,
                    last_seen=excluded.last_seen""",
                          (r["ip"], ip_mac.get(r["ip"]), rd.get(r["ip"]), r["netbios"], block_of.get(r["ip"]),
                           ",".join(map(str, r["ports"])), r["method"], ts, ts))
            for v in seen.values():
                t.execute("""INSERT INTO net_seen(mac,ip,hostname,switch,port,vlan,first_seen,last_seen,source) VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(mac) DO UPDATE SET ip=coalesce(excluded.ip,ip), hostname=coalesce(excluded.hostname,hostname),
                    switch=coalesce(excluded.switch,switch), port=coalesce(excluded.port,port), vlan=coalesce(excluded.vlan,vlan),
                    last_seen=excluded.last_seen, source=excluded.source""",
                          (v["mac"], v.get("ip"), names.get(v.get("ip")), v.get("switch"), v.get("port"), v.get("vlan"), ts, ts,
                           "snmp" if v.get("switch") else "arp"))
        res = {"at": ts, "alive": len(alive), "macs": len(seen), "switches": len(sw_rows), "errors": errors,
               "seconds": round(time.time() - t0, 1), "scanned": len(hosts),
               "blocks": [{"name": t["name"], "target": t["target"], "size": len(t["hosts"]),
                           "alive": sum(1 for r in found if block_of.get(r["ip"]) == t["name"])} for t in targets]}
        STATE.update(last_run=ts, last_result=res)
        db.audit(user, "net_scan", None, {k: res[k] for k in ("alive", "macs", "switches")})
        return res
    finally:
        STATE.update(running=False, progress="")
        _lock.release()


def scan_async(user):
    if STATE["running"]:
        raise RuntimeError("Tarama zaten sürüyor")
    threading.Thread(target=lambda: _safe_scan(user), daemon=True, name="netscan").start()


def _safe_scan(user):
    try:
        scan(user)
    except Exception as e:
        STATE["last_result"] = {"at": db.now(), "errors": [str(e)]}


def scheduler():
    def loop():
        time.sleep(60)
        while True:
            try:
                h = float((db.get_setting("net_scan") or {}).get("interval_hours") or 0)
                last = STATE["last_run"]
                if h > 0 and (not last or datetime.fromisoformat(last) < datetime.now() - timedelta(hours=h)):
                    _safe_scan("zamanlayıcı")
            except Exception:
                pass
            time.sleep(300)
    threading.Thread(target=loop, daemon=True, name="netsched").start()


# ---------------- eşleştirme ----------------
def asset_mac_map() -> dict[str, dict]:
    out = {}
    for r in db.conn().execute("SELECT id, asset_code, json_extract(data,'$.mac_address') m, "
                               "json_extract(data,'$.brand_model') bm FROM assets WHERE archived=0 AND m IS NOT NULL"):
        for mac in str(r["m"]).split(","):
            out[mac.strip().upper()] = {"id": r["id"], "asset_code": r["asset_code"], "brand_model": r["bm"]}
    return out


def overview() -> dict:
    cfg = db.get_setting("net_scan") or {}
    stale_days = int(cfg.get("stale_days") or 30)
    amap = asset_mac_map()
    c = db.conn()
    since = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
    unknown = [dict(r) for r in c.execute("SELECT * FROM net_seen WHERE last_seen>=? ORDER BY ip", (since,))
               if r["mac"] not in amap]
    seen = {r["mac"]: r["last_seen"] for r in c.execute("SELECT mac,last_seen FROM net_seen")}
    lim = (datetime.now() - timedelta(days=stale_days)).isoformat(timespec="seconds")
    stale = []
    for mac, a in amap.items():
        ls = seen.get(mac)
        if not ls or ls < lim:
            stale.append({**a, "mac": mac, "last_seen": ls})
    total_seen = c.execute("SELECT COUNT(*) FROM net_seen WHERE last_seen>=?", (since,)).fetchone()[0]
    ipmap, namemap = {}, {}
    for r in c.execute("SELECT id, asset_code, json_extract(data,'$.ip_address') ip, json_extract(data,'$.hostname') hn, "
                       "json_extract(data,'$.brand_model') bm FROM assets WHERE archived=0"):
        for ipx in str(r["ip"] or "").replace(";", ",").split(","):
            if ipx.strip():
                ipmap[ipx.strip()] = {"id": r["id"], "asset_code": r["asset_code"], "brand_model": r["bm"]}
        if r["hn"]:
            namemap[fold(r["hn"])] = {"id": r["id"], "asset_code": r["asset_code"], "brand_model": r["bm"]}
    hosts = []
    for r in c.execute("SELECT * FROM net_hosts WHERE last_seen>=? ORDER BY block, ip", (since,)):
        h = dict(r)
        short = fold((h["netbios"] or (h["hostname"] or "").split(".")[0]) or "")
        h["asset"] = amap.get(h["mac"] or "") or ipmap.get(h["ip"]) or (namemap.get(short) if short else None)
        h["kind"] = _kind(h["ports"])
        hosts.append(h)
    blocks = {}
    for h in hosts:
        b = blocks.setdefault(h["block"] or "—", {"name": h["block"] or "—", "alive": 0, "matched": 0})
        b["alive"] += 1
        b["matched"] += bool(h["asset"])
    for t in (STATE.get("last_result") or {}).get("blocks") or []:
        blocks.setdefault(t["name"], {"name": t["name"], "alive": 0, "matched": 0}).update(target=t["target"], size=t["size"])
    return {"state": {k: STATE[k] for k in ("running", "last_run", "last_result", "progress")}, "config": cfg,
            "switches": [dict(r) for r in c.execute("SELECT id,name,host,active,last_poll,last_error FROM net_switches")],
            "unknown": unknown[:2000], "stale": sorted(stale, key=lambda x: x["last_seen"] or "")[:2000],
            "matched": len(amap) - len(stale), "seen_7d": total_seen, "stale_days": stale_days,
            "hosts": hosts[:5000], "blocks": list(blocks.values())}


def _kind(ports: str | None) -> str:
    p = set((ports or "").split(","))
    if p & {"9100", "515", "631"}:
        return "Yazıcı"
    if "3389" in p or ("445" in p and "135" in p):
        return "Windows"
    if "22" in p and not p & {"445", "135"}:
        return "Linux / ağ cihazı"
    if p & {"80", "443"}:
        return "Web arayüzlü cihaz"
    return ""


def for_asset(asset: dict) -> list[dict]:
    macs = [m.strip().upper() for m in str(asset.get("data", {}).get("mac_address") or "").split(",") if m.strip()]
    if not macs:
        return []
    return [dict(r) for r in db.conn().execute(
        f"SELECT * FROM net_seen WHERE mac IN ({','.join('?' * len(macs))})", macs)]


def save_switch(data, sid=None):
    host = (data.get("host") or "").strip()
    if not sid and not host:
        raise ValueError("Switch adresi gerekli")
    c = db.conn()
    if sid:
        sets = {k: data[k] for k in ("name", "host", "community", "active") if k in data}
        if sets:
            c.execute(f"UPDATE net_switches SET {','.join(k + '=?' for k in sets)} WHERE id=?", (*sets.values(), sid))
    else:
        c.execute("INSERT INTO net_switches(name,host,community) VALUES(?,?,?)",
                  ((data.get("name") or "").strip() or None, host, data.get("community") or "public"))


def delete_switch(sid):
    db.conn().execute("DELETE FROM net_switches WHERE id=?", (sid,))
