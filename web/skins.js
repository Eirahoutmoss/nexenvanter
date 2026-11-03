"use strict";
/* NexEnvanter görünüm paketleri — paketlere özel ana sayfalar ve çerçeve parçaları.
   Paket listesi app.js içindeki SKINS dizisindedir; renk/yerleşim kuralları skins.css'tedir. */

const SKINDASH = {};

/* ---------- ortak yardımcılar ---------- */
const skMin = iso => { const t = Date.parse(String(iso || "").replace(" ", "T")); return isNaN(t) ? 0 : Math.max(0, Math.round((Date.now() - t) / 60000)); };
const skAgo = iso => { const m = skMin(iso); return m < 60 ? `${m} dk` : m < 1440 ? `${Math.floor(m / 60)} sa ${m % 60} dk` : `${Math.floor(m / 1440)} gün`; };
const skHHMM = iso => { const m = skMin(iso); return m < 60 ? `00:${String(m).padStart(2, "0")}` : m < 6000 ? `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}` : `${Math.floor(m / 1440)}g`; };
const skTime = iso => String(iso || "").replace("T", " ").slice(11, 16);
const skN = n => (+n || 0).toLocaleString("tr-TR");
const PRI = {acil: 0, "yüksek": 1, normal: 2, "düşük": 3};
const skUrgent = list => [...list].sort((a, b) => (PRI[a.priority] ?? 2) - (PRI[b.priority] ?? 2) || String(a.created_at).localeCompare(String(b.created_at)));
const skInit = s => (String(s || "?").match(/\p{L}+/gu) || ["?"]).slice(0, 2).map(w => w[0]).join("").toLocaleUpperCase("tr");
const skHash = s => { let h = 7; for (const c of String(s)) h = (h * 31 + c.charCodeAt(0)) >>> 0; return h; };

async function skData(extra = {}) {
  const g = (u, ok = true) => ok ? api(u).catch(() => null) : Promise.resolve(null);
  const [st, sm, tk, al, noc, pend, locs, done] = await Promise.all([
    api("/api/stats"), g("/api/summary"), g("/api/tickets?status=open", can("ticket.read")), g("/api/alerts", can("alerts.read")),
    g("/api/noc"), g("/api/pending", can("discovery")), g("/api/locations/overview", extra.locs), g("/api/tickets?status=çözüldü", extra.done && can("ticket.read"))]);
  return {st, sm: sm || {}, tk: tk?.items || [], tkTotal: tk?.total || 0, al: al?.items || [], noc: noc || {points: [], critical: []},
    pend: pend?.items || [], pendN: pend?.count || 0, locs: locs || [], done: done?.items || []};
}
const skNewTicket = () => { if (typeof ticketModal === "function" && can("ticket.create")) ticketModal(null); else go("/tickets"); };
async function skSearch(val) {
  const v = val.trim(); if (!v) return;
  const low = v.toLocaleLowerCase("tr");
  const cmds = [["yeni talep", skNewTicket], ["arıza", skNewTicket], ["yeni cihaz", () => go("/new")], ["cihaz ekle", () => go("/new")],
    ["tara", () => go("/network")], ["zimmet", () => go("/assign")], ["rapor", () => go("/reports")], ["onay", () => go("/pending")],
    ["yedek", () => go("/spares")], ["alarm", () => go("/alerts")], ["ayar", () => go("/settings")], ["sayım", () => go("/counts")]];
  const c = cmds.find(([k]) => low.startsWith(k)); if (c) return c[1]();
  try { const a = await api("/api/assets/by-code/" + encodeURIComponent(v)); go("/asset/" + a.id); }
  catch (_) { go("/assets?q=" + encodeURIComponent(v)); }
}
function skStyle() {
  if ($("#sk-style")) return;
  const st = document.createElement("style"); st.id = "sk-style"; st.textContent = SK_CSS; document.head.append(st);
}

/* ---------- çerçeve: durum çubuğu ve F tuşları ---------- */
const FKEYS = [["F1", "Yardım", () => go("/kb")], ["F2", "Yeni talep", skNewTicket], ["F3", "Cihaz bul", () => $("#gsearch")?.focus()],
  ["F4", "Zimmet", () => go("/assign")], ["F5", "Ağ", () => go("/network")], ["F6", "Onay", () => go("/pending")], ["F7", "Yedek", () => go("/spares")],
  ["F8", "Rapor", () => go("/reports")], ["F9", "Ayarlar", () => go("/settings")], ["F10", "Ana sayfa", () => go("/")]];
function skinChrome() {
  skStyle();
  $("#sbar")?.remove(); $("#fbar")?.remove();
  const lay = THEME.skin()[3];
  if (lay === "tree") {
    const b = document.createElement("div"); b.id = "sbar"; b.className = "no-print"; document.body.append(b);
    api("/api/summary").then(s => { b.innerHTML = `<span>${skN(s.assets)} cihaz</span><span>${skN(s.tickets_open)} açık arıza</span><span>${skN(s.alerts_open)} alarm</span><span>${skN(s.pending)} onay bekliyor</span><span style="margin-left:auto">${esc(S.state.app.name)} ${esc(S.state.app.version)} · ${esc(S.state.user.full_name || S.state.user.username)}</span>`; }).catch(() => {});
  }
  if (lay === "fkeys") {
    const b = document.createElement("div"); b.id = "fbar"; b.className = "no-print";
    b.innerHTML = FKEYS.map((k, i) => `<button data-i="${i}"><b>${k[0]}</b>${k[1]}</button>`).join(""); document.body.append(b);
    $$("#fbar button").forEach(x => x.onclick = () => FKEYS[+x.dataset.i][2]());
  }
}
document.addEventListener("keydown", e => {
  if (THEME.skin()[3] !== "fkeys" || !S.state?.user) return;
  const k = FKEYS.find(x => x[0] === e.key); if (!k) return;
  e.preventDefault(); k[2]();
});

