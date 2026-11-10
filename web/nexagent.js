"use strict";
/* NexAgent yönetimi: Ağ & Ajan > NexAgent sekmesi ve cihaz kartındaki donanım bilgisi */
const NX_COL = {"çevrimiçi": "#13a05a", "yeni": "#1463ff", "çevrimdışı": "#e6930a", "parmak izi": "#d93636", "kaldırıldı": "#888"};
const nxPill = st => `<span style="background:${NX_COL[st] || "#888"}22;color:${NX_COL[st] || "#888"};padding:2px 9px;border-radius:10px;font-size:12px;white-space:nowrap">${esc(st)}</span>`;
const nxGb = b => b ? (b >= 1e12 ? (b / 1e12).toFixed(2) + " TB" : (b / 1073741824).toFixed(b / 1073741824 < 10 ? 1 : 0) + " GB") : "";
const nxKv = (rows) => `<table class="small" style="width:100%"><tbody>${rows.filter(r => r[1] !== undefined && r[1] !== null && r[1] !== "").map(([k, v]) => `<tr><td class="muted" style="width:34%">${esc(k)}</td><td>${esc(v)}</td></tr>`).join("")}</tbody></table>`;
const nxBool = v => v === true ? "Açık" : v === false ? "Kapalı" : "";

function nxSnap(sn) {
  if (!sn) return `<p class="muted small">Henüz veri alınmadı.</p>`;
  const m = sn.modules || {}, s = m.system || {}, os = s.os || {}, cpu = m.cpu || {}, mem = m.memory || {}, st = m.storage || {}, sec = m.security || {}, up = m.updates || {}, sw = m.software;
  const out = [];
  if (m.system) out.push(`<h3>Sistem</h3>${nxKv([["Model", [s.manufacturer, s.model].filter(Boolean).join(" ")], ["Seri no", s.serial], ["Tür", s.formFactor], ["BIOS", [s.biosVersion, (s.biosDate || "").slice(0, 10)].filter(Boolean).join(" · ")],
    ["İşletim sistemi", [os.caption, os.version].filter(Boolean).join(" ")], ["Mimari", os.arch], ["Kurulum", (os.installDate || "").slice(0, 10)], ["Son açılış", fmtDate(os.lastBoot)], ["Oturum", s.lastUser], ["Etki alanı", s.domain]])}`);
  if (m.cpu) out.push(`<h3>İşlemci</h3>${nxKv([["Ad", cpu.name], ["Çekirdek / iş parçacığı", cpu.cores ? `${cpu.cores} / ${cpu.threads}` : ""], ["Azami hız", cpu.maxMhz ? cpu.maxMhz + " MHz" : ""]])}`);
  if (m.memory) out.push(`<h3>Bellek — ${nxGb(mem.totalBytes)}</h3>${(mem.modules || []).length ? `<table class="small"><tr><th>Yuva</th><th>Boyut</th><th>Tür</th><th>Hız</th><th>Üretici</th><th>Parça no</th></tr>${mem.modules.map(x => `<tr><td>${esc(x.slot || "")}</td><td>${esc(x.size || nxGb(x.sizeBytes))}</td><td>${esc(x.type || "")}</td><td>${esc(x.speedMhz || x.speed || "")}</td><td>${esc(x.manufacturer || "")}</td><td class="mono">${esc(x.partNumber || "")}</td></tr>`).join("")}</table>` : ""}`);
  if (m.storage) out.push(`<h3>Diskler</h3><table class="small"><tr><th>Model</th><th>Seri</th><th>Boyut</th><th>Tür</th><th>Sağlık</th></tr>${(st.disks || []).map(d => `<tr><td>${esc(d.model || "")}</td><td class="mono">${esc(d.serial || "")}</td><td>${nxGb(d.sizeBytes)}</td><td>${esc(d.mediaType || d.interface || "")}</td><td>${esc(d.health || "")}</td></tr>`).join("")}</table>
    <table class="small" style="margin-top:6px"><tr><th>Bölüm</th><th>Dosya sistemi</th><th>Boş / toplam</th></tr>${(st.volumes || []).map(v => `<tr><td>${esc(v.letter)} ${esc(v.label || "")}</td><td>${esc(v.fs || "")}</td><td>${nxGb(v.freeBytes)} / ${nxGb(v.sizeBytes)}</td></tr>`).join("")}</table>`);
  if ((m.gpu || []).length) out.push(`<h3>Ekran kartı</h3>${m.gpu.map(g => `<div class="small">${esc(g.name)} ${g.driver ? `<span class="muted">· sürücü ${esc(g.driver)}</span>` : ""}</div>`).join("")}`);
  if ((m.display || []).length) out.push(`<h3>Monitörler</h3><table class="small"><tr><th>Üretici</th><th>Model</th><th>Seri no</th><th>Üretim</th></tr>${m.display.map(d => `<tr><td>${esc(d.manufacturer || "")}</td><td>${esc(d.model || "")}</td><td class="mono">${esc(d.serial || "")}</td><td>${esc(d.year || "")}${d.week ? "/" + d.week : ""}</td></tr>`).join("")}</table>`);
  if ((m.network || []).length) out.push(`<h3>Ağ</h3><table class="small"><tr><th>Kart</th><th>MAC</th><th>IP</th><th>Ağ geçidi</th><th>DNS</th><th>DHCP</th></tr>${m.network.map(n => `<tr><td>${esc(n.name)}${n.virtual ? ' <span class="muted">(sanal)</span>' : ""}</td><td class="mono">${esc(n.mac || "")}</td><td>${esc((n.ips || []).join(", "))}</td><td>${esc((n.gateways || []).join(", "))}</td><td>${esc((n.dns || []).join(", "))}</td><td>${n.dhcp === undefined ? "" : n.dhcp ? "evet" : "hayır"}</td></tr>`).join("")}</table>`);
  if ((m.printers || []).length) out.push(`<h3>Yazıcılar</h3>${m.printers.map(p => `<div class="small">${esc(p.name)} <span class="muted">· ${esc(p.port || "")} ${p.default ? "· varsayılan" : ""}</span></div>`).join("")}`);
  if (m.security) out.push(`<h3>Güvenlik</h3>${nxKv([["Antivirüs", (sec.antivirus || []).map(a => `${a.name} (${a.enabled ? "etkin" : "kapalı"}${a.signaturesUpToDate ? "" : ", imzalar eski"})`).join("; ")],
    ["Güvenlik duvarı", sec.firewall ? Object.entries(sec.firewall).map(([k, v]) => `${k}: ${typeof v === "boolean" ? (v ? "açık" : "kapalı") : v}`).join(" · ") : ""], ["BitLocker", (sec.bitlocker || []).map(b => `${b.drive} ${b.protected ? "korumalı" : "korumasız"}`).join(", ")],
    ["TPM", sec.tpm ? `${sec.tpm.enabled ? "etkin" : "kapalı"} ${sec.tpm.spec || ""}` : ""], ["Güvenli önyükleme", nxBool(sec.secureBoot)]])}`);
  if (m.updates) out.push(`<h3>Güncellemeler</h3>${nxKv([["Son yükleme", up.lastInstalled], ["Toplam", up.count], ["Yeniden başlatma bekliyor", up.rebootRequired === true ? "evet" : ""]])}`);
  if (sw) out.push(`<details><summary><b>Kurulu programlar (${sw.count}${sw.truncated ? ", liste kısaltıldı" : ""})</b></summary><div class="small" style="columns:2;margin-top:6px">${(sw.items || []).map(x => `<div>${esc(x.name)} <span class="muted">${esc(x.version || "")}</span></div>`).join("")}</div></details>`);
  if ((m.usb || []).length) out.push(`<details><summary><b>USB aygıtları (${m.usb.length})</b></summary>${m.usb.map(u => `<div class="small">${esc(u.name)}</div>`).join("")}</details>`);
  if (m.admins) out.push(`<h3>Yerel yöneticiler</h3><div class="small">${esc((m.admins || []).join(", "))}</div>`);
  const er = Object.entries(sn.errors || {});
  if (er.length) out.push(`<p class="small err">Alınamayan modüller: ${er.map(([k, v]) => `${esc(k)} (${esc(v)})`).join(", ")}</p>`);
  return `<p class="small muted">Ajan verisi: ${fmtDate(sn.collectedAt || sn.at)} · ajan ${esc(sn.agentVersion || "")}</p>${out.join("")}`;
}

