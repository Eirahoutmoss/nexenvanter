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
    # Gelecek geçişler: if ver < 2: ...


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