/* ---------- D · Arama odaklı ---------- */
SKINDASH.search = async v => {
  const d = await skData();
  const att = [
    ...skUrgent(d.tk).slice(0, 3).map(t => [`#/ticket/${t.id}`, true, esc(t.description.slice(0, 70)), `#${t.id} · ${esc(t.location || t.reporter_unit || "")} · ${skAgo(t.created_at)} önce`]),
    ...(d.pendN ? [["#/pending", true, `${d.pendN} yeni cihaz onay bekliyor`, "ağ keşfi"]] : []),
    ...d.al.slice(0, 2).map(a => ["#/alerts", false, esc(a.message), `${esc(a.asset_code || "")} · ${skTime(a.at)}`]),
    ...(d.sm.warranty_soon ? [["#/maint", false, `${d.sm.warranty_soon} cihazın garantisi bitiyor`, "yakında"]] : [])];
  const acts = [["Yeni talep", skNewTicket], ["Cihaz ekle", () => go("/new")], ["Ağı tara", () => go("/network")], ["Zimmet ver", () => go("/assign")], ["Yedek havuzu", () => go("/spares")], ["Raporlar", () => go("/reports")]];
  v.innerHTML = `<div class="sk-dash sk-search">
    <div class="muted">${new Date().toLocaleDateString("tr-TR", {weekday: "long", day: "numeric", month: "long"})} · ${att.length ? `${att.length} konu dikkat istiyor` : "her şey yolunda"}</div>
    <label class="sk-sbox"><span aria-hidden="true">⌕</span><input id="skq" placeholder="Bir cihaz, kişi, birim ya da komut yazın… (örn. “yeni talep”, “zimmet”)" autocomplete="off"></label>
    <div class="row sk-chips">${acts.map((a, i) => `<button class="btn" data-a="${i}">${a[0]}</button>`).join("")}</div>
    <h2 class="sk-lbl">Dikkat isteyenler</h2>
    <div class="sk-att">${att.map(a => `<a href="${a[0]}"><i class="${a[1] ? "hot" : ""}"></i><span><b>${a[2]}</b> <span class="muted">· ${a[3]}</span></span><span class="muted">↵</span></a>`).join("") || `<p class="muted">Bekleyen iş yok.</p>`}</div>
    <div class="sk-foot mono"><span>${skN(d.st.total)} cihaz</span><span>${skN(d.tkTotal)} açık talep</span><span>${skN(d.sm.alerts_open)} alarm</span><span>${skN(d.sm.spares)} yedek</span></div></div>`;
  $("#skq").focus();
  $("#skq").onkeydown = e => { if (e.key === "Enter") skSearch(e.target.value); };
  $$(".sk-chips button").forEach(b => b.onclick = () => acts[+b.dataset.a][1]());
};

