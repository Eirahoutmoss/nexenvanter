# NexEnvanter

**Hastane Envanter Yönetim Sistemi** — Takip. Kontrol. Güven. Her Zaman.

Cihaz envanterini tek merkezde tutar; Excel'den toplu aktarır, QR kodlu etiket basar (Brother PT-P900WC ve diğer yazıcılar), telefonla QR okutulunca cihaz kartını açar. QR'dan arıza bildirimi, sayım, zimmet/devir tutanağı, bakım-garanti takibi, sarf stok, bilgi bankası, ağ keşfi (SNMP/ARP), PC donanım ajanı, raporlar ve denetim paketi, Active Directory girişi, kurumlar paneli. Tek dosya `NexEnvanter.exe` — kurulum ve ek bağımlılık gerektirmez.

Geliştiren: **Hasan Güler**

## Hızlı başlangıç

1. [Sürümler](../../releases) sayfasından `NexEnvanter.exe` indirin, bir klasöre koyun (ör. `C:\NexEnvanter\`).
2. Çalıştırın. Tarayıcı açılır → ilk kurulumda yönetici hesabını oluşturun.
3. Program tepsi simgesiyle çalışır. Sağ tık → **Arka plan hizmeti olarak kur** (yönetici): bilgisayar açılınca oturum açılmasa da çalışır, güvenlik duvarı kuralı da eklenir. Hizmet kurmadan yalnızca port açmak için: `NexEnvanter.exe --firewall`
4. **Ayarlar → QR temel adresi**: sunucunun sabit IP'si veya yerel DNS adı (ör. `http://envanter.hastane.local:8750`). Etiket basmadan önce ayarlayın.
5. **Excel İşlemleri** → `test.xlsx` biçimindeki dosyayı yükleyin → eşleştirmeyi kontrol edin → *Deneme* → *İçe aktar*.

Veriler exe'nin yanındaki `data\` klasöründedir (veritabanı, otomatik yedekler, günlükler `logs\`, HTTPS sertifikası `tls\`).

## Komut satırı

```
NexEnvanter.exe [--port 8750] [--host 0.0.0.0] [--data KLASÖR] [--no-browser] [--headless] [--tray]
                [--firewall] [--install-service] [--uninstall-service] [--version]
```

## Geliştirme

```bat
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements-dev.txt
python run.py            :: http://127.0.0.1:8750
python -m pytest -q
build.bat                :: dist\NexEnvanter.exe
```

**Sürüm yayınlama:** `git tag v0.1.0 && git push --tags` → GitHub Actions testleri çalıştırır, exe'yi derler, dener ve sürüme ekler. Uygulama içindeki "Güncellemeleri denetle" bu sürümü bulup kurar.

## Yapı

```
app/
  main.py       giriş noktası (sunucu, veri klasörü, yedek döngüsü)
  api.py        REST API + QR önizleme sayfası
  db.py         SQLite şeması, geçişler, ayarlar, yedek
  fields.py     dinamik alan şeması (Excel'e eklenen sütunlar)
  assets.py     envanter kayıtları, arama, geçmiş
  importer.py   Excel analiz / eşleştirme / dry-run / uygula
  exporter.py   Excel dışa aktarma
  labels.py     mm tabanlı etiket + QR çizici
  printing.py   yazıcı adaptörleri (Windows GDI; genişletilebilir)
  auth.py       kullanıcı, oturum, roller
  updater.py    GitHub sürüm denetimi ve uygulama içi güncelleme
  tickets.py counts.py assignments.py maintenance.py stock.py kb.py   operasyon modülleri
  network.py snmp.py agent.py   ağ keşfi, SNMP istemcisi, PC ajanı
  reports.py federation.py      raporlar, denetim paketi, kurumlar paneli
  api_pro.py    pro API + QR sayfası + yazdırılabilir tutanaklar
  tls.py        HTTPS sertifikası
  license.py    Ed25519 lisans (şu an zorlanmıyor)
tools/license_tool.py  lisans anahtarı/dosyası üretimi (yalnızca geliştirici)
web/            arayüz (derleme adımı yok)
docs/TASARIM.md tasarım, mimari, karar günlüğü, yol haritası
```

Ayrıntılar: [docs/TASARIM.md](docs/TASARIM.md)
