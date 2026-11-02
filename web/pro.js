"use strict";
/* NexEnvanter pro modülleri: arıza, sayım, zimmet, bakım, sarf, bilgi bankası, ağ & ajan, raporlar, kurumlar, ileri ayarlar */
const PRO = {};
const M = {meta: null};
async function meta() { return M.meta || (M.meta = await api("/api/meta")); }
const today = () => new Date().toISOString().slice(0, 10);
const ago = d => { const t = new Date(); t.setDate(t.getDate() - d); return t.toISOString().slice(0, 10); };

/* ---------- ortak bileşenler ---------- */
function modal(title, body, onOk, okText = "Kaydet") {
  const w = document.createElement("div");
  w.className = "modal";
  w.innerHTML = `<form class="card mbox"><div class="row"><h2 style="margin:0">${title}</h2><span class="sp"></span><button type="button" class="btn s" data-x>✕</button></div>
    <div class="mbody">${body}</div><div class="row" style="margin-top:14px"><span class="sp"></span><button type="button" class="btn" data-x>Vazgeç</button>
    ${onOk ? `<button class="btn p">${okText}</button>` : ""}</div></form>`;
  document.body.append(w);
  const close = () => w.remove();
  $$("[data-x]", w).forEach(b => b.onclick = close);
  w.onclick = e => { if (e.target === w) close(); };
  $("form", w).onsubmit = async e => {
    e.preventDefault();
    const btn = $("button.p", w); if (btn) btn.disabled = true;
    try { await onOk(Object.fromEntries(new FormData(e.target)), w); close(); } catch (err) { fail(err); if (btn) btn.disabled = false; }
  };
  setTimeout(() => $("input:not([type=hidden]),textarea,select", w)?.focus(), 30);
  return w;
}
function sigPad(el) {
  el.innerHTML = `<canvas width="560" height="160" class="sig"></canvas><div class="row small"><span class="muted">Parmak veya fareyle imzalayın</span><span class="sp"></span><button type="button" class="btn s">Temizle</button></div>`;
  const c = $("canvas", el), x = c.getContext("2d");
  let draw = false, dirty = false;
  x.lineWidth = 2.4; x.lineCap = "round"; x.strokeStyle = "#000";
  const pos = e => { const r = c.getBoundingClientRect(); return [(e.clientX - r.left) * c.width / r.width, (e.clientY - r.top) * c.height / r.height]; };
  c.onpointerdown = e => { draw = true; dirty = true; c.setPointerCapture(e.pointerId); x.beginPath(); x.moveTo(...pos(e)); };
  c.onpointermove = e => { if (draw) { x.lineTo(...pos(e)); x.stroke(); } };
  c.onpointerup = c.onpointercancel = () => { draw = false; };
  $("button", el).onclick = () => { x.clearRect(0, 0, c.width, c.height); dirty = false; };
  return {get: () => dirty ? c.toDataURL("image/png") : null};
}
function beep(ok) {
  try { const a = new (window.AudioContext || window.webkitAudioContext)(), o = a.createOscillator(), g = a.createGain();
    o.frequency.value = ok ? 880 : 220; g.gain.value = .08; o.connect(g); g.connect(a.destination); o.start(); o.stop(a.currentTime + (ok ? .08 : .25)); } catch (_) {}
}
const statusPill = s => `<span class="pill t-${esc(s)}">${esc(s)}</span>`;
const prioPill = p => p === "normal" ? "" : `<span class="pill p-${esc(p)}">${esc(p)}</span>`;
async function locOptions(sel = "") {
  const vals = await api("/api/values/location_name").catch(() => []);
  return vals.map(x => `<option ${x === sel ? "selected" : ""}>${esc(x)}</option>`).join("");
}
async function codesToIds(text) {
  const ids = [], bad = [];
  for (const c of text.split(/[\s,;]+/).map(x => x.trim()).filter(Boolean)) {
    try { ids.push((await api("/api/assets/by-code/" + encodeURIComponent(c))).id); } catch (_) { bad.push(c); }
  }
  if (bad.length) throw new Error("Bulunamayan barkod: " + bad.join(", "));
  return ids;
}

/* ---------- form: tür → kategori + otomatik numara ---------- */
async function formPro(form, isNew) {
  const ti = $('[name="hardware_info"]', form), ci = $('[name="asset_code"]', form), ki = $('[name="category"]', form);
  if (!ti) return;
  const cat = await api("/api/catalog").catch(() => ({types: [], categories: []}));
  const dl = $("#dl_hardware_info", form) || Object.assign(document.createElement("datalist"), {id: "dl_hardware_info"});
  if (!dl.parentNode) { form.append(dl); ti.setAttribute("list", "dl_hardware_info"); }
  const have = new Set($$("option", dl).map(o => o.value));
  dl.insertAdjacentHTML("afterbegin", cat.types.filter(t => t.active && !have.has(t.name)).map(t => `<option value="${esc(t.name)}">${esc(t.category)}</option>`).join(""));
  const hint = document.createElement("div"); hint.className = "small muted"; ti.after(hint);
  let tm;
  const upd = () => { clearTimeout(tm); tm = setTimeout(async () => {
    const r = ti.value.trim() ? await api("/api/catalog/next?" + qs({type: ti.value})).catch(() => ({})) : {};
    if (r.category) {
      hint.innerHTML = `Kategori: <b>${esc(r.category)}</b>${isNew ? ` · sıradaki numara: <b class="mono">${esc(r.code)}</b>` : ""}`;
      if (ki && (!ki.value || ki.dataset.auto)) { ki.value = r.category; ki.dataset.auto = "1"; }
      if (isNew && ci) ci.placeholder = "Otomatik: " + r.code;
    } else {
      hint.textContent = ti.value.trim() ? "Bu tür tanımlı değil — barkodu elle girin veya Türler & Kategoriler'den ekleyin" : "";
      if (isNew && ci) ci.placeholder = "Boş bırakılırsa türe göre otomatik";
    }
  }, 200); };
  ti.addEventListener("input", upd); upd();
}

/* ---------- türler & kategoriler ---------- */
PRO["/catalog"] = async v => {
  const c = await api("/api/catalog"), ed = can("fields");
  v.innerHTML = `<h1>Türler & Kategoriler</h1><div class="card small muted">Cihaz kaydında <b>Envanter Türü</b> seçildiğinde kategori otomatik atanır; barkod boş bırakılırsa o kategoriye ait <b>sıradaki numara</b> verilir (ör. BLG-00001, BLG-00002…). Elle girilen ve kalıba uyan numaralarda sayaç kendiliğinden ileri alınır; çakışan numara atlanır. Excel içe aktarmada “barkodu boş satırlara otomatik numara ver” seçeneği de aynı sayacı kullanır.</div>
    <div class="grid g2"><div class="card"><h2>Kategoriler ve numara kalıbı</h2><div class="tw"><table><thead><tr><th>Kategori</th><th>Ön ek</th><th>Basamak</th><th>Sıradaki no</th><th>Örnek</th><th>Tür</th><th></th></tr></thead><tbody>
      ${c.categories.map(k => `<tr data-c="${k.id}"><td><input data-k="name" value="${esc(k.name)}" ${ed ? "" : "disabled"} style="min-width:150px"></td><td><input data-k="prefix" value="${esc(k.prefix)}" ${ed ? "" : "disabled"} style="width:80px"></td>
        <td><input data-k="digits" type="number" min="0" max="12" value="${k.digits}" ${ed ? "" : "disabled"} style="width:64px"></td><td><input data-k="next_no" type="number" min="1" value="${k.next_no}" ${ed ? "" : "disabled"} style="width:90px"></td>
        <td class="mono small">${esc(k.next_code)}</td><td>${k.types}</td><td>${ed ? `<button class="btn s d" data-dc="${k.id}">Sil</button>` : ""}</td></tr>`).join("")}</tbody></table></div>
      ${ed ? `<form id="nc" class="row" style="margin-top:10px"><input name="name" placeholder="Yeni kategori" required style="flex:1"><input name="prefix" placeholder="Ön ek (ör. MON-)" style="width:120px"><input name="digits" type="number" value="5" style="width:70px"><button class="btn">Ekle</button></form>` : ""}</div>
    <div class="card"><h2>Envanter türleri</h2><div class="tw" style="max-height:560px"><table><thead><tr><th>Tür</th><th>Kategori</th><th>Eş adlar (Excel'deki farklı yazımlar)</th><th></th></tr></thead><tbody>
      ${c.types.map(t => `<tr data-t="${t.id}"><td><input data-k="name" value="${esc(t.name)}" ${ed ? "" : "disabled"} style="min-width:160px"></td>
        <td><select data-k="category_id" ${ed ? "" : "disabled"}>${c.categories.map(k => `<option value="${k.id}" ${k.id === t.category_id ? "selected" : ""}>${esc(k.name)}</option>`).join("")}</select></td>
        <td><input data-k="aliases" value="${esc(t.aliases.join(", "))}" ${ed ? "" : "disabled"} placeholder="PC, kasa"></td><td>${ed ? `<button class="btn s d" data-dt="${t.id}">Sil</button>` : ""}</td></tr>`).join("")}</tbody></table></div>
      ${ed ? `<form id="nt" class="row" style="margin-top:10px"><input name="name" placeholder="Yeni tür" required style="flex:1"><select name="category_id" style="width:200px">${c.categories.map(k => `<option value="${k.id}">${esc(k.name)}</option>`).join("")}</select><button class="btn">Ekle</button></form>` : ""}</div></div>`;
  if (!ed) return;
  $$("[data-c] [data-k]").forEach(el => el.onchange = async () => { const id = el.closest("[data-c]").dataset.c;
    try { await api("/api/catalog/categories/" + id, {method: "PATCH", body: {[el.dataset.k]: el.type === "number" ? +el.value : el.value}}); toast("Kaydedildi"); route(); } catch (e) { fail(e); route(); } });
  $$("[data-t] [data-k]").forEach(el => el.onchange = async () => { const id = el.closest("[data-t]").dataset.t;
    let val = el.value; if (el.dataset.k === "aliases") val = val.split(",").map(x => x.trim()).filter(Boolean); if (el.dataset.k === "category_id") val = +val;
    try { await api("/api/catalog/types/" + id, {method: "PATCH", body: {[el.dataset.k]: val}}); toast("Kaydedildi"); } catch (e) { fail(e); route(); } });
  $$("[data-dc]").forEach(b => b.onclick = async () => { if (!confirm("Kategori silinsin mi?")) return; try { await api("/api/catalog/categories/" + b.dataset.dc, {method: "DELETE"}); route(); } catch (e) { fail(e); } });
  $$("[data-dt]").forEach(b => b.onclick = async () => { if (!confirm("Tür silinsin mi? (Kayıtlardaki değer değişmez)")) return; await api("/api/catalog/types/" + b.dataset.dt, {method: "DELETE"}); route(); });
  $("#nc").onsubmit = async e => { e.preventDefault(); const b = Object.fromEntries(new FormData(e.target)); b.digits = +b.digits;
    try { await api("/api/catalog/categories", {method: "POST", body: b}); route(); } catch (err) { fail(err); } };
  $("#nt").onsubmit = async e => { e.preventDefault(); const b = Object.fromEntries(new FormData(e.target)); b.category_id = +b.category_id;
    try { await api("/api/catalog/types", {method: "POST", body: b}); route(); } catch (err) { fail(err); } };
};