/* ---------- G · Bina kesiti ---------- */
function skFloor(name) {
  const n = String(name || ""), l = n.toLocaleLowerCase("tr");
  if (/zemin/.test(l)) return 0;
  if (/bodrum/.test(l)) { const m = l.match(/(\d+)\s*\.?\s*bodrum|bodrum\s*(\d+)/); return -(+(m?.[1] || m?.[2] || 1)); }
  const m = l.match(/(-?\d+)\s*\.?\s*kat|kat\s*[:.-]?\s*(-?\d+)/); if (m) return +(m[1] ?? m[2]);
  return null;
}
SKINDASH.building = async v => {
  const d = await skData({locs: true});
  const prob = {};
  const bump = (l, k) => { if (!l) return; (prob[l] ||= {t: [], a: []})[k].push(1); };
  d.tk.forEach(t => bump(t.location || t.reporter_unit, "t")); d.al.forEach(a => bump(a.location, "a"));
  const floors = new Map();
  d.locs.forEach(L => { const f = skFloor(L.name); const k = f === null ? "?" : f; if (!floors.has(k)) floors.set(k, []); floors.get(k).push(L); });
  const keys = [...floors.keys()].sort((a, b) => a === "?" ? 1 : b === "?" ? -1 : b - a);
  const code = k => k === "?" ? "D" : k === 0 ? "Z" : String(k);
  const fname = k => k === "?" ? "Kat bilgisi olmayan birimler" : k === 0 ? "Zemin kat" : k < 0 ? `${-k}. bodrum` : `${k}. kat`;
  let sel = S.skRoom && d.locs.find(L => L.name === S.skRoom) || [...d.locs].sort((a, b) => ((prob[b.name]?.t.length || 0) + (prob[b.name]?.a.length || 0) + b.bad) - ((prob[a.name]?.t.length || 0) + (prob[a.name]?.a.length || 0) + a.bad))[0];
  const dots = L => { const p = prob[L.name] || {t: [], a: []}; const hot = Math.min(L.count, p.t.length + p.a.length + L.bad); const n = Math.min(L.count, 48);
    return Array.from({length: n}, (_, i) => `<i class="${i < hot ? "x" : ""}"></i>`).join("") + (L.count > 48 ? `<em>+${L.count - 48}</em>` : ""); };
  const panel = () => {
    if (!sel) return `<p class="muted">Henüz birim kaydı yok.</p>`;
    const tks = d.tk.filter(t => (t.location || t.reporter_unit) === sel.name), als = d.al.filter(a => a.location === sel.name);
    return `<div class="mono small muted">${esc(fname(skFloor(sel.name) ?? "?"))}</div><h2>${esc(sel.name)}</h2>
      <div class="sk-kv"><span>Cihaz</span><b>${skN(sel.count)}</b><span>Arızalı / serviste</span><b>${skN(sel.bad)}</b><span>Açık talep</span><b>${tks.length}</b><span>Açık alarm</span><b>${als.length}</b></div>
      <div class="sk-list">${tks.slice(0, 6).map(t => `<a href="#/ticket/${t.id}"><span>#${t.id} ${esc(t.description.slice(0, 40))}</span><span class="hot">${skAgo(t.created_at)}</span></a>`).join("")}
      ${als.slice(0, 4).map(a => `<a href="#/alerts"><span>${esc(a.asset_code || "")} ${esc(a.message.slice(0, 34))}</span><span class="hot">${skTime(a.at)}</span></a>`).join("")}</div>
      <a class="btn p" href="#/assets?${qs({"f.location_name": sel.name})}">Bu birimin cihazları</a>`;
  };
  v.innerHTML = `<div class="sk-dash sk-bld"><nav class="sk-lift" aria-label="Katlar"><span class="mono small">ASANSÖR</span>${keys.map(k => {
      const hot = floors.get(k).some(L => prob[L.name] || L.bad);
      return `<button class="${hot ? "hot" : ""}" data-f="${code(k)}" title="${fname(k)}">${code(k)}</button>`; }).join("")}</nav>
    <div class="sk-sec"><div class="row"><h1>Bina kesiti</h1><span class="sp"></span><span class="mono small muted">${skN(d.st.total)} CİHAZ · ${d.locs.length} BİRİM · CANLI</span></div>
      <div class="sk-floors">${keys.map(k => `<div class="sk-fl" id="fl-${code(k)}"><b class="mono">${code(k)}</b><div class="sk-rooms">${floors.get(k).map(L =>
        `<button class="sk-room ${sel && sel.name === L.name ? "on" : ""}" data-n="${esc(L.name)}"><span>${esc(L.name)}</span><span class="sk-dots">${dots(L)}</span></button>`).join("")}</div></div>`).join("")
        || `<p class="muted" style="padding:20px">Birim adlarında “Zemin”, “1. Kat”, “Bodrum” gibi ifadeler varsa birimler katlara kendiliğinden yerleşir.</p>`}<div class="sk-ground"></div></div>
      <div class="row small muted mono"><span><i class="sk-k"></i> çalışıyor</span><span><i class="sk-k x"></i> talep / alarm / arıza</span><span class="sp"></span><span>Kat bilgisi birim adından okunur (ör. “2. Kat Laboratuvar”).</span></div></div>
    <aside class="card sk-side" id="skp">${panel()}</aside></div>`;
  $$(".sk-room").forEach(b => b.onclick = () => { S.skRoom = b.dataset.n; sel = d.locs.find(L => L.name === b.dataset.n); $$(".sk-room").forEach(x => x.classList.toggle("on", x === b)); $("#skp").innerHTML = panel(); });
  $$(".sk-lift button").forEach(b => b.onclick = () => $("#fl-" + b.dataset.f)?.scrollIntoView({behavior: "smooth", block: "center"}));
};

/* ---------- H · Envanter Postası ---------- */
SKINDASH.gazette = async v => {
  const d = await skData();
  const u = skUrgent(d.tk), h = u[0];
  const org = d.sm.org_name || S.state.app.name;
  const stories = [
    ...u.slice(1, 3).map(t => [`${esc((t.location || t.reporter_unit || "Birim"))}: ${esc(t.category || "Arıza")}`, `${esc(t.description.slice(0, 110))} — #${t.id}, ${skAgo(t.created_at)} önce açıldı${t.assigned_to ? `, ${esc(t.assigned_to)} ilgileniyor` : ""}.`, `#/ticket/${t.id}`]),
    ...(d.pendN ? [[`${skN(d.pendN)} Yabancı Cihaz Kapıda`, "Ağ taramasında kayıtlı olmayan cihazlar bulundu; kayda alınmak için onay bekliyorlar.", "#/pending"]] : []),
    ...(d.sm.warranty_soon ? [[`${skN(d.sm.warranty_soon)} Garanti Vadesi Yaklaşıyor`, "Süresi dolmak üzere olan cihazların listesi bakım sayfasında.", "#/maint"]] : []),
    ...(d.sm.low_stock ? [["Sarf Stokunda Alarm", `${skN(d.sm.low_stock)} kalem kritik seviyenin altında.`, "#/stock"]] : [])].slice(0, 3);
  const loc = d.st.by_location.slice(0, 6);
  v.innerHTML = `<div class="sk-dash sk-gz">
    <div class="sk-gz-top"><span>${new Date().toLocaleDateString("tr-TR", {weekday: "long", day: "numeric", month: "long", year: "numeric"})}</span><span>${esc(org)}</span><span>Bilgi İşlem yayınıdır · ücretsiz</span></div>
    <div class="sk-gz-mast">Envanter Postası</div>
    <div class="sk-gz-strip"><i>“Hastanenin her kablosu kayıt altındadır.”</i><span>Ağ havası: <b>${d.sm.alerts_open ? `${skN(d.sm.alerts_open)} noktada sağanak` : "açık"}</b></span><span>${skN(d.st.total)} cihaz · ${skN(d.tkTotal)} açık talep · ${skN(d.pendN)} yeni gelen</span></div>
    <div class="sk-gz-cols"><article>
      ${h ? `<div class="sk-gz-kick">Manşet · ${esc(h.location || h.reporter_unit || "")}</div><h1>${esc(h.description.slice(0, 70))}</h1>
        <p class="sk-gz-dek">#${h.id} numaralı talep ${skAgo(h.created_at)}dır açık${h.assigned_to ? `; ${esc(h.assigned_to)} ilgileniyor` : "; henüz kimseye atanmadı"}.</p>
        <div class="sk-gz-body"><p>${esc(h.description)}</p><p>Cihaz: <b>${esc(h.asset_code || "belirtilmemiş")}</b> · Kategori: ${esc(h.category || "—")} · Öncelik: ${esc(h.priority || "normal")} · Bildiren: ${esc(h.reporter_name || "—")}.</p>
        ${d.sm.spares ? `<p>Yedek havuzunda şu an <b>${skN(d.sm.spares)}</b> cihaz hazır bekliyor.</p>` : ""}</div>
        <div class="row" style="margin-top:14px"><a class="btn p" href="#/ticket/${h.id}">Talebi aç</a><a class="btn" href="#/spares">Yedekten cihaz ver</a></div>`
        : `<div class="sk-gz-kick">Manşet</div><h1>Bugün Sakin Bir Gün</h1><p class="sk-gz-dek">Açık arıza kaydı bulunmuyor. Tüm birimler hizmette.</p>`}
    </article><section>${stories.map(s => `<h3><a href="${s[2]}">${s[0]}</a></h3><p>${s[1]}</p>`).join("") || "<p class=muted>Başka haber yok.</p>"}</section>
    <section><div class="sk-gz-h">Birim borsası · cihaz</div><div class="sk-kv">${loc.map(x => `<span>${esc(x.name)}</span><b>${skN(x.count)}</b>`).join("")}</div>
      <div class="sk-gz-h" style="margin-top:14px">Küçük ilanlar</div>
      <p class="sk-gz-ad">VERİLİK! ${skN(d.sm.spares)} adet temiz yedek cihaz, acil ihtiyacı olan birime. <a href="#/spares">Yedek havuzu</a></p>
      ${d.sm.counts_open ? `<p class="sk-gz-ad">DUYURU: ${skN(d.sm.counts_open)} sayım devam ediyor. <a href="#/counts">Sayım</a></p>` : ""}
      ${d.al[0] ? `<p class="sk-gz-ad">UYARI: ${esc(d.al[0].message)} <a href="#/alerts">Alarmlar</a></p>` : ""}</section></div></div>`;
};

