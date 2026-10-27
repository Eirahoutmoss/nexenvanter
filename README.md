# NexEnvanter

**Hastane Envanter Yönetim Sistemi** — Takip. Kontrol. Güven. Her Zaman.

Cihaz envanterini tek merkezde tutar; Excel'den toplu aktarır, QR kodlu etiket basar (Brother PT-P900WC ve diğer yazıcılar), telefonla QR okutulunca cihaz kartını açar. Tek dosya `NexEnvanter.exe` — kurulum ve ek bağımlılık gerektirmez.

Geliştiren: **Hasan Güler**

## Hızlı başlangıç

1. [Sürümler](../../releases) sayfasından `NexEnvanter.exe` indirin, bir klasöre koyun (ör. `C:\NexEnvanter\`).
2. Çalıştırın. Tarayıcı açılır → ilk kurulumda yönetici hesabını oluşturun.
3. Telefonların erişebilmesi için **bir kez** yönetici olarak: `NexEnvanter.exe --firewall`
4. **Ayarlar → QR temel adresi**: sunucunun sabit IP'si veya yerel DNS adı (ör. `http://envanter.hastane.local:8750`). Etiket basmadan önce ayarlayın.
5. **Excel İşlemleri** → `test.xlsx` biçimindeki dosyayı yükleyin → eşleştirmeyi kontrol edin → *Deneme* → *İçe aktar*.

Veriler exe'nin yanındaki `data\` klasöründedir (veritabanı + otomatik yedekler).

## Komut satırı

```
NexEnvanter.exe [--port 8750] [--host 0.0.0.0] [--data KLASÖR] [--no-browser] [--firewall] [--version]
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
  license.py    lisans kancası (şu an kapalı)
web/            arayüz (derleme adımı yok)
docs/TASARIM.md tasarım, mimari, karar günlüğü, yol haritası
```

Ayrıntılar: [docs/TASARIM.md](docs/TASARIM.md)