/* ---------- toplu işlemler (liste) ve detay eklentileri ---------- */
function bulkActions(el, ids) {
  if (!el) return;
  el.innerHTML = !ids.length ? "" : [
    can("assign") ? `<button class="btn" data-a="z">✍ Zimmetle</button>` : "",
    can("maint") ? `<button class="btn" data-a="m">🔧 Bakım planı</button>` : "",
    can("asset.archive") ? `<button class="btn d" data-a="h">Hurdaya ayır</button>` : ""].join(" ");
  $$("[data-a]", el).forEach(b => b.onclick = () => ({z: assignModal, m: maintModal, h: disposeModal})[b.dataset.a](ids));
}
function assignModal(ids, done) {
  const w = modal(`Zimmet / Devir — ${ids.length} cihaz`, `<div class="grid g2">
    <label class="f"><span>Tür</span><select name="kind"><option>kişi</option><option>birim</option></select></label>
    <label class="f"><span>Zimmet alan (ad soyad / birim adı) *</span><input name="holder_name" required></label>
    <label class="f"><span>Unvan</span><input name="holder_title"></label><label class="f"><span>Birim</span><input name="holder_unit" list="dl_loc"></label></div>
    <datalist id="dl_loc"></datalist><label class="f"><span>Not</span><input name="note"></label>
    <div class="grid g2"><div><b class="small">Teslim alan imzası</b><div id="sg1"></div></div><div><b class="small">Teslim eden imzası</b><div id="sg2"></div></div></div>
    <p class="small muted">Cihaz başka birine zimmetliyse önceki zimmet bu belgeyle kapanır (devir).</p>`, async b => {
    const r = await api("/api/assignments", {method: "POST", body: {...b, asset_ids: ids, signature: s1.get(), giver_signature: s2.get()}});
    toast("Zimmet belgesi: " + r.doc_no); window.open("/print/zimmet/" + r.doc_no, "_blank"); S.sel.clear(); done ? done() : route();
  }, "Zimmetle ve tutanak");
  const s1 = sigPad($("#sg1", w)), s2 = sigPad($("#sg2", w));
  locOptions().then(o => $("#dl_loc", w).innerHTML = o.replace(/<option>/g, "<option value=\"").replace(/<\/option>/g, "\">"));
}
function returnModal(ids, done) {
  const w = modal(`Zimmet iadesi — ${ids.length} cihaz`, `<label class="f"><span>Not</span><input name="note"></label><b class="small">İade eden imzası</b><div id="sg"></div>`, async b => {
    const r = await api("/api/assignments/return", {method: "POST", body: {...b, asset_ids: ids, return_signature: sg.get()}});
    toast("İade belgesi: " + r.doc_no); window.open("/print/zimmet/" + r.doc_no, "_blank"); done ? done() : route();
  }, "İade al ve tutanak");
  const sg = sigPad($("#sg", w));
}
function maintModal(ids) {
  modal(`Bakım planı — ${ids.length} cihaz`, `<label class="f"><span>Bakım adı *</span><input name="title" required placeholder="ör. UPS akü kontrolü"></label>
    <div class="grid g2"><label class="f"><span>Periyot (gün) *</span><input name="interval_days" type="number" min="1" value="90" required></label>
    <label class="f"><span>İlk bakım tarihi</span><input name="first_due" type="date" value="${today()}"></label></div>
    <label class="f"><span>Not</span><input name="note"></label>`, async b => {
    const r = await api("/api/maintenance", {method: "POST", body: {...b, asset_ids: ids}}); toast(`${r.created} plan oluşturuldu`); route();
  });
}
function disposeModal(ids) {
  modal(`Hurdaya ayırma (terkin) — ${ids.length} cihaz`, `<label class="f"><span>Gerekçe *</span><textarea name="reason" rows="2" required placeholder="ör. Anakart arızalı, onarımı ekonomik değil"></textarea></label>
    <b class="small">Komisyon üyeleri</b>${[1, 2, 3].map(i => `<div class="grid g2"><input name="n${i}" placeholder="Ad soyad"><input name="t${i}" placeholder="Unvan / görev" value="${i === 1 ? "Başkan" : "Üye"}"></div>`).join("")}
    <p class="small err">Cihazlar "hurda" durumuna alınıp arşivlenir.</p>`, async b => {
    const commission = [1, 2, 3].map(i => ({name: b["n" + i], title: b["t" + i]})).filter(x => x.name);
    const r = await api("/api/disposals", {method: "POST", body: {asset_ids: ids, reason: b.reason, commission}});
    toast("Tutanak: " + r.doc_no); window.open("/print/hurda/" + r.doc_no, "_blank"); S.sel.clear(); route();
  }, "Hurdaya ayır");
}
function ticketModal(asset) {
  meta().then(m => modal("Arıza kaydı aç", `${asset ? `<p>Cihaz: <b>${esc(asset.asset_code)}</b></p>` : `<label class="f"><span>Cihaz barkodu (isteğe bağlı)</span><input name="code"></label>`}
    <div class="grid g2"><label class="f"><span>Kategori</span><select name="category">${(m.ticket_categories || []).map(c => `<option>${esc(c)}</option>`).join("")}</select></label>
    <label class="f"><span>Öncelik</span><select name="priority">${m.ticket_priorities.map(p => `<option ${p === "normal" ? "selected" : ""}>${p}</option>`).join("")}</select></label></div>
    <label class="f"><span>Açıklama *</span><textarea name="description" rows="3" required minlength="5"></textarea></label>
    <div class="grid g2"><label class="f"><span>Bildiren</span><input name="reporter_name" value="${esc(S.state.user.full_name || "")}"></label><label class="f"><span>İletişim</span><input name="reporter_contact"></label></div>`,
    async b => {
      let asset_id = asset?.id;
      if (!asset_id && b.code) asset_id = (await api("/api/assets/by-code/" + encodeURIComponent(b.code))).id;
      const t = await api("/api/tickets", {method: "POST", body: {...b, asset_id}}); toast("Arıza #" + t.id + " açıldı"); go("/ticket/" + t.id);
    }));
}
function detailPro(a) {
  const acts = [];
  if (a.remote_url) acts.push(`<a class="btn p" href="${esc(a.remote_url)}">🖥 Uzak bağlan</a>`);
  if (can("ticket.create")) acts.push(`<button class="btn" data-d="t">⚠ Arıza kaydı</button>`);
  if (can("assign")) acts.push(`<button class="btn" data-d="z">✍ ${a.assignment ? "Devret" : "Zimmetle"}</button>`);
  if (can("assign") && a.assignment) acts.push(`<button class="btn" data-d="i">↩ İade al</button>`);
  if (can("maint")) acts.push(`<button class="btn" data-d="m">🔧 Bakım planı</button>`);
  const isPrinter = /yaz[ıi]c[ıi]/i.test((a.data.hardware_info || "") + (a.data.category || ""));
  if (can("network") && isPrinter && a.data.ip_address) acts.push(`<button class="btn" data-d="p">🖨 SNMP sorgula</button>`);
  if (can("asset.write")) acts.push(`<button class="btn ${a.critical ? "d" : ""}" data-d="c">${a.critical ? "★ Kritik (kaldır)" : "☆ Kritik işaretle"}</button>`);
  $("#dacts").innerHTML = acts.join("");
  $$("[data-d]").forEach(b => b.onclick = () => ({t: () => ticketModal(a), z: () => assignModal([a.id]), i: () => returnModal([a.id]), m: () => maintModal([a.id]),
    c: async () => { await api(`/api/assets/${a.id}/critical`, {method: "POST", body: {critical: !a.critical}}); route(); },
    p: async () => { try { toast("Sorgulanıyor…"); await api(`/api/assets/${a.id}/printer-poll`, {method: "POST"}); toast("Güncellendi"); route(); } catch (e) { fail(e); } }})[b.dataset.d]());
  const sec = [];
  if (a.alerts && a.alerts.length) sec.push(`<div class="card" style="border-color:var(--bad)"><h2>Açık alarmlar</h2><ul class="tl">${a.alerts.map(x => `<li>${esc(x.severity)}: ${esc(x.message)} <span class="small muted">${fmtDate(x.at)}</span></li>`).join("")}</ul></div>`);
  if (a.service_point) sec.push(`<div class="card"><h2>Hizmet noktası</h2><p><a href="#/servicepoints?open=${a.service_point.id}"><b>${esc(a.service_point.name)}</b></a> <span class="small muted">${esc(a.service_point.location || "")}</span></p></div>`);
  if (a.printer_reading) { const pr = a.printer_reading; sec.push(`<div class="card"><h2>Yazıcı durumu <span class="small muted">${fmtDate(pr.at)}</span></h2><p>Durum: <b>${esc(pr.status || "")}</b>${pr.pages != null ? ` · Sayaç: <b>${pr.pages}</b> sayfa` : ""}${(pr.errors || []).length ? ` · <span class="err">${pr.errors.map(esc).join(", ")}</span>` : ""}</p>
    ${(pr.supplies || []).length ? `<div>${pr.supplies.map(s => `<div style="margin-bottom:6px"><div class="row small"><span>${esc(s.name)}</span><span class="sp"></span><b>${s.pct >= 0 ? "%" + s.pct : (s.pct === -3 ? "biraz" : "?")}</b></div>${s.pct >= 0 ? `<div class="bar"><i style="width:${s.pct}%;background:${s.pct <= 10 ? "var(--bad)" : s.pct <= 25 ? "var(--warn)" : "var(--pri)"}"></i></div>` : ""}</div>`).join("")}</div>` : ""}</div>`); }
  if (a.spare_history && a.spare_history.length) sec.push(`<div class="card"><h2>Yedek hareketleri</h2><ul class="tl">${a.spare_history.map(l => `<li>${fmtDate(l.out_at)} → ${esc(l.to_unit || "")} ${esc(l.to_person || "")}${l.replacing_code ? " (yerine " + esc(l.replacing_code) + ")" : ""} ${l.back_at ? `<span class="small muted">· iade ${fmtDate(l.back_at)}</span>` : '<span class="pill aktif">sahada</span>'}</li>`).join("")}</ul></div>`);
  if (a.assignment) sec.push(`<div class="card"><h2>Zimmet</h2><p><b>${esc(a.assignment.holder_name)}</b> ${esc(a.assignment.holder_title || "")} ${a.assignment.holder_unit ? "— " + esc(a.assignment.holder_unit) : ""}<br>
    <span class="small muted">${fmtDate(a.assignment.started_at)} · <a href="/print/zimmet/${esc(a.assignment.doc_no)}" target="_blank">${esc(a.assignment.doc_no)}</a></span></p>
    ${a.assignments.length > 1 ? `<details><summary class="small">Zimmet geçmişi (${a.assignments.length})</summary><ul class="tl">${a.assignments.map(z => `<li>${esc(z.holder_name)} <span class="small muted">${fmtDate(z.started_at)} → ${fmtDate(z.ended_at) || "…"}</span></li>`).join("")}</ul></details>` : ""}</div>`);
  if (a.tickets.length) sec.push(`<div class="card"><h2>Arıza kayıtları</h2><ul class="tl">${a.tickets.map(t => `<li><a href="#/ticket/${t.id}">#${t.id}</a> ${statusPill(t.status)} ${esc(t.category || "")}<div class="small muted">${fmtDate(t.created_at)} · ${esc(t.description.slice(0, 90))}</div></li>`).join("")}</ul></div>`);
  if (a.maintenance.length) sec.push(`<div class="card"><h2>Bakım planları</h2><ul class="tl">${a.maintenance.map(m => `<li><b>${esc(m.title)}</b> <span class="small muted">her ${m.interval_days} gün</span><div class="small ${m.next_due < today() ? "err" : ""}">Sonraki: ${m.next_due}${m.last_done ? " · son: " + m.last_done : ""}</div></li>`).join("")}</ul></div>`);
  if (a.kb.length) sec.push(`<div class="card"><h2>Bilgi bankası önerileri</h2><ul class="tl">${a.kb.map(k => `<li><a href="#/kb/${k.id}">${esc(k.title)}</a></li>`).join("")}</ul></div>`);
  if (a.consumables.length) sec.push(`<div class="card"><h2>Uyumlu sarf malzemeleri</h2><ul class="tl">${a.consumables.map(c => `<li><a href="#/stock/${c.id}">${esc(c.name)}</a> <span class="${c.low ? "err" : "muted"} small">stok ${c.stock} ${esc(c.unit)}</span></li>`).join("")}</ul></div>`);
  if (a.network.length) sec.push(`<div class="card"><h2>Ağda görülme</h2><table><tr><th>MAC</th><th>IP</th><th>Ad</th><th>Switch / port</th><th>Son</th></tr>${a.network.map(n => `<tr><td class="mono small">${n.mac}</td><td>${esc(n.ip || "")}</td><td class="small">${esc(n.hostname || "")}</td><td class="small">${esc(n.switch || "")} ${esc(n.port || "")}${n.vlan ? " · VLAN " + esc(n.vlan) : ""}</td><td class="small">${fmtDate(n.last_seen)}</td></tr>`).join("")}</table></div>`);
  $("#dx").innerHTML = sec.join("");
}
async function dashPro(el) {
  const s = await api("/api/summary").catch(() => null);
  if (!s || !el) return;
  const tile = (href, n, l, col, ok) => `<a class="card stat" href="#${href}"><div class="i" style="background:${col}22;color:${col}">${n}</div><div class="l">${l}</div></a>`;
  el.innerHTML = `<div class="grid g4">
    ${can("alerts.read") ? tile("/alerts", s.alerts_open, "Açık alarm", s.alerts_open ? "#d93636" : "#13a05a") : ""}
    ${can("discovery") && s.pending ? tile("/pending", s.pending, "Onay bekleyen cihaz", "#e6930a") : ""}
    ${can("ticket.read") ? tile("/tickets", s.tickets_open, `Açık arıza${s.tickets_new ? ` <b class="err">(${s.tickets_new} yeni)</b>` : ""}`, s.tickets_open ? "#d93636" : "#13a05a") : ""}
    ${tile("/maint", s.maint_overdue + s.warranty_soon, `Gecikmiş bakım ${s.maint_overdue} · garanti biten ${s.warranty_soon}`, s.maint_overdue ? "#e6930a" : "#13a05a")}
    ${can("stock.read") ? tile("/stock", s.low_stock, "Kritik sarf stoku", s.low_stock ? "#e6930a" : "#13a05a") : ""}
    ${tile("/spares", s.spares, "Havuzdaki yedek", "#1463ff")}
    ${tile("/assign", s.assigned, `Zimmetli cihaz · açık sayım ${s.counts_open}`, "#1463ff")}</div>`;
}

/* ---------- arıza kayıtları ---------- */
PRO["/tickets"] = async (v, p) => {
  p = {status: "open", q: "", ...p};
  const [r, m] = await Promise.all([api("/api/tickets?" + qs(p)), meta()]);
  const setp = o => go("/tickets?" + qs({...p, ...o}));
  v.innerHTML = `<div class="row"><h1>Arıza Kayıtları</h1><span class="sp"></span>${can("ticket.create") ? `<button class="btn p" id="nt">＋ Yeni kayıt</button>` : ""}</div>
    <div class="card"><div class="row" style="margin-bottom:10px"><select id="ts" style="max-width:180px"><option value="open">Açık olanlar</option><option value="">Tümü</option>${m.ticket_statuses.map(s => `<option ${p.status === s ? "selected" : ""}>${s}</option>`).join("")}</select>
      <input id="tq" placeholder="Ara (açıklama, barkod, bildiren, #no)" value="${esc(p.q)}" style="max-width:320px">${m.staff.length ? `<select id="ta" style="max-width:160px"><option value="">Herkes</option>${m.staff.map(x => `<option ${p.assigned === x ? "selected" : ""}>${esc(x)}</option>`).join("")}</select>` : ""}<span class="sp"></span><span class="muted">${r.total} kayıt</span></div>
    <div class="tw"><table><thead><tr><th>#</th><th>Tarih</th><th>Cihaz</th><th>Birim</th><th>Kategori</th><th>Açıklama</th><th>Bildiren</th><th>Durum</th><th>Atanan</th></tr></thead><tbody>
    ${r.items.map(t => `<tr class="cl" data-id="${t.id}"><td><b>${t.id}</b></td><td class="small">${fmtDate(t.created_at)}</td><td>${esc(t.asset_code || "—")}</td><td class="small">${esc(t.location || t.reporter_unit || "")}</td>
      <td class="small">${esc(t.category || "")}</td><td>${esc(t.description.slice(0, 80))} ${prioPill(t.priority)}</td><td class="small">${esc(t.reporter_name || "")}${t.source === "qr" ? ' <span class="pill">QR</span>' : ""}</td><td>${statusPill(t.status)}</td><td class="small">${esc(t.assigned_to || "")}</td></tr>`).join("") || `<tr><td colspan=9 class=muted>Kayıt yok</td></tr>`}</tbody></table></div></div>`;
  $("#ts").value = p.status; $("#ts").onchange = e => setp({status: e.target.value});
  $("#tq").onchange = e => setp({q: e.target.value});
  if ($("#ta")) $("#ta").onchange = e => setp({assigned: e.target.value});
  if ($("#nt")) $("#nt").onclick = () => ticketModal(null);
  $$("tr.cl").forEach(r => r.onclick = () => go("/ticket/" + r.dataset.id));
};
PRO["/ticket/:id"] = async (v, id) => {
  const [t, m] = await Promise.all([api("/api/tickets/" + id), meta()]);
  const mg = can("ticket.manage");
  v.innerHTML = `<div class="row"><h1>Arıza #${t.id} ${statusPill(t.status)} ${prioPill(t.priority)}</h1><span class="sp"></span><a class="btn" href="#/tickets">‹ Liste</a></div>
    <div class="grid g2"><div class="card"><dl class="kv"><dt>Cihaz</dt><dd>${t.asset ? `<a href="#/asset/${t.asset.id}">${esc(t.asset.asset_code)}</a> ${esc(t.asset.data.brand_model || "")} — ${esc(t.asset.data.location_name || "")}` : "—"}</dd>
      <dt>Kategori</dt><dd>${esc(t.category || "—")}</dd><dt>Açıklama</dt><dd style="white-space:pre-wrap">${esc(t.description)}</dd>
      <dt>Bildiren</dt><dd>${esc(t.reporter_name || "")} ${esc(t.reporter_contact || "")} ${t.reporter_unit ? "· " + esc(t.reporter_unit) : ""} <span class="small muted">(${t.source === "qr" ? "QR ile" : "panelden"})</span></dd>
      <dt>Açılış</dt><dd>${fmtDate(t.created_at)}</dd>${t.resolved_at ? `<dt>Çözüm tarihi</dt><dd>${fmtDate(t.resolved_at)}</dd>` : ""}
      <dt>Takip no</dt><dd class="mono">${esc(t.public_code || "")} · <a href="/t/${esc(t.public_code || "")}" target="_blank">bildiren sayfası</a></dd>
      ${t.kb_id ? `<dt>Bilgi bankası</dt><dd><a href="#/kb/${t.kb_id}">Kayıt #${t.kb_id}</a></dd>` : ""}</dl></div>
    <div>${mg ? `<form class="card" id="tf"><h2>İşlem</h2><div class="grid g3">
      <label class="f"><span>Durum</span><select name="status">${m.ticket_statuses.map(s => `<option ${t.status === s ? "selected" : ""}>${s}</option>`).join("")}</select></label>
      <label class="f"><span>Atanan</span><select name="assigned_to"><option value="">—</option>${m.staff.map(x => `<option ${t.assigned_to === x ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></label>
      <label class="f"><span>Öncelik</span><select name="priority">${m.ticket_priorities.map(x => `<option ${t.priority === x ? "selected" : ""}>${x}</option>`).join("")}</select></label></div>
      <label class="f"><span>Çözüm açıklaması</span><textarea name="resolution" rows="3">${esc(t.resolution || "")}</textarea></label>
      <label class="row small"><input type="checkbox" name="save_kb" ${t.kb_id ? "disabled" : ""}> Çözümü bilgi bankasına kaydet (aynı modeldeki cihazlarda önerilir)</label>
      <div class="row" style="margin-top:10px"><button class="btn p">Kaydet</button><button type="button" class="btn" id="solve">✓ Çözüldü olarak kapat</button></div></form>` : ""}
    <div class="card"><h2>Notlar</h2><form id="nf" class="row" style="margin-bottom:10px"><input name="note" placeholder="Not ekle…" required style="flex:1"><button class="btn">Ekle</button></form>
      <ul class="tl">${t.notes.slice().reverse().map(n => `<li>${esc(n.note)}<div class="small muted">${fmtDate(n.at)} · ${esc(n.user || "")}</div></li>`).join("") || "<li class=muted>Not yok</li>"}</ul></div></div></div>`;
  const save = async extra => {
    const b = Object.fromEntries(new FormData($("#tf"))); b.save_kb = !!b.save_kb;
    await api("/api/tickets/" + id, {method: "PATCH", body: {...b, ...extra}}); toast("Kaydedildi"); route(); refreshBadges();
  };
  if ($("#tf")) { $("#tf").onsubmit = e => { e.preventDefault(); save({}).catch(fail); }; $("#solve").onclick = () => save({status: "çözüldü"}).catch(fail); }
  $("#nf").onsubmit = async e => { e.preventDefault(); try { await api(`/api/tickets/${id}/notes`, {method: "POST", body: Object.fromEntries(new FormData(e.target))}); route(); } catch (err) { fail(err); } };
};

/* ---------- sayım ---------- */
PRO["/counts"] = async v => {
  const list = await api("/api/counts");
  v.innerHTML = `<div class="row"><h1>Envanter Sayımı</h1><span class="sp"></span><button class="btn p" id="nc">＋ Yeni sayım</button></div>
    <div class="card small muted">Sayım açıkken personel cihazdaki QR'ı telefon kamerasıyla okutup açılan sayfada <b>“Sayıma ekle”</b>ye basar ya da sayım ekranında barkod okuyucu / kamera ile art arda okutur. Bağlantı koparsa okutmalar telefonda biriktirilir, bağlantı gelince gönderilir.</div>
    <div class="grid g3">${list.map(c => `<a class="card" href="#/count/${c.id}"><div class="row"><b>${esc(c.name)}</b><span class="sp"></span><span class="pill ${c.status === "açık" ? "aktif" : "depoda"}">${esc(c.status)}</span></div>
      <div class="small muted">${esc(c.location || "Tüm birimler")} · ${fmtDate(c.created_at)} · ${esc(c.created_by || "")}</div>
      <div class="bar" style="margin:10px 0 6px"><i style="width:${c.progress}%"></i></div><div class="small">${c.seen_expected}/${c.expected} sayıldı · <span class="err">${c.missing} eksik</span> · ${c.foreign} başka birimden · ${c.unknown} tanınmayan</div></a>`).join("") || `<div class="card muted">Henüz sayım yok.</div>`}</div>`;
  $("#nc").onclick = async () => modal("Yeni sayım", `<label class="f"><span>Sayım adı</span><input name="name" value="Sayım ${today()}"></label>
    <label class="f"><span>Birim (boş = tüm envanter)</span><select name="location"><option value="">Tüm birimler</option>${await locOptions()}</select></label>`,
    async b => { const c = await api("/api/counts", {method: "POST", body: b}); go("/count/" + c.id); }, "Başlat");
};
PRO["/count/:id"] = async (v, id, p) => {
  const d = await api("/api/counts/" + id);
  const QK = "nx_count_q_" + id;
  const queue = () => { try { return JSON.parse(localStorage.getItem(QK) || "[]"); } catch (_) { return []; } };
  const setQ = q => { try { localStorage.setItem(QK, JSON.stringify(q)); } catch (_) {} };
  const tab = p.tab || "missing";
  const rows = (items, extra) => items.map(x => `<tr><td><a href="#/asset/${x.id}">${esc(x.asset_code)}</a></td><td>${esc(x.hardware_info || "")}</td><td>${esc(x.brand_model || "")}</td><td>${esc(x.location || "")}</td>${extra ? `<td class="small">${fmtDate(x.seen_at)} · ${esc(x.seen_by || "")}</td>` : ""}</tr>`).join("");
  const open = d.status === "açık";
  v.innerHTML = `<div class="row"><h1>${esc(d.name)} <span class="pill ${open ? "aktif" : "depoda"}">${esc(d.status)}</span></h1><span class="sp"></span>
      <a class="btn" href="/api/counts/${id}/report.xlsx">⇩ Excel</a><a class="btn" href="/print/sayim/${id}" target="_blank">⎙ Tutanak</a>${open ? `<button class="btn d" id="cl">Sayımı kapat</button>` : ""}</div>
    <div class="grid g4"><div class="card stat"><div><div class="n">${d.seen_expected}/${d.expected}</div><div class="l">Sayıldı · %${d.progress}</div></div></div>
      <div class="card stat"><div><div class="n err">${d.missing}</div><div class="l">Bulunamayan</div></div></div>
      <div class="card stat"><div><div class="n">${d.foreign}</div><div class="l">Başka birimden</div></div></div><div class="card stat"><div><div class="n">${d.unknown}</div><div class="l">Tanınmayan kod</div></div></div></div>
    ${open ? `<div class="card"><h2>Okut</h2><form id="sf" class="row"><input id="code" placeholder="Barkod okutun veya QR bağlantısı yapıştırın, Enter" autocomplete="off" style="flex:1;font-size:18px;padding:14px">
      <button class="btn p">Ekle</button>${"BarcodeDetector" in window && window.isSecureContext ? `<button type="button" class="btn" id="cam">📷 Kamera</button>` : ""}</form>
      <video id="vid" playsinline hidden style="width:100%;max-width:420px;margin-top:10px;border-radius:10px"></video><div id="last" style="margin-top:10px"></div>
      <div id="qinfo" class="small muted"></div>${!window.isSecureContext ? `<p class="small muted">Tarayıcı kamerası yalnızca HTTPS'te çalışır; telefonun kendi kamera uygulamasıyla QR'ı okutup açılan sayfada “Sayıma ekle”ye basabilirsiniz.</p>` : ""}</div>` : ""}
    <div class="card"><div class="steps">${[["missing", `Bulunamayan (${d.missing})`], ["foreign", `Başka birimden (${d.foreign})`], ["seen", `Sayılan (${d.seen})`], ["unknown", `Tanınmayan (${d.unknown})`]].map(([k, l]) => `<a href="#/count/${id}?tab=${k}"><span class="${tab === k ? "on" : ""}">${l}</span></a>`).join("")}</div>
    <div class="tw"><table><thead><tr><th>Barkod</th><th>Donanım</th><th>Marka Model</th><th>Kayıtlı birim</th>${tab === "missing" ? "" : "<th>Görülme</th>"}</tr></thead><tbody>
    ${tab === "missing" ? rows(d.missing_items) : tab === "foreign" ? rows(d.foreign_items, 1) : tab === "seen" ? rows(d.seen_items, 1)
      : d.unknown_items.map(x => `<tr><td class="mono">${esc(x.code)}</td><td colspan=3></td><td class="small">${fmtDate(x.seen_at)} · ${esc(x.seen_by || "")}</td></tr>`).join("")}</tbody></table></div></div>`;
  if (!open) return;
  const show = (r, code) => {
    const ok = r.result === "ok", cls = ok ? "ok" : r.result === "already" ? "depoda" : r.result === "queued" ? "bakımda" : "hurda";
    S.lastScan = {id, html: `<div class="pill ${cls}" style="font-size:15px;padding:8px 14px">${esc(r.asset ? r.asset.asset_code : code)} — ${esc(r.message)}</div>`};
    beep(ok || r.result === "queued");
    if (r.result === "queued" || r.result === "error") $("#last").innerHTML = S.lastScan.html; else route();
  };
  const flush = async () => {
    const q = queue(); $("#qinfo").textContent = q.length ? `${q.length} okutma bağlantı bekliyor…` : "";
    if (!q.length) return;
    try { await api(`/api/counts/${id}/scan-batch`, {method: "POST", body: {items: q}}); setQ([]); toast(`${q.length} bekleyen okutma gönderildi`); route(); } catch (_) {}
  };
  const submit = async code => {
    code = code.trim(); if (!code) return;
    try { show(await api(`/api/counts/${id}/scan`, {method: "POST", body: {code}}), code); }
    catch (e) {
      if (e instanceof TypeError || /Failed to fetch|NetworkError/i.test(e.message)) {
        const q = queue(); q.push({code, at: new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 19)}); setQ(q);
        show({result: "queued", message: "Çevrimdışı: kuyruğa alındı"}, code); $("#qinfo").textContent = `${q.length} okutma bağlantı bekliyor…`;
      } else { show({result: "error", message: e.message}, code); }
    }
  };
  $("#sf").onsubmit = e => { e.preventDefault(); const c = $("#code").value; $("#code").value = ""; submit(c); $("#code").focus(); };
  $("#code").focus();
  if (S.lastScan?.id === id) $("#last").innerHTML = S.lastScan.html;
  flush(); clearInterval(S.qt); S.qt = setInterval(() => { if (location.hash.startsWith("#/count/" + id)) flush(); else clearInterval(S.qt); }, 15000);
  if ($("#cam")) $("#cam").onclick = async () => {
    const vid = $("#vid"); vid.hidden = false;
    const st = await navigator.mediaDevices.getUserMedia({video: {facingMode: "environment"}}); vid.srcObject = st; await vid.play();
    const det = new BarcodeDetector({formats: ["qr_code", "code_128", "ean_13", "code_39"]}); let lastCode = "", lastAt = 0;
    const tick = async () => {
      if (!location.hash.startsWith("#/count/" + id)) { st.getTracks().forEach(t => t.stop()); return; }
      try { const r = await det.detect(vid); if (r[0] && (r[0].rawValue !== lastCode || Date.now() - lastAt > 3000)) { lastCode = r[0].rawValue; lastAt = Date.now(); await submit(lastCode); } } catch (_) {}
      requestAnimationFrame(tick);
    };
    tick();
  };
  $("#cl").onclick = () => modal("Sayımı kapat", `<p>Bulunamayan: <b>${d.missing}</b>, başka birimden: <b>${d.foreign}</b>.</p>
    ${d.location && can("count.manage") ? `<label class="row"><input type="checkbox" name="move_foreign"> Başka birimden bulunan ${d.foreign} cihazın kayıtlı birimini “${esc(d.location)}” olarak güncelle</label>` : ""}
    <p class="small muted">Sayılan cihazların geçmişine “sayımda görüldü” kaydı düşülür. Kapatılan sayıma okutma eklenemez.</p>`,
    async b => { const r = await api(`/api/counts/${id}/close`, {method: "POST", body: {move_foreign: !!b.move_foreign}}); toast(`Sayım kapatıldı${r.moved ? `, ${r.moved} cihazın yeri güncellendi` : ""}`); route(); }, "Kapat");
};

/* ---------- zimmet ---------- */
PRO["/assign"] = async (v, p) => {
  p = {q: "", active: "1", ...p};
  const r = await api("/api/assignments?" + qs(p));
  v.innerHTML = `<div class="row"><h1>Zimmet</h1><span class="sp"></span>${can("assign") ? `<button class="btn" id="off">⎋ Personel ayrılışı</button><button class="btn p" id="na">＋ Yeni zimmet</button><button class="btn" id="ni">↩ İade al</button>` : ""}</div>
    <div class="card"><div class="row" style="margin-bottom:10px"><input id="aq" placeholder="Kişi, birim, barkod, belge no" value="${esc(p.q)}" style="max-width:300px">
      <select id="aa" style="max-width:180px"><option value="1">Aktif zimmetler</option><option value="0" ${p.active === "0" ? "selected" : ""}>Tüm geçmiş</option></select><span class="sp"></span><span class="muted">${r.total} kayıt</span></div>
    <div class="tw"><table><thead><tr><th>Belge</th><th>Barkod</th><th>Cihaz</th><th>Zimmet alan</th><th>Birim</th><th>Başlangıç</th><th>Bitiş</th><th></th></tr></thead><tbody>
    ${r.items.map(z => `<tr><td><a href="/print/zimmet/${esc(z.doc_no)}" target="_blank">${esc(z.doc_no)}</a></td><td><a href="#/asset/${z.asset_id}">${esc(z.asset_code)}</a></td><td class="small">${esc(z.brand_model || "")}</td>
      <td><b>${esc(z.holder_name)}</b> <span class="small muted">${esc(z.holder_title || "")}</span></td><td class="small">${esc(z.holder_unit || "")}</td><td class="small">${fmtDate(z.started_at)}</td>
      <td class="small">${z.ended_at ? fmtDate(z.ended_at) + ` · <a href="/print/zimmet/${esc(z.return_doc_no)}" target="_blank">${esc(z.return_doc_no)}</a>` : ""}</td>
      <td>${!z.ended_at && can("assign") ? `<button class="btn s" data-r="${z.asset_id}">İade</button>` : ""}</td></tr>`).join("") || "<tr><td colspan=8 class=muted>Kayıt yok</td></tr>"}</tbody></table></div></div>`;
  $("#aq").onchange = e => go("/assign?" + qs({...p, q: e.target.value}));
  $("#aa").onchange = e => go("/assign?" + qs({...p, active: e.target.value}));
  $$("[data-r]").forEach(b => b.onclick = () => returnModal([+b.dataset.r]));
  const pick = (title, then) => modal(title, `<label class="f"><span>Barkodlar (her satıra bir tane veya okuyucuyla art arda)</span><textarea name="codes" rows="5" required></textarea></label>`,
    async b => { const ids = await codesToIds(b.codes); setTimeout(() => then(ids), 50); }, "Devam");
  if ($("#na")) { $("#na").onclick = () => pick("Zimmetlenecek cihazlar", ids => assignModal(ids)); $("#ni").onclick = () => pick("İade edilecek cihazlar", ids => returnModal(ids)); }
  if ($("#off")) $("#off").onclick = async () => {
    const holders = await api("/api/holders");
    const w = modal("Personel ayrılışı / birim değişikliği", `<p class="small muted">Ayrılan personeli seçin; üstündeki tüm cihazlar tek belgeyle iade alınır (devir tutanağı çıkar).</p>
      <label class="f"><span>Personel</span><select name="h">${holders.map((h, i) => `<option value="${i}">${esc(h.holder_name)} — ${esc(h.holder_unit || "")} (${h.n} cihaz)</option>`).join("") || "<option>Aktif zimmet yok</option>"}</select></label><div id="hd"></div>`,
      null);
    const sel = $("[name=h]", w);
    const show = async () => { const h = holders[+sel.value]; if (!h) return;
      const list = await api("/api/assignments?" + qs({q: h.holder_name, active: "1", size: 200}));
      const mine = list.items.filter(x => x.holder_name === h.holder_name && !x.ended_at);
      $("#hd", w).innerHTML = `<div class="tw" style="max-height:260px"><table><thead><tr><th>Barkod</th><th>Cihaz</th><th>Belge</th></tr></thead><tbody>${mine.map(z => `<tr><td>${esc(z.asset_code)}</td><td class="small">${esc(z.brand_model || "")}</td><td class="small">${esc(z.doc_no)}</td></tr>`).join("")}</tbody></table></div>
        <button type="button" class="btn p" id="offret" style="margin-top:10px">${mine.length} cihazı iade al</button>`;
      $("#offret", w).onclick = () => { returnModal(mine.map(z => z.asset_id), () => { w.remove(); route(); }); };
    };
    if (holders.length) { sel.onchange = show; show(); }
  };
};

/* ---------- bakım & garanti ---------- */
PRO["/maint"] = async v => {
  const g = await api("/api/maintenance");
  v.innerHTML = `<h1>Bakım & Garanti</h1><div class="grid g2"><div class="card"><h2>Yaklaşan / gecikmiş bakımlar <span class="small muted">(${g.days} gün içinde)</span></h2>
    <table><thead><tr><th>Tarih</th><th>Bakım</th><th>Cihaz</th><th>Birim</th><th></th></tr></thead><tbody>${g.due.map(m => `<tr><td class="${m.overdue ? "err" : ""}"><b>${m.next_due}</b></td><td>${esc(m.title)}</td>
      <td><a href="#/asset/${m.asset_id}">${esc(m.asset_code)}</a> <span class="small muted">${esc(m.brand_model || "")}</span></td><td class="small">${esc(m.location || "")}</td>
      <td>${can("maint") ? `<button class="btn s" data-done="${m.id}">✓ Yapıldı</button>` : ""}</td></tr>`).join("") || "<tr><td colspan=5 class=muted>Yaklaşan bakım yok</td></tr>"}</tbody></table></div>
    <div class="card"><h2>Garantisi biten / bitecek <span class="small muted">(${g.warranty_days} gün)</span></h2><table><thead><tr><th>Bitiş</th><th>Cihaz</th><th>Birim</th></tr></thead><tbody>
    ${g.warranty.map(w => `<tr><td class="${w.expired ? "err" : ""}"><b>${w.warranty_end}</b></td><td><a href="#/asset/${w.id}">${esc(w.asset_code)}</a> <span class="small muted">${esc(w.brand_model || "")}</span></td><td class="small">${esc(w.location || "")}</td></tr>`).join("") || "<tr><td colspan=3 class=muted>Yok</td></tr>"}</tbody></table>
    <p class="small muted">Garanti bitiş tarihi cihaz kaydındaki “Garanti Bitiş” alanından okunur.</p></div></div>
    <div class="card"><h2>Tüm bakım planları (${g.plans.length})</h2><p class="small muted">Plan eklemek için Cihazlar listesinde cihazları seçip “Bakım planı”na basın veya cihaz sayfasını kullanın.</p>
    <div class="tw"><table><thead><tr><th>Cihaz</th><th>Bakım</th><th>Periyot</th><th>Son</th><th>Sonraki</th><th></th></tr></thead><tbody>${g.plans.map(m => `<tr><td><a href="#/asset/${m.asset_id}">${esc(m.asset_code)}</a> <span class="small muted">${esc(m.brand_model || "")}</span></td>
      <td>${esc(m.title)}</td><td>${m.interval_days} gün</td><td class="small">${m.last_done || "—"}</td><td class="small">${m.next_due}</td><td>${can("maint") ? `<button class="btn s d" data-off="${m.id}">Kaldır</button>` : ""}</td></tr>`).join("")}</tbody></table></div></div>`;
  $$("[data-done]").forEach(b => b.onclick = () => modal("Bakım yapıldı", `<label class="f"><span>Tarih</span><input type="date" name="date" value="${today()}"></label><label class="f"><span>Not</span><input name="note"></label>`,
    async x => { const r = await api(`/api/maintenance/${b.dataset.done}/done`, {method: "POST", body: x}); toast("Sonraki bakım: " + r.next_due); route(); refreshBadges(); }));
  $$("[data-off]").forEach(b => b.onclick = async () => { if (!confirm("Plan kaldırılsın mı?")) return; await api("/api/maintenance/" + b.dataset.off, {method: "PATCH", body: {active: false}}); route(); });
};

/* ---------- sarf stok ---------- */
const stockForm = (x = {}) => `<div class="grid g2"><label class="f"><span>Malzeme adı *</span><input name="name" value="${esc(x.name || "")}" required></label><label class="f"><span>Kod</span><input name="code" value="${esc(x.code || "")}"></label>
  <label class="f"><span>Birim</span><input name="unit" value="${esc(x.unit || "adet")}"></label><label class="f"><span>En az stok</span><input name="min_stock" type="number" step="any" value="${x.min_stock ?? 1}"></label>
  ${x.id ? "" : `<label class="f"><span>Açılış stoku</span><input name="stock" type="number" step="any" value="0"></label>`}<label class="f"><span>Depo yeri</span><input name="location" value="${esc(x.location || "")}"></label></div>
  <label class="f"><span>Uyumlu modeller (virgülle; cihaz marka-modelinde geçen kelimeler)</span><input name="compatible" value="${esc(x.compatible || "")}" placeholder="M428, M404"></label>
  <label class="f"><span>Not</span><input name="note" value="${esc(x.note || "")}"></label>`;
function moveModal(c, sign) {
  modal(`${sign > 0 ? "Stok girişi" : "Stok çıkışı"} — ${esc(c.name)}`, `<label class="f"><span>Miktar (${esc(c.unit)})</span><input name="qty" type="number" step="any" min="0.01" value="1" required></label>
    ${sign < 0 ? `<label class="f"><span>Takılan cihaz barkodu (isteğe bağlı)</span><input name="asset_code"></label>` : ""}<label class="f"><span>Not</span><input name="note"></label>`,
    async b => { await api(`/api/stock/${c.id}/move`, {method: "POST", body: {...b, qty: sign * Math.abs(+b.qty)}}); toast("Kaydedildi"); route(); refreshBadges(); });
}
PRO["/stock"] = async (v, p) => {
  const list = await api("/api/stock?" + qs({q: p.q || "", low: p.low || ""}));
  v.innerHTML = `<div class="row"><h1>Sarf Stok</h1><span class="sp"></span>${can("stock") ? `<button class="btn p" id="ns">＋ Malzeme</button>` : ""}</div><div class="card">
    <div class="row" style="margin-bottom:10px"><input id="sq" placeholder="Ara" value="${esc(p.q || "")}" style="max-width:260px"><label class="row small"><input type="checkbox" id="sl" ${p.low ? "checked" : ""}> Yalnızca kritik</label></div>
    <table><thead><tr><th>Malzeme</th><th>Kod</th><th>Uyumlu</th><th>Depo</th><th>Stok</th><th>En az</th><th></th></tr></thead><tbody>${list.map(c => `<tr><td><a href="#/stock/${c.id}"><b>${esc(c.name)}</b></a></td><td class="small">${esc(c.code || "")}</td>
      <td class="small">${esc(c.compatible || "")}</td><td class="small">${esc(c.location || "")}</td><td class="${c.low ? "err" : ""}"><b>${c.stock}</b> ${esc(c.unit)}</td><td class="small">${c.min_stock}</td>
      <td>${can("stock") ? `<button class="btn s" data-in="${c.id}">＋ Giriş</button> <button class="btn s" data-out="${c.id}">− Çıkış</button>` : ""}</td></tr>`).join("") || "<tr><td colspan=7 class=muted>Malzeme yok</td></tr>"}</tbody></table></div>`;
  $("#sq").onchange = e => go("/stock?" + qs({...p, q: e.target.value}));
  $("#sl").onchange = e => go("/stock?" + qs({...p, low: e.target.checked ? 1 : ""}));
  if ($("#ns")) $("#ns").onclick = () => modal("Yeni malzeme", stockForm(), async b => { await api("/api/stock", {method: "POST", body: b}); route(); });
  const byId = Object.fromEntries(list.map(c => [c.id, c]));
  $$("[data-in]").forEach(b => b.onclick = () => moveModal(byId[b.dataset.in], 1));
  $$("[data-out]").forEach(b => b.onclick = () => moveModal(byId[b.dataset.out], -1));
};
PRO["/stock/:id"] = async (v, id) => {
  const c = await api("/api/stock/" + id);
  v.innerHTML = `<div class="row"><h1>${esc(c.name)}</h1><span class="sp"></span>${can("stock") ? `<button class="btn" id="in">＋ Giriş</button><button class="btn" id="out">− Çıkış</button><button class="btn" id="ed">✎ Düzenle</button>` : ""}<a class="btn" href="#/stock">‹ Liste</a></div>
    <div class="card"><p class="${c.low ? "err" : ""}" style="font-size:20px"><b>${c.stock}</b> ${esc(c.unit)} <span class="small muted">(en az ${c.min_stock})</span></p><p class="small muted">${esc(c.compatible || "")} · ${esc(c.location || "")}</p>
    <table><thead><tr><th>Tarih</th><th>Miktar</th><th>Cihaz</th><th>Kullanıcı</th><th>Not</th></tr></thead><tbody>${c.moves.map(m => `<tr><td class="small">${fmtDate(m.at)}</td><td class="${m.qty < 0 ? "err" : "res-eklendi"}"><b>${m.qty > 0 ? "+" : ""}${m.qty}</b></td>
      <td>${m.asset_id ? `<a href="#/asset/${m.asset_id}">${esc(m.asset_code)}</a>` : ""}</td><td class="small">${esc(m.user || "")}</td><td class="small">${esc(m.note || "")}</td></tr>`).join("")}</tbody></table></div>`;
  if ($("#in")) { $("#in").onclick = () => moveModal(c, 1); $("#out").onclick = () => moveModal(c, -1);
    $("#ed").onclick = () => modal("Malzemeyi düzenle", stockForm(c) + `<label class="row small"><input type="checkbox" name="passive"> Pasife al (listeden kaldır)</label>`,
      async b => { if (b.passive) b.active = false; delete b.passive; await api("/api/stock/" + id, {method: "PATCH", body: b}); route(); }); }
};

/* ---------- bilgi bankası ---------- */
const kbForm = (x = {}) => `<label class="f"><span>Başlık *</span><input name="title" value="${esc(x.title || "")}" required></label>
  <label class="f"><span>İçerik * (sorun, belirti, çözüm adımları)</span><textarea name="body" rows="10" required>${esc(x.body || "")}</textarea></label>
  <div class="grid g2"><label class="f"><span>İlgili model/donanım anahtar kelimeleri (virgülle)</span><input name="match" value="${esc(x.match || "")}" placeholder="M428, Esprimo"></label>
  <label class="f"><span>Etiketler</span><input name="tags" value="${esc(x.tags || "")}"></label></div>
  <label class="row"><input type="checkbox" name="public" ${x.public ? "checked" : ""}> Herkese açık — QR sayfasında "Sık karşılaşılan sorunlar" olarak kullanıcıya göster</label>`;
PRO["/kb"] = async (v, p) => {
  const list = await api("/api/kb?" + qs({q: p.q || ""}));
  v.innerHTML = `<div class="row"><h1>Bilgi Bankası</h1><span class="sp"></span>${can("kb.write") ? `<button class="btn p" id="nk">＋ Yeni kayıt</button>` : ""}</div>
    <div class="card"><input id="kq" placeholder="Ara (model, belirti, çözüm…)" value="${esc(p.q || "")}" style="max-width:360px;margin-bottom:10px">
    <ul class="tl">${list.map(k => `<li><a href="#/kb/${k.id}"><b>${esc(k.title)}</b></a> <span class="small muted">${esc(k.match || "")} ${k.tags ? "· " + esc(k.tags) : ""}</span><div class="small muted">${fmtDate(k.updated_at)} · ${esc(k.updated_by || "")} · ${k.views} görüntülenme</div></li>`).join("") || "<li class=muted>Kayıt yok. Arıza çözerken “bilgi bankasına kaydet” ile de eklenir.</li>"}</ul></div>`;
  $("#kq").onchange = e => go("/kb?" + qs({q: e.target.value}));
  if ($("#nk")) $("#nk").onclick = () => modal("Yeni bilgi bankası kaydı", kbForm(), async b => { b.public = !!b.public; const k = await api("/api/kb", {method: "POST", body: b}); go("/kb/" + k.id); });
};
PRO["/kb/:id"] = async (v, id) => {
  const k = await api("/api/kb/" + id);
  v.innerHTML = `<div class="row"><h1>${esc(k.title)}</h1><span class="sp"></span>${can("kb.write") ? `<button class="btn" id="ke">✎ Düzenle</button><button class="btn d" id="kd">Sil</button>` : ""}<a class="btn" href="#/kb">‹ Liste</a></div>
    <div class="card"><div style="white-space:pre-wrap;font-size:15px">${esc(k.body)}</div><p class="small muted" style="margin-top:14px">Modeller: ${esc(k.match || "—")} · ${esc(k.tags || "")} ${k.public ? "· <b>herkese açık (QR)</b>" : ""} · ${fmtDate(k.updated_at)} ${esc(k.updated_by || "")}</p></div>`;
  if ($("#ke")) { $("#ke").onclick = () => modal("Düzenle", kbForm(k), async b => { b.public = !!b.public; await api("/api/kb/" + id, {method: "PATCH", body: b}); route(); });
    $("#kd").onclick = async () => { if (confirm("Silinsin mi?")) { await api("/api/kb/" + id, {method: "DELETE"}); go("/kb"); } }; }
};

/* ---------- ağ & ajan ---------- */
PRO["/network"] = async (v, p) => {
  const tab = p.tab || "hosts";
  const [n, st] = await Promise.all([api("/api/network"), api("/api/settings")]);
  const ag = tab === "agent" ? await api("/api/agent/reports") : [];
  const s = n.state, lr = s.last_result || {};
  const cmd = `powershell -NoProfile -ExecutionPolicy Bypass -Command "irm '${S.state.base_url}/agent.ps1?t=${st.agent_token || ""}' | iex"`;
  v.innerHTML = `<div class="row"><h1>Ağ & Ajan</h1><span class="sp"></span><button class="btn p" id="scan" ${s.running ? "disabled" : ""}>${s.running ? "Taranıyor… " + esc(s.progress) : "⟳ Şimdi tara"}</button></div>
    <div class="grid g4"><div class="card stat"><div><div class="n">${n.seen_7d}</div><div class="l">Son 7 günde görülen MAC</div></div></div><div class="card stat"><div><div class="n">${n.matched}</div><div class="l">Envanterle eşleşen</div></div></div>
      <div class="card stat"><div><div class="n err">${n.unknown.length}</div><div class="l">Envanterde olmayan</div></div></div><div class="card stat"><div><div class="n">${n.stale.length}</div><div class="l">${n.stale_days} gündür görülmeyen</div></div></div></div>
    <p class="small muted">Son tarama: ${fmtDate(s.last_run) || "—"} ${lr.seconds ? `· ${lr.seconds} sn · ${lr.alive ?? 0} yanıt veren adres · ${lr.macs ?? 0} MAC` : ""} ${(lr.errors || []).length ? `<span class="err">· Hatalar: ${esc(lr.errors.join(" | "))}</span>` : ""}</p>
    <div class="grid g2"><form class="card" id="nc"><h2>Tarama ayarları</h2><label class="f"><span>Taranacak bloklar — her satıra bir; isteğe bağlı ad verilebilir. Örnek: <span class="mono">Acil: 10.20.1.0/24</span> · <span class="mono">Poliklinik: 10.20.5.10-10.20.5.200</span> · <span class="mono">10.30.0.0/22</span> · <span class="mono">10.40.1.7</span> (toplam en fazla 16.384 adres)</span><textarea name="subnets" rows="5">${esc((n.config.subnets || []).join("\n"))}</textarea></label>
      <div class="grid g2"><label class="f"><span>Otomatik tarama (saat, 0 = kapalı)</span><input name="interval_hours" type="number" step="0.5" min="0" value="${n.config.interval_hours || 0}"></label>
      <label class="f"><span>“Görülmüyor” eşiği (gün)</span><input name="stale_days" type="number" min="1" value="${n.stale_days}"></label></div><button class="btn">Kaydet</button>
      <p class="small muted">Her blok, sunucunun kendi ağı olmasa da taranır: ping'e yanıt vermeyen cihazlar yaygın portlar (445, 3389, 80, 443, 22, 9100…) denenerek bulunur; Windows cihazlardan NetBIOS ile ad ve MAC alınır. Farklı VLAN'lardaki diğer cihazların MAC/port bilgisi için switch/yönlendiricileri SNMP ile ekleyin. Sunucuyla bloklar arasında güvenlik duvarı ICMP/portları engelliyorsa o cihazlar görünmez.</p></form>
    <div class="card"><h2>SNMP cihazları (switch / yönlendirici)</h2><table><tr><th>Ad</th><th>Adres</th><th>Son okuma</th><th></th></tr>${n.switches.map(w => `<tr><td>${esc(w.name || "")}</td><td class="mono">${esc(w.host)}</td>
      <td class="small ${w.last_error ? "err" : ""}">${fmtDate(w.last_poll) || "—"} ${esc(w.last_error || "")}</td><td><button class="btn s d" data-del="${w.id}">Sil</button></td></tr>`).join("")}</table>
      <form id="sw" class="row" style="margin-top:10px"><input name="name" placeholder="Ad" style="width:120px"><input name="host" placeholder="IP adresi" required style="width:140px"><input name="community" placeholder="community (public)" style="width:160px"><button class="btn">Ekle</button></form>
      <p class="small muted">Salt-okuma SNMP v2c. Okunanlar: BRIDGE-MIB/Q-BRIDGE MAC tablosu, port adları, ARP tablosu. En az MAC barındıran port cihazın bağlı olduğu port kabul edilir (uplink'ler elenir).</p></div></div>
    ${n.blocks.length ? `<div class="card"><h2>Bloklar</h2><table><tr><th>Blok</th><th>Hedef</th><th>Adres</th><th>Bulunan</th><th>Envanterle eşleşen</th><th>Eşleşmeyen</th></tr>${n.blocks.map(b => `<tr><td><a href="#/network?tab=hosts&block=${encodeURIComponent(b.name)}"><b>${esc(b.name)}</b></a></td><td class="mono small">${esc(b.target || "")}</td><td>${b.size ?? ""}</td><td>${b.alive}</td><td>${b.matched}</td><td class="${b.alive - b.matched ? "err" : ""}">${b.alive - b.matched}</td></tr>`).join("")}</table></div>` : ""}
    <div class="card"><div class="steps">${[["hosts", `Bulunan cihazlar (${n.hosts.length})`], ["unknown", `MAC: envanterde olmayan (${n.unknown.length})`], ["stale", `Görülmeyen (${n.stale.length})`], ["agent", "PC ajanı"]].map(([k, l]) => `<a href="#/network?tab=${k}"><span class="${tab === k ? "on" : ""}">${l}</span></a>`).join("")}</div>
    ${tab === "hosts" ? (() => { const hs = n.hosts.filter(h => (!p.block || h.block === p.block) && (!p.unk || !h.asset));
      return `<div class="row" style="margin-bottom:8px"><select id="hb" style="max-width:240px"><option value="">Tüm bloklar</option>${n.blocks.map(b => `<option ${p.block === b.name ? "selected" : ""}>${esc(b.name)}</option>`).join("")}</select>
        <label class="row small"><input type="checkbox" id="hu" ${p.unk ? "checked" : ""}> Yalnızca envanterde olmayanlar</label><span class="sp"></span><span class="muted small">${hs.length} cihaz</span></div>
      <div class="tw"><table><thead><tr><th>IP</th><th>Ad</th><th>MAC</th><th>Tahmin</th><th>Açık portlar</th><th>Blok</th><th>Son görülme</th><th>Envanter</th></tr></thead><tbody>${hs.map(h => `<tr><td class="mono">${esc(h.ip)}</td>
        <td class="small">${esc(h.netbios || h.hostname || "")}</td><td class="mono small">${esc(h.mac || "")}</td><td class="small">${esc(h.kind)}</td><td class="small mono">${esc(h.ports || "")}</td><td class="small">${esc(h.block || "")}</td><td class="small">${fmtDate(h.last_seen)}</td>
        <td>${h.asset ? `<a href="#/asset/${h.asset.id}">${esc(h.asset.asset_code)}</a>` : can("asset.write") ? `<a class="btn s" href="#/new?${qs({mac_address: h.mac || "", ip_address: h.ip, hostname: h.netbios || (h.hostname || "").split(".")[0], hardware_info: h.kind === "Yazıcı" ? "Yazıcı" : ""})}">Envantere ekle</a>` : ""}</td></tr>`).join("") || "<tr><td colspan=8 class=muted>Henüz cihaz bulunmadı. Blok ekleyip “Şimdi tara”ya basın.</td></tr>"}</tbody></table></div>`; })()
    : tab === "unknown" ? `<div class="tw"><table><thead><tr><th>MAC</th><th>IP</th><th>Ad</th><th>Switch / port</th><th>İlk / son görülme</th><th></th></tr></thead><tbody>${n.unknown.map(x => `<tr><td class="mono small">${x.mac}</td><td>${esc(x.ip || "")}</td><td class="small">${esc(x.hostname || "")}</td>
      <td class="small">${esc(x.switch || "")} ${esc(x.port || "")}${x.vlan ? " · VLAN " + esc(x.vlan) : ""}</td><td class="small">${fmtDate(x.first_seen)} / ${fmtDate(x.last_seen)}</td>
      <td>${can("asset.write") ? `<a class="btn s" href="#/new?${qs({mac_address: x.mac, ip_address: x.ip || "", hostname: (x.hostname || "").split(".")[0]})}">Envantere ekle</a>` : ""}</td></tr>`).join("") || "<tr><td colspan=6 class=muted>Yok</td></tr>"}</tbody></table></div>`
    : tab === "stale" ? `<div class="tw"><table><thead><tr><th>Barkod</th><th>Cihaz</th><th>MAC</th><th>Son görülme</th></tr></thead><tbody>${n.stale.map(x => `<tr><td><a href="#/asset/${x.id}">${esc(x.asset_code)}</a></td><td class="small">${esc(x.brand_model || "")}</td><td class="mono small">${x.mac}</td><td class="small">${fmtDate(x.last_seen) || "hiç"}</td></tr>`).join("") || "<tr><td colspan=4 class=muted>Yok</td></tr>"}</tbody></table></div>`
    : `<h3>Kurulum</h3><p class="small">Bilgisayarlarda aşağıdaki komut donanım bilgisini (seri no, model, işlemci, RAM, disk, MAC, IP, oturum açan kullanıcı) gönderir. Grup İlkesi (GPO) ile “Zamanlanmış görev — oturum açılışında ve günlük” olarak dağıtın.</p>
      <pre class="mono small code">${esc(cmd)}</pre><button class="btn s" id="cp">Kopyala</button>
      <p class="small muted">Eşleştirme sırası: seri no → MAC → bilgisayar adı. Elle girilmiş marka-model / seri no korunur, yalnızca boşsa doldurulur.</p>
      <h3>Bildirimler (${ag.length})</h3><div class="tw"><table><thead><tr><th>Bilgisayar</th><th>Seri no</th><th>Model</th><th>Kullanıcı</th><th>IP</th><th>Son bildirim</th><th>Envanter</th></tr></thead><tbody>
      ${ag.map(r => `<tr><td><b>${esc(r.hostname)}</b></td><td class="small mono">${esc(r.serial || "")}</td><td class="small">${esc((r.data.manufacturer || "") + " " + (r.data.model || ""))}<br><span class="muted">${esc(r.data.cpu || "")} · ${esc(r.data.ram_gb || "")} GB</span></td>
        <td class="small">${esc(r.data.user || "")}</td><td class="small">${esc((r.data.ips || []).join(", "))}</td><td class="small">${fmtDate(r.at)}</td>
        <td>${r.asset_id ? `<a href="#/asset/${r.asset_id}">${esc(r.asset_code)}</a>` : `<button class="btn s" data-link="${esc(r.hostname)}">Eşle / ekle</button>`}</td></tr>`).join("") || "<tr><td colspan=7 class=muted>Henüz bildirim yok</td></tr>"}</tbody></table></div>`}</div>`;
  if ($("#hb")) { $("#hb").onchange = e => go("/network?" + qs({tab: "hosts", block: e.target.value, unk: p.unk || ""})); $("#hu").onchange = e => go("/network?" + qs({tab: "hosts", block: p.block || "", unk: e.target.checked ? 1 : ""})); }
  $("#scan").onclick = async () => { try { await api("/api/network/scan", {method: "POST"}); toast("Tarama başladı"); setTimeout(function poll() { if (location.hash.startsWith("#/network")) api("/api/network").then(x => x.state.running ? setTimeout(poll, 3000) : route()); }, 2000); route(); } catch (e) { fail(e); } };
  $("#nc").onsubmit = async e => { e.preventDefault(); const b = Object.fromEntries(new FormData(e.target)); b.subnets = b.subnets.split("\n").map(x => x.trim()).filter(Boolean);
    try { await api("/api/network/config", {method: "PUT", body: b}); toast("Kaydedildi"); } catch (err) { fail(err); } };
  $("#sw").onsubmit = async e => { e.preventDefault(); try { await api("/api/network/switches", {method: "POST", body: Object.fromEntries(new FormData(e.target))}); route(); } catch (err) { fail(err); } };
  $$("[data-del]").forEach(b => b.onclick = async () => { if (confirm("Silinsin mi?")) { await api("/api/network/switches/" + b.dataset.del, {method: "DELETE"}); route(); } });
  if ($("#cp")) $("#cp").onclick = () => navigator.clipboard?.writeText(cmd).then(() => toast("Kopyalandı"));
  $$("[data-link]").forEach(b => b.onclick = () => modal("Ajan bildirimini eşle: " + b.dataset.link, `<label class="f"><span>Mevcut kaydın barkodu</span><input name="code"></label><p class="small muted">— ya da —</p>
    <label class="f"><span>Yeni kayıt oluştur: barkod</span><input name="new_code"></label>`, async x => {
      const asset_id = x.code ? (await api("/api/assets/by-code/" + encodeURIComponent(x.code))).id : null;
      const a = await api("/api/agent/link", {method: "POST", body: {hostname: b.dataset.link, asset_id, new_code: x.new_code}}); toast("Eşlendi: " + a.asset_code); route(); }, "Eşle"));
};

/* ---------- raporlar ---------- */
PRO["/reports"] = async v => {
  const [r, ds] = await Promise.all([api("/api/reports/renewal"), api("/api/disposals")]);
  v.innerHTML = `<h1>Raporlar</h1><div class="grid g3">
    <div class="card"><h2>Denetim paketi</h2><p class="small muted">Tüm envanter, taşınır listesi, zimmetler, hurda tutanakları, dönem içi değişiklikler, denetim kaydı, sayımlar ve arızalar — tek ZIP.</p>
      <div class="row"><input type="date" id="ps" value="${ago(365)}" style="width:auto"><input type="date" id="pe" value="${today()}" style="width:auto"><button class="btn p" id="pk">⇩ ZIP</button></div></div>
    <div class="card"><h2>Taşınır listesi</h2><p class="small muted">Taşınır kodu, sicil no, edinme tarihi/bedeli ile Excel. Kurumunuzun taşınır/MKYS sistemine aktarmadan önce sütun biçimini kontrol edin.</p><a class="btn" href="/api/reports/tasinir.xlsx">⇩ Excel</a></div>
    <div class="card"><h2>Yenileme / yatırım gerekçesi</h2><p class="small muted">Eşik: ${r.thresholds.age_years} yaş veya 12 ayda ${r.thresholds.tickets_12m} arıza (Ayarlar'dan değişir). Yaş “Edinme Tarihi” alanından hesaplanır.</p><a class="btn" href="/api/reports/renewal.xlsx">⇩ Excel</a></div></div>
    <div class="card"><div class="row"><h2 style="margin:0">Yazıcı baskı ve maliyet raporu</h2><span class="sp"></span><a class="btn s" href="/api/reports/printing.xlsx">⇩ Excel</a></div><div id="pr"></div></div>
    <div class="card"><h2>Birimlere göre durum</h2><div class="tw"><table><thead><tr><th>Birim</th><th>Cihaz</th><th>Ort. yaş</th><th>12 ay arıza</th><th>Cihaz başı arıza</th><th>Arızalı/serviste</th><th>Yenileme adayı</th></tr></thead><tbody>
      ${r.units.map(u => `<tr><td><b>${esc(u.location)}</b></td><td>${u.count}</td><td>${u.avg_age ?? "—"} <span class="small muted">${u.age_known < u.count ? `(${u.age_known} cihazda)` : ""}</span></td><td>${u.tickets}</td><td>${u.tickets_per_device}</td><td>${u.faulty}</td><td class="${u.candidates ? "err" : ""}"><b>${u.candidates}</b></td></tr>`).join("")}</tbody></table></div></div>
    <div class="card"><h2>Yenileme adayları (${r.candidates.length})</h2><div class="tw" style="max-height:420px"><table><thead><tr><th>Barkod</th><th>Birim</th><th>Cihaz</th><th>Yaş</th><th>Arıza</th><th>Gerekçe</th></tr></thead><tbody>
      ${r.candidates.map(c => `<tr><td><a href="#/asset/${c.id}">${esc(c.asset_code)}</a></td><td class="small">${esc(c.location)}</td><td class="small">${esc(c.hardware_info || "")} ${esc(c.brand_model || "")}</td><td>${c.age ?? "—"}</td><td>${c.tickets}</td><td class="small">${esc(c.reasons)}</td></tr>`).join("") || "<tr><td colspan=6 class=muted>Aday yok</td></tr>"}</tbody></table></div></div>
    <div class="card"><h2>Hurda / terkin tutanakları</h2><p class="small muted">Yeni tutanak: Cihazlar listesinde seçip “Hurdaya ayır”.</p><table><tr><th>Belge</th><th>Tarih</th><th>Gerekçe</th><th>Adet</th></tr>${ds.map(d => `<tr><td><a href="/print/hurda/${esc(d.doc_no)}" target="_blank">${esc(d.doc_no)}</a></td><td class="small">${fmtDate(d.at)}</td><td class="small">${esc(d.reason)}</td><td>${JSON.parse(d.asset_ids).length}</td></tr>`).join("")}</table></div>`;
  $("#pk").onclick = () => download("/api/reports/audit-pack.zip?" + qs({start: $("#ps").value, end: $("#pe").value}));
  api("/api/reports/printing").then(pr => {
    $("#pr").innerHTML = pr.printers.length ? `<p class="small muted">Sayfa başı maliyet: <b>${pr.cost_per_page} TL</b> (Ayarlar). Sayaçlar yazıcı SNMP sorgusuyla güncellenir.</p>
      <div class="grid g2"><div><h3>En çok basan birimler</h3><table><tr><th>Birim</th><th>Sayfa</th><th>Maliyet</th></tr>${pr.top_units.map(u => `<tr><td>${esc(u.location)}</td><td>${u.pages.toLocaleString("tr-TR")}</td><td>${u.cost.toLocaleString("tr-TR")} TL</td></tr>`).join("")}</table></div>
      <div><h3>Yazıcılar</h3><div class="tw" style="max-height:240px"><table><tr><th>Barkod</th><th>Birim</th><th>Sayfa</th><th>Maliyet</th></tr>${pr.printers.map(x => `<tr><td><a href="#/asset/${x.id}">${esc(x.asset_code)}</a></td><td class="small">${esc(x.location)}</td><td>${x.pages.toLocaleString("tr-TR")}</td><td>${x.cost.toLocaleString("tr-TR")} TL</td></tr>`).join("")}</table></div></div></div>
      <p style="margin-top:8px"><b>Toplam: ${pr.total_pages.toLocaleString("tr-TR")} sayfa · ${pr.total_cost.toLocaleString("tr-TR")} TL</b></p>`
      : `<p class="muted small">Henüz yazıcı sayaç verisi yok. Yazıcı cihaz sayfasında “SNMP sorgula” ya da Ağ&Ajan → yazıcıları sorgula ile veri toplanır. En az iki okuma arasındaki fark raporlanır.</p>`;
  }).catch(() => {});
};

/* ---------- kurumlar ---------- */
PRO["/federation"] = async v => {
  const list = await api("/api/federation");
  v.innerHTML = `<div class="row"><h1>Kurumlar Paneli</h1><span class="sp"></span><button class="btn p" id="pl">⟳ Özetleri getir</button></div>
    <div class="card small muted">Diğer hastanelerdeki NexEnvanter sunucularını ekleyin. Her kurumda <b>Ayarlar → API anahtarları</b>'ndan “Denetçi” rolünde bir anahtar oluşturup buraya girin; bağlantı salt okumadır.</div>
    <div class="card" id="fr"><p class="muted">Özetleri görmek için “Özetleri getir”e basın.</p></div>
    <div class="card"><h2>Bağlı kurumlar</h2><table><tr><th>Ad</th><th>Adres</th><th>Son başarılı</th><th>Hata</th><th></th></tr>${list.map(r => `<tr><td><b>${esc(r.name)}</b></td><td class="mono small">${esc(r.url)}</td><td class="small">${fmtDate(r.last_ok) || "—"}</td><td class="small err">${esc(r.last_error || "")}</td><td><button class="btn s d" data-del="${r.id}">Sil</button></td></tr>`).join("")}</table>
    <form id="fa" class="row" style="margin-top:10px"><input name="name" placeholder="Kurum adı" required style="width:180px"><input name="url" placeholder="http://10.20.0.5:8750" required style="width:220px"><input name="token" placeholder="API anahtarı (nxt_…)" required style="flex:1"><button class="btn">Ekle</button></form></div>`;
  $("#fa").onsubmit = async e => { e.preventDefault(); try { await api("/api/federation", {method: "POST", body: Object.fromEntries(new FormData(e.target))}); route(); } catch (err) { fail(err); } };
  $$("[data-del]").forEach(b => b.onclick = async () => { if (confirm("Silinsin mi?")) { await api("/api/federation/" + b.dataset.del, {method: "DELETE"}); route(); } });
  $("#pl").onclick = async () => {
    $("#fr").innerHTML = `<p class="muted">Sorgulanıyor…</p>`;
    const res = await api("/api/federation/poll");
    const ok = res.filter(x => x.ok), sum = k => ok.reduce((a, x) => a + (x.summary[k] || 0), 0);
    $("#fr").innerHTML = `<div class="tw"><table><thead><tr><th>Kurum</th><th>Cihaz</th><th>Açık arıza</th><th>Gecikmiş bakım</th><th>Garanti biten</th><th>Kritik stok</th><th>Zimmetli</th><th>Sürüm</th></tr></thead><tbody>
      ${res.map(x => x.ok ? `<tr><td><b>${esc(x.name)}</b>${x.local ? ' <span class="pill">bu sunucu</span>' : ""}</td><td>${x.summary.assets}</td><td>${x.summary.tickets_open}</td><td>${x.summary.maint_overdue}</td><td>${x.summary.warranty_soon}</td><td>${x.summary.low_stock}</td><td>${x.summary.assigned}</td><td class="small">${esc(x.summary.version)}</td></tr>`
        : `<tr><td><b>${esc(x.name)}</b></td><td colspan=7 class="err small">Ulaşılamadı: ${esc(x.error)}</td></tr>`).join("")}
      <tr style="font-weight:700"><td>Toplam (${ok.length} kurum)</td><td>${sum("assets")}</td><td>${sum("tickets_open")}</td><td>${sum("maint_overdue")}</td><td>${sum("warranty_soon")}</td><td>${sum("low_stock")}</td><td>${sum("assigned")}</td><td></td></tr></tbody></table></div>`;
  };
};

/* ---------- ileri ayarlar ---------- */
async function settingsPro(el, s) {
  if (!el || !can("settings")) return;
  const [tl, toks, tls] = await Promise.all([api("/api/license"), api("/api/tokens"), api("/api/tls")]);
  const L = s.ldap || {}, R = S.state.roles;
  el.innerHTML = `<div class="grid g2"><div>
    <form class="card" id="ps"><h2>Operasyon</h2>
      <label class="row"><input type="checkbox" name="public_tickets" ${s.public_tickets ? "checked" : ""}> QR sayfasından oturumsuz arıza bildirimi açık</label>
      <label class="f" style="margin-top:10px"><span>Arıza kategorileri (her satıra bir)</span><textarea name="ticket_categories" rows="4">${esc((s.ticket_categories || []).join("\n"))}</textarea></label>
      <div class="grid g2"><label class="f"><span>Bakım uyarısı (gün önce)</span><input name="maintenance_warn_days" type="number" min="0" value="${s.maintenance_warn_days}"></label>
      <label class="f"><span>Garanti uyarısı (gün önce)</span><input name="warranty_warn_days" type="number" min="0" value="${s.warranty_warn_days}"></label>
      <label class="f"><span>Yenileme eşiği: yaş (yıl)</span><input name="age_years" type="number" step="0.5" value="${(s.renewal || {}).age_years ?? 5}"></label>
      <label class="f"><span>Yenileme eşiği: 12 ayda arıza</span><input name="tickets_12m" type="number" value="${(s.renewal || {}).tickets_12m ?? 3}"></label></div>
      <label class="f"><span>Uzak bağlantı şablonu — cihaz sayfasında “Uzak bağlan” düğmesi (ör. <span class="mono">nexdesk://connect/{nexdesk_id}</span>; {alan_anahtarı} yer tutucuları)</span><input name="remote_url_template" value="${esc(s.remote_url_template || "")}"></label>
      <label class="row"><input type="checkbox" name="discovery_approval" ${s.discovery_approval ? "checked" : ""}> Tarama/ajan yeni cihazı doğrudan değil onay kuyruğuna düşürsün</label>
      <div class="grid g4" style="margin-top:10px"><label class="f"><span>Çevrimdışı alarmı (gün)</span><input name="offline_alert_days" type="number" min="1" value="${s.offline_alert_days ?? 3}"></label>
        <label class="f"><span>Toner alarm eşiği (%)</span><input name="toner_alert_pct" type="number" min="0" max="100" value="${s.toner_alert_pct ?? 10}"></label>
        <label class="f"><span>Sayfa başı maliyet (TL)</span><input name="cost_per_page" type="number" step="0.01" min="0" value="${s.cost_per_page ?? 0}"></label>
        <label class="f"><span>Yazıcı otomatik sorgu (saat, 0=kapalı)</span><input name="printer_poll_hours" type="number" step="0.5" min="0" value="${s.printer_poll_hours ?? 0}"></label></div>
      <label class="f"><span>Varsayılan SNMP community</span><input name="default_community" value="${esc(s.default_community || "public")}" style="max-width:220px"></label>
      <button class="btn p">Kaydet</button></form>
    <form class="card" id="ld"><h2>Active Directory girişi</h2>
      <label class="row"><input type="checkbox" name="enabled" ${L.enabled ? "checked" : ""}> Etkin (yerel hesaplar çalışmaya devam eder)</label>
      <div class="grid g2" style="margin-top:10px"><label class="f"><span>Sunucu</span><input name="server" value="${esc(L.server || "")}" placeholder="ldap://dc01.hastane.local"></label><label class="f"><span>Etki alanı</span><input name="domain" value="${esc(L.domain || "")}" placeholder="hastane.local"></label></div>
      <label class="f"><span>Arama kökü (Base DN)</span><input name="base_dn" value="${esc(L.base_dn || "")}" placeholder="DC=hastane,DC=local"></label>
      <label class="row small"><input type="checkbox" name="use_ssl" ${L.use_ssl ? "checked" : ""}> LDAPS (636)</label>
      <label class="f" style="margin-top:10px"><span>Grup → rol eşlemesi (her satır: <span class="mono">grup adı = rol</span>; roller: ${Object.keys(R).join(", ")})</span>
        <textarea name="role_map" rows="4" placeholder="NexEnvanter-BIM = operator&#10;NexEnvanter-Yonetici = admin">${esc((L.role_map || []).map(m => `${m.group} = ${m.role}${(m.units || []).length ? " : " + m.units.join(", ") : ""}`).join("\n"))}</textarea></label>
      <div class="grid g2"><label class="row small"><input type="checkbox" name="allow_unmapped" ${L.allow_unmapped ? "checked" : ""}> Eşlenmeyen kullanıcılar da girebilsin</label>
        <label class="f"><span>Onların rolü</span><select name="default_role">${Object.entries(R).map(([k, l]) => `<option value="${k}" ${L.default_role === k ? "selected" : ""}>${l}</option>`).join("")}</select></label></div>
      <div class="row"><button class="btn p">Kaydet</button><span class="sp"></span><input id="lu" placeholder="test kullanıcı" style="width:130px"><input id="lp" type="password" placeholder="parola" style="width:110px"><button type="button" class="btn" id="lt">Dene</button></div><div id="lr" class="small"></div></form></div>
    <div><div class="card"><h2>Lisans</h2><dl class="kv"><dt>Sürüm türü</dt><dd>${esc(tl.edition)}</dd><dt>Lisans sahibi</dt><dd>${esc(tl.licensee || "—")}</dd><dt>Bitiş</dt><dd>${esc(tl.expires || "süresiz")}</dd>
      <dt>Sınırlar</dt><dd>${tl.limits.assets ?? "sınırsız"} cihaz · ${tl.limits.users ?? "sınırsız"} kullanıcı</dd><dt>Makine kimliği</dt><dd class="mono">${esc(tl.machine_id)}</dd></dl>
      ${tl.error ? `<p class="err small">${esc(tl.error)}</p>` : ""}${tl.can_install ? `<form id="li"><textarea name="text" rows="2" placeholder="Lisans metnini yapıştırın"></textarea><button class="btn" style="margin-top:6px">Lisansı yükle</button></form>` : `<p class="small muted">Bu derleme lisans gerektirmez.</p>`}</div>
    <div class="card"><h2>HTTPS</h2><p class="small">${tls.enabled ? "<b>Etkin</b>" : "Kapalı"} ${tls.available ? `· sertifika: ${esc(tls.subject || "")} · bitiş ${esc(tls.not_after || "")} ${tls.self_signed ? "(kendinden imzalı)" : ""}` : "· sertifika yok"}</p>
      <p class="small muted">HTTPS, telefonda tarayıcı kamerasıyla sayımı ve güvenli oturumu sağlar. Kurum sertifikanız varsa <span class="mono">${esc(s.data_dir || "")}\\tls\\cert.pem</span> ve <span class="mono">key.pem</span> olarak koyun. Kendinden imzalı sertifikada telefonlar bir kez uyarı gösterir. Değişiklik program yeniden başlatılınca geçerli olur; QR temel adresini https:// ile güncelleyin.</p>
      <div class="row"><input id="th" placeholder="Ek ad (ör. envanter.hastane.local)" style="flex:1"><button class="btn" id="tg">Sertifika oluştur</button>
      ${tls.available ? `<button class="btn ${tls.enabled ? "d" : "p"}" id="tt">${tls.enabled ? "HTTPS'i kapat" : "HTTPS'i aç"}</button>` : ""}</div></div>
    <div class="card"><h2>API anahtarları</h2><p class="small muted">Kurumlar paneli ve diğer sistemlerle (HBYS vb.) entegrasyon için. Anahtar yalnızca oluşturulurken bir kez gösterilir.</p>
      <table><tr><th>Ad</th><th>Rol</th><th>Son kullanım</th><th></th></tr>${toks.map(t => `<tr><td>${esc(t.name)}</td><td class="small">${esc(R[t.role] || t.role)}</td><td class="small">${fmtDate(t.last_used) || "—"}</td><td>${t.active ? `<button class="btn s d" data-rv="${t.id}">İptal</button>` : '<span class="muted small">iptal</span>'}</td></tr>`).join("")}</table>
      <form id="tk" class="row" style="margin-top:8px"><input name="name" placeholder="Anahtar adı" required style="flex:1"><select name="role" style="width:170px">${Object.entries(R).map(([k, l]) => `<option value="${k}" ${k === "auditor" ? "selected" : ""}>${l}</option>`).join("")}</select><button class="btn">Oluştur</button></form><div id="tko"></div></div>
    <div class="card"><h2>PC ajanı anahtarı</h2><p class="small mono" style="word-break:break-all">${esc(s.agent_token || "")}</p><button class="btn s" id="ar">Yenile</button> <span class="small muted">Yenilerseniz GPO komutunu güncelleyin.</span></div></div></div>`;
  // Kartları Ayarlar sekmelerine dağıt (simetrik sütun düzeni)
  const TAB = {"Operasyon": "operasyon", "Active Directory girişi": "entegrasyon", "API anahtarları": "entegrasyon",
    "PC ajanı anahtarı": "entegrasyon", "Lisans": "sistem", "HTTPS": "sistem"};
  const cols = $("#scols");
  if (cols) { $$(".card", el).forEach(c => { c.dataset.tab = TAB[($("h2", c)?.firstChild?.textContent || "").trim()] || "sistem"; cols.append(c); });
    let t = "genel"; try { t = sessionStorage.getItem("nx_stab") || "genel"; } catch (_) {} S.showSettingsTab && S.showSettingsTab(t); }
  $("#ps").onsubmit = async e => { e.preventDefault(); const b = Object.fromEntries(new FormData(e.target));
    const body = {public_tickets: !!b.public_tickets, ticket_categories: b.ticket_categories.split("\n").map(x => x.trim()).filter(Boolean), remote_url_template: b.remote_url_template.trim(),
      maintenance_warn_days: +b.maintenance_warn_days, warranty_warn_days: +b.warranty_warn_days, renewal: {age_years: +b.age_years, tickets_12m: +b.tickets_12m},
      discovery_approval: !!b.discovery_approval, offline_alert_days: +b.offline_alert_days, toner_alert_pct: +b.toner_alert_pct,
      cost_per_page: +b.cost_per_page, printer_poll_hours: +b.printer_poll_hours, default_community: b.default_community.trim() || "public"};
    try { await api("/api/settings", {method: "PUT", body}); M.meta = null; toast("Kaydedildi"); } catch (err) { fail(err); } };
  $("#ld").onsubmit = async e => { e.preventDefault(); const b = Object.fromEntries(new FormData(e.target));
    const role_map = b.role_map.split("\n").map(l => l.trim()).filter(Boolean).map(l => { const [g, rest] = l.split("="); const [r, u] = (rest || "").split(":");
      return {group: (g || "").trim(), role: (r || "").trim(), units: (u || "").split(",").map(x => x.trim()).filter(Boolean)}; });
    const ldap = {enabled: !!b.enabled, server: b.server.trim(), domain: b.domain.trim(), base_dn: b.base_dn.trim(), use_ssl: !!b.use_ssl, role_map, allow_unmapped: !!b.allow_unmapped, default_role: b.default_role};
    try { await api("/api/settings", {method: "PUT", body: {ldap}}); toast("Kaydedildi"); } catch (err) { fail(err); } };
  $("#lt").onclick = async () => { try { const r = await api("/api/ldap/test", {method: "POST", body: {username: $("#lu").value, password: $("#lp").value}});
    $("#lr").innerHTML = r.ok ? `<span class="res-eklendi">Bağlandı: ${esc(r.info.full_name)} → rol: <b>${esc(r.role_name || "giriş izni yok")}</b></span><br><span class="muted">Gruplar: ${esc(r.info.groups.join(" | "))}</span>` : `<span class="err">${esc(r.message)}</span>`; } catch (e) { fail(e); } };
  if ($("#li")) $("#li").onsubmit = async e => { e.preventDefault(); try { await api("/api/license", {method: "POST", body: Object.fromEntries(new FormData(e.target))}); toast("Lisans yüklendi"); route(); } catch (err) { fail(err); } };
  $("#tg").onclick = async () => { try { const r = await api("/api/tls/selfsigned", {method: "POST", body: {hostnames: [$("#th").value]}}); toast(r.message); route(); } catch (e) { fail(e); } };
  if ($("#tt")) $("#tt").onclick = async () => { try { const r = await api("/api/tls", {method: "PUT", body: {enabled: !tls.enabled}}); toast(r.message); route(); } catch (e) { fail(e); } };
  $("#tk").onsubmit = async e => { e.preventDefault(); try { const t = await api("/api/tokens", {method: "POST", body: Object.fromEntries(new FormData(e.target))});
    $("#tko").innerHTML = `<p class="small">Anahtar (bir daha gösterilmeyecek):</p><pre class="mono small code">${esc(t.token)}</pre>`; } catch (err) { fail(err); } };
  $$("[data-rv]").forEach(b => b.onclick = async () => { if (confirm("Anahtar iptal edilsin mi?")) { await api("/api/tokens/" + b.dataset.rv, {method: "DELETE"}); route(); } });
  $("#ar").onclick = async () => { if (confirm("Ajan anahtarı yenilensin mi? Eski komut çalışmaz.")) { await api("/api/agent/token/rotate", {method: "POST"}); route(); } };
}

boot().catch(e => { document.body.innerHTML = `<p style="padding:20px">Sunucuya bağlanılamadı: ${esc(e.message)}</p>`; });