/* ---------- I · Fosfor terminal ---------- */
SKINDASH.terminal = async v => {
  const d = await skData();
  const pad = (s, n) => { s = String(s ?? "").toLocaleUpperCase("tr"); return s.length > n ? s.slice(0, n - 1) + "…" : s.padEnd(n); };
  const bar = (a, b) => { const n = b ? Math.round(a / b * 20) : 0; return "█".repeat(n) + "░".repeat(20 - n); };
  const act = (d.st.by_status["aktif"] || 0);
  v.innerHTML = `<div class="sk-dash sk-term"><section class="card sk-tbox"><span class="sk-tt">[ AÇIK TALEPLER: ${d.tkTotal} ]</span>
      <pre>${pad("NO", 7)} ${pad("KONU", 36)} ${pad("BİRİM", 15)} SÜRE\n${"─".repeat(7)} ${"─".repeat(36)} ${"─".repeat(15)} ─────</pre>
      ${skUrgent(d.tk).slice(0, 14).map((t, i) => `<a href="#/ticket/${t.id}" class="${i === 0 ? "on" : ""}"><pre>${pad("T-" + t.id, 7)} ${pad(t.description, 36)} ${pad(t.location || t.reporter_unit, 15)} ${skHHMM(t.created_at)}</pre></a>`).join("") || "<pre>KAYIT YOK.</pre>"}
      <div class="sk-tcur">&gt; seç: TAB   aç: ENTER   yeni: F2<i></i></div></section>
    <div class="sk-tside"><section class="card sk-tbox"><span class="sk-tt">[ SİSTEM ]</span><pre>CİHAZ   ${pad(skN(d.st.total), 6)}${bar(act, d.st.total)}
AKTİF   ${pad(skN(act), 6)}
ALARM   ${pad(skN(d.sm.alerts_open), 6)}açık
ONAY    ${pad(skN(d.pendN), 6)}bekliyor
GARANTİ ${pad(skN(d.sm.warranty_soon), 6)}yakında
YEDEK   ${pad(skN(d.sm.spares), 6)}hazır</pre></section>
      <section class="card sk-tbox"><span class="sk-tt">[ OLAY GÜNLÜĞÜ ]</span>${d.al.slice(0, 10).map(a => `<a href="#/alerts"><pre>${skTime(a.at) || "--:--"} ${pad(a.kind, 8)} ${pad(a.asset_code || "", 12)}${a.severity === "kritik" ? " !" : ""}</pre></a>`).join("") || "<pre>SESSİZ.</pre>"}</section></div></div>`;
};

/* ---------- J · Nex ile konuşma ---------- */
SKINDASH.chat = async v => {
  const d = await skData();
  const msgs = [];
  if (d.pendN) msgs.push({at: d.pend[0]?.seen_at, who: "Nex", av: "N", nex: 1, body: `Ağ taramasında daha önce görmediğim <b>${skN(d.pendN)} cihaz</b> buldum.`, acts: [["Onay kuyruğunu aç", "#/pending"]]});
  d.al.slice(0, 5).forEach(a => msgs.push({at: a.at, who: "Nex", av: "N", nex: 1, body: `${esc(a.asset_code || "")} ${esc(a.brand_model || "")} — <b>${esc(a.message)}</b>${a.location ? ` · ${esc(a.location)}` : ""}`, acts: [["Alarmlar", "#/alerts"], ...(a.asset_id ? [["Cihaz kartı", `#/asset/${a.asset_id}`]] : [])]}));
  d.tk.slice(0, 8).forEach(t => msgs.push({at: t.created_at, who: t.reporter_name || t.reporter_unit || "Bildiren", av: skInit(t.reporter_name || t.reporter_unit), body: `${esc(t.description)}<div class="small muted">#${t.id} · ${esc(t.location || t.reporter_unit || "")}${t.assigned_to ? ` · ${esc(t.assigned_to)}` : " · atanmadı"}</div>`, acts: [["Talebi aç", `#/ticket/${t.id}`], ...(t.asset_id ? [["Cihaz kartı", `#/asset/${t.asset_id}`]] : []), ["Yedekten cihaz", "#/spares"]]}));
  if (d.sm.warranty_soon) msgs.push({at: "", who: "Nex", av: "N", nex: 1, body: `${skN(d.sm.warranty_soon)} cihazın garantisi yakında bitiyor.`, acts: [["Listeyi göster", "#/maint"]]});
  msgs.sort((a, b) => String(a.at).localeCompare(String(b.at)));
  v.innerHTML = `<div class="sk-dash sk-chat"><div class="sk-ch-h"><b># bugün</b><span class="muted small">Olan biten, sırayla. Mesajdaki düğme işi yapar.</span></div>
    <div class="sk-feed" id="skf">${msgs.map(m => `<div class="sk-msg"><div class="sk-av ${m.nex ? "nex" : ""}">${esc(m.av)}</div><div><div class="small muted"><b>${esc(m.who)}</b>${m.at ? ` · ${skTime(m.at)}` : ""}</div>
      <div class="sk-bub">${m.body}<div class="row" style="margin-top:10px">${m.acts.map((a, i) => `<a class="btn s ${i === 0 ? "p" : ""}" href="${a[1]}">${a[0]}</a>`).join("")}</div></div></div></div>`).join("")
      || `<div class="sk-msg"><div class="sk-av nex">N</div><div class="sk-bub">Sessiz bir gün. Bekleyen iş yok.</div></div>`}</div>
    <label class="sk-say"><input id="sks" placeholder="Yazın: “yeni talep”, “PC-0042”, “zimmet”, “rapor”, “onay”…" autocomplete="off"><button class="btn p" id="sksb">Gönder</button></label></div>`;
  const f = $("#skf"); f.scrollTop = f.scrollHeight;
  const send = () => { const x = $("#sks").value; if (!x.trim()) return;
    f.insertAdjacentHTML("beforeend", `<div class="sk-msg me"><div class="sk-bub">${esc(x)}</div></div><div class="sk-msg"><div class="sk-av nex">N</div><div class="sk-bub">Hemen bakıyorum…</div></div>`);
    f.scrollTop = f.scrollHeight; setTimeout(() => skSearch(x), 250); };
  $("#sks").onkeydown = e => { if (e.key === "Enter") send(); }; $("#sksb").onclick = send;
};

