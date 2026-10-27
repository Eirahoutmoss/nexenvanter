"""Türkçe metin normalizasyonu ve değer dönüştürücüler."""
import re
import unicodedata
from datetime import date, datetime, timedelta

_TR_LOWER = str.maketrans({"I": "ı", "İ": "i"})
_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜâîû", "cgiosuCGIOSUaiu")


def tr_lower(s) -> str:
    if s is None:
        return ""
    return str(s).translate(_TR_LOWER).lower()


def tr_upper(s) -> str:
    if s is None:
        return ""
    return str(s).replace("i", "İ").replace("ı", "I").upper()


def fold(s) -> str:
    """Arama/eşleştirme anahtarı: küçük harf, Türkçe→ASCII, aksansız, tek boşluk."""
    s = tr_lower(s).translate(_ASCII)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip()


def header_key(s) -> str:
    """Excel başlığı karşılaştırma anahtarı ('BULUNDUĞU BİRİM \\nSERVİS' → 'bulundugu birim servis')."""
    return re.sub(r"[^a-z0-9]+", " ", fold(s)).strip()


def slug(s) -> str:
    k = header_key(s).replace(" ", "_")
    if not k or k[0].isdigit():
        k = "f_" + k
    return k[:48]


def cell_text(v) -> str | None:
    """Excel hücresini metne çevir; 123123123.0 → '123123123', baştaki sıfırlar korunur (metin hücrede)."""
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d") if v.time() == datetime.min.time() else v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    return s or None


_MAC_HEX = re.compile(r"[^0-9A-Fa-f]")


def norm_mac(v) -> str | None:
    """Birden çok MAC ',', ';' veya boşlukla ayrılabilir. Hatalıysa ValueError."""
    s = cell_text(v)
    if not s or s in ("-", "—"):
        return None
    out = []
    for part in re.split(r"[,;\s/]+", s):
        if not part:
            continue
        h = _MAC_HEX.sub("", part).upper()
        if len(h) != 12:
            raise ValueError(f"Geçersiz MAC: {part}")
        out.append(":".join(h[i:i + 2] for i in range(0, 12, 2)))
    return ", ".join(out) or None


_DATE_FMTS = ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M",
              "%Y-%m-%d %H:%M:%S", "%d.%m.%y")


def norm_date(v) -> str | None:
    """Excel tarih hücresi, seri numarası veya metin → ISO 'YYYY-MM-DD'. Hatalıysa ValueError."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (int, float)) and 20000 < v < 80000:  # Excel seri tarih
        return (date(1899, 12, 30) + timedelta(days=int(v))).isoformat()
    s = str(v).strip()
    if not s:
        return None
    for f in _DATE_FMTS:
        try:
            return datetime.strptime(s, f).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Tarih anlaşılamadı: {s}")


def norm_number(v) -> str | None:
    s = cell_text(v)
    if s is None:
        return None
    try:
        float(s.replace(",", "."))
    except ValueError:
        raise ValueError(f"Sayı değil: {s}")
    return s
