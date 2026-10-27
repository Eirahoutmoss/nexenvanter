"""SQLite (WAL) veritabanı: şema, sürüm geçişleri, ayarlar, yedekleme."""
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime

from .paths import DIRS

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

-- Dinamik alan şeması: Excel'e yeni sütun eklendiğinde kod değişmeden alan eklenir.
CREATE TABLE IF NOT EXISTS fields (
  key          TEXT PRIMARY KEY,
  label        TEXT NOT NULL,
  type         TEXT NOT NULL DEFAULT 'text',   -- text|longtext|number|date|mac|select
  options      TEXT NOT NULL DEFAULT '[]',     -- select seçenekleri
  aliases      TEXT NOT NULL DEFAULT '[]',     -- Excel başlık eş adları
  required     INTEGER NOT NULL DEFAULT 0,
  show_list    INTEGER NOT NULL DEFAULT 1,
  show_preview INTEGER NOT NULL DEFAULT 0,     -- QR önizlemesinde (oturum açmış)
  public       INTEGER NOT NULL DEFAULT 0,     -- QR önizlemesinde oturumsuz görünür
  sort         INTEGER NOT NULL DEFAULT 100,
  system       INTEGER NOT NULL DEFAULT 0,
  active       INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS assets (
  id          INTEGER PRIMARY KEY,
  public_id   TEXT NOT NULL UNIQUE,
  asset_code  TEXT NOT NULL UNIQUE COLLATE NOCASE,
  status      TEXT NOT NULL DEFAULT 'aktif',
  data        TEXT NOT NULL DEFAULT '{}',
  search      TEXT NOT NULL DEFAULT '',
  archived    INTEGER NOT NULL DEFAULT 0,
  source_import INTEGER,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL,
  created_by  TEXT,
  updated_by  TEXT
);
CREATE INDEX IF NOT EXISTS ix_assets_status ON assets(status, archived);
CREATE INDEX IF NOT EXISTS ix_assets_updated ON assets(updated_at);

CREATE TABLE IF NOT EXISTS asset_events (
  id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL, at TEXT NOT NULL, user TEXT,
  action TEXT NOT NULL, changes TEXT NOT NULL DEFAULT '{}', note TEXT
);
CREATE INDEX IF NOT EXISTS ix_events_asset ON asset_events(asset_id, at);

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, full_name TEXT,
  role TEXT NOT NULL DEFAULT 'viewer', pw_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, last_login TEXT
);
CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires REAL NOT NULL);

CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, user TEXT, ip TEXT, action TEXT NOT NULL, target TEXT, detail TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_at ON audit(at);