/* ---------- K · Talep metrosu ---------- */
SKINDASH.metro = async v => {
  const d = await skData({done: true});
  const today = new Date().toISOString().slice(0, 10);
  const doneToday = d.done.filter(t => String(t.resolved_at || t.updated_at || "").startsWith(today));
  const ST = [["yeni", "Açıldı", 120, 150], ["atandı", "Atandı", 380, 150], ["işlemde", "İşlemde", 640, 150], ["beklemede", "Beklemede (parça / servis)", 640, 330], ["çözüldü", "Çözüldü", 1080, 150]];
  const pos = Object.fromEntries(ST.map(s => [s[0], s]));
  const by = {}; d.tk.forEach(t => (by[t.status] ||= []).push(t));
  const trains = Object.entries(by).flatMap(([st, ts]) => { const p = pos[st]; if (!p) return [];
    return skUrgent(ts).slice(0, 5).map((t, i) => ({t, x: p[2], y: p[3] - 46 - i * 32})); });
  const red = "var(--pri)";
  v.innerHTML = `<div class="sk-dash sk-metro"><div class="row"><h1>Talep metrosu</h1><span class="sp"></span>${can("ticket.create") ? `<button class="btn p" id="skn">＋ Yeni talep</button>` : ""}<a class="btn" href="#/tickets">Liste görünümü</a></div>
    <p class="muted">Her açık talep bir tren. Trene tıklayın, talep açılsın; durumu değiştikçe tren sonraki durağa geçer.</p>
    <svg viewBox="0 0 1200 420" class="sk-map" role="img" aria-label="Taleplerin durum hattı">
      <path d="M120 150 H1080" stroke="${red}" stroke-width="16" stroke-linecap="round" fill="none"/>
      <path d="M640 150 Q640 190 640 230 V330 Q640 360 700 360 H980 Q1080 360 1080 260 V150" stroke="#2e6fd8" stroke-width="12" stroke-linecap="round" fill="none" opacity=".85"/>
      ${ST.map(s => `<a href="#/tickets?${qs({status: s[0]})}"><circle cx="${s[2]}" cy="${s[3]}" r="${s[0] === "çözüldü" ? 22 : 17}" fill="var(--card)" stroke="var(--ink)" stroke-width="6"/>
        <text x="${s[2]}" y="${s[3] + 46}" text-anchor="middle" font-weight="700" font-size="18" fill="var(--ink)">${s[1]}</text>
        <text x="${s[2]}" y="${s[3] + 68}" text-anchor="middle" font-size="14" fill="var(--muted)">${s[0] === "çözüldü" ? `bugün ${doneToday.length}` : `${(by[s[0]] || []).length} talep`}</text></a>`).join("")}
      ${trains.map(({t, x, y}) => `<a href="#/ticket/${t.id}"><title>#${t.id} ${esc(t.description.slice(0, 60))}</title><rect x="${x - 44}" y="${y - 13}" width="88" height="26" rx="13" fill="${t.status === "beklemede" ? "#2e6fd8" : t.priority === "acil" || t.priority === "yüksek" ? red : "var(--ink)"}" stroke="var(--bg)" stroke-width="3"/>
        <text x="${x}" y="${y + 5}" text-anchor="middle" font-size="13" fill="#fff" font-family="var(--font-n)">T-${t.id}</text></a>`).join("")}
    </svg>
    <div class="grid g3">${ST.slice(0, 4).map(s => `<div class="card"><h2>${s[1]}</h2><div class="sk-list">${skUrgent(by[s[0]] || []).slice(0, 5).map(t => `<a href="#/ticket/${t.id}"><span>#${t.id} ${esc(t.description.slice(0, 38))}</span><span class="muted">${skAgo(t.created_at)}</span></a>`).join("") || "<p class=muted>Boş durak</p>"}</div></div>`).join("")}</div></div>`;
  if ($("#skn")) $("#skn").onclick = skNewTicket;
};

/* ---------- L · Mantar pano ---------- */
SKINDASH.cork = async v => {
  const d = await skData({done: true});
  const col = (title, list, pin) => `<div class="sk-col"><h2>${title}</h2>${list.map((t, i) => `<a class="sk-fis" href="#/ticket/${t.id}" style="--r:${(skHash(t.id) % 5 - 2) * 0.7}deg"><i style="background:${pin}"></i>
    <b class="${t.priority === "acil" || t.priority === "yüksek" ? "hot" : ""}">#${t.id}${t.priority === "acil" ? " · ACİL" : ""}</b><span>${esc(t.description.slice(0, 70))}</span><span class="muted">${esc(t.location || t.reporter_unit || "")} · ${t.assigned_to ? esc(t.assigned_to) : skAgo(t.created_at)}</span></a>`).join("") || `<p class="sk-empty">boş</p>`}</div>`;
  const todo = skUrgent(d.tk.filter(t => t.status === "yeni")), doing = skUrgent(d.tk.filter(t => t.status !== "yeni"));
  v.innerHTML = `<div class="sk-dash sk-cork"><div class="sk-cols">${col("Yapılacak", todo.slice(0, 8), "#c0392b")}${col("Üzerinde çalışılıyor", doing.slice(0, 8), "#1f9d6b")}${col("Bitti ✓", d.done.slice(0, 6), "#8a8a8a")}</div>
    <div class="sk-notes">${d.pendN ? `<a class="sk-sticky" href="#/pending" style="--r:3deg">${skN(d.pendN)} yeni cihaz ağda! Onay bekliyor →</a>` : ""}
      ${d.al.slice(0, 2).map((a, i) => `<a class="sk-polar" href="#/alerts" style="--r:${i ? 3 : -4}deg"><span>${esc(a.asset_code || "!")}</span><em>${esc(a.message.slice(0, 40))}</em></a>`).join("")}
      ${d.sm.warranty_soon ? `<a class="sk-tape" href="#/maint" style="--r:2deg"><b>Garanti takvimi</b><br>${skN(d.sm.warranty_soon)} cihaz yakında bitiyor</a>` : ""}
      <a class="sk-tape" href="#/spares" style="--r:-2deg"><b>Yedek havuzu</b><br>${skN(d.sm.spares)} cihaz hazır</a></div>
    ${can("ticket.create") ? `<button class="sk-plus" id="skn" aria-label="Yeni talep">+</button>` : ""}</div>`;
  if ($("#skn")) $("#skn").onclick = skNewTicket;
};

