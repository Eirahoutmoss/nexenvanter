# NexAgent

NexEnvanter için sakin ve güvenli envanter ajanı (C# / .NET 10, Windows + Linux). **Çekme (pull) modeli:** ajan kendiliğinden
bir yere bağlanmaz; Envanter açılınca ajanlara bağlanıp veriyi alır.

## Güvenlik
- İstekler Envanter'in **ECDSA P-256** anahtarıyla imzalanır (`NEX1` imza metni: yöntem, hedef, ajan kimliği, zaman, nonce, gövde özeti).
  Ajanda yalnızca **açık anahtar** bulunur; bir ajan ele geçse bile başka ajanlara erişilemez. ±5 dk zaman penceresi + nonce ile tekrar saldırısı engellenir.
- Ajan kendi kendine imzalı **TLS** sertifikası üretir; Envanter parmak izini ilk temasta saklar, değişirse veri almaz ve onay ister.
- Kaynak IP denetimi (izinli adresler) + Windows güvenlik duvarı kuralı yalnızca o adreslere açılır. Port taramasına yanıt yalnızca `/v1/hello` (kimlik + sürüm).
- Uzaktan komut çalıştırma **yoktur**. Yapılabilenler: veri okuma, ayar güncelleme, kendini kaldırma.
- Kurulum/kaldırma yalnızca **yönetici** (Windows) / **root** (Linux). Yerel kaldırma **parola** sorar (PBKDF2-SHA256 özeti ajanda). Not: yerel yönetici
  servisi/klasörü yine de silebilir; parola caydırıcıdır. Kesin koruma için Kaspersky/GPO politikası gerekir.
- Veri klasörü (`%ProgramData%\NexAgent`, `/etc/nexagent`) yalnızca SYSTEM/Yöneticiler (root) erişimine kapatılır.

## Sakin çalışma
Düşük öncelik + arka plan G/Ç modu, açılışta 90–240 sn rastgele gecikme, 85% üzeri CPU'da erteleme, modüller arası bekleme, her toplamadan sonra
bellek budama, 220 MB üzeri bellekte yeniden başlatma, önbellekten anlık yanıt (varsayılan 6 saatte bir toplama), Linux'ta `CPUQuota=20%`, `IOSchedulingClass=idle`.
Kapalı modüller hiç çalıştırılmaz. Sensör/sürücü (LibreHardwareMonitor) **kullanılmaz** → Kaspersky ile çakışma riski düşük.

## Kurulum
1. Derle: `agent\build.ps1` (Windows) veya `agent/build.sh linux-x64`. Çıktı `build/agent/<rid>/`. Dosyayı `NexAgent-1.0.0-win-x64.exe` biçiminde adlandırıp
   Envanter veri klasöründeki `agent_bins` klasörüne koyun (ya da GitHub sürümüne `NexAgent-*` olarak yükleyip arayüzden indirin).
2. Envanter > Ağ & Ajan > NexAgent: **izinli kaynak** (Envanter sunucusunun IP'si), port, parola, modülleri ayarlayın; **kurulum paketini** indirin.
3. İstemcide yönetici olarak: `NexAgent.exe install` (Linux: `sudo ./nexagent install`). Port doluysa kurulum yapılmaz ve nedeni yazılır.
4. Envanter > **Ajanları bul** → ajanlar kaydolur, ilk veri çekilir. Sonra Envanter her açıldığında (ve 6 saatte bir) otomatik çeker.

## Komutlar
`install` · `uninstall [--password P] [--keep-data]` · `status` · `run` · `version`.
Servis günlüğü: `%ProgramData%\NexAgent\logs\agent.log`.

## Kaspersky (KSC)
Güvenilen uygulama: `C:\Program Files\NexAgent\NexAgent.exe`. Kendi imzalı sertifikayla imzalarsanız sertifika bazlı istisna her sürümde geçerli kalır.
Gelen bağlantı için TCP port (varsayılan 47820), yalnızca Envanter IP'sinden.
