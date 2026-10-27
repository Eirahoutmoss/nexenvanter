# NexEnvanter — Tasarım, Mimari ve Yol Haritası

> Bu belge, `BIM_Envanter_Yapi_Taslagi_Yol_Haritasi.md`, `BIM_Envanter_Yapi_Taslagi_Yol_Haritasi1.md` ve `bi_m_envanter_yap_tasla.md` taslaklarının tekrarlardan arındırılmış, tek ve güncel hâlidir. Taslaklarla çelişen yerlerde **bu belge** geçerlidir (bkz. §12 Karar günlüğü).

**Kullanım alanı:** Adıyaman Eğitim ve Araştırma Hastanesi, Bilgi İşlem Birimi · **Hedef ölçek:** 10.000+ kayıt (100.000'e kadar) · **Yazıcı:** Brother PT-P900WC, adaptörle genişletilebilir · **Dağıtım:** Tek dosya `NexEnvanter.exe`, hastane yerel ağında çalışır.

---

## 1. Amaç ve ilkeler

Envanter cihazları tek merkezi veritabanında tutulur; elle girilir veya Excel'den toplu aktarılır, düzenlenir ve her cihaz için QR kodlu fiziksel etiket basılır. QR okutulunca cihazın önizleme sayfası açılır; yetkili kullanıcı detaya geçer.

| İlke | Uygulama |
|---|---|
| **QR'da veri değil, kimlik** | QR = `<temel-adres>/e/<public_id>`. Bilgi değişince etiket yeniden basılmaz. |
| **Tek doğruluk kaynağı** | Excel ilk kaynak olabilir; canlı kayıt veritabanıdır. Excel satır no kimlik değildir. |
| **Yerel ağ öncelikli** | İnternet kesilse de LAN ve sunucu çalışıyorsa sistem çalışır. |
| **Esnek alan şeması** | Excel'e yeni sütun eklenince kod değişmeden yeni alan oluşur (§4). |
| **İzlenebilirlik** | Oluşturma, güncelleme, içe aktarma, baskı, giriş ve ayar değişiklikleri denetim kaydına yazılır. |
| **Yazıcıdan bağımsızlık** | Etiket mm tabanlı çizilir; yazıcıya gönderme adaptörde. |
| **Güvenli erişim** | QR bağlantısı tek başına detay yetkisi vermez; oturumsuz görünen alanlar ayarlanır. |
| **Silme yok, arşiv var** | Kayıtlar arşivlenir; geçmiş korunur. |

## 2. Sözlük

| Terim | Anlam |
|---|---|
| `asset_code` | Kurum içi barkod/envanter no (Excel: `BARKOT NUMARASI`), benzersiz |
| `public_id` | QR'daki tahmin edilemez kalıcı kimlik (12 karakter, URL-güvenli) |
| Dry-run | İçe aktarmanın veritabanına yazmadan rapor üretmesi |
| Label renderer | Etiketi mm ölçüsüyle yazıcı DPI'ında çizen katman (`app/labels.py`) |
| Printer adapter | Çizilen etiketi belirli yazıcıya gönderen katman (`app/printing.py`) |
| RBAC | Rol tabanlı erişim denetimi |
| RTO / RPO | Kurtarma süresi hedefi / veri kaybı toleransı |

## 3. Kullanıcı akışları

- **Yeni cihaz:** Form → zorunlu alan ve mükerrer barkod kontrolü → kayıt + kalıcı `public_id` → etiket önizleme → yazdır / kuyruğa ekle. "Kaydettikten sonra yeni kayda devam et" seçeneği seri girişi hızlandırır.
- **QR okutma:** Telefon kamerası → `/e/<public_id>` → önizleme kartı (herkese açık alanlar) → "Detayları Gör" (oturum + yetki).
- **Barkod okuyucu:** Üst arama kutusuna okut + Enter → barkod tam eşleşirse doğrudan cihaz sayfası, değilse arama sonucu.
- **Excel içe aktarma:** Yükle → sayfa/başlık satırı otomatik bulunur → sütun eşleştirme (mevcut alan / yeni alan / aktarma) → **dry-run** → onay → satır bazlı sonuç raporu (.xlsx).
- **Toplu etiket:** Liste filtrele → çoklu seç → Etiket → yazıcı + kopya → yazdır veya PDF.

## 4. Veri modeli ve esneklik

**SQLite (WAL)** tek dosya: `data/nexenvanter.db`.

| Tablo | İçerik |
|---|---|
| `fields` | Dinamik alan şeması: anahtar, ad, tip (`text/longtext/number/date/mac/select`), Excel eş adları, liste/önizleme/herkese açık/zorunlu/aktif bayrakları, sıra |
| `assets` | `id`, `public_id`, `asset_code` (UNIQUE), `status`, `data` (JSON: tüm alan değerleri), `search` (normalize arama metni), `archived`, oluşturma/güncelleme kim-ne zaman |
| `asset_events` | Değişiklik geçmişi (eski → yeni), bakım/arıza/devir notları, baskı kayıtları |
| `users`, `sessions` | Kullanıcılar (PBKDF2-SHA256), kayan süreli oturumlar |
| `import_jobs` | İçe aktarma işi, eşleştirme, istatistik, satır raporu |
| `print_jobs` | Baskı işi, yazıcı, adet, durum (`printing/sent/failed/completed`), hata |
| `audit` | Güvenlik ve yönetim denetim kaydı |
| `settings` | Kurum adı, QR temel adresi, etiket şablonu vb. |

**Neden JSON + alan şeması?** `test.xlsx` sütun ve satırları artacak. Yeni sütun: içe aktarmada "＋ Yeni alan oluştur" seçilir (tanınmayan başlıklar varsayılan olarak buna önerilir) → `fields` tablosuna eklenir, başlık eş ad olarak kaydedilir → sonraki dosyalarda otomatik eşleşir. Tablo şeması değişmez, geçiş (migration) gerekmez.

### 4.1 `test.xlsx` eşlemesi

| Excel sütunu | Alan | Tip | Not |
|---|---|---|---|
| `NO` | — | — | Yok sayılır (satır sırası, kimlik değil) |
| `BARKOT NUMARASI` | `asset_code` | metin | Zorunlu, benzersiz; boşsa satır reddedilir |
| `DONANIM BİLGİSİ` | `hardware_info` | metin | |
| `SON YAPILAN İŞLEM TARİHİ` | `last_action_at` | tarih | Excel tarihi, seri sayı veya `GG.AA.YYYY` → ISO |
| `BULUNDUĞU BİRİM SERVİS ALAN` | `location_name` | metin | Çok satırlı başlık normalize edilir |
| `MARKA MODEL` | `brand_model` | metin | |
| `SERİ NUMARASI` | `serial_number` | metin | Metin saklanır; baştaki sıfır korunur |
| `AÇIKLAMA` | `description` | uzun metin | |
| `MAC ADRES` | `mac_address` | MAC | `AA:BB:CC:DD:EE:FF`; birden çok MAC virgülle |

### 4.2 Doğrulama kuralları

- Boş hücre "önceki satırın değeri" sayılmaz. Tamamen boş satırlar atlanır.
- Dosya içinde mükerrer barkod → ikinci satır hata. Sistemde mevcut barkod → seçime göre **atla** (varsayılan) veya **güncelle**; güncellemede boş hücre mevcut değeri silmez (isteğe bağlı açılır).
- Metin ≤ 300, uzun metin ≤ 4000 karakter; tarih/MAC/sayı biçim hataları satır raporunda Türkçe mesajla.
- Yükleme: yalnızca `.xlsx/.xlsm`, ≤ 50 MB; satır satır akış (salt-okunur mod), tüm dosya belleğe alınmaz.
- Dry-run aynı kodu bir işlem (transaction) içinde çalıştırıp geri alır: deneme ile gerçek sonuç birebir aynıdır.

### 4.3 Türkçe arama

`tr_lower` + ASCII katlama: `İ→i, I→ı`, sonra `ç→c, ğ→g, ı→i, ö→o, ş→s, ü→u`. "BİLGİ İŞLEM", "bilgi islem" ve "Bilgi İşlem" aynı sonucu verir. Arama, her kayıtta tutulan `search` sütununda kelime bazlı yapılır.

## 5. Etiket ve yazıcı

**Yerleşim (varsayılan 70×36 mm, 360 dpi):** üstte siyah bant + kurum adı (isteğe bağlı sol/sağ logo) · çerçeveli alt başlık (`BİLGİ İŞLEM BİRİMİ` / `TEKNİK MALZEME KONTROL KAYIT SİSTEMİ`) · solda bilgi satırları (ÜRÜN MARKA MODEL, BİRİM ADI, SERİ NO — alan ve etiket metni seçilebilir) · sağda QR + altında envanter no.

- Ölçüler mm; yazı otomatik küçülür, sığmazsa `…` ile kısalır; satırlarda ortak yazı boyutu.
- QR: hata düzeltme M, tam sayı modül ölçeği (keskin), ayarlanabilir sessiz alan; üzerine metin/logo bindirilmez.
- Logo: yalnızca kurumun kullanım izni verdiği resmî dosya yüklenir.
- Şerit genişliği, QR basılı ölçüsü ve okunabilirlik **gerçek baskıyla** doğrulanmadan kesinleşmez.

**Adaptörler:**
1. **Windows yazdırma kuyruğu (GDI)** — üretici sürücüsü kurulu yazıcıya doğrudan; özel kağıt ölçüsü DEVMODE ile gönderilir. İlk hedef PT-P900WC.
2. **PDF** — her etiket bir sayfa, sayfa ölçüsü etiket ölçüsüyle birebir; her yazıcıyla uyum ve arşiv.
3. **Brother SDK / diğer markalar** — `PrinterAdapter` alt sınıfı olarak eklenir; uygulamanın geri kalanı değişmez.

"Gönderildi" durumu fiziksel baskının kanıtı sayılmaz; ilk baskıda QR telefonla okutulur.

## 6. Mimari

```
[Telefon / Tablet / PC tarayıcı] ──LAN──▶ NexEnvanter.exe (tek süreç)
                                          ├─ Web arayüzü (gömülü, derleme adımsız SPA)
                                          ├─ REST API (FastAPI + Uvicorn)
                                          ├─ Envanter · Alan şeması · Excel · Etiket/QR · Yetki · Denetim
                                          ├─ SQLite (WAL) + otomatik yedek döngüsü
                                          └─ Yazıcı adaptörleri ──▶ Windows kuyruğu ──▶ Brother PT-P900WC
```

**Neden tek exe + SQLite (taslaklardaki PostgreSQL/React yerine)?** Kurulum gerektirmeyen, lisanslanabilir tek dosya ürün hedefi; 100.000 kayıt SQLite için küçük ölçek; ayrı veritabanı sunucusu, Node derlemesi ve servis bağımlılığı yok. Erişim katmanı tek modülde (`app/db.py`) olduğundan ileride PostgreSQL'e geçiş sınırlı iştir.

| Katman | Seçim |
|---|---|
| Çalışma zamanı | Python 3.12, PyInstaller tek dosya (tüm bağımlılıklar exe içinde) |
| Web/API | FastAPI + Uvicorn |
| Veritabanı | SQLite WAL, `PRAGMA user_version` ile sürüm geçişleri |
| Excel | openpyxl (salt-okunur akış) |
| Etiket/QR | Pillow + qrcode |
| Yazdırma | pywin32 (Windows GDI) |
| Arayüz | Tek dosya JS/CSS, harici CDN yok (ağ kapalıyken de çalışır) |

**Veri klasörü önceliği:** `--data` → `NEXENVANTER_DATA` → exe yanındaki `data\` (taşınabilir) → `%LOCALAPPDATA%\NexEnvanter`.

## 7. Güvenlik, erişim ve KVKK

- **Roller:** Sistem Yöneticisi (her şey) · BİM Yöneticisi (envanter, içe aktarma, alanlar, etiket şablonu, arşiv) · Envanter Operatörü (ekle/düzenle, etiket) · Denetçi (okuma, dışa aktarma, denetim kaydı) · Görüntüleyici (okuma).
- Yetki her API çağrısında sunucuda denetlenir; düğme gizlemek güvenlik sayılmaz.
- Oturum: HttpOnly + SameSite=Strict çerez, 12 saat kayan süre; hatalı girişte hız sınırı (5 dk'da 8 deneme).
- CSRF: değiştiren tüm API çağrıları özel başlık (`x-nx`) taşır.
- QR önizleme: varsayılan herkese açık alanlar barkod, donanım, marka-model, birim, durum. **Seri no, MAC, açıklama oturumsuz gösterilmez** (Alanlar ekranından değiştirilebilir).
- Sistemde hasta verisi tutulmaz; açıklama/zimmet alanlarında kişisel veri olabileceğinden yedekler erişim kontrollü saklanmalı, RBAC sıkı tutulmalı (KVKK 6698).
- HTTPS: kurum sertifikasıyla ters vekil (IIS/nginx) önüne konabilir; QR temel adresi ayarlardan `https://…` yapılır.

## 8. Performans ve işletim

- Sunucu tarafı sayfalama/sıralama/filtre; liste bir seferde en fazla 1000 kayıt.
- Hedef: tipik LAN'da arama ve detay < 1 sn (10.000 kayıtta ölçülerek onaylanır; 25.000 ve 100.000 ile tekrar).
- **Yedek:** açılışta + 24 saatte bir `data\backups\` (son 14 otomatik yedek), güncelleme öncesi zorunlu yedek, el ile yedek ve indirme. Yedekler ayrıca NAS'a kopyalanmalı. **RPO ≤ 24 saat, RTO ≤ 4 saat** (yedek dosyasını `nexenvanter.db` yerine koymak yeterli).
- **Güncelleme:** Ayarlar → "Güncellemeleri denetle" → GitHub son sürüm → "İndir ve kur": yedek alınır, exe değiştirilir, program yeniden başlar.
- **Ağ:** telefonların açabilmesi için hastane Wi-Fi'ı sunucuya erişmeli; Windows Güvenlik Duvarı'nda port açık olmalı (`NexEnvanter.exe --firewall`, yönetici olarak bir kez). Sabit IP yerine yerel DNS adı önerilir (`envanter.<kurum>.local`).

## 9. API özeti

| Uç nokta | İş |
|---|---|
| `GET /api/assets` | Arama (`q`), `status`, `archived`, `f.<alan>=değer`, `sort`, `dir`, `page`, `size` |
| `POST /api/assets` · `PATCH /api/assets/{id}` | Ekle · kısmi güncelle |
| `GET /api/assets/{id}` · `/by-code/{kod}` | Detay + geçmiş + QR adresi |
| `POST /api/assets/{id}/archive` · `/events` | Arşivle/geri al · not/bakım/arıza/devir |
| `POST /api/import/upload` · `/analyze` · `/run` | Yükle+analiz · yeniden analiz · dry-run/uygula |
| `GET /api/export.xlsx` · `/api/template.xlsx` | Filtreli dışa aktarma · boş şablon |
| `GET /api/labels/preview/{id}.png` · `/api/labels/pdf?ids=` | Önizleme · PDF |
| `POST /api/print` · `GET /api/printers` | Yazdır · yazıcı listesi/durum |
| `GET/POST/PATCH /api/fields` | Alan şeması |
| `/api/users` · `/api/audit` · `/api/settings` · `/api/backup` · `/api/update/*` | Yönetim |
| `GET /e/{public_id}` | QR önizleme sayfası |

Hata biçimi: `{"error": {"code": "...", "message": "..."}}` — `VALIDATION_ERROR` 422 (alan bazlı), `ASSET_CODE_DUPLICATE` 409, `PRINT_FAILED` 503, `UNAUTHORIZED` 401, `FORBIDDEN` 403.

## 10. Test ve kabul

- **Otomatik (`pytest`):** Türkçe normalizasyon, MAC/tarih, CSRF/yetki, CRUD + mükerrer, gerçek `test.xlsx` dry-run/uygula/tekrar, yeni sütun → yeni alan, etiket PNG/PDF, Excel dışa aktarma, roller. GitHub Actions her gönderimde testleri çalıştırır, exe derler ve exe'yi ayağa kaldırıp dener.
- **Saha:** PT-P900WC ile gerçek baskı; QR'ın en az 5 farklı Android/iPhone ile okunması; uzun marka-model/seri metinleri; şerit genişliği–ölçü tutarlılığı; yıpranma.
- **Performans/güvenlik:** 10.000+ kayıtla arama; eşzamanlı kullanıcı; büyük Excel; doğrudan URL erişim denetimi; yedekten geri yükleme tatbikatı.

## 11. Yol haritası

| Faz | Kapsam | Durum |
|---|---|---|
| **0 Gereksinim** | Etiket ölçüsü/şerit, logo izni, yazıcı bağlantısı (USB/Wi-Fi), sunucu PC, DNS adı, oturumsuz alanlar | Açık kararlar §13 |
| **1 Temel ürün** | CRUD, arama/filtre/sayfalama, QR önizleme, detay + geçmiş, roller, denetim | ✅ v0.1 |
| **2 Excel** | Analiz, eşleştirme, yeni alan, dry-run, atla/güncelle, rapor, dışa aktarma, şablon | ✅ v0.1 |
| **3 Etiket & yazıcı** | mm şablon editörü, logo, PDF, Windows yazıcı adaptörü, baskı geçmişi | ✅ v0.1 · saha testi bekliyor |
| **4 Sağlamlaştırma** | Otomatik yedek, güncelleme, pilot (BİM içi küçük grup), 10.000+ kayıt testi, kullanıcı kılavuzu | Kısmen |
| **5 Genişletme** | Lisans, Windows hizmeti/tepsi simgesi, HTTPS, LDAP/AD, bakım iş akışı, zimmet, ekler | Planlı (§14) |

## 12. Karar günlüğü

| No | Karar | Gerekçe |
|---|---|---|
| K-01 | Python (FastAPI) | Ağ/otomasyon tarafında Python deneyimi, hızlı müdahale |
| K-02 | Aynı barkod veritabanında reddedilir (UNIQUE); Excel'de varsayılan "atla", isteğe bağlı "güncelle" | Tek doğruluk kaynağı, kargaşayı önleme |
| K-03 | Tek exe + SQLite + gömülü arayüz | Kurulumsuz dağıtım, lisanslanabilir ürün, 100k ölçek için yeterli |
| K-04 | Alan değerleri JSON + `fields` şeması | Excel sütunları artacak; kod/şema değişmeden alan ekleme |
| K-05 | QR = temel adres + 12 karakter rastgele kimlik | Kısa QR (daha büyük modül, kolay okuma), tahmin edilemez |
| K-06 | Etiket tek çizicide (Pillow) → önizleme, PDF, yazıcı aynı görüntü | Ekranda görülen = basılan |
| K-07 | Lisans şimdilik kapalı; kanca `app/license.py` | Lisanslı derlemeye geçişte tek modül değişir |

## 13. Açık kararlar

1. Brother şerit genişliği (24 / 36 mm) ve etiket uzunluğu? (Varsayılan 70×36 mm.)
2. PT-P900WC bağlantısı: sunucu PC'ye USB mi, ağ (Wi-Fi/LAN) mı?
3. Sunucu olacak bilgisayar / sanal makine ve yerel DNS adı.
4. Oturumsuz QR önizlemesinde görünecek alanların kurumca onayı.
5. Logo dosyalarının yüksek çözünürlüklü, kullanım izni olan sürümü.
6. Kimlik: yerel kullanıcı (şu an) mı, Active Directory mi?

## 14. Geliştirme fikirleri (öncelik sırasıyla)

1. **Lisanslama:** Ed25519 imzalı lisans dosyası + makine kimliği (`license.machine_id()` hazır); sürüm türüne göre kayıt/kullanıcı sınırı.
2. **Windows hizmeti / tepsi simgesi:** oturum kapalıyken de çalışma, konsol penceresi yerine tepsi menüsü.
3. **Kamera ile sayım (envanter turu):** telefondan art arda QR okutup "görüldü" işaretleme; birim bazlı sayım raporu ve kayıp/fazla listesi.
4. **Zimmet ve devir-teslim:** kişi/birim zimmeti, imzalı devir tutanağı PDF'i.
5. **Bakım/arıza iş akışı:** açık–devam–kapalı durumları, servis firması, maliyet, garanti bitiş uyarısı.
6. **Belge ekleri:** fatura, garanti, fotoğraf.
7. **Ağ keşfi entegrasyonu:** NexScan/SNMP ile MAC–IP–switch portu eşleştirme; envanterde olmayan cihaz uyarısı.
8. **HBYS/AD entegrasyonu:** LDAP girişi, kullanıcı listesinden zimmet.
9. **Raporlar:** birim × tür matrisi, yaş/garanti analizi, denetim dışa aktarma.
10. **Çoklu yazıcı profilleri** ve Brother b-PAC/SDK adaptörü (kesme, yarım kesme, yüksek çözünürlük).