/* ---------- M · Hasta monitörü ---------- */
SKINDASH.vitals = async v => {
  const d = await skData();
  const pts = d.noc.points || [], okPts = pts.filter(p => p.status === "ok").length;
  const act = d.st.by_status["aktif"] || 0, pct = pts.length ? Math.round(okPts / pts.length * 100) : d.st.total ? Math.round(act / d.st.total * 100) : 0;
  const wave = (seed, spike, flat) => { const p = []; for (let x = 0; x <= 1000; x += 10) { let y = 55 + Math.sin(x / 23 + seed) * 4; const m = (x + seed * 37) % 160;
    if (flat && x > 700) y = 55; else if (spike && m >= 60 && m < 70) y = 12; else if (spike && m >= 70 && m < 80) y = 88; p.push(x + "," + y.toFixed(1)); } return p.join(" "); };
  const rows = [
    ["ÇEVRİMİÇİ · SpO₂", "#3fd8ff", pct, "%", pts.length ? `${okPts} / ${pts.length} hizmet noktası sağlam` : `${skN(act)} / ${skN(d.st.total)} cihaz aktif`, wave(2, false, pct < 90), "#/noc"],
    ["AÇIK TALEP", d.tkTotal ? "#ff3b3b" : "#3cff7a", d.tkTotal, "talep", `${skN(d.sm.tickets_new)} yeni`, wave(1, true, false), "#/tickets"],
    ["ALARM", d.sm.alerts_open ? "#ffd23f" : "#3cff7a", d.sm.alerts_open || 0, "açık", d.al[0] ? esc(d.al[0].message.slice(0, 34)) : "sessiz", wave(4, !!d.sm.alerts_open, false), "#/alerts"],
    ["KEŞİF · YENİ CİHAZ", "#e07bff", d.pendN, "bekliyor", "onay kuyruğu", wave(5, !!d.pendN, false), "#/pending"],
    ["BAKIM · GARANTİ", "#3cff7a", (d.sm.maint_overdue || 0) + (d.sm.warranty_soon || 0), "kayıt", `gecikmiş ${skN(d.sm.maint_overdue)} · garanti ${skN(d.sm.warranty_soon)}`, wave(3, false, false), "#/maint"]];
  const crit = d.al.filter(a => a.severity === "kritik");
  const btns = [["TALEPLER", "/tickets"], ["CİHAZLAR", "/assets"], ["ONAY", "/pending"], ["YEDEK", "/spares"], ["ZİMMET", "/assign"], ["RAPOR", "/reports"], ["DURUM PANOSU", "/noc"], ["AYARLAR", "/settings"]];
  v.innerHTML = `<div class="sk-dash sk-vit"><div class="row sk-alarm">${crit.slice(0, 2).map(a => `<a class="crit" href="#/alerts">ALARM · ${esc(a.asset_code || "")} · ${esc(a.message.slice(0, 50))}</a>`).join("")}
      ${d.al.filter(a => a.severity !== "kritik").slice(0, 1).map(a => `<a class="warn" href="#/alerts">UYARI · ${esc(a.message.slice(0, 50))}</a>`).join("")}<span class="sp"></span><span class="muted">HASTA: ${esc(d.sm.org_name || "HASTANE AĞI")} · ${new Date().toLocaleTimeString("tr-TR", {hour: "2-digit", minute: "2-digit"})}</span></div>
    <div class="sk-rows">${rows.map(r => `<a class="sk-vrow" href="${r[6]}" style="--c:${r[1]}"><span class="lb">${r[0]}</span><svg viewBox="0 0 1000 100" preserveAspectRatio="none" aria-hidden="true"><polyline points="${r[5]}"/></svg>
      <span class="val"><span class="row small"><span>${r[0].split(" · ")[0]}</span><span class="sp"></span><span>${r[3]}</span></span><b>${skN(r[2])}</b><span class="small">${r[4]}</span></span></a>`).join("")}</div>
    <nav class="sk-vbtn">${btns.map(b => `<a class="btn" href="#${b[1]}">${b[0]}</a>`).join("")}</nav></div>`;
};

/* ---------- N · Radar ---------- */
SKINDASH.radar = async v => {
  const d = await skData();
  const C = 400, R = [95, 190, 285, 380];
  const col = {kritik: "#ff5d5d", "arıza": "#ff9f43", "uyarı": "#e9f27a", pasif: "#3fae8c", ok: "#7dfcd2"};
  const blips = [];
  const put = (key, ring, color, size, href, label) => { const h = skHash(key); const a = (h % 3600) / 3600 * Math.PI * 2; const r = (ring ? R[ring - 1] : 0) + 18 + (h >> 12) % 70;
    blips.push({x: C + Math.cos(a) * r, y: C + Math.sin(a) * r, color, size, href, label}); };
  d.noc.critical.forEach(a => put("c" + a.id, 1, col[a.live] || col.ok, a.live === "ok" ? 6 : 10, `#/asset/${a.id}`, a.asset_code));
  (d.noc.points || []).forEach(p => (p.items || []).forEach(it => put("p" + it.asset_id, 2, col[it.live] || col.ok, it.live === "ok" ? 6 : 10, `#/asset/${it.asset_id}`, it.asset_code)));
  d.tk.forEach(t => put("t" + t.id, 3, "#ff9f43", 9, `#/ticket/${t.id}`, `#${t.id}`));
  d.pend.slice(0, 120).forEach(p => put("u" + p.id, 4, "#e9f27a", 8, "#/pending", p.ip || p.hostname || "?"));
  const lost = d.al.filter(a => a.severity === "kritik").length;
  v.innerHTML = `<div class="sk-dash sk-rad"><div class="sk-scope"><svg viewBox="0 0 800 800" role="img" aria-label="Ağ radarı">
      ${R.map(r => `<circle cx="${C}" cy="${C}" r="${r}" fill="none" stroke="var(--line)" stroke-width="${r === 380 ? 2 : 1}"/>`).join("")}
      <line x1="20" y1="${C}" x2="780" y2="${C}" stroke="var(--line)"/><line x1="${C}" y1="20" x2="${C}" y2="780" stroke="var(--line)"/>
      <g class="sk-sweep"><path d="M${C} ${C} L${C + 380} ${C} A380 380 0 0 0 ${C + 380 * Math.cos(-0.9)} ${C + 380 * Math.sin(-0.9)} Z" fill="url(#skg)"/></g>
      <defs><radialGradient id="skg"><stop offset="0" stop-color="var(--pri)" stop-opacity=".05"/><stop offset="1" stop-color="var(--pri)" stop-opacity=".35"/></radialGradient></defs>
      ${["KRİTİK", "HİZMET NOKTASI", "ARIZA", "BİLİNMEYEN"].map((t, i) => `<text x="${C + 6}" y="${C - R[i] + 14}" font-size="11" fill="var(--muted)">${t}</text>`).join("")}
      <circle cx="${C}" cy="${C}" r="9" fill="var(--pri)"/>
      ${blips.map(b => `<a href="${b.href}"><title>${esc(b.label || "")}</title><circle cx="${b.x.toFixed(1)}" cy="${b.y.toFixed(1)}" r="${b.size / 2}" fill="${b.color}" style="filter:drop-shadow(0 0 4px ${b.color})"/></a>`).join("")}
    </svg></div>
    <aside class="card sk-side"><h1>Nex · Radar</h1><p class="small muted">Merkez: çekirdek. İç halka kritik cihazlar, sonra hizmet noktaları, açık arızalar ve dışta ağda görülen ama kayıtlı olmayan cihazlar.</p>
      <div class="sk-tiles"><a href="#/assets"><span>KAYITLI</span><b>${skN(d.st.total)}</b></a><a href="#/alerts" class="${lost ? "bad" : ""}"><span>KRİTİK ALARM</span><b>${lost}</b></a>
        <a href="#/pending" class="${d.pendN ? "unk" : ""}"><span>BİLİNMEYEN</span><b>${skN(d.pendN)}</b></a><a href="#/tickets"><span>AÇIK ARIZA</span><b>${skN(d.tkTotal)}</b></a></div>
      <h2 style="margin-top:14px">Temas günlüğü</h2><div class="sk-list">${d.al.slice(0, 7).map(a => `<a href="#/alerts"><span>${esc(a.asset_code || "—")}</span><span class="muted">${esc(a.message.slice(0, 26))}</span></a>`).join("") || "<p class=muted>Sessiz.</p>"}</div>
      <div class="sk-tiles" style="margin-top:auto"><a class="btn p" href="#/network">TARA</a><a class="btn" href="#/pending">TANIMLA (${skN(d.pendN)})</a></div></aside></div>`;
};

