# NexEnvanter

**Hastane Envanter Yönetim Sistemi** — Takip. Kontrol. Güven. Her Zaman.

Geliştiren: **Hasan Güler**

---

## İçindekiler

1. [Bu program nedir, ne işe yarar?](#1-bu-program-nedir-ne-işe-yarar)
2. [Önce bilmeniz gerekenler (sözlük)](#2-önce-bilmeniz-gerekenler-sözlük)
3. [Hangi dosyayı indirmeliyim?](#3-hangi-dosyayı-indirmeliyim)
4. [Windows'ta kurulum — adım adım](#4-windowsta-kurulum--adım-adım)
5. [Linux'ta kurulum — adım adım](#5-linuxta-kurulum--adım-adım)
6. [İlk açılış: yönetici hesabı ve temel ayarlar](#6-ilk-açılış-yönetici-hesabı-ve-temel-ayarlar)
7. [Cihazları programa almak (Excel ile toplu aktarım)](#7-cihazları-programa-almak-excel-ile-toplu-aktarım)
8. [QR etiket basmak ve telefonla okutmak](#8-qr-etiket-basmak-ve-telefonla-okutmak)
9. [Menüdeki bölümler ne işe yarar?](#9-menüdeki-bölümler-ne-işe-yarar)
10. [NexAgent: bilgisayarlardan otomatik bilgi toplama](#10-nexagent-bilgisayarlardan-otomatik-bilgi-toplama)
11. [Güncelleme, yedekleme, kaldırma](#11-güncelleme-yedekleme-kaldırma)
12. [Sorun giderme](#12-sorun-giderme)
13. [Geliştiriciler için](#13-geliştiriciler-için)

---

## 1. Bu program nedir, ne işe yarar?

Bir kurumda (hastane, okul, belediye…) yüzlerce bilgisayar, yazıcı, telefon, ağ cihazı bulunur. "Hangi cihaz nerede, kimde, kaç yaşında, garantisi bitti mi, en son ne zaman bozuldu?" sorularının cevabı genelde dağınık Excel dosyalarında ya da kişilerin kafasındadır.

**NexEnvanter bu bilgilerin hepsini tek yerde toplar.** Bir sunucu bilgisayarda çalışır; kurumdaki herkes kendi bilgisayarından ya da telefonundan **tarayıcı** (Chrome, Edge…) ile ona bağlanır. Ek bir program kurmaları gerekmez.

Programla yapabilecekleriniz:

| Ne yapmak istiyorum? | Program ne sunuyor? |
|---|---|
| Elimdeki cihaz listesini programa almak | Excel dosyasını yükleyin; program sütunları tanır, hataları gösterir, onayınızla aktarır |
| Her cihaza etiket yapıştırmak | Her cihaz için **QR kodlu etiket** basılır (Brother PT-P900WC ve diğer yazıcılar) |
| Cihazın bilgisine hızlıca ulaşmak | Telefonla etiketteki QR okutulur, cihaz kartı açılır |
| Arıza bildirmek / takip etmek | QR'dan veya menüden arıza kaydı açılır, durumu izlenir |
| Cihaz kimde, kime devredildi? | **Zimmet** ve devir tutanağı (yazdırılabilir) |
| Yıllık sayım yapmak | **Sayım** bölümü: sahadaki cihazlar işaretlenir, eksikler listelenir |
| Bakım ve garanti tarihlerini kaçırmamak | **Bakım & Garanti** bölümü yaklaşan/geçen tarihleri gösterir |
| Toner, kablo gibi sarf malzemeleri izlemek | **Sarf Stok** |
| Ağdaki cihazları kendiliğinden bulmak | **Ağ & Ajan**: ağ taraması (SNMP/ARP) |
| Bilgisayarların donanım ve yazılım bilgisini elle yazmamak | **NexAgent**: her bilgisayara küçük bir ajan kurulur, program bilgileri kendisi çeker |
| Yönetime / denetime rapor vermek | **Raporlar** ve denetim paketi |
| Kimin ne zaman ne değiştirdiğini görmek | **Denetim Kaydı** |

Program **tek bir dosya** olarak çalışır (Windows'ta `NexEnvanter.exe`). Veritabanı programın içindedir (SQLite); ayrıca veritabanı programı kurmanız gerekmez. İnternet bağlantısı yalnızca güncelleme kontrolü için gerekir; **yerel ağ çalıştıkça program çalışır.**

---

## 2. Önce bilmeniz gerekenler (sözlük)

Bu bölüm teknik bilgisi olmayanlar içindir. Sonraki bölümlerde bu kelimeler geçecek.

- **Sunucu:** NexEnvanter'in çalıştığı bilgisayar. Sürekli açık kalması gerekir. Sıradan bir masaüstü bilgisayar da olur.
- **İstemci:** Kurumdaki diğer bilgisayarlar (kullanıcıların bilgisayarları).
- **Tarayıcı:** Chrome, Edge, Firefox gibi internet gezme programı. NexEnvanter'e tarayıcıdan girilir.
- **IP adresi:** Bilgisayarın ağdaki "ev numarası" (örn. `192.168.1.25`). Sunucunun IP adresini öğrenmek için sunucuda **Başlat → `cmd` yazıp Enter → `ipconfig` yazıp Enter** deyin; "IPv4 Adresi" satırındaki sayı IP adresidir. Linux'ta `hostname -I`.
- **Sabit IP:** IP adresinin değişmemesi. Sunucunun IP'si değişirse QR etiketler ve ajanlar sunucuyu bulamaz. **Sunucuya mutlaka sabit IP verin** (ağ yöneticinize "bu bilgisayara sabit IP ayırın" demeniz yeterli).
- **Port:** Bir bilgisayardaki programlara açılan numaralı kapılar. NexEnvanter varsayılan olarak **8750** numaralı kapıyı kullanır. Adres şöyle yazılır: `http://192.168.1.25:8750`
- **Güvenlik duvarı:** Bilgisayarı dışarıdan gelen bağlantılara karşı koruyan yazılım. Başka bilgisayarların NexEnvanter'e girebilmesi için 8750 portuna izin verilmelidir (kurucu bunu sizin için yapar).
- **Yönetici olarak çalıştırmak:** Programa sağ tıklayıp **"Yönetici olarak çalıştır"** demek. Kurulumlar bunu ister.
- **Hizmet (servis):** Siz oturum açmasanız bile bilgisayar açılınca kendiliğinden çalışan program. Sunucu için önerilen yöntem budur.
- **QR kod:** Telefon kamerasıyla okunan kare barkod. Etiketteki QR, cihazın kartının adresini taşır.
- **Ajan (NexAgent):** İstemci bilgisayara kurulan küçük, sessiz çalışan program. Bilgisayarın donanım/yazılım bilgisini toplar, NexEnvanter sorunca verir.
- **GitHub / Release (Sürüm):** Programın indirme sayfası. Her yeni sürüm orada yayınlanır.

---

## 3. Hangi dosyayı indirmeliyim?

İndirme sayfası: bu sayfadaki **Releases** (Sürümler) bağlantısı. En üstteki (en yeni) sürümün altında **Assets** bölümünü açın.

| Durumunuz | İndirilecek dosya |
|---|---|
| Sunucum **Windows** ve **kalıcı kurmak** istiyorum (önerilen) | `NexEnvanter-Setup-<sürüm>.exe` |
| Sunucum Windows, sadece **denemek** istiyorum (kurulum yok) | `NexEnvanter.exe` |
| Sunucum **Linux (Ubuntu/Debian/…)** | `NexEnvanter-<sürüm>-linux-x64.tar.gz` |
| Kurumdaki bilgisayarlara ajan kuracağım | `NexAgent-…` dosyaları (**elle indirmeniz gerekmez**; bkz. [Bölüm 10](#10-nexagent-bilgisayarlardan-otomatik-bilgi-toplama)) |

> Emin değilseniz: Windows sunucu için **Setup.exe**, Linux sunucu için **tar.gz**.

---

## 4. Windows'ta kurulum — adım adım

### 4.1. Kurulum sihirbazıyla (önerilen)

1. `NexEnvanter-Setup-<sürüm>.exe` dosyasını sunucu bilgisayara indirin.
2. Dosyaya **sağ tıklayın → Yönetici olarak çalıştır**. (Windows "Bilinmeyen yayıncı" uyarısı verirse **Ek bilgi → Yine de çalıştır** deyin. Program henüz kod imzalama sertifikasıyla imzalı değildir; bu normaldir.)
3. Dil Türkçe gelir. **İleri** ile devam edin.
4. **Port seçimi** sayfası: Varsayılan **8750** iyidir. Bu port başka bir program tarafından kullanılıyorsa kurulum sizi uyarır ve durur; başka bir sayı yazın (1024–65535 arası, örn. 8751).
5. **Ek görevler** sayfasındaki seçenekleri okuyun:
   - ☑ **Arka plan hizmeti olarak kur** — Bilgisayar açılınca program kendiliğinden çalışır. *Sunucu için işaretli bırakın.*
   - ☑ **Güvenlik duvarına izin ver** — Diğer bilgisayarların girebilmesi için gerekir. İşaretli bırakın.
   - ☐ **Masaüstü kısayolu** — İsteğe bağlı.
6. **Kur**'a basın. Bitince **Son**.
7. Tarayıcıyı açın ve adres çubuğuna `http://127.0.0.1:8750` yazın (sunucunun kendisinde). Başka bir bilgisayardan: `http://SUNUCUNUN_IP_ADRESI:8750`.
8. Karşınıza ilk kurulum ekranı gelir → [Bölüm 6](#6-ilk-açılış-yönetici-hesabı-ve-temel-ayarlar).

**Verileriniz nerede?** `C:\ProgramData\NexEnvanter` klasöründe (veritabanı, otomatik yedekler, günlükler, sertifikalar). Program silinse bile bu klasör silinmez.

**Sessiz kurulum** (birçok bilgisayara betikle kuracaksanız): `NexEnvanter-Setup-<sürüm>.exe /VERYSILENT /PORT=8750`

### 4.2. Kurulumsuz kullanım (`NexEnvanter.exe`)

1. `NexEnvanter.exe` dosyasını kalıcı bir klasöre koyun (örn. `C:\NexEnvanter\`). Masaüstü veya İndirilenler klasörüne koymayın.
2. Çift tıklayın. Tarayıcı kendiliğinden açılır.
3. Saatin yanındaki **tepsi simgesine** sağ tıklayın → **"Arka plan hizmeti olarak kur"** (yönetici izni ister). Böylece bilgisayar açılınca program kendiliğinden çalışır.
4. Veriler `NexEnvanter.exe`'nin yanındaki `data` klasöründe tutulur.

### 4.3. Başka bilgisayarlar bağlanamıyorsa

- Sunucuda güvenlik duvarına izin verin: yönetici komut isteminde `NexEnvanter.exe --firewall`
- Adres doğru mu? `http://SUNUCU_IP:8750` — `https` değil, `http` ile başlar (HTTPS, ilgili ayardan açılabilir).
- Sunucu açık mı, hizmet çalışıyor mu? (Hizmetler → "NexEnvanter")

---

## 5. Linux'ta kurulum — adım adım

Ubuntu 22.04 ve benzeri systemd'li dağıtımlar için. Terminalde:

```bash
# 1) Dosyayı indirip açın (dosya adındaki sürüm numarasını kendinize göre değiştirin)
tar xzf NexEnvanter-0.7.1-linux-x64.tar.gz
cd NexEnvanter-0.7.1-linux-x64

# 2) Kurun (port 8750; başka port için --port 8751)
sudo ./install.sh --port 8750
```

Betik şunları yapar: `nexenvanter` adlı yetkisiz bir kullanıcı oluşturur, programı `/opt/nexenvanter` içine koyar, verileri `/var/lib/nexenvanter` içinde tutar, systemd hizmeti olarak kurup başlatır, güvenlik duvarında (ufw veya firewalld varsa) portu açar ve sonunda **adresi yazdırır**. Port doluysa hata verip kurulumu yapmaz.

- Durum: `systemctl status nexenvanter`
- Günlük: `journalctl -u nexenvanter -f`
- **Güncelleme:** yeni tar.gz'yi açıp aynı komutu tekrar çalıştırın; veriler korunur.
- **Kaldırma:** `sudo ./install.sh --uninstall` (verileri korur) — verilerle birlikte silmek için `--purge` ekleyin.
- Güvenlik duvarına dokunmasın isterseniz kurarken `--no-firewall` ekleyin.

---

## 6. İlk açılış: yönetici hesabı ve temel ayarlar

1. **Yönetici hesabını oluşturun.** İlk açılışta kullanıcı adı ve parola istenir. Bu hesap her şeyi yapabilir ("Sistem Yöneticisi"). Parolayı not edin ve kimseyle paylaşmayın; unutulursa sıfırlamak zordur.
2. **Giriş yapın.** Soldaki (veya üstteki) menü açılır.
3. **Ayarlar → Genel → QR temel adresi:** Buraya sunucunun sabit adresini yazın, örn. `http://192.168.1.25:8750` ya da kurumda yerel bir isim varsa `http://envanter.kurum.local:8750`. **Etiket basmadan önce mutlaka ayarlayın**; QR'lar bu adresi taşır. Sonradan değişirse basılmış etiketler çalışmaz.
4. **Kullanıcıları ekleyin** (Menü → Yönetim → Kullanıcılar). Herkese yönetici yetkisi vermeyin. Roller:

| Rol | Ne yapabilir (özet) |
|---|---|
| Sistem Yöneticisi | Her şey: ayarlar, kullanıcılar, ajan, silme/arşiv |
| BİM Yöneticisi | Operasyonun tamamı ve raporlar |
| Envanter Operatörü | Cihaz ekleme/düzenleme, etiket, zimmet, sayım |
| Denetçi | Okuma ve denetim kayıtları |
| Birim Envanter Temsilcisi | Yalnızca kendi birimindeki cihazlar |
| Görüntüleyici | Sadece görme |

5. **Görünüm:** Ayarlar'dan tema (açık/koyu) ve çok sayıda görünüm paketi (Klasik, Kontrol Odası, Radar, Terminal…) seçilebilir. Bu tamamen zevk meselesidir; veriyi etkilemez.
6. İsterseniz **Active Directory (LDAP)** ile giriş ayarlanabilir (Ayarlar → Entegrasyon). Kurumdaki mevcut Windows parolasıyla girilir.

---

## 7. Cihazları programa almak (Excel ile toplu aktarım)

Elinizde bir Excel cihaz listesi varsa tek tek yazmanıza gerek yok.

1. Menü → **Yönetim → Excel İşlemleri**.
2. Excel dosyanızı (`.xlsx`) yükleyin. İlk satır **sütun başlıkları** olmalıdır (örn. `BARKOT NUMARASI`, `CİHAZ ADI`, `MARKA`, `MODEL`, `SERİ NO`, `BİRİM`…).
3. Program sütunları tanır ve eşleştirmeyi gösterir. Yanlış eşleşen sütunu kendiniz değiştirebilirsiniz. **Tanımadığı yeni sütunlar için otomatik yeni alan oluşturur** (kod değişikliği gerekmez).
4. **Deneme (dry-run):** Veritabanına hiçbir şey yazmadan "şu kadar yeni kayıt, şu kadar güncelleme, şu satırlarda hata var" raporu verir. **Önce bunu çalıştırın**, hataları düzeltin.
5. Rapordan memnunsanız **İçe aktar**. Aynı barkod numarası ikinci kez gelirse çoğaltmaz, mevcut kaydı günceller.
6. Tek tek eklemek için: **Cihazlar → Yeni cihaz**.

İpuçları: Barkod/envanter numarası her cihazda **benzersiz** olmalıdır. Kayıtlar silinmez, **arşive** alınır; geçmiş her zaman korunur.

---

## 8. QR etiket basmak ve telefonla okutmak

**Etiket basmak**

1. Menü → **Yönetim → Etiket & Yazıcı**. Etiket ölçüsünü ve yazıcıyı seçin (Windows'ta bilgisayara tanıtılmış yazıcılar listelenir).
2. Cihazlar sayfasında etiket basılacak cihazları işaretleyin → **Etiket yazdır** (ya da kuyruğa ekleyin).
3. Önce **önizlemeye** bakın, sonra yazdırın. İlk seferde tek etiketle deneyin.

**QR'ın içinde ne var?** Cihazın bilgisi değil, yalnızca *tahmin edilemeyen kalıcı bir kimlik* (adres: `…/e/<kimlik>`). Cihazın bilgisi sonradan değişse bile etiketi yeniden basmanız gerekmez.

**Telefonla okutmak**

1. Telefon kamerasını QR'a tutun, çıkan bağlantıya dokunun. (Telefonun kurum ağına bağlı olması gerekir.)
2. Herkese açık kısa bir **cihaz kartı** açılır. Oturum açmadan görünecek alanlar Ayarlar'dan belirlenir.
3. **"Detayları Gör"** deyince giriş istenir; yetkiniz varsa tüm bilgi görünür.
4. Aynı sayfadan **Arıza bildir** denebilir. Barkod okuyucunuz varsa üst arama kutusuna barkodu okutup Enter'a basmanız cihazı doğrudan açar.

---

## 9. Menüdeki bölümler ne işe yarar?

Menüde görünen bölümler yetkinize göre değişir.

**Genel**
- **Ana Sayfa:** Özet sayılar ve hızlı erişim.
- **Cihazlar:** Tüm envanter. Arama, süzme, düzenleme, etiket, arşivleme. Cihaza tıklayınca kartı (geçmiş, zimmet, bakım, arıza, ajan bilgisi) açılır.
- **Durum Panosu:** Cihazların ve ağın genel durumu, büyük ekranda izlemeye uygun.
- **Alarmlar:** Garanti bitişi, bakım gecikmesi, düşük stok, ajan uyarıları gibi dikkat gerektiren durumlar.

**Operasyon**
- **Arıza Kayıtları:** Arıza açma, birime/kişiye atama, durum takibi.
- **Sayım:** Sayım oturumu başlatın; sahada cihazlar (QR ile) işaretlenir; bulunmayanlar raporlanır.
- **Zimmet:** Cihazı kişiye/birime verme ve devir; yazdırılabilir tutanak.
- **Bakım & Garanti:** Planlı bakım, garanti bitiş takibi; geciken işler öne çıkar.
- **Sarf Stok:** Toner, kablo, mouse gibi tüketim malzemesi giriş-çıkış ve minimum stok uyarısı.
- **Yedek Havuzu:** Yedekte bekleyen cihazların takibi.
- **Hizmet Noktaları:** Cihazların bulunduğu yerlerin (oda/poliklinik/servis) tanımı.
- **Bilgi Bankası:** Sık karşılaşılan sorunların çözüm notları.

**Analiz**
- **Onay Kuyruğu:** Ağ taraması ya da ajanın bulduğu, henüz envantere alınmamış cihazlar; onaylayınca kayda dönüşür.
- **Ağ & Ajan:** Ağ keşfi (SNMP/ARP) ve NexAgent yönetimi ([Bölüm 10](#10-nexagent-bilgisayarlardan-otomatik-bilgi-toplama)).
- **Arıza Analizi:** Hangi cihaz türü/marka/birimde ne kadar arıza çıkıyor.
- **Raporlar:** Hazır raporlar ve Excel çıktısı, denetim paketi.
- **Kurumlar:** Birden fazla NexEnvanter kurulumunu (örn. farklı kurumlar) tek panelde özetleme.

**Yönetim**
- **Excel İşlemleri:** İçe/dışa aktarma ([Bölüm 7](#7-cihazları-programa-almak-excel-ile-toplu-aktarım)).
- **Etiket & Yazıcı:** Etiket tasarımı ve yazdırma ([Bölüm 8](#8-qr-etiket-basmak-ve-telefonla-okutmak)).
- **Türler & Kategoriler:** Cihaz türlerini (bilgisayar, yazıcı…) düzenleme.
- **Alanlar:** Cihaz kartındaki alanları ekleme/düzenleme.
- **Kullanıcılar:** Hesap ve rol yönetimi.
- **Denetim Kaydı:** Kim, ne zaman, neyi değiştirdi — silinemez kayıt.
- **Ayarlar:** QR adresi, güvenlik, yedekleme, güncelleme, tema, LDAP vb.

---

## 10. NexAgent: bilgisayarlardan otomatik bilgi toplama

### 10.1. Ne işe yarar?

Her bilgisayarın işlemcisini, belleğini, diskini, seri numarasını, kurulu programlarını elle yazmak yerine, bilgisayara küçük bir program (**NexAgent**) kurarsınız. NexEnvanter açılınca ajanlara bağlanır, bilgiyi alır ve ilgili cihaz kartına yazar. Ajan:

- **Sakin çalışır:** Düşük öncelikte, günde birkaç kez kısa süre. Bilgisayar yoğunsa erteler. Kullanıcı yavaşlık hissetmez.
- **Bilgisayar açıldığında kendiliğinden çalışır** (Windows hizmeti / Linux systemd).
- **Güvenlidir:** Kendiliğinden bir yere bağlanmaz; yalnızca sizin NexEnvanter sunucunuz imzalı istek gönderirse yanıt verir. Uzaktan komut çalıştırma yoktur.
- **Sadece yönetici kurabilir/kaldırabilir;** isterseniz kaldırma parolayla korunur.
- Hangi bilgilerin toplanacağı NexEnvanter'den seçilir (sistem, işlemci, bellek, disk, ekran kartı, ekran, ağ, yazılım, yazıcı, güvenlik, güncellemeler; ayrıca varsayılan kapalı: USB cihazlar, yerel yöneticiler).

Windows (10/11 ve Server, 64-bit) ve Linux (x64, arm64) desteklenir. Windows 7/8 ve 32-bit için ajan yoktur.

### 10.2. Kurulum — baştan sona

**A) Sunucuda hazırlık (bir kez)**

1. Menü → **Ağ & Ajan** → **NexAgent** sekmesi.
2. **İzinli kaynak adresler:** Ajanlar yalnızca bu adreslerden gelen isteğe cevap verir. Boş bırakırsanız sunucunun kendi IP adresleri otomatik kullanılır (çoğu durumda yeterlidir). Sunucuya sabit IP vermeyi unutmayın.
3. **Port:** Varsayılan **47820**. Tüm istemcilerde **aynı port** kullanılır. Kurumunuzda bu port başka bir iş için kullanılıyorsa değiştirin. Ajan, portu kullanımda bulursa **kurulumu yapmaz ve nedenini yazar**; başka port seçmez.
4. **Kaldırma parolası** (isteğe bağlı ama önerilir): En az 6 karakter. İstemcide ajan kaldırılırken sorulur.
5. Hangi bilgilerin toplanacağını işaretleyin, **Kaydet**.
6. **"GitHub sürümünden indir"** düğmesine basın. Program ajan dosyalarını (Windows, Linux x64, Linux arm64) kendisi indirir; sizin bir şey aramanız gerekmez. *(İnternet erişimi yoksa dosyaları `NexAgent-…` adıyla başka bir bilgisayarda indirip veri klasöründeki `agent_bins` klasörüne koyun.)*

**B) Kurulum paketini hazırlama**

7. **Kurulum paketi** kutusunda **Windows x64** (ya da Linux) düğmesine basın. Bir **zip** iner. İçinde:
   - `NexAgent.exe` (veya `nexagent`) — ajan programı
   - `enroll.json` — **bu kurulumunuza özel** anahtar, port, izinli adres ve ayarlar
   - `KURULUM.txt` — kısa yönerge

   > `enroll.json` sizin sunucunuza özeldir. Başka kurumlara/sunuculara vermeyin; başka bir NexEnvanter kurulumunun paketi sizin ajanlarınızla çalışmaz.

**C) Her istemciye kurma**

8. Zip'i istemci bilgisayara kopyalayın (USB, ağ paylaşımı, uzaktan masaüstü…) ve bir klasöre çıkarın. `NexAgent.exe` ile `enroll.json` **aynı klasörde** olmalıdır.
9. **Windows:** `NexAgent.exe`'ye çift tıklayın → açılan menüde **K** (Kur) tuşuna basın (yönetici izni ister, onaylayın). Ya da yönetici komut isteminde: `NexAgent.exe install` · Sessiz: `NexAgent.exe install --password KALDIRMA_PAROLASI`
   **Linux:** `chmod +x nexagent` ardından `sudo ./nexagent install`
10. Ekrandaki sonucu okuyun: "kuruldu, hizmet çalışıyor" yazmalıdır. Hata olursa nedeni yazar (en sık neden: port kullanımda).
11. Kontrol için: `NexAgent.exe status`.

Kurulumdan sonra klasörü silebilirsiniz; ajan `C:\Program Files\NexAgent` içine yerleşir. **Yüzlerce bilgisayar için:** aynı zip'i her bilgisayara aynı yöntemle kurun (örn. Active Directory GPO başlangıç betiği veya Kaspersky/KSC uzaktan kurulum görevi ile `NexAgent.exe install --password …`).

**D) Ajanları bulma ve veri çekme**

12. NexEnvanter'de **Ağ & Ajan → NexAgent → Ajanları bul** deyin. Program ağdaki ajanları bulur, kaydeder ve ilk bilgiyi çeker (yüzlerce bilgisayar için birkaç dakika sürebilir; ilerleme gösterilir).
13. Tablodaki satırlardan her bilgisayarın durumunu görürsünüz (çevrimiçi/çevrimdışı, son bilgi zamanı, sürüm). Bilgisayarlar cihaz kayıtlarıyla **seri no → MAC → bilgisayar adı** sırasıyla eşleştirilir. Eşleşmeyenler "eşleşmeyen raporlar" listesinde görünür; **Eşle / ekle** ile elle bağlayabilir ya da yeni cihaz olarak ekleyebilirsiniz. Elle yazdığınız alanlar ajan tarafından ezilmez.
14. Bundan sonra NexEnvanter her açıldığında ve **6 saatte bir** ajanları kendiliğinden yeniler. İsterseniz üstteki **Cihazdan çek** düğmesiyle (tek bilgisayar için satırdaki **Çek**) elle yenileyebilirsiniz.

### 10.3. Ayarı sonradan değiştirmek, ajan kaldırmak

- Modülleri/aralığı Envanter'den değiştirip kaydedin; ajanlara **kendiliğinden iletilir**, istemcide bir şey yapmanız gerekmez. Tek bir bilgisayar için özel ayar da verilebilir.
- **Ajanı kaldırmak (sunucudan):** Tabloda bilgisayarın satırındaki **Kaldır** düğmesine basın. Ajan kendini siler.
- **Ajanı kaldırmak (istemciden):** Ayarlar → Uygulamalar → NexAgent → Kaldır (parola sorar) ya da `NexAgent.exe uninstall`.
- **"Parmak izi" uyarısı:** Ajanın güvenlik sertifikası değiştiyse (örn. ajan yeniden kurulduysa) Envanter güvenlik için veri almayı durdurur ve onayınızı bekler. Bilgisayarı yeniden kurmadıysanız şüpheli olabilir; yeniden kurduysanız satırdaki **Sertifikayı onayla** düğmesine basın.

### 10.4. Kaspersky / güvenlik yazılımları

Ajan sürücü yüklemez ve uzaktan komut çalıştırmaz; yine de kurumdaki Kaspersky ilk karşılaşmada uyarabilir. Kaspersky Security Center'da:

- `C:\Program Files\NexAgent\NexAgent.exe` dosyasını **güvenilen uygulama / istisna** yapın.
- Gelen bağlantı için ajan portunun (47820) açık olması gerekir. Kurulum, Windows güvenlik duvarı kuralını yalnızca izinli adresler için kendisi ekler.

Daha teknik ayrıntı: [docs/NEXAGENT.md](docs/NEXAGENT.md).

---

## 11. Güncelleme, yedekleme, kaldırma

**Güncelleme (uygulama içinden):** **Ayarlar → Sistem → Güncelleme** kutusundaki **Güncellemeleri denetle** düğmesi. Yeni sürüm varsa **İndir ve kur** deyin; program kendini yeniler, **veritabanına dokunmaz**. Elle güncellemek isterseniz yeni Setup.exe'yi eskisinin üzerine kurmanız yeterlidir (Linux'ta `install.sh`'ı tekrar çalıştırın).

> Güncellemeden önce yedek almak iyi bir alışkanlıktır.

**Yedekleme:** Program her gün veri klasöründe otomatik yedek alır. Tepsi simgesindeki **Şimdi yedekle** ile anında yedek alınır. Ancak yedekler aynı diskte durur; **veri klasörünü düzenli olarak başka bir yere (başka bilgisayar, harici disk, ağ paylaşımı) kopyalayın.** Veri klasörü:

| Sistem | Konum |
|---|---|
| Windows (kurucu ile) | `C:\ProgramData\NexEnvanter` |
| Windows (kurulumsuz exe) | `NexEnvanter.exe`'nin yanındaki `data` |
| Linux | `/var/lib/nexenvanter` |

> **Çok önemli:** Veri klasöründeki `nexagent\signing.pem` dosyası, ajanları yöneten **imza anahtarınızdır**. Bu dosya kaybolursa kurulu ajanlar artık sizin sunucunuzdan yönetilemez (ajanları yeniden kurmak gerekir). Yedeğinizde bulunduğundan emin olun ve başkalarıyla paylaşmayın.

**Başka bilgisayara taşıma:** Yeni sunucuya aynı sürümü kurun, hizmeti durdurun, eski veri klasörünün içeriğini yenisine kopyalayın, hizmeti başlatın. Sunucunun IP'si değiştiyse **QR temel adresi** ve ajanların **izinli kaynak adresi** de güncellenmelidir.

**Kaldırma:** Windows'ta Ayarlar → Uygulamalar → NexEnvanter → Kaldır (veriyi silmek isteyip istemediğinizi sorar; varsayılan *silme*). Linux: `sudo ./install.sh --uninstall [--purge]`.

---

## 12. Sorun giderme

| Belirti | Olası neden / çözüm |
|---|---|
| Tarayıcıda sayfa açılmıyor | Program çalışıyor mu? (Windows: Hizmetler → NexEnvanter; Linux: `systemctl status nexenvanter`). Adres `http://IP:8750` biçiminde mi? |
| Başka bilgisayardan açılmıyor, sunucuda açılıyor | Güvenlik duvarı. Windows: yönetici komut isteminde `NexEnvanter.exe --firewall`. Linux: `sudo ufw allow 8750/tcp` |
| Kurulum "port kullanımda" diyor | Başka bir program o portu kullanıyor. Farklı bir port yazın (örn. 8751) |
| Telefondan QR açılmıyor | Telefon kurum Wi‑Fi ağında mı? **QR temel adresi** doğru mu (Ayarlar)? |
| Basılmış etiketler çalışmıyor | QR temel adresi sonradan değişmiş olabilir; eski adrese geri alın veya sabit IP/DNS adı kullanın |
| "GitHub'a ulaşılamadı" / sertifika hatası | Sunucunun internet erişimini ve kurumsal vekil/SSL denetimini kontrol edin. Program, Windows deposu yetmezse kendi sertifika paketiyle de dener. Sorun sürerse dosyayı başka bir bilgisayarda indirip elle kurun |
| "İzinli kaynak adres tanımlı değil" | v0.7.1 ile otomatik doldurulur; eski sürümdeyseniz güncelleyin ya da Ağ & Ajan → İzinli kaynak adresler alanına sunucu IP'sini yazın |
| Ajan "çevrimdışı" görünüyor | Bilgisayar kapalı olabilir; ajan portu (47820) güvenlik duvarında/Kaspersky'de engelleniyor olabilir; izinli kaynak listesi sunucu IP'sini içermiyor olabilir (sunucu IP'si değişmiş olabilir) |
| Ajan "parmak izi" durumunda | Bölüm 10.3'e bakın |
| Ajan kurulumu "yönetici gerekli" diyor | Yönetici olarak çalıştırın (Windows: sağ tık → Yönetici olarak çalıştır; Linux: `sudo`) |
| Parolamı unuttum | Başka bir yönetici, Kullanıcılar sayfasından **Parola sıfırla** ile yeni parola verebilir. Tek yönetici sizseniz geliştiriciye başvurun |
| Program açılırken hata veriyor | Günlüğe bakın: `data\logs\nexenvanter.log` (Linux: `journalctl -u nexenvanter -n 100`) ve bir kopyasını geliştiriciye iletin |

---

## 13. Geliştiriciler için

### Komut satırı

```
NexEnvanter.exe [--port 8750] [--host 0.0.0.0] [--data KLASÖR] [--no-browser] [--headless] [--tray]
                [--firewall] [--install-service] [--uninstall-service] [--version]
```

### Geliştirme

```bat
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements-dev.txt
python run.py            :: http://127.0.0.1:8750
python -m pytest -q
build.bat                :: dist\NexEnvanter.exe
```

**Sürüm yayınlama:** `git tag v0.1.0 && git push --tags` → GitHub Actions testleri çalıştırır, exe'yi derler, dener ve sürüme ekler. Uygulama içindeki "Güncellemeleri denetle" bu sürümü bulup kurar.

### Yapı

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
  network.py snmp.py agent.py   ağ keşfi, SNMP istemcisi, ajan verisini envanterle eşleme
  nexagent.py api_nexagent.py   NexAgent istemcisi (imzalı çağrı, TLS sabitleme), yönetim API
  agent/                        NexAgent (C# / .NET 10) — bkz. docs/NEXAGENT.md
  reports.py federation.py      raporlar, denetim paketi, kurumlar paneli
  api_pro.py    pro API + QR sayfası + yazdırılabilir tutanaklar
  tls.py        HTTPS sertifikası
  license.py    Ed25519 lisans (şu an zorlanmıyor)
tools/license_tool.py  lisans anahtarı/dosyası üretimi (yalnızca geliştirici)
web/            arayüz (derleme adımı yok)
docs/TASARIM.md tasarım, mimari, karar günlüğü, yol haritası
```

Ayrıntılar: [docs/TASARIM.md](docs/TASARIM.md)
