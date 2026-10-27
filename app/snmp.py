"""Bağımlılıksız, minimal SNMP v2c istemcisi (GETBULK ile tablo yürütme). Yalnızca okuma."""
import os
import socket


def _len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _tlv(tag: int, val: bytes) -> bytes:
    return bytes([tag]) + _len(len(val)) + val


def _int(v: int) -> bytes:
    return _tlv(0x02, v.to_bytes(max(1, (v.bit_length() + 8) // 8), "big", signed=True))


def _oid(oid: tuple) -> bytes:
    out = bytearray([oid[0] * 40 + oid[1]])
    for n in oid[2:]:
        enc = [n & 0x7F]
        n >>= 7
        while n:
            enc.append(0x80 | (n & 0x7F))
            n >>= 7
        out += bytes(reversed(enc))
    return _tlv(0x06, bytes(out))


def encode_getbulk(community: str, req_id: int, oid: tuple, max_rep=25) -> bytes:
    vb = _tlv(0x30, _tlv(0x30, _oid(oid) + b"\x05\x00"))
    pdu = _tlv(0xA5, _int(req_id) + _int(0) + _int(max_rep) + vb)
    return _tlv(0x30, _int(1) + _tlv(0x04, community.encode()) + pdu)


def _read(buf: bytes, i: int):
    tag = buf[i]
    ln = buf[i + 1]
    i += 2
    if ln & 0x80:
        k = ln & 0x7F
        ln = int.from_bytes(buf[i:i + k], "big")
        i += k
    return tag, buf[i:i + ln], i + ln


def _dec_oid(b: bytes) -> tuple:
    out = [b[0] // 40, b[0] % 40]
    n = 0
    for x in b[1:]:
        n = (n << 7) | (x & 0x7F)
        if not x & 0x80:
            out.append(n)
            n = 0
    return tuple(out)


def _value(tag, v):
    if tag in (0x02, 0x41, 0x42, 0x43, 0x46):
        return int.from_bytes(v, "big", signed=(tag == 0x02))
    if tag == 0x06:
        return _dec_oid(v)
    if tag == 0x40:
        return ".".join(str(x) for x in v)
    if tag in (0x80, 0x81, 0x82):
        return StopIteration
    return v  # OCTET STRING → bytes


def decode_response(buf: bytes):
    """→ (request_id, error_status, [(oid, value), ...])"""
    _, msg, _ = _read(buf, 0)
    _, _, i = _read(msg, 0)        # version
    _, _, i = _read(msg, i)        # community
    tag, pdu, _ = _read(msg, i)
    if tag != 0xA2:
        raise ValueError("Beklenmeyen SNMP PDU")
    _, rid, j = _read(pdu, 0)
    _, err, j = _read(pdu, j)
    _, _, j = _read(pdu, j)
    _, vbl, _ = _read(pdu, j)
    out, k = [], 0
    while k < len(vbl):
        _, vb, k = _read(vbl, k)
        _, ob, m = _read(vb, 0)
        vt, vv, _ = _read(vb, m)
        out.append((_dec_oid(ob), _value(vt, vv)))
    return int.from_bytes(rid, "big", signed=True), int.from_bytes(err, "big"), out


def parse_oid(s: str) -> tuple:
    return tuple(int(x) for x in s.strip(".").split("."))


def walk(host: str, community: str, oid: str, timeout=2.0, retries=1, port=161, limit=50000):
    """Tablo yürüt: [(indeks_tuple, değer)] (indeks = kök OID'den sonraki kısım)."""
    root = parse_oid(oid)
    cur = root
    out = []
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        while len(out) < limit:
            rid = int.from_bytes(os.urandom(3), "big")
            pkt = encode_getbulk(community, rid, cur)
            for attempt in range(retries + 1):
                try:
                    s.sendto(pkt, (host, port))
                    while True:
                        data, _ = s.recvfrom(65535)
                        r_id, err, vbs = decode_response(data)
                        if r_id == rid:
                            break
                    break
                except socket.timeout:
                    if attempt == retries:
                        raise TimeoutError(f"{host} SNMP yanıt vermedi (community/erişim listesi?)")
            if err:
                break
            done = False
            for o, v in vbs:
                if v is StopIteration or o[:len(root)] != root:
                    done = True
                    break
                out.append((o[len(root):], v))
                cur = o
            if done or not vbs:
                break
    finally:
        s.close()
    return out