/* ---------- paket sayfalarının stilleri ---------- */
const SK_CSS = `
.sk-search{max-width:780px;margin:40px auto 0;display:flex;flex-direction:column;gap:14px}
.sk-sbox{display:flex;align-items:center;gap:14px;height:68px;padding:0 22px;border:2px solid var(--ink);border-radius:14px;background:var(--card)}
.sk-sbox span{font-size:24px}.sk-sbox input{border:0;outline:0;font-size:20px;background:transparent;padding:0}
.sk-lbl{margin-top:30px;font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.sk-att a{display:flex;gap:16px;align-items:center;padding:15px 0;border-bottom:1px solid var(--line);color:var(--ink)}.sk-att a>span:nth-child(2){flex:1}
.sk-att i{width:10px;height:10px;border-radius:50%;background:var(--line)}.sk-att i.hot{background:var(--pri)}
.sk-foot{display:flex;justify-content:space-between;color:var(--muted);font-size:12px;margin-top:30px}
.sk-bld{display:grid;grid-template-columns:96px minmax(0,1fr) 320px;gap:20px;align-items:start}
.sk-lift{display:flex;flex-direction:column;align-items:center;gap:10px;border:1px solid var(--line);padding:14px 0;position:sticky;top:20px}
.sk-lift button{width:62px;height:62px;border-radius:50%;border:2px solid var(--muted);background:transparent;color:var(--ink);font:inherit;font-family:var(--font-n);font-size:20px;cursor:pointer}
.sk-lift button.hot{border-color:var(--pri);color:var(--pri)}
.sk-floors{border:2px solid var(--ink);border-top-width:6px;margin:10px 0}
.sk-fl{display:flex;border-bottom:2px solid var(--ink);min-height:92px}.sk-fl>b{width:56px;display:grid;place-items:center;border-right:2px solid var(--ink);font-size:18px;flex:0 0 auto}
.sk-rooms{display:flex;flex-wrap:wrap;flex:1}
.sk-room{flex:1 1 170px;text-align:left;background:transparent;border:0;border-right:1px dashed var(--line);color:var(--ink);font:inherit;padding:8px 10px;cursor:pointer;display:flex;flex-direction:column;gap:6px}
.sk-room:hover{background:color-mix(in srgb,var(--ink) 6%,transparent)}.sk-room.on{outline:2px solid var(--pri);outline-offset:-4px}
.sk-room>span:first-child{font-size:12px;letter-spacing:.03em}
.sk-dots{display:flex;flex-wrap:wrap;gap:3px}.sk-dots i,.sk-k{display:inline-block;width:9px;height:9px;background:#8ff0b0}.sk-dots i.x,.sk-k.x{background:var(--pri)}.sk-dots em{font-size:11px;font-style:normal;color:var(--muted)}
.sk-ground{height:20px;background:repeating-linear-gradient(45deg,var(--line) 0 2px,transparent 2px 10px)}
.sk-side{position:sticky;top:20px;display:flex;flex-direction:column;gap:12px}
.sk-kv{display:grid;grid-template-columns:1fr auto;gap:6px 12px}.sk-kv b{font-family:var(--font-n)}
.sk-list a{display:flex;justify-content:space-between;gap:10px;padding:8px 0;border-top:1px solid var(--line);color:var(--ink)}.sk-list a:last-child{border-bottom:1px solid var(--line)}
.sk-list .hot,.hot{color:var(--pri)}
.sk-gz-top{display:flex;justify-content:space-between;font-size:11px;text-transform:uppercase;letter-spacing:.12em;border-bottom:1px solid var(--ink);padding-bottom:6px;flex-wrap:wrap;gap:8px}
.sk-gz-mast{font-family:UnifrakturCook,serif;font-size:clamp(44px,7vw,84px);text-align:center;line-height:1.05;margin:6px 0}
.sk-gz-strip{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;border-top:3px double var(--ink);border-bottom:1px solid var(--ink);padding:5px 0;font-size:12px}
.sk-gz-cols{display:grid;grid-template-columns:2.2fr 1fr 1fr;margin-top:16px}.sk-gz-cols>*{padding:0 20px;border-left:1px solid var(--ink)}.sk-gz-cols>:first-child{padding-left:0;border:0}
.sk-gz-cols h1{font-size:clamp(30px,3.6vw,48px);line-height:1.04;border:0;padding:0;margin:6px 0 10px}
.sk-gz-kick{font-size:11px;text-transform:uppercase;letter-spacing:.14em;color:var(--pri)}.sk-gz-dek{font-family:var(--font-h);font-style:italic;font-size:18px;margin:0 0 12px}
.sk-gz-body{columns:2;column-gap:22px;text-align:justify;line-height:1.6}.sk-gz-body p{margin:0 0 10px}
.sk-gz-cols h3{font-family:var(--font-h);font-weight:900;font-size:21px;line-height:1.1;margin:0 0 6px;padding-top:12px;border-top:1px solid var(--ink)}.sk-gz-cols h3:first-child{border:0;padding:0}.sk-gz-cols h3 a{color:var(--ink)}
.sk-gz-h{font-size:11px;text-transform:uppercase;letter-spacing:.14em;border-bottom:1px solid var(--ink);padding-bottom:4px;margin-bottom:8px}
.sk-gz-ad{font-size:12px;border:1px solid var(--ink);padding:8px;line-height:1.5}
.sk-term{display:grid;grid-template-columns:1.6fr 1fr;gap:16px}.sk-tside{display:flex;flex-direction:column;gap:16px}
.sk-tbox{position:relative;padding-top:18px}.sk-tt{position:absolute;top:-14px;left:12px;background:var(--bg);padding:0 8px}
.sk-term pre{margin:0;font:inherit;white-space:pre;overflow:hidden}.sk-term a{color:var(--ink);display:block}.sk-term a:hover,.sk-term a.on{background:var(--ink);color:var(--bg);text-shadow:none}
.sk-tcur{margin-top:12px}.sk-tcur i{display:inline-block;width:12px;height:20px;background:var(--ink);vertical-align:-4px;margin-left:6px;animation:skblink 1s steps(1) infinite}
@keyframes skblink{50%{opacity:0}}
.sk-chat{display:flex;flex-direction:column;height:calc(100vh - 110px);max-width:900px}
.sk-ch-h{display:flex;gap:14px;align-items:baseline;padding-bottom:12px;border-bottom:1px solid var(--line)}
.sk-feed{flex:1;overflow:auto;padding:18px 0;display:flex;flex-direction:column;gap:16px}
.sk-msg{display:flex;gap:12px;max-width:760px}.sk-msg.me{align-self:flex-end}.sk-msg.me .sk-bub{background:var(--side);color:var(--side-ink);border-radius:16px 4px 16px 16px}
.sk-av{width:40px;height:40px;border-radius:12px;background:var(--muted);color:#fff;display:grid;place-items:center;font-weight:700;flex:0 0 auto}.sk-av.nex{background:var(--pri)}
.sk-bub{background:var(--card);border-radius:4px 16px 16px 16px;padding:12px 16px;margin-top:4px}
.sk-say{display:flex;gap:10px;align-items:center;padding:8px 8px 8px 16px;background:var(--card);border:2px solid var(--ink);border-radius:16px}.sk-say input{border:0;outline:0;background:transparent}
.sk-map{width:100%;height:auto;max-height:440px;display:block;margin:6px 0 16px}.sk-map a{cursor:pointer}
.sk-cork{position:relative;display:grid;grid-template-columns:minmax(0,3fr) minmax(220px,1fr);gap:24px}
.sk-cols{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:22px}.sk-col h2{color:#fffdf6;text-shadow:0 2px 3px rgba(0,0,0,.4);font-size:32px}
.sk-fis{position:relative;display:flex;flex-direction:column;margin-bottom:16px;padding:20px 14px 12px;background:#fffdf6;background-image:repeating-linear-gradient(#fffdf6 0 23px,#cfe0ee 23px 24px);color:#2a1d10;line-height:24px;box-shadow:0 8px 16px rgba(0,0,0,.35);transform:rotate(var(--r))}
.sk-fis i{position:absolute;left:50%;top:-6px;width:15px;height:15px;border-radius:50%;box-shadow:0 3px 4px rgba(0,0,0,.4)}.sk-fis .hot{color:#b2321f}.sk-empty{color:#fffdf6;font-family:Caveat,cursive;font-size:24px}
.sk-notes{display:flex;flex-direction:column;gap:22px}.sk-notes>a{color:#2a1d10;transform:rotate(var(--r));box-shadow:0 10px 18px rgba(0,0,0,.35)}
.sk-sticky{background:#ffe46b;padding:18px;font-family:Caveat,cursive;font-size:26px;line-height:1.15;min-height:150px}
.sk-polar{background:#fffdf6;padding:10px 10px 30px;display:flex;flex-direction:column}.sk-polar span{height:110px;background:#2a2f36;color:#e9e3d6;display:grid;place-items:center;font-size:20px;font-weight:700}
.sk-polar em{font-family:Caveat,cursive;font-size:22px;text-align:center;margin-top:8px;font-style:normal}
.sk-tape{background:#cfe6f2;padding:14px 16px;line-height:1.6;font-size:13px}
.sk-plus{position:fixed;right:40px;bottom:40px;width:64px;height:64px;border-radius:50%;border:0;background:#c0392b;color:#fff;font-size:34px;box-shadow:0 6px 12px rgba(0,0,0,.4);cursor:pointer}
.sk-vit{display:flex;flex-direction:column;gap:10px;height:calc(100vh - 110px)}
.sk-alarm a{padding:4px 14px;font-weight:700;letter-spacing:.05em}.sk-alarm .crit{background:#ff3b3b;color:#000}.sk-alarm .warn{color:#ffd23f}
.sk-rows{flex:1;display:flex;flex-direction:column;border-top:1px solid var(--line)}
.sk-vrow{flex:1;display:grid;grid-template-columns:minmax(0,1fr) 280px;border-bottom:1px solid var(--line);color:var(--c);position:relative;min-height:90px}
.sk-vrow .lb{position:absolute;left:6px;top:6px;font-weight:600}.sk-vrow svg{width:100%;height:100%}.sk-vrow polyline{fill:none;stroke:var(--c);stroke-width:2.5}
.sk-vrow .val{border-left:1px solid var(--line);padding:6px 16px;display:flex;flex-direction:column;justify-content:center}.sk-vrow .val b{font-size:64px;line-height:.9}
.sk-vrow:hover{background:#0b1015}
.sk-vbtn{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px}.sk-vbtn .btn{justify-content:center;height:46px;letter-spacing:.04em}
.sk-rad{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:20px;align-items:start}
.sk-scope svg{width:100%;max-height:calc(100vh - 120px);display:block}
.sk-sweep{transform-origin:400px 400px;animation:sksweep 6s linear infinite}@keyframes sksweep{to{transform:rotate(360deg)}}
.sk-tiles{display:grid;grid-template-columns:1fr 1fr;gap:8px}.sk-tiles a{border:1px solid var(--line);padding:10px;color:var(--ink);display:flex;flex-direction:column}
.sk-tiles a span{font-size:11px;color:var(--muted)}.sk-tiles a b{font-size:30px}.sk-tiles a.bad{border-color:#ff5d5d;color:#ff5d5d}.sk-tiles a.unk{border-color:#e9f27a;color:#e9f27a}
.sk-tiles .btn{justify-content:center}.sk-tiles a.btn.p{color:var(--bg)}
@media (prefers-reduced-motion:reduce){.sk-sweep,.sk-tcur i{animation:none}}
@media (max-width:1000px){.sk-bld,.sk-rad,.sk-term,.sk-cork{grid-template-columns:1fr}.sk-lift{flex-direction:row;flex-wrap:wrap;position:static;padding:8px}
.sk-gz-cols{grid-template-columns:1fr}.sk-gz-cols>*{padding:12px 0;border-left:0;border-top:1px solid var(--ink)}.sk-gz-body{columns:1}.sk-cols{grid-template-columns:1fr}
.sk-vrow{grid-template-columns:1fr 160px}.sk-vrow .val b{font-size:40px}}
`;