/* ---- cihaz kartı ---- */
async function nxAssetCard(a) {
  let r; try { r = await api("/api/nexagent/asset/" + a.id); } catch (_) { return; }
  const host = $("#dx"); if (!host || !r.node) return;
  const n = r.node, el = document.createElement("div"); el.className = "card";
  el.innerHTML = `<div class="row"><h2 style="margin:0">Donanım (NexAgent)</h2><span class="sp"></span>${nxPill(n.state)} ${can("network") ? `<button class="btn s" id="nxp">Cihazdan çek</button>` : ""}</div>
    ${n.last_error && n.state !== "çevrimiçi" ? `<p class="small err">${esc(n.last_error)}</p>` : ""}<details ${r.snapshot ? "open" : ""}><summary class="small muted">Ayrıntılar</summary>${nxSnap(r.snapshot)}</details>`;
  host.append(el);
  if ($("#nxp", el)) $("#nxp", el).onclick = async () => { try { toast("Cihaz sorgulanıyor…"); await api(`/api/nexagent/nodes/${n.agent_id}/pull`, {method: "POST"}); toast("Güncellendi"); route(); } catch (e) { fail(e); } };
}

/* ---- Ağ & Ajan > NexAgent sekmesi ---- */
async function nxRender(el) {
  const [o, un] = await Promise.all([api("/api/nexagent"), api("/api/agent/reports?unmatched=1").catch(() => [])]);
  const c = o.cfg, st = o.state, canSet = can("settings"), cnt = o.counts || {};
  const mod = k => (c.modules || {})[k];
  el.innerHTML = `<div class="grid g4">
      <div class="card stat"><div><div class="n">${o.nodes.filter(n => n.state !== "kaldırıldı").length}</div><div class="l">Kayıtlı ajan</div></div></div>
      <div class="card stat"><div><div class="n">${cnt["çevrimiçi"] || 0}</div><div class="l">Çevrimiçi</div></div></div>
      <div class="card stat"><div><div class="n ${cnt["çevrimdışı"] ? "err" : ""}">${cnt["çevrimdışı"] || 0}</div><div class="l">Yanıt vermeyen</div></div></div>
      <div class="card stat"><div><div class="n ${cnt["parmak izi"] ? "err" : ""}">${cnt["parmak izi"] || 0}</div><div class="l">Sertifika onayı bekleyen</div></div></div></div>
    <div class="row" style="margin:10px 0"><button class="btn p" id="nxall" ${st.running ? "disabled" : ""}>${st.running ? `${esc(st.kind === "discover" ? "Aranıyor" : "Çekiliyor")}… ${esc(st.progress)}` : "⟳ Tüm ajanlardan veri çek"}</button>
      ${canSet ? `<button class="btn" id="nxfind" ${st.running ? "disabled" : ""}>🔍 Ajanları bul</button>` : ""}<span class="sp"></span>
      <span class="small muted">${st.last_result ? `Son iş: ${fmtDate(st.last_run)} · ${esc(JSON.stringify(st.last_result).replace(/[{}"]/g, "").slice(0, 160))}` : ""}</span></div>
    <div class="tw"><table><thead><tr><th>Bilgisayar</th><th>Envanter</th><th>Durum</th><th>Sürüm</th><th>Son görülme</th><th>Son veri</th><th></th></tr></thead><tbody>
    ${o.nodes.map(n => `<tr><td><b>${esc(n.hostname || "?")}</b><div class="small mono muted">${esc(n.address)}:${n.port}</div></td>
      <td>${n.asset_id ? `<a href="#/asset/${n.asset_id}">${esc(n.asset_code || "kayıt")}</a>` : `<span class="muted small">eşleşmedi</span> ${can("network") ? `<button class="btn s" data-lk="${n.agent_id}">Eşle</button>` : ""}`}</td>
      <td>${nxPill(n.state)}${n.last_error ? `<div class="small err">${esc(n.last_error)}</div>` : ""}</td><td class="small">${esc(n.version || "")}</td><td class="small">${fmtDate(n.last_seen)}</td><td class="small">${fmtDate(n.collected_at)}</td>
      <td style="white-space:nowrap"><button class="btn s" data-dt="${n.agent_id}">Ayrıntı</button>
        ${n.state === "parmak izi" && canSet ? `<button class="btn s d" data-fp="${n.agent_id}">Sertifikayı onayla</button>` : ""}
        ${n.state !== "kaldırıldı" ? `<button class="btn s" data-pl="${n.agent_id}">Çek</button>${canSet ? `<button class="btn s" data-ov="${n.agent_id}">Ayarla</button><button class="btn s d" data-un="${n.agent_id}">Kaldır</button>` : ""}` : ""}
        ${canSet && (n.state === "kaldırıldı" || n.state === "çevrimdışı") ? `<button class="btn s" data-fg="${n.agent_id}">Kaydı sil</button>` : ""}</td></tr>`).join("") || `<tr><td colspan=7 class="muted">Henüz ajan yok. Aşağıdan kurulum paketini indirip bilgisayarlara kurun; ardından “Ajanları bul”a basın.</td></tr>`}</tbody></table></div>
    ${canSet ? `<div class="grid g2"><form class="card" id="nxcfg"><h2>Ajan ayarları</h2>
      <div class="grid g2"><label class="f"><span>Ajan portu (tüm filo)</span><input name="port" type="number" min="1024" max="65535" value="${c.port}"></label>
        <label class="f"><span>Ajanın verisini yenileme (dk)</span><input name="interval_minutes" type="number" min="15" value="${c.interval_minutes}"></label></div>
      <label class="f"><span>İzinli kaynak adresler — bu Envanter sunucusunun IP'si (her satıra bir; IP veya CIDR). Boş bırakılırsa sunucunun kendi adresleri otomatik kullanılır</span><textarea name="sources" rows="2">${esc((c.sources || []).join("\n"))}</textarea></label>
      <div class="grid g2"><label class="f"><span>Otomatik çekme (saat, 0 = kapalı)</span><input name="pull_hours" type="number" min="0" value="${c.pull_hours}"></label>
        <label class="f"><span>Yazılım listesi üst sınırı</span><input name="software_max" type="number" min="0" max="5000" value="${c.software_max}"></label></div>
      <label class="row small"><input type="checkbox" name="pull_on_start" ${c.pull_on_start ? "checked" : ""}> Envanter açılınca ajanlardan otomatik veri çek</label>
      <h3>Ne toplansın?</h3><div class="grid g2">${o.modules.map(m => `<label class="row small"><input type="checkbox" name="m_${m.key}" ${mod(m.key) ? "checked" : ""}> ${esc(m.label)}</label>`).join("")}</div>
      <p class="small muted">Kapalı modüller ajan tarafında hiç toplanmaz (kaynak harcamaz). Değişiklik ajanlara bir sonraki çekmede iletilir.</p>
      <h3>Kaldırma parolası</h3><p class="small muted">Durum: <b>${c.uninstall_protected ? "tanımlı" : "yok"}</b>. Parola, ajanlara yalnızca özet (hash) olarak gider. Yerel kaldırma bu parolayı ister; Envanter'den kaldırma parola istemez.</p>
      <label class="f"><span>Yeni parola (boş bırakırsanız değişmez)</span><input name="uninstall_password" type="password" autocomplete="new-password"></label>
      ${c.uninstall_protected ? `<label class="row small"><input type="checkbox" name="clear_pw"> Parolayı kaldır</label>` : ""}<button class="btn">Kaydet</button></form>
      <div class="card"><h2>Kurulum paketi</h2><p class="small">Pakette ajan, imza anahtarı (yalnızca açık anahtar), port ve izinli adresler hazır gelir; bilgisayarda <b>yönetici olarak</b> <span class="mono">NexAgent.exe install</span> yeterlidir.</p>
        <div class="row"><a class="btn p" href="/api/nexagent/package?os=win&arch=x64">Windows x64</a><a class="btn" href="/api/nexagent/package?os=linux&arch=x64">Linux x64</a><a class="btn" href="/api/nexagent/package?os=linux&arch=arm64">Linux arm64</a></div>
        <p class="small muted" style="margin-top:10px">Ajan dosyaları: ${o.bins.length ? o.bins.map(b => `<span class="mono">${esc(b.name)}</span> (${nxGb(b.size)})`).join(", ") : "<b class=err>yok</b>"}<br>Klasör: <span class="mono">${esc(o.bins_dir)}</span> — derlediğiniz <span class="mono">NexAgent-*-win-x64.exe</span> gibi dosyaları buraya koyun ya da GitHub sürümünden indirin.</p>
        <button class="btn s" id="nxbins">GitHub sürümünden indir</button>
        <p class="small muted">İmza anahtarı parmak izi: <span class="mono">${esc(o.public_key_fp)}</span></p></div></div>` : ""}
    ${un.length ? `<div class="card"><h2>Envanterle eşleşmeyen bildirimler (${un.length})</h2><table><tr><th>Bilgisayar</th><th>Seri no</th><th>Model</th><th></th></tr>${un.map(r => `<tr><td><b>${esc(r.hostname)}</b></td><td class="mono small">${esc(r.serial || "")}</td><td class="small">${esc((r.data.manufacturer || "") + " " + (r.data.model || ""))}</td><td><button class="btn s" data-link="${esc(r.hostname)}">Eşle / ekle</button></td></tr>`).join("")}</table></div>` : ""}`;

  const poll = () => setTimeout(function p() { if (!location.hash.startsWith("#/network")) return; api("/api/nexagent/job").then(j => j.running ? setTimeout(p, 2000) : route()); }, 1500);
  const start = async (url, body, msg) => { try { const r = await api(url, {method: "POST", body}); toast(r.started ? msg : "Zaten çalışan bir iş var"); route(); poll(); } catch (e) { fail(e); } };
  if ($("#nxall")) $("#nxall").onclick = () => start("/api/nexagent/pull", {fresh: false}, "Veri çekiliyor");
  if ($("#nxfind")) $("#nxfind").onclick = () => modal("Ajanları bul", `<p class="small">Varsayılan: ağ taramasında görülen ve envanter kayıtlarındaki IP adresleri denenir. Ek olarak aralık verebilirsiniz (her satıra bir; boşsa yukarıdakiler).</p><label class="f"><span>İsteğe bağlı hedefler</span><textarea name="targets" rows="3" placeholder="10.20.0.0/24&#10;10.30.1.10-10.30.1.200"></textarea></label>`, async x => { await start("/api/nexagent/discover", {targets: x.targets || ""}, "Arama başladı"); }, "Başlat");
  $$("[data-pl]", el).forEach(b => b.onclick = async () => { try { toast("Cihaz sorgulanıyor…"); await api(`/api/nexagent/nodes/${b.dataset.pl}/pull`, {method: "POST"}); toast("Güncellendi"); route(); } catch (e) { fail(e); route(); } });
  $$("[data-dt]", el).forEach(b => b.onclick = async () => { const r = await api("/api/nexagent/nodes/" + b.dataset.dt); const n = r.node;
    modal(`${esc(n.hostname || n.address)} — ${esc(n.state)}`, `<div class="small muted">Ajan kimliği: <span class="mono">${esc(n.agent_id)}</span> · parmak izi <span class="mono">${esc((n.fingerprint || "").slice(0, 16))}</span></div>${nxSnap(r.snapshot)}`, null); });
  $$("[data-fp]", el).forEach(b => b.onclick = async () => { if (confirm("Ajanın sertifikası değişti. Bilgisayarı yeniden kurduysanız onaylayın; aksi halde ağda başka bir cihaz ajanı taklit ediyor olabilir. Onaylansın mı?")) { try { await api(`/api/nexagent/nodes/${b.dataset.fp}/accept-fingerprint`, {method: "POST"}); route(); } catch (e) { fail(e); } } });
  $$("[data-fg]", el).forEach(b => b.onclick = async () => { if (confirm("Ajan kaydı silinsin mi? (Envanter kaydına dokunulmaz)")) { await api("/api/nexagent/nodes/" + b.dataset.fg, {method: "DELETE"}); route(); } });
  $$("[data-un]", el).forEach(b => b.onclick = () => { const n = o.nodes.find(x => x.agent_id === b.dataset.un); const name = n.hostname || n.agent_id;
    modal("Ajanı kaldır", `<p>Bu bilgisayardaki NexAgent <b>kaldırılacak</b>. Devam etmek için bilgisayar adını yazın: <b>${esc(name)}</b></p><label class="f"><span>Bilgisayar adı</span><input name="confirm" autocomplete="off"></label>`,
      async x => { await api(`/api/nexagent/nodes/${n.agent_id}/uninstall`, {method: "POST", body: {confirm: x.confirm}}); toast("Kaldırma komutu gönderildi"); route(); }, "Kaldır"); });
  $$("[data-ov]", el).forEach(b => b.onclick = () => { const n = o.nodes.find(x => x.agent_id === b.dataset.ov); const ov = n.override || {}; const mm = Object.assign({}, c.modules, ov.modules || {});
    modal(`Bu bilgisayar için ayar — ${esc(n.hostname || "")}`, `<p class="small muted">Genel ayardan farklı olacak modüller. “Genel ayara dön” cihaz özel ayarını siler.</p><div class="grid g2">${o.modules.map(m => `<label class="row small"><input type="checkbox" name="m_${m.key}" ${mm[m.key] ? "checked" : ""}> ${esc(m.label)}</label>`).join("")}</div>
      <label class="f"><span>Yenileme aralığı (dk, boş = genel)</span><input name="interval_minutes" type="number" min="15" value="${ov.interval_minutes || ""}"></label><label class="row small"><input type="checkbox" name="reset"> Genel ayara dön</label>`,
      async x => { const modules = {}; o.modules.forEach(m => modules[m.key] = x["m_" + m.key] === "on"); const override = x.reset ? null : {modules, interval_minutes: x.interval_minutes ? +x.interval_minutes : null};
        await api(`/api/nexagent/nodes/${n.agent_id}/override`, {method: "POST", body: {override}}); toast("Kaydedildi; bir sonraki çekmede ajana iletilir"); route(); }); });
  $$("[data-lk]", el).forEach(b => b.onclick = () => modal("Envanter kaydıyla eşle", `<label class="f"><span>Envanter kaydının barkodu</span><input name="code" required></label>`, async x => {
    const a = await api("/api/assets/by-code/" + encodeURIComponent(x.code)); await api(`/api/nexagent/nodes/${b.dataset.lk}/link`, {method: "POST", body: {asset_id: a.id}}); toast("Eşlendi"); route(); }, "Eşle"));
  $$("[data-link]", el).forEach(b => b.onclick = () => modal("Bildirimi eşle: " + esc(b.dataset.link), `<label class="f"><span>Mevcut kaydın barkodu</span><input name="code"></label><p class="small muted">— ya da —</p><label class="f"><span>Yeni kayıt oluştur: barkod</span><input name="new_code"></label>`,
    async x => { const asset_id = x.code ? (await api("/api/assets/by-code/" + encodeURIComponent(x.code))).id : null;
      const a = await api("/api/agent/link", {method: "POST", body: {hostname: b.dataset.link, asset_id, new_code: x.new_code}}); toast("Eşlendi: " + a.asset_code); route(); }, "Eşle"));
  if ($("#nxcfg")) $("#nxcfg").onsubmit = async e => { e.preventDefault(); const f = new FormData(e.target), b = Object.fromEntries(f);
    const modules = {}; o.modules.forEach(m => modules[m.key] = f.has("m_" + m.key));
    const body = {port: +b.port, interval_minutes: +b.interval_minutes, pull_hours: +b.pull_hours, software_max: +b.software_max, sources: b.sources.split("\n").map(x => x.trim()).filter(Boolean), pull_on_start: f.has("pull_on_start"), modules};
    if (b.uninstall_password) body.uninstall_password = b.uninstall_password; if (f.has("clear_pw")) body.clear_uninstall_password = true;
    try { await api("/api/nexagent/settings", {method: "PUT", body}); toast("Kaydedildi"); route(); } catch (err) { fail(err); } };
  if ($("#nxbins")) $("#nxbins").onclick = async () => { try { toast("İndiriliyor…"); const r = await api("/api/nexagent/bins/fetch", {method: "POST"}); toast(r.files.length ? r.files.length + " dosya indirildi" : "Sürümde ajan dosyası bulunamadı"); route(); } catch (e) { fail(e); } };
  if (st.running) poll();
}