CREATE TABLE IF NOT EXISTS import_jobs (
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, user TEXT, filename TEXT, sheet TEXT,
  mode TEXT, mapping TEXT, stats TEXT, report TEXT
);
CREATE TABLE IF NOT EXISTS print_jobs (
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, user TEXT, printer TEXT, adapter TEXT,
  asset_ids TEXT, copies INTEGER, status TEXT NOT NULL, error TEXT
);
"""

# test.xlsx sütunlarından türetilen başlangıç alanları
DEFAULT_FIELDS = [
    # key, label, type, aliases, show_list, show_preview, public, sort
    ("hardware_info", "Donanım Bilgisi", "text", ["donanim", "donanim bilgisi", "cihaz turu", "tur"], 1, 1, 1, 20),
    ("brand_model", "Marka Model", "text", ["marka", "model", "marka model", "urun", "urun marka model"], 1, 1, 1, 30),
    ("location_name", "Birim / Servis / Alan", "text",
     ["birim", "servis", "alan", "bulundugu birim", "bulundugu birim servis alan", "birim adi", "konum"], 1, 1, 1, 40),
    ("serial_number", "Seri Numarası", "text", ["seri", "seri no", "seri numarasi", "serial", "sn"], 1, 0, 0, 50),
    ("mac_address", "MAC Adresi", "mac", ["mac", "mac adres", "mac adresi"], 0, 0, 0, 60),
    ("last_action_at", "Son Yapılan İşlem Tarihi", "date", ["son islem", "son yapilan islem tarihi", "islem tarihi"], 1, 1, 0, 70),
    ("description", "Açıklama", "longtext", ["aciklama", "not", "notlar"], 0, 0, 0, 80),
]

# Sabit (sistem) alanlar: assets tablosunun kendi sütunları
SYSTEM_FIELDS = [
    ("asset_code", "Barkod / Envanter No", "text",
     ["barkod", "barkot", "barkod no", "barkot numarasi", "barkod numarasi", "envanter no", "demirbas no"], 1, 1, 1, 10),
    ("status", "Durum", "select", ["durum", "status"], 1, 1, 1, 90),
]

STATUSES = ["aktif", "depoda", "bakımda", "serviste", "arızalı", "hurda"]

DEFAULT_SETTINGS = {
    "org_name": "ADIYAMAN EĞİTİM VE ARAŞTIRMA HASTANESİ",
    "unit_name": "BİLGİ İŞLEM BİRİMİ",
    "system_title": "TEKNİK MALZEME KONTROL KAYIT SİSTEMİ",
    "base_url": "",            # boşsa LAN IP + port otomatik
    "import_ignore_headers": ["no", "sira", "sira no", "s no"],
    "backup_keep": 14,
    "label_template": None,     # labels.DEFAULT_TEMPLATE
    "default_printer": "",
    # Pro
    "public_tickets": True,          # QR sayfasından oturumsuz arıza bildirimi
    "ticket_categories": ["Açılmıyor / çalışmıyor", "Yazdırma sorunu", "Ağ / internet", "Yazılım / HBYS", "Ekran / çevre birimi", "Diğer"],
    "remote_url_template": "",       # ör. nexdesk://connect/{nexdesk_id}
    "ldap": {"enabled": False, "server": "", "domain": "", "base_dn": "", "use_ssl": False,
             "role_map": [], "default_role": "viewer", "allow_unmapped": False},
    "net_scan": {"subnets": [], "interval_hours": 0, "stale_days": 30},
    "renewal": {"age_years": 5, "tickets_12m": 3},
    "maintenance_warn_days": 14,
    "warranty_warn_days": 60,
    "tls": {"enabled": False},
}

_local = threading.local()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    c = sqlite3.connect(DIRS.db, timeout=30, check_same_thread=False, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA foreign_keys=ON")
    from .textnorm import fold
    c.create_function("fold", 1, lambda v: fold(v) if v is not None else None, deterministic=True)
    return c


def conn() -> sqlite3.Connection:
    c = getattr(_local, "c", None)
    if c is None:
        c = _local.c = connect()
    return c


@contextmanager
def tx():
    c = conn()
    c.execute("BEGIN IMMEDIATE")
    try:
        yield c
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise


def init():
    c = conn()
    c.executescript(SCHEMA)
    ver = c.execute("PRAGMA user_version").fetchone()[0]
    if ver < 1:
        with tx() as t:
            for key, label, typ, al, sl, sp, pub, sort in SYSTEM_FIELDS:
                t.execute("INSERT OR IGNORE INTO fields(key,label,type,aliases,required,show_list,show_preview,public,sort,system,options)"
                          " VALUES(?,?,?,?,?,?,?,?,?,1,?)",
                          (key, label, typ, json.dumps(al), 1 if key == "asset_code" else 0, sl, sp, pub, sort,
                           json.dumps(STATUSES if key == "status" else [])))
            for key, label, typ, al, sl, sp, pub, sort in DEFAULT_FIELDS:
                t.execute("INSERT OR IGNORE INTO fields(key,label,type,aliases,show_list,show_preview,public,sort)"
                          " VALUES(?,?,?,?,?,?,?,?)", (key, label, typ, json.dumps(al), sl, sp, pub, sort))
            for k, v in DEFAULT_SETTINGS.items():
                t.execute("INSERT OR IGNORE INTO settings VALUES(?,?)", (k, json.dumps(v, ensure_ascii=False)))
        c.execute("PRAGMA user_version=1")
    if ver < 2:
        with tx() as t:
            for stmt in SCHEMA_V2.split(";"):
                if stmt.strip():
                    t.execute(stmt)
            for key, label, typ, al, sl, sp, pub, sort in FIELDS_V2:
                t.execute("INSERT OR IGNORE INTO fields(key,label,type,aliases,show_list,show_preview,public,sort)"
                          " VALUES(?,?,?,?,?,?,?,?)", (key, label, typ, json.dumps(al), sl, sp, pub, sort))
            import secrets
            t.execute("INSERT OR IGNORE INTO settings VALUES('agent_token',?)", (json.dumps(secrets.token_urlsafe(24)),))
        c.execute("PRAGMA user_version=2")
    # Gelecek geçişler: if ver < 3: ...


SCHEMA_V2 = """
ALTER TABLE users ADD COLUMN source TEXT NOT NULL DEFAULT 'local';
ALTER TABLE users ADD COLUMN units TEXT NOT NULL DEFAULT '[]';
ALTER TABLE users ADD COLUMN email TEXT;
CREATE TABLE api_tokens (id INTEGER PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, role TEXT NOT NULL,
  created_at TEXT NOT NULL, created_by TEXT, last_used TEXT, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE tickets (id INTEGER PRIMARY KEY, asset_id INTEGER, status TEXT NOT NULL DEFAULT 'yeni', priority TEXT NOT NULL DEFAULT 'normal',
  category TEXT, description TEXT NOT NULL, reporter_name TEXT, reporter_contact TEXT, reporter_unit TEXT, reporter_ip TEXT,
  source TEXT NOT NULL DEFAULT 'panel', assigned_to TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  resolved_at TEXT, resolution TEXT, kb_id INTEGER, public_code TEXT);
CREATE INDEX ix_tickets_status ON tickets(status);
CREATE INDEX ix_tickets_asset ON tickets(asset_id);
CREATE TABLE ticket_notes (id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, at TEXT NOT NULL, user TEXT, note TEXT NOT NULL);
CREATE TABLE counts (id INTEGER PRIMARY KEY, name TEXT NOT NULL, location TEXT, status TEXT NOT NULL DEFAULT 'açık',
  created_at TEXT NOT NULL, created_by TEXT, closed_at TEXT, closed_by TEXT, note TEXT);
CREATE TABLE count_items (count_id INTEGER NOT NULL, asset_id INTEGER NOT NULL, seen_at TEXT NOT NULL, seen_by TEXT,
  seen_location TEXT, PRIMARY KEY(count_id, asset_id));
CREATE TABLE count_unknown (id INTEGER PRIMARY KEY, count_id INTEGER NOT NULL, code TEXT NOT NULL, seen_at TEXT NOT NULL, seen_by TEXT);
CREATE TABLE assignments (id INTEGER PRIMARY KEY, doc_no TEXT NOT NULL, asset_id INTEGER NOT NULL, kind TEXT NOT NULL DEFAULT 'kişi',
  holder_name TEXT NOT NULL, holder_title TEXT, holder_unit TEXT, started_at TEXT NOT NULL, ended_at TEXT, created_by TEXT,
  ended_by TEXT, note TEXT, signature TEXT, giver_signature TEXT, return_doc_no TEXT, return_signature TEXT);
CREATE INDEX ix_assign_asset ON assignments(asset_id);
CREATE INDEX ix_assign_doc ON assignments(doc_no);
CREATE TABLE maintenance_plans (id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL, title TEXT NOT NULL, interval_days INTEGER NOT NULL,
  next_due TEXT NOT NULL, last_done TEXT, note TEXT, active INTEGER NOT NULL DEFAULT 1, created_by TEXT, created_at TEXT NOT NULL);
CREATE INDEX ix_maint_due ON maintenance_plans(active, next_due);
CREATE TABLE consumables (id INTEGER PRIMARY KEY, name TEXT NOT NULL, code TEXT, unit TEXT NOT NULL DEFAULT 'adet', stock REAL NOT NULL DEFAULT 0,
  min_stock REAL NOT NULL DEFAULT 0, compatible TEXT, location TEXT, note TEXT, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE consumable_moves (id INTEGER PRIMARY KEY, consumable_id INTEGER NOT NULL, at TEXT NOT NULL, user TEXT, qty REAL NOT NULL,
  asset_id INTEGER, note TEXT);
CREATE TABLE kb (id INTEGER PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL, match TEXT, tags TEXT, created_by TEXT,
  created_at TEXT NOT NULL, updated_by TEXT, updated_at TEXT NOT NULL, views INTEGER NOT NULL DEFAULT 0, search TEXT NOT NULL DEFAULT '');
CREATE TABLE net_seen (mac TEXT PRIMARY KEY, ip TEXT, hostname TEXT, switch TEXT, port TEXT, vlan TEXT, first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL, source TEXT);
CREATE TABLE net_switches (id INTEGER PRIMARY KEY, name TEXT, host TEXT NOT NULL, community TEXT NOT NULL DEFAULT 'public',
  active INTEGER NOT NULL DEFAULT 1, last_poll TEXT, last_error TEXT);
CREATE TABLE agent_reports (hostname TEXT PRIMARY KEY, serial TEXT, macs TEXT, data TEXT NOT NULL, ip TEXT, at TEXT NOT NULL,
  asset_id INTEGER);
CREATE TABLE federation (id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL, token TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
  last_ok TEXT, last_error TEXT);
CREATE TABLE disposals (id INTEGER PRIMARY KEY, doc_no TEXT NOT NULL, at TEXT NOT NULL, user TEXT, reason TEXT, commission TEXT,
  asset_ids TEXT NOT NULL)
"""

# Pro sürüm alanları: taşınır mevzuatı, ağ, ajan, NexDesk
FIELDS_V2 = [
    ("tasinir_kodu", "Taşınır Kodu", "text", ["tasinir kodu", "tasinir kod", "hesap kodu"], 0, 0, 0, 100),
    ("sicil_no", "Sicil No", "text", ["sicil", "sicil no", "sicil numarasi", "demirbas sicil"], 0, 0, 0, 102),
    ("purchase_date", "Edinme Tarihi", "date", ["edinme tarihi", "alim tarihi", "alis tarihi", "satin alma tarihi", "giris tarihi"], 0, 0, 0, 104),
    ("purchase_price", "Edinme Bedeli", "number", ["edinme bedeli", "bedel", "fiyat", "alis fiyati", "tutar"], 0, 0, 0, 106),
    ("supplier", "Tedarikçi", "text", ["tedarikci", "firma", "satici"], 0, 0, 0, 108),
    ("warranty_end", "Garanti Bitiş", "date", ["garanti", "garanti bitis", "garanti bitis tarihi"], 0, 0, 0, 110),
    ("hostname", "Bilgisayar Adı", "text", ["bilgisayar adi", "hostname", "host", "pc adi", "cihaz adi"], 0, 0, 0, 120),
    ("ip_address", "IP Adresi", "text", ["ip", "ip adresi", "ip adres"], 0, 0, 0, 122),
    ("nexdesk_id", "NexDesk ID", "text", ["nexdesk", "nexdesk id", "uzak masaustu id"], 0, 0, 0, 124),
    ("os", "İşletim Sistemi", "text", ["isletim sistemi", "os"], 0, 0, 0, 130),
    ("cpu", "İşlemci", "text", ["islemci", "cpu"], 0, 0, 0, 132),
    ("ram_gb", "RAM (GB)", "number", ["ram", "bellek", "ram gb"], 0, 0, 0, 134),
    ("disk", "Disk", "text", ["disk", "depolama"], 0, 0, 0, 136),
    ("last_user", "Son Oturum Açan", "text", ["son kullanici", "kullanici"], 0, 0, 0, 138),
    ("agent_seen_at", "Ajan Son Bildirim", "text", [], 0, 0, 0, 140),
]


def get_setting(key, default=None):
    r = conn().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if r is None:
        return DEFAULT_SETTINGS.get(key, default)
    v = json.loads(r[0])
    return default if v is None and default is not None else v


def set_setting(key, value):
    conn().execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (key, json.dumps(value, ensure_ascii=False)))


def all_settings() -> dict:
    out = dict(DEFAULT_SETTINGS)
    for r in conn().execute("SELECT key,value FROM settings"):
        out[r[0]] = json.loads(r[1])
    return out


def audit(user, action, target=None, detail=None, ip=None):
    conn().execute("INSERT INTO audit(at,user,ip,action,target,detail) VALUES(?,?,?,?,?,?)",
                   (now(), user, ip, action, None if target is None else str(target),
                    None if detail is None else (detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False))))


def backup(tag="auto") -> str:
    name = f"nexenvanter-{datetime.now():%Y%m%d-%H%M%S}-{tag}.db"
    dst = DIRS.backups / name
    b = sqlite3.connect(dst)
    with b:
        conn().backup(b)
    b.close()
    keep = int(get_setting("backup_keep", 14) or 14)
    olds = sorted(DIRS.backups.glob("nexenvanter-*-auto.db"))
    for p in olds[:-keep]:
        p.unlink(missing_ok=True)
    return name


def backup_loop():
    """Açılışta ve her 24 saatte bir otomatik yedek."""
    def run():
        while True:
            try:
                backup("auto")
            except Exception as e:  # yedek hatası uygulamayı durdurmaz
                print("Yedekleme hatası:", e)
            time.sleep(24 * 3600)
    threading.Thread(target=run, daemon=True, name="backup").start()
