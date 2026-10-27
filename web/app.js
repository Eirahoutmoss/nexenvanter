"use strict";
/* NexEnvanter web arayüzü — derleme adımı gerektirmeyen tek dosya SPA */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const S = {state: null, fields: [], sel: new Set()};

async function api(path, {method = "GET", body, form, blob} = {}) {
  const opt = {method, headers: {"x-nx": "1"}};
  if (form) opt.body = form;
  else if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
  const r = await fetch(path, opt);
  if (r.status === 401 && !path.includes("/login")) { S.state.user = null; go("/login"); throw new Error("Oturum açın"); }
  if (!r.ok) {
    let e = {message: r.statusText};
    try { e = (await r.json()).error || e; } catch (_) {}
    const err = new Error(e.message); err.data = e; throw err;
  }
  if (blob) return r.blob();
  return (r.headers.get("content-type") || "").includes("json") ? r.json() : r.text();
}
function toast(msg, isErr) {
  const d = document.createElement("div"); d.textContent = msg; if (isErr) d.className = "e";
  $("#toast").append(d); setTimeout(() => d.remove(), isErr ? 6000 : 3000);
}
const fail = e => toast(e.message || String(e), true);
const can = p => S.state?.perms?.includes(p);
const go = (p) => { location.hash = "#" + p; };
const fv = (a, f) => f.system ? a[f.key] : (a.data || {})[f.key];
const fmtDate = s => s ? s.replace("T", " ").slice(0, 16) : "";
const pill = st => `<span class="pill ${esc(st)}">${esc(st)}</span>`;
const qs = o => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== "" && v != null)).toString();
function download(url) { const a = document.createElement("a"); a.href = url; a.click(); }

/* ---------------- yerleşim ---------------- */
const NAV = [
  ["/", "⌂", "Ana Sayfa", "asset.read"], ["/assets", "▤", "Cihazlar", "asset.read"], ["/new", "＋", "Yeni Cihaz", "asset.write"],
  ["/import", "⇪", "Excel İşlemleri", "import"], ["/labels", "▦", "Etiket & Yazıcı", "print"], ["/fields", "☰", "Alanlar", "fields"],
  ["/users", "☺", "Kullanıcılar", "users"], ["/audit", "⌕", "Denetim Kaydı", "audit"], ["/settings", "⚙", "Ayarlar", "asset.read"],
];
function shell() {
  const u = S.state.user;
  $("#app").innerHTML = `<div class="shell"><aside class="side" id="side">
    <div class="brand"><img src="/static/logo.svg" alt=""><span>Nex<b>Envanter</b></span></div>
    <nav class="nav">${NAV.filter(n => can(n[3])).map(n => `<a href="#${n[0]}" data-p="${n[0]}"><span class="ic">${n[1]}</span>${n[2]}</a>`).join("")}</nav>
    <div class="foot">${esc(S.state.app.name)} ${esc(S.state.app.version)}<br>${esc(S.state.app.author)}</div></aside>
    <div class="main"><div class="top no-print"><button class="btn menu-btn" id="menu">☰</button>
      <input class="search" id="gsearch" placeholder="Cihaz, seri no, birim ara… (barkod okutup Enter)">
      <div class="who"><div><b>${esc(u.full_name || u.username)}</b><div class="small muted">${esc(u.role_name)}</div></div>
      <div class="avatar">${esc((u.full_name || u.username).slice(0, 2).toUpperCase())}</div>
      <button class="btn s" id="logout">Çıkış</button></div></div><div id="view"></div></div></div>`;
  $("#logout").onclick = async () => { await api("/api/logout", {method: "POST"}); S.state.user = null; go("/login"); };
  $("#menu").onclick = () => $("#side").classList.toggle("open");
  $("#gsearch").onkeydown = async e => {
    if (e.key !== "Enter") return;
    const v = e.target.value.trim(); if (!v) return;
    try { const a = await api("/api/assets/by-code/" + encodeURIComponent(v)); e.target.value = ""; go("/asset/" + a.id); }
    catch (_) { go("/assets?q=" + encodeURIComponent(v)); }
  };
}
function setActive(path) {
  $$(".nav a").forEach(a => a.classList.toggle("on", a.dataset.p === path || (a.dataset.p !== "/" && path.startsWith(a.dataset.p))));
  $("#side")?.classList.remove("open");
}

/* ---------------- yönlendirici ---------------- */
async function route() {
  const [path, query] = (location.hash.slice(1) || "/").split("?");
  const params = Object.fromEntries(new URLSearchParams(query || ""));
  if (S.state.setup_needed) return setupPage();
  if (!S.state.user) return loginPage(params.next);
  if (!$("#view")) shell();
  setActive(path);
  const v = $("#view");
  const m = path.match(/^\/asset\/(\d+)/);
  try {
    if (path === "/") await dashboard(v);
    else if (path === "/assets") await assetList(v, params);
    else if (path === "/new") await assetForm(v, null);
    else if (m) await assetDetail(v, +m[1], params.edit);
    else if (path === "/import") await importPage(v);
    else if (path === "/labels") await labelsPage(v, params);
    else if (path === "/fields") await fieldsPage(v);
    else if (path === "/users") await usersPage(v);
    else if (path === "/audit") await auditPage(v, params);
    else if (path === "/settings") await settingsPage(v);
    else if (path === "/login") go(params.next || "/");
    else v.innerHTML = `<div class="card">Sayfa bulunamadı.</div>`;
  } catch (e) { if (e.message !== "Oturum açın") v.innerHTML = `<div class="card err">${esc(e.message)}</div>`; }
}
async function boot() {
  S.state = await api("/api/state");
  if (S.state.user) S.fields = await api("/api/fields");
  route();
}
window.addEventListener("hashchange", route);

/* ---------------- giriş / kurulum ---------------- */
function loginPage(next) {
  $("#app").innerHTML = `<div class="login"><form class="card" id="f">
    <div class="brand" style="color:var(--ink)"><img src="/static/logo.svg" alt=""><span>Nex<b>Envanter</b></span></div>
    <p class="muted">${esc(S.state.org.org_name)}<br>${esc(S.state.org.unit_name)}</p>
    <label class="f"><span>Kullanıcı adı</span><input name="username" autofocus required></label>
    <label class="f"><span>Parola</span><input name="password" type="password" required></label>
    <button class="btn p" style="width:100%;justify-content:center">Giriş yap</button></form></div>`;
  $("#f").onsubmit = async e => {
    e.preventDefault();
    try {
      await api("/api/login", {method: "POST", body: Object.fromEntries(new FormData(e.target))});
      $("#app").innerHTML = ""; await boot(); go(next || "/");
    } catch (err) { fail(err); }
  };
}
function setupPage() {
  $("#app").innerHTML = `<div class="login"><form class="card" id="f">
    <div class="brand" style="color:var(--ink)"><img src="/static/logo.svg" alt=""><span>Nex<b>Envanter</b></span></div>
    <h2>İlk kurulum</h2><p class="muted small">Sistem yöneticisi hesabını oluşturun.</p>
    <label class="f"><span>Ad soyad</span><input name="full_name"></label>
    <label class="f"><span>Kullanıcı adı</span><input name="username" required minlength="3"></label>
    <label class="f"><span>Parola (en az 8 karakter)</span><input name="password" type="password" required minlength="8"></label>
    <button class="btn p" style="width:100%;justify-content:center">Kurulumu tamamla</button></form></div>`;
  $("#f").onsubmit = async e => {
    e.preventDefault();
    try { await api("/api/setup", {method: "POST", body: Object.fromEntries(new FormData(e.target))}); $("#app").innerHTML = ""; await boot(); go("/"); }
    catch (err) { fail(err); }
  };
}

/* ---------------- ana sayfa ---------------- */
async function dashboard(v) {
  const s = await api("/api/stats");
  const bs = s.by_status, n = k => bs[k] || 0;
  const card = (ic, col, num, l) => `<div class="card stat"><div class="i" style="background:${col}22;color:${col}">${ic}</div><div><div class="n">${num.toLocaleString("tr-TR")}</div><div class="l">${l}</div></div></div>`;
  const bars = (arr) => { const mx = Math.max(1, ...arr.map(x => x.count)); return arr.map(x => `<div style="margin-bottom:9px"><div class="row small"><span>${esc(x.name)}</span><span class="sp"></span><b>${x.count}</b></div><div class="bar"><i style="width:${x.count / mx * 100}%"></i></div></div>`).join("") || `<p class="muted">Kayıt yok</p>`; };
  v.innerHTML = `<h1>Ana Sayfa</h1><div class="grid g4">
    ${card("🖥", "#1463ff", s.total, "Toplam Cihaz")}${card("✔", "#13a05a", n("aktif"), "Aktif")}
    ${card("🔧", "#e6930a", n("bakımda") + n("serviste") + n("arızalı"), "Bakım / Serviste / Arızalı")}${card("⚠", "#d93636", n("hurda") + s.archived, "Hurda / Arşiv")}</div>
    <div class="grid g3"><div class="card"><h2>Birimlere göre</h2>${bars(s.by_location)}</div>
    <div class="card"><h2>Donanım türüne göre</h2>${bars(s.by_hardware)}</div>
    <div class="card"><h2>Son güncellenenler</h2><ul class="tl">${s.recent.map(a => `<li><a href="#/asset/${a.id}"><b>${esc(a.asset_code)}</b></a> ${esc(a.data.brand_model || "")}<div class="small muted">${fmtDate(a.updated_at)} · ${esc(a.updated_by || "")}</div></li>`).join("") || "<li class=muted>Henüz kayıt yok</li>"}</ul>
    ${s.failed_prints ? `<p class="err">${s.failed_prints} başarısız baskı işi var.</p>` : ""}</div></div>`;
}

/* ---------------- liste ---------------- */
async function assetList(v, p) {
  p = {q: "", status: "", archived: "0", sort: "asset_code", dir: "asc", page: 1, size: 50, ...p};
  const cols = S.fields.filter(f => f.show_list && f.key !== "status" && f.key !== "asset_code");
  const filterKeys = ["location_name", "hardware_info"].filter(k => S.fields.some(f => f.key === k));
  const [res, ...vals] = await Promise.all([api("/api/assets?" + qs(p)), ...filterKeys.map(k => api("/api/values/" + k))]);
  const setp = o => go("/assets?" + qs({...p, page: 1, ...o}));
  const th = (key, label) => `<th class="s" data-k="${key}">${esc(label)}${p.sort === key ? (p.dir === "asc" ? " ▲" : " ▼") : ""}</th>`;
  const pages = Math.max(1, Math.ceil(res.total / p.size));
  v.innerHTML = `<div class="row"><h1>Cihazlar</h1><span class="sp"></span>
      ${can("asset.write") ? `<a class="btn p" href="#/new">＋ Yeni Cihaz</a>` : ""}</div>
    <div class="card"><div class="row" style="margin-bottom:12px">
      <input id="q" placeholder="Ara…" value="${esc(p.q)}" style="max-width:260px">
      <select id="st" style="max-width:160px"><option value="">Tüm durumlar</option>${S.state.statuses.map(s => `<option ${s === p.status ? "selected" : ""}>${esc(s)}</option>`).join("")}</select>
      ${filterKeys.map((k, i) => `<select class="ff" data-k="${k}" style="max-width:200px"><option value="">Tüm ${esc(S.fields.find(f => f.key === k).label)}</option>${vals[i].map(x => `<option ${p["f." + k] === x ? "selected" : ""}>${esc(x)}</option>`).join("")}</select>`).join("")}
      <select id="ar" style="max-width:140px"><option value="0">Kullanımda</option><option value="1" ${p.archived === "1" ? "selected" : ""}>Arşiv</option><option value="all" ${p.archived === "all" ? "selected" : ""}>Tümü</option></select>
      <span class="sp"></span><span class="muted small" id="selc"></span>
      ${can("print") ? `<button class="btn" id="bprint" disabled>▦ Etiket</button>` : ""}
      ${can("export") ? `<button class="btn" id="bexp">⇩ Excel</button>` : ""}</div>
    <div class="tw"><table><thead><tr><th><input type="checkbox" id="all"></th>${th("asset_code", "Envanter No")}${cols.map(f => th(f.key, f.label)).join("")}${th("status", "Durum")}</tr></thead>
    <tbody>${res.items.map(a => `<tr class="cl" data-id="${a.id}"><td><input type="checkbox" class="ck" value="${a.id}" ${S.sel.has(a.id) ? "checked" : ""}></td>
      <td><b>${esc(a.asset_code)}</b>${a.archived ? ' <span class="pill">arşiv</span>' : ""}</td>${cols.map(f => `<td>${esc(fv(a, f))}</td>`).join("")}<td>${pill(a.status)}</td></tr>`).join("")
      || `<tr><td colspan="${cols.length + 3}" class="muted">Kayıt bulunamadı.</td></tr>`}</tbody></table></div>
    <div class="pager"><span class="muted">${res.total.toLocaleString("tr-TR")} kayıt · Sayfa ${p.page}/${pages}</span>
      <button class="btn s" id="prev" ${p.page <= 1 ? "disabled" : ""}>‹</button><button class="btn s" id="next" ${p.page >= pages ? "disabled" : ""}>›</button>
      <select id="sz" style="width:auto">${[25, 50, 100, 250].map(n => `<option ${+p.size === n ? "selected" : ""}>${n}</option>`).join("")}</select></div></div>`;
  const updSel = () => { $("#selc").textContent = S.sel.size ? `${S.sel.size} seçili` : ""; if ($("#bprint")) $("#bprint").disabled = !S.sel.size; };
  updSel();
  let t; $("#q").oninput = e => { clearTimeout(t); t = setTimeout(() => setp({q: e.target.value}), 350); };
  $("#q").focus(); $("#q").setSelectionRange(p.q.length, p.q.length);
  $("#st").onchange = e => setp({status: e.target.value});
  $("#ar").onchange = e => setp({archived: e.target.value});
  $$(".ff").forEach(s => s.onchange = e => setp({["f." + s.dataset.k]: e.target.value}));
  $$("th.s").forEach(h => h.onclick = () => setp({sort: h.dataset.k, dir: p.sort === h.dataset.k && p.dir === "asc" ? "desc" : "asc"}));
  $("#prev").onclick = () => go("/assets?" + qs({...p, page: +p.page - 1}));
  $("#next").onclick = () => go("/assets?" + qs({...p, page: +p.page + 1}));
  $("#sz").onchange = e => setp({size: e.target.value});
  $$("tr.cl").forEach(r => r.onclick = e => { if (e.target.type !== "checkbox") go("/asset/" + r.dataset.id); });
  $$(".ck").forEach(c => c.onchange = () => { c.checked ? S.sel.add(+c.value) : S.sel.delete(+c.value); updSel(); });
  $("#all").onchange = e => { $$(".ck").forEach(c => { c.checked = e.target.checked; c.onchange(); }); };
  if ($("#bprint")) $("#bprint").onclick = () => go("/labels?ids=" + [...S.sel].join(","));
  if ($("#bexp")) $("#bexp").onclick = () => download("/api/export.xlsx?" + qs({...p, page: "", size: "", ids: S.sel.size ? [...S.sel].join(",") : ""}));
}

/* ---------------- form ---------------- */
function input(f, val) {
  const n = `name="${esc(f.key)}"`, v = esc(val ?? "");
  if (f.type === "longtext") return `<textarea ${n} rows="3">${v}</textarea>`;
  if (f.type === "date") return `<input ${n} type="date" value="${v}">`;
  if (f.type === "select") { const o = f.key === "status" ? S.state.statuses : f.options;
    return `<select ${n}>${f.key === "status" ? "" : "<option value=''></option>"}${o.map(x => `<option ${x === val ? "selected" : ""}>${esc(x)}</option>`).join("")}</select>`; }
  return `<input ${n} value="${v}" ${f.type === "mac" ? 'placeholder="AA:BB:CC:DD:EE:FF"' : ""} ${f.type === "text" ? `list="dl_${f.key}"` : ""} ${f.key === "asset_code" ? "required" : ""}>`;
}
async function assetForm(v, a) {
  const isNew = !a;
  const textF = S.fields.filter(f => f.type === "text" && !f.system && f.show_list);
  const lists = await Promise.all(textF.map(f => api("/api/values/" + f.key).catch(() => [])));
  v.innerHTML = `<h1>${isNew ? "Yeni Cihaz" : "Düzenle: " + esc(a.asset_code)}</h1><form class="card" id="af"><div class="grid g2">
    ${S.fields.map(f => `<label class="f" ${f.type === "longtext" ? 'style="grid-column:1/-1"' : ""}><span>${esc(f.label)}${f.required ? " *" : ""}</span>${input(f, a ? fv(a, f) : (f.key === "status" ? "aktif" : ""))}<div class="err" data-e="${f.key}"></div></label>`).join("")}
    </div>${textF.map((f, i) => `<datalist id="dl_${f.key}">${lists[i].map(x => `<option value="${esc(x)}">`).join("")}</datalist>`).join("")}
    <div class="row"><button class="btn p">${isNew ? "Kaydet" : "Değişiklikleri kaydet"}</button>
    ${isNew ? `<label class="row small"><input type="checkbox" id="again"> Kaydettikten sonra yeni kayda devam et</label>` : ""}
    <span class="sp"></span><a class="btn" href="#${isNew ? "/assets" : "/asset/" + a.id}">Vazgeç</a></div></form>`;
  $("#af").onsubmit = async e => {
    e.preventDefault(); $$("[data-e]").forEach(x => x.textContent = "");
    const body = Object.fromEntries(new FormData(e.target));
    try {
      const r = await api(isNew ? "/api/assets" : "/api/assets/" + a.id, {method: isNew ? "POST" : "PATCH", body});
      toast("Kaydedildi");
      if (isNew && $("#again").checked) { assetForm(v, null); return; }
      go("/asset/" + r.id);
    } catch (err) {
      const fe = err.data?.fields; if (fe) Object.entries(fe).forEach(([k, m]) => { const x = $(`[data-e="${k}"]`); if (x) x.textContent = m; });
      fail(err);
    }
  };
}

/* ---------------- detay ---------------- */
const ACT = {create: "Oluşturuldu", update: "Güncellendi", import: "Excel'den", archive: "Arşivlendi", restore: "Geri alındı", label_print: "Etiket basıldı", not: "Not", bakim: "Bakım", devir: "Devir/Teslim", ariza: "Arıza"};
async function assetDetail(v, id, edit) {
  const a = await api("/api/assets/" + id);
  if (edit) return assetForm(v, a);
  const chg = c => Object.entries(c || {}).map(([k, x]) => { const f = S.fields.find(f => f.key === k); const lab = f ? f.label : k;
    return Array.isArray(x) ? `${esc(lab)}: <s class="muted">${esc(x[0] ?? "—")}</s> → ${esc(x[1] ?? "—")}` : `${esc(lab)}: ${esc(x)}`; }).join("<br>");
  v.innerHTML = `<div class="row"><h1>${esc(a.asset_code)} ${pill(a.status)} ${a.archived ? '<span class="pill">arşiv</span>' : ""}</h1><span class="sp"></span>
    ${can("asset.write") ? `<a class="btn" href="#/asset/${id}?edit=1">✎ Düzenle</a>` : ""}
    ${can("print") ? `<a class="btn" href="#/labels?ids=${id}">▦ Etiket bas</a>` : ""}
    ${can("asset.archive") ? `<button class="btn ${a.archived ? "" : "d"}" id="arch">${a.archived ? "Arşivden çıkar" : "Arşivle"}</button>` : ""}</div>
    <div class="grid g2"><div class="card"><h2>Bilgiler</h2><dl class="kv">${S.fields.map(f => `<dt>${esc(f.label)}</dt><dd>${esc(fv(a, f) || "—")}</dd>`).join("")}
      <dt>Oluşturma</dt><dd>${fmtDate(a.created_at)} · ${esc(a.created_by || "")}</dd><dt>Son güncelleme</dt><dd>${fmtDate(a.updated_at)} · ${esc(a.updated_by || "")}</dd></dl></div>
    <div><div class="card"><h2>Etiket</h2><img class="lbl-prev" src="/api/labels/preview/${id}.png?t=${Date.now()}" alt="etiket">
      <p class="small muted">QR bağlantısı: <a href="${esc(a.qr_url)}" target="_blank" class="mono">${esc(a.qr_url)}</a></p></div>
    <div class="card"><h2>Geçmiş</h2>
      ${can("asset.write") ? `<form id="ev" class="row" style="margin-bottom:10px"><select name="action" style="max-width:150px"><option value="not">Not</option><option value="bakim">Bakım</option><option value="ariza">Arıza</option><option value="devir">Devir/Teslim</option></select><input name="note" placeholder="Not ekle…" required style="flex:1"><button class="btn">Ekle</button></form>` : ""}
      <ul class="tl">${a.events.map(e => `<li><b>${esc(ACT[e.action] || e.action)}</b> <span class="small muted">${fmtDate(e.at)} · ${esc(e.user || "")}</span>
        ${e.note ? `<div>${esc(e.note)}</div>` : ""}${e.action === "update" || e.action === "import" ? `<div class="small">${chg(e.changes)}</div>` : ""}</li>`).join("")}</ul></div></div></div>`;
  if ($("#arch")) $("#arch").onclick = async () => {
    const note = a.archived ? null : prompt("Arşivleme nedeni (isteğe bağlı):");
    if (note === null && !a.archived) return;
    try { await api(`/api/assets/${id}/archive`, {method: "POST", body: {archived: !a.archived, note}}); route(); } catch (e) { fail(e); }
  };
  if ($("#ev")) $("#ev").onsubmit = async e => { e.preventDefault();
    try { await api(`/api/assets/${id}/events`, {method: "POST", body: Object.fromEntries(new FormData(e.target))}); route(); } catch (err) { fail(err); } };
}

/* ---------------- Excel içe aktarma ---------------- */
async function importPage(v) {
  const jobs = await api("/api/import/jobs");
  v.innerHTML = `<h1>Excel İşlemleri</h1><div class="card"><div class="steps"><span class="on">1 Dosya</span><span>2 Eşleştirme</span><span>3 Deneme</span><span>4 Sonuç</span></div>
    <div class="row"><input type="file" id="file" accept=".xlsx,.xlsm" style="max-width:360px"><button class="btn p" id="up">Yükle ve analiz et</button>
    <span class="sp"></span><button class="btn" id="tpl">⇩ Boş şablon</button><button class="btn" id="exp">⇩ Tüm envanter</button></div><div id="wiz"></div></div>
    <div class="card"><h2>Geçmiş içe aktarmalar</h2><table><thead><tr><th>#</th><th>Tarih</th><th>Kullanıcı</th><th>Dosya</th><th>Eklenen</th><th>Güncellenen</th><th>Atlanan</th><th>Hata</th><th></th></tr></thead>
    <tbody>${jobs.map(j => `<tr><td>${j.id}</td><td>${fmtDate(j.at)}</td><td>${esc(j.user)}</td><td>${esc(j.filename)}</td><td>${j.stats.inserted ?? ""}</td><td>${j.stats.updated ?? ""}</td><td>${j.stats.skipped ?? ""}</td><td>${j.stats.errors ?? ""}</td><td><a href="/api/import/jobs/${j.id}/report.xlsx">Rapor</a></td></tr>`).join("") || "<tr><td colspan=9 class=muted>Henüz yok</td></tr>"}</tbody></table></div>`;
  $("#tpl").onclick = () => download("/api/template.xlsx");
  $("#exp").onclick = () => download("/api/export.xlsx");
  $("#up").onclick = async () => {
    const f = $("#file").files[0]; if (!f) return toast("Dosya seçin", true);
    const fd = new FormData(); fd.append("file", f);
    try { mapping(await api("/api/import/upload", {method: "POST", form: fd})); } catch (e) { fail(e); }
  };
}
function mapping(an) {
  $$(".steps span").forEach((s, i) => s.classList.toggle("on", i === 1));
  const opts = (sel) => `<option value="__ignore__" ${sel === "__ignore__" ? "selected" : ""}>— Aktarma —</option><option value="__new__" ${sel === "__new__" ? "selected" : ""}>＋ Yeni alan oluştur</option>` +
    an.fields.map(f => `<option value="${f.key}" ${sel === f.key ? "selected" : ""}>${esc(f.label)}</option>`).join("");
  $("#wiz").innerHTML = `<div class="row" style="margin:14px 0"><label class="f" style="margin:0"><span>Sayfa</span><select id="sh">${an.sheets.map(s => `<option ${s === an.sheet ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></label>
    <label class="f" style="margin:0;width:120px"><span>Başlık satırı</span><input id="hr" type="number" min="1" value="${an.header_row}"></label>
    <span class="muted small" style="align-self:flex-end">≈ ${an.row_estimate} veri satırı</span></div>
    <div class="tw"><table><thead><tr><th>Excel sütunu</th><th>Uygulama alanı</th><th>Yeni alan adı / tipi</th><th>Örnek değerler</th></tr></thead><tbody>
    ${an.columns.map(c => `<tr><td><b>${esc(c.header) || `<i class=muted>(başlıksız ${c.index + 1})</i>`}</b></td><td><select class="mp" data-i="${c.index}">${opts(c.suggestion)}</select></td>
      <td><div class="row nf" data-i="${c.index}" style="${c.suggestion === "__new__" ? "" : "display:none"}"><input class="nfl" value="${esc(c.header)}" style="width:160px"><select class="nft" style="width:110px"><option value="text">Metin</option><option value="longtext">Uzun metin</option><option value="date">Tarih</option><option value="number">Sayı</option><option value="mac">MAC</option></select></div></td>
      <td class="small muted">${an.sample.slice(0, 3).map(r => esc(r[c.index] ?? "")).filter(Boolean).join(" · ")}</td></tr>`).join("")}</tbody></table></div>
    <div class="row" style="margin-top:14px"><label class="f" style="margin:0;width:280px"><span>Barkod sistemde zaten varsa</span><select id="mode"><option value="skip">Atla (mevcut kayda dokunma)</option><option value="update">Mevcut kaydı güncelle</option></select></label>
    <label class="row small" style="align-self:flex-end"><input type="checkbox" id="bo"> Boş hücreler mevcut değeri silsin</label><span class="sp"></span>
    <button class="btn" id="dry">Deneme (kaydetmeden)</button><button class="btn p" id="go">İçe aktar</button></div><div id="res"></div>`;
  $$(".mp").forEach(s => s.onchange = () => { $(`.nf[data-i="${s.dataset.i}"]`).style.display = s.value === "__new__" ? "" : "none"; });
  const reanalyze = async () => { try { mapping(await api("/api/import/analyze", {method: "POST", body: {token: an.token, sheet: $("#sh").value, header_row: +$("#hr").value}})); } catch (e) { fail(e); } };
  $("#sh").onchange = () => { $("#hr").value = ""; reanalyze(); };
  $("#hr").onchange = reanalyze;
  const run = async (dry) => {
    const map = {}, nf = {};
    $$(".mp").forEach(s => { map[s.dataset.i] = s.value; if (s.value === "__new__") { const r = $(`.nf[data-i="${s.dataset.i}"]`); nf[s.dataset.i] = {label: $(".nfl", r).value, type: $(".nft", r).value}; } });
    if (!dry && !confirm("Veriler veritabanına yazılacak. Devam edilsin mi?")) return;
    try {
      const r = await api("/api/import/run", {method: "POST", body: {token: an.token, sheet: $("#sh").value, header_row: +$("#hr").value, mapping: map, new_fields: nf, mode: $("#mode").value, blank_overwrites: $("#bo").checked, dry_run: dry}});
      $$(".steps span").forEach((s, i) => s.classList.toggle("on", i === (dry ? 2 : 3)));
      const st = r.stats;
      $("#res").innerHTML = `<h3>${dry ? "Deneme sonucu (hiçbir şey kaydedilmedi)" : "İçe aktarma tamamlandı"}</h3>
        <div class="row"><span class="pill aktif">Eklenecek/eklenen: ${st.inserted}</span><span class="pill">Güncellenen: ${st.updated}</span><span class="pill depoda">Değişmeyen: ${st.unchanged}</span><span class="pill bakımda">Atlanan: ${st.skipped}</span><span class="pill hurda">Hata: ${st.errors}</span><span class="muted small">Boş satır: ${st.blank}</span>
        ${st.new_fields.length ? `<span class="small">Yeni alanlar: <b>${esc(st.new_fields.join(", "))}</b></span>` : ""}
        ${r.job_id ? `<a class="btn s" href="/api/import/jobs/${r.job_id}/report.xlsx">⇩ Rapor</a>` : ""}</div>
        <div class="tw" style="max-height:360px;margin-top:10px"><table><thead><tr><th>Satır</th><th>Barkod</th><th>Sonuç</th><th>Mesaj</th></tr></thead><tbody>
        ${r.report.filter(x => x.result !== "eklendi" || r.report.length < 200).slice(0, 500).map(x => `<tr><td>${x.row}</td><td>${esc(x.asset_code)}</td><td class="res-${esc(x.result)}">${esc(x.result)}</td><td>${esc(x.message)}</td></tr>`).join("")}</tbody></table></div>`;
      if (!dry) { S.fields = await api("/api/fields"); toast("İçe aktarma tamamlandı"); }
    } catch (e) { fail(e); }
  };
  $("#dry").onclick = () => run(true);
  $("#go").onclick = () => run(false);
}

/* ---------------- etiket & yazıcı ---------------- */
async function labelsPage(v, p) {
  const ids = (p.ids || "").split(",").filter(Boolean);
  const [T, P, jobs] = await Promise.all([api("/api/labels/template"), can("print") ? api("/api/printers") : {printers: [], adapters: []}, api("/api/print/jobs")]);
  const t = T.template, editable = can("labels");
  const fieldOpts = sel => S.fields.map(f => `<option value="${f.key}" ${sel === f.key ? "selected" : ""}>${esc(f.label)}</option>`).join("");
  const rowHtml = r => `<div class="row lr" style="margin-bottom:6px"><input class="rl" value="${esc(r.label)}" placeholder="Etiket metni" style="width:180px"><select class="rf" style="width:200px">${fieldOpts(r.field)}</select><button type="button" class="btn s rdel">✕</button></div>`;
  v.innerHTML = `<h1>Etiket & Yazıcı</h1>
    ${ids.length ? `<div class="card"><h2>Yazdır: ${ids.length} etiket</h2><div class="row">
      <select id="prn" style="max-width:320px">${P.printers.map(x => `<option data-a="${x.adapter}" ${x.name === P.default || (!P.default && x.default) ? "selected" : ""}>${esc(x.name)}</option>`).join("") || "<option value=''>Doğrudan yazıcı yok (PDF kullanın)</option>"}</select>
      <label class="f" style="margin:0;width:90px"><input id="cp" type="number" min="1" max="20" value="1" title="Kopya"></label>
      <button class="btn p" id="doprint" ${P.printers.length ? "" : "disabled"}>▦ Yazdır</button><button class="btn" id="pdf">⇩ PDF</button><button class="btn s" id="pst">Durum</button>
      <span class="sp"></span><button class="btn s" id="clr">Seçimi temizle</button></div>
      <div class="row" style="margin-top:12px">${ids.slice(0, 6).map(i => `<img class="lbl-prev" style="width:230px" src="/api/labels/preview/${i}.png">`).join("")}${ids.length > 6 ? `<span class="muted">+${ids.length - 6}</span>` : ""}</div>
      <p class="small muted">Not: "Gönderildi" durumu fiziksel baskının başarılı olduğunu kanıtlamaz; ilk baskıda QR'ı telefonla okutun.</p></div>` : ""}
    <div class="grid g2"><form class="card" id="tf"><h2>Etiket şablonu</h2><fieldset ${editable ? "" : "disabled"} style="border:0;padding:0;margin:0">
      <div class="grid g4"><label class="f"><span>Genişlik (mm)</span><input name="width_mm" type="number" step="0.5" value="${t.width_mm}"></label>
      <label class="f"><span>Yükseklik (mm)</span><input name="height_mm" type="number" step="0.5" value="${t.height_mm}"></label>
      <label class="f"><span>DPI</span><select name="dpi">${[180, 203, 300, 360, 600, 720].map(d => `<option ${+t.dpi === d ? "selected" : ""}>${d}</option>`).join("")}</select></label>
      <label class="f"><span>Kenar (mm)</span><input name="margin_mm" type="number" step="0.1" value="${t.margin_mm}"></label></div>
      <label class="f"><span>Üst bant metni ({org_name} = kurum adı)</span><input name="h_text" value="${esc(t.header.text)}"></label>
      <div class="row small"><label><input type="checkbox" name="h_en" ${t.header.enabled ? "checked" : ""}> Üst bant</label><label><input type="checkbox" name="h_inv" ${t.header.inverted ? "checked" : ""}> Siyah zemin</label>
        <label><input type="checkbox" name="logo_left" ${t.logo_left ? "checked" : ""}> Sol logo</label><label><input type="checkbox" name="logo_right" ${t.logo_right ? "checked" : ""}> Sağ logo</label>
        <label><input type="checkbox" name="uppercase" ${t.uppercase ? "checked" : ""}> BÜYÜK HARF</label><label><input type="checkbox" name="border" ${t.border ? "checked" : ""}> Çerçeve</label></div>
      <label class="f" style="margin-top:10px"><span>Alt başlık satırları (her satır ayrı; {unit_name}, {system_title})</span><textarea name="s_lines" rows="2">${esc(t.subheader.lines.join("\n"))}</textarea></label>
      <label class="row small"><input type="checkbox" name="s_en" ${t.subheader.enabled ? "checked" : ""}> Alt başlık</label>
      <h3>Bilgi satırları</h3><div id="rows">${t.rows.map(rowHtml).join("")}</div><button type="button" class="btn s" id="radd">＋ Satır</button>
      <h3>QR</h3><div class="row small"><label><input type="checkbox" name="q_en" ${t.qr.enabled ? "checked" : ""}> QR kod</label><label><input type="checkbox" name="q_code" ${t.qr.show_code ? "checked" : ""}> Altında envanter no</label>
        <label>Sessiz alan (modül) <input name="q_quiet" type="number" min="0" max="4" value="${t.qr.quiet_modules}" style="width:60px"></label></div>
      ${editable ? `<div class="row" style="margin-top:12px"><span class="small">Logo yükle:</span><input type="file" id="lgf" accept="image/*" style="max-width:220px"><select id="lgs" style="width:90px"><option value="left">Sol</option><option value="right">Sağ</option></select><button type="button" class="btn s" id="lgu">Yükle</button></div>
      <p class="small muted">Yalnızca kullanım izni olan resmî logo dosyalarını yükleyin.</p>
      <div class="row" style="margin-top:12px"><button class="btn p">Şablonu kaydet</button><button type="button" class="btn" id="rst">Varsayılana dön</button></div>` : ""}</fieldset></form>
    <div><div class="card"><h2>Önizleme</h2><img id="pv" class="lbl-prev" alt="önizleme"><p class="small muted">Ölçüler milimetre tabanlıdır; Brother şerit genişliği ve QR okunabilirliği gerçek baskıyla doğrulanmalıdır.</p></div>
    <div class="card"><h2>Baskı geçmişi</h2><div class="tw" style="max-height:300px"><table><thead><tr><th>Tarih</th><th>Kullanıcı</th><th>Yazıcı</th><th>Adet</th><th>Durum</th></tr></thead><tbody>
      ${jobs.map(j => `<tr><td>${fmtDate(j.at)}</td><td>${esc(j.user)}</td><td>${esc(j.printer)}</td><td>${j.asset_ids.length}×${j.copies}</td><td class="${j.status === "failed" ? "res-hata" : ""}" title="${esc(j.error || "")}">${esc(j.status)}</td></tr>`).join("") || "<tr><td colspan=5 class=muted>Yok</td></tr>"}</tbody></table></div></div></div></div>`;
  const collect = () => {
    const f = new FormData($("#tf")), b = k => f.get(k) === "on";
    return {...t, width_mm: +f.get("width_mm"), height_mm: +f.get("height_mm"), dpi: +f.get("dpi"), margin_mm: +f.get("margin_mm"),
      uppercase: b("uppercase"), border: b("border"), logo_left: b("logo_left"), logo_right: b("logo_right"),
      header: {...t.header, enabled: b("h_en"), inverted: b("h_inv"), text: f.get("h_text")},
      subheader: {...t.subheader, enabled: b("s_en"), lines: f.get("s_lines").split("\n").map(s => s.trim()).filter(Boolean)},
      rows: $$(".lr").map(r => ({label: $(".rl", r).value, field: $(".rf", r).value})),
      qr: {enabled: b("q_en"), show_code: b("q_code"), quiet_modules: +f.get("q_quiet")}};
  };
  let pt; const preview = () => { clearTimeout(pt); pt = setTimeout(async () => {
    try { const bl = await fetch("/api/labels/preview", {method: "POST", headers: {"x-nx": "1", "Content-Type": "application/json"}, body: JSON.stringify({template: collect(), asset_id: +(ids[0] || 0)})});
      if (bl.ok) $("#pv").src = URL.createObjectURL(await bl.blob()); } catch (_) {} }, 250); };
  const bindRows = () => $$(".rdel").forEach(b => b.onclick = () => { b.parentElement.remove(); preview(); });
  bindRows(); preview();
  $("#tf").oninput = preview; $("#tf").onchange = preview;
  if (editable) {
    $("#radd").onclick = () => { $("#rows").insertAdjacentHTML("beforeend", rowHtml({label: "", field: "hardware_info"})); bindRows(); preview(); };
    $("#tf").onsubmit = async e => { e.preventDefault(); try { await api("/api/labels/template", {method: "PUT", body: {template: collect()}}); toast("Şablon kaydedildi"); } catch (err) { fail(err); } };
    $("#rst").onclick = async () => { if (!confirm("Varsayılan şablona dönülsün mü?")) return; await api("/api/labels/template", {method: "PUT", body: {template: T.default}}); route(); };
    $("#lgu").onclick = async () => { const f = $("#lgf").files[0]; if (!f) return; const fd = new FormData(); fd.append("file", f);
      try { await api("/api/labels/logo/" + $("#lgs").value, {method: "POST", form: fd}); toast("Logo yüklendi"); preview(); } catch (e) { fail(e); } };
  }
  if (ids.length) {
    $("#pdf").onclick = () => window.open("/api/labels/pdf?ids=" + ids.join(","), "_blank");
    $("#clr").onclick = () => { S.sel.clear(); go("/labels"); };
    $("#pst").onclick = async () => { const o = $("#prn").selectedOptions[0]; if (!o) return;
      try { const s = await api("/api/printers/status?" + qs({name: o.value, adapter: o.dataset.a})); toast(`${o.value}: ${s.message}`, !s.ok); } catch (e) { fail(e); } };
    $("#doprint").onclick = async () => { const o = $("#prn").selectedOptions[0];
      if (!confirm(`${ids.length} etiket × ${$("#cp").value} kopya "${o.value}" yazıcısına gönderilsin mi?`)) return;
      try { const r = await api("/api/print", {method: "POST", body: {ids, printer: o.value, adapter: o.dataset.a, copies: +$("#cp").value}}); toast(`${r.count} etiket gönderildi (iş #${r.job_id})`); S.sel.clear(); }
      catch (e) { fail(e); } };
  }
}

/* ---------------- alanlar ---------------- */
async function fieldsPage(v) {
  const all = await api("/api/fields?all=1");
  const T = {text: "Metin", longtext: "Uzun metin", number: "Sayı", date: "Tarih", mac: "MAC", select: "Seçim"};
  const ck = (f, k, dis) => `<input type="checkbox" data-k="${f.key}" data-p="${k}" ${f[k] ? "checked" : ""} ${dis ? "disabled" : ""}>`;
  v.innerHTML = `<h1>Alanlar</h1><div class="card"><p class="muted small">Excel'e yeni sütun eklendiğinde içe aktarma sırasında otomatik alan oluşturulabilir. Eş adlar, farklı yazılmış Excel başlıklarını bu alana eşler (virgülle ayırın).</p>
    <div class="tw"><table><thead><tr><th>Sıra</th><th>Ad</th><th>Tip</th><th>Eş adlar (Excel başlıkları)</th><th title="Listede sütun">Liste</th><th title="Oturum açmış QR önizlemesi">Önizleme</th><th title="Oturumsuz QR önizlemesi">Herkese açık</th><th>Zorunlu</th><th>Aktif</th></tr></thead>
    <tbody>${all.map(f => `<tr><td><input data-k="${f.key}" data-p="sort" type="number" value="${f.sort}" style="width:70px"></td>
      <td><input data-k="${f.key}" data-p="label" value="${esc(f.label)}" style="min-width:170px"><div class="small muted mono">${f.key}${f.system ? " · sistem" : ""}</div></td>
      <td>${f.system ? T[f.type] : `<select data-k="${f.key}" data-p="type">${Object.entries(T).map(([k, l]) => `<option value="${k}" ${f.type === k ? "selected" : ""}>${l}</option>`).join("")}</select>`}
        ${f.type === "select" && !f.system ? `<input data-k="${f.key}" data-p="options" value="${esc(f.options.join(", "))}" placeholder="Seçenekler" style="margin-top:4px">` : ""}</td>
      <td><input data-k="${f.key}" data-p="aliases" value="${esc(f.aliases.join(", "))}" style="min-width:220px"></td>
      <td>${ck(f, "show_list")}</td><td>${ck(f, "show_preview")}</td><td>${ck(f, "public")}</td><td>${ck(f, "required", f.key === "asset_code")}</td><td>${ck(f, "active", f.system)}</td></tr>`).join("")}</tbody></table></div></div>
    <form class="card row" id="nf"><b>Yeni alan</b><input name="label" placeholder="Alan adı (ör. IP Adresi)" required style="max-width:260px">
      <select name="type" style="max-width:150px">${Object.entries(T).map(([k, l]) => `<option value="${k}">${l}</option>`).join("")}</select><button class="btn p">Ekle</button></form>`;
  $$("[data-p]").forEach(el => el.onchange = async () => {
    let val = el.type === "checkbox" ? el.checked : el.value;
    if (el.dataset.p === "aliases" || el.dataset.p === "options") val = val.split(",").map(s => s.trim()).filter(Boolean);
    if (el.dataset.p === "sort") val = +val;
    try { await api("/api/fields/" + el.dataset.k, {method: "PATCH", body: {[el.dataset.p]: val}}); S.fields = await api("/api/fields"); toast("Kaydedildi"); if (el.dataset.p === "type") route(); }
    catch (e) { fail(e); }
  });
  $("#nf").onsubmit = async e => { e.preventDefault();
    try { await api("/api/fields", {method: "POST", body: Object.fromEntries(new FormData(e.target))}); S.fields = await api("/api/fields"); route(); } catch (err) { fail(err); } };
}

/* ---------------- kullanıcılar ---------------- */
async function usersPage(v) {
  const us = await api("/api/users"), R = S.state.roles;
  v.innerHTML = `<h1>Kullanıcılar</h1><div class="card"><table><thead><tr><th>Kullanıcı</th><th>Ad soyad</th><th>Rol</th><th>Son giriş</th><th>Aktif</th><th></th></tr></thead><tbody>
    ${us.map(u => `<tr><td><b>${esc(u.username)}</b></td><td>${esc(u.full_name || "")}</td>
      <td><select data-u="${u.id}" data-p="role">${Object.entries(R).map(([k, l]) => `<option value="${k}" ${u.role === k ? "selected" : ""}>${l}</option>`).join("")}</select></td>
      <td class="small">${fmtDate(u.last_login)}</td><td><input type="checkbox" data-u="${u.id}" data-p="active" ${u.active ? "checked" : ""}></td>
      <td><button class="btn s" data-pw="${u.id}">Parola sıfırla</button></td></tr>`).join("")}</tbody></table></div>
    <form class="card" id="nu"><h2>Yeni kullanıcı</h2><div class="grid g4"><input name="username" placeholder="Kullanıcı adı" required><input name="full_name" placeholder="Ad soyad">
      <input name="password" type="password" placeholder="Parola (≥8)" required><select name="role">${Object.entries(R).map(([k, l]) => `<option value="${k}" ${k === "viewer" ? "selected" : ""}>${l}</option>`).join("")}</select></div>
      <button class="btn p" style="margin-top:12px">Ekle</button></form>
    <div class="card small muted">Roller: <b>Sistem Yöneticisi</b> her şey · <b>BİM Yöneticisi</b> envanter, içe aktarma, alanlar, etiket şablonu · <b>Envanter Operatörü</b> ekle/düzenle, etiket bas · <b>Denetçi</b> okuma ve denetim kaydı · <b>Görüntüleyici</b> yalnızca okuma</div>`;
  $$("[data-u]").forEach(el => el.onchange = async () => {
    try { await api("/api/users/" + el.dataset.u, {method: "PATCH", body: {[el.dataset.p]: el.type === "checkbox" ? el.checked : el.value}}); toast("Kaydedildi"); }
    catch (e) { fail(e); route(); }
  });
  $$("[data-pw]").forEach(b => b.onclick = async () => { const p = prompt("Yeni parola (en az 8 karakter):"); if (!p) return;
    try { await api("/api/users/" + b.dataset.pw, {method: "PATCH", body: {password: p}}); toast("Parola değiştirildi"); } catch (e) { fail(e); } });
  $("#nu").onsubmit = async e => { e.preventDefault();
    try { await api("/api/users", {method: "POST", body: Object.fromEntries(new FormData(e.target))}); route(); } catch (err) { fail(err); } };
}

/* ---------------- denetim ---------------- */
async function auditPage(v, p) {
  const page = +(p.page || 1), r = await api("/api/audit?" + qs({page, q: p.q || ""}));
  v.innerHTML = `<h1>Denetim Kaydı</h1><div class="card"><input id="aq" placeholder="Kullanıcı, işlem veya hedef ara…" value="${esc(p.q || "")}" style="max-width:340px;margin-bottom:10px">
    <div class="tw"><table><thead><tr><th>Tarih</th><th>Kullanıcı</th><th>IP</th><th>İşlem</th><th>Hedef</th><th>Ayrıntı</th></tr></thead><tbody>
    ${r.items.map(a => `<tr><td class="small">${fmtDate(a.at)}</td><td>${esc(a.user)}</td><td class="small mono">${esc(a.ip)}</td><td>${esc(a.action)}</td><td>${esc(a.target)}</td><td class="small muted" style="max-width:420px;word-break:break-all">${esc(a.detail)}</td></tr>`).join("")}</tbody></table></div>
    <div class="pager"><span class="muted">${r.total} kayıt</span><button class="btn s" id="pp" ${page <= 1 ? "disabled" : ""}>‹</button><button class="btn s" id="np" ${page * 100 >= r.total ? "disabled" : ""}>›</button></div></div>`;
  $("#aq").onchange = e => go("/audit?" + qs({q: e.target.value}));
  $("#pp").onclick = () => go("/audit?" + qs({q: p.q, page: page - 1}));
  $("#np").onclick = () => go("/audit?" + qs({q: p.q, page: page + 1}));
}

/* ---------------- ayarlar ---------------- */
async function settingsPage(v) {
  const s = await api("/api/settings"), admin = can("settings"), lic = S.state.license;
  const bk = admin ? await api("/api/backups") : [];
  v.innerHTML = `<h1>Ayarlar</h1><div class="grid g2"><div>
    <form class="card" id="sf"><h2>Kurum ve ağ</h2><fieldset ${admin ? "" : "disabled"} style="border:0;padding:0;margin:0">
      <label class="f"><span>Kurum adı</span><input name="org_name" value="${esc(s.org_name)}"></label>
      <label class="f"><span>Birim adı</span><input name="unit_name" value="${esc(s.unit_name)}"></label>
      <label class="f"><span>Sistem başlığı</span><input name="system_title" value="${esc(s.system_title)}"></label>
      <label class="f"><span>QR temel adresi (boşsa otomatik: <span class="mono">${esc(s.detected_url)}</span>)</span><input name="base_url" value="${esc(s.base_url)}" placeholder="http://envanter.hastane.local:8750"></label>
      <p class="small muted">QR içinde yalnızca bu adres + kalıcı kimlik bulunur. Sabit IP yerine yerel DNS adı önerilir; adres değişirse etiketleri yeniden basmak gerekir.</p>
      <label class="f"><span>İçe aktarmada yok sayılacak başlıklar (virgülle)</span><input name="import_ignore_headers" value="${esc((s.import_ignore_headers || []).join(", "))}"></label>
      <label class="f"><span>Saklanacak otomatik yedek sayısı</span><input name="backup_keep" type="number" min="1" value="${s.backup_keep}"></label>
      ${admin ? `<button class="btn p">Kaydet</button>` : ""}</fieldset></form>
    <form class="card" id="pw"><h2>Parolamı değiştir</h2><label class="f"><span>Mevcut parola</span><input name="old_password" type="password" required></label>
      <label class="f"><span>Yeni parola</span><input name="new_password" type="password" minlength="8" required></label><button class="btn">Değiştir</button></form></div>
    <div><div class="card"><h2>Güncelleme</h2><p>Sürüm <b>${esc(S.state.app.version)}</b></p><div id="upd"></div><button class="btn p" id="chk">Güncellemeleri denetle</button></div>
    <div class="card"><h2>Lisans</h2><dl class="kv"><dt>Sürüm türü</dt><dd>${esc(lic.edition)}</dd><dt>Durum</dt><dd>${lic.valid ? "Geçerli" : "Geçersiz"}</dd><dt>Makine kimliği</dt><dd class="mono">${esc(lic.machine_id)}</dd></dl></div>
    ${admin ? `<div class="card"><h2>Yedekleme</h2><p class="small muted">Veri klasörü: <span class="mono">${esc(s.data_dir)}</span><br>Açılışta ve 24 saatte bir otomatik yedek alınır. Yedekleri ayrı bir diske/NAS'a da kopyalayın.</p>
      <button class="btn" id="bkn">Şimdi yedekle</button><ul class="tl" style="margin-top:10px;max-height:240px;overflow:auto">${bk.map(b => `<li><a href="/api/backups/${encodeURIComponent(b.name)}">${esc(b.name)}</a> <span class="small muted">${(b.size / 1024).toFixed(0)} KB</span></li>`).join("")}</ul></div>` : ""}</div></div>`;
  if (admin) {
    $("#sf").onsubmit = async e => { e.preventDefault(); const b = Object.fromEntries(new FormData(e.target));
      b.import_ignore_headers = b.import_ignore_headers.split(",").map(x => x.trim()).filter(Boolean); b.backup_keep = +b.backup_keep;
      try { await api("/api/settings", {method: "PUT", body: b}); S.state = await api("/api/state"); toast("Kaydedildi"); } catch (err) { fail(err); } };
    $("#bkn").onclick = async () => { try { const r = await api("/api/backup", {method: "POST"}); toast("Yedek alındı: " + r.name); route(); } catch (e) { fail(e); } };
  }
  $("#pw").onsubmit = async e => { e.preventDefault();
    try { await api("/api/me/password", {method: "POST", body: Object.fromEntries(new FormData(e.target))}); toast("Parola değiştirildi"); e.target.reset(); } catch (err) { fail(err); } };
  $("#chk").onclick = async () => {
    $("#upd").innerHTML = `<p class="muted">Denetleniyor…</p>`;
    const u = await api("/api/update/check");
    if (!u.ok) { $("#upd").innerHTML = `<p class="err">${esc(u.message)}</p>`; return; }
    if (!u.update_available) { $("#upd").innerHTML = `<p>En güncel sürümü kullanıyorsunuz (${esc(u.latest || u.current)}).</p>`; return; }
    $("#upd").innerHTML = `<p><b>Yeni sürüm: ${esc(u.latest)}</b></p><pre class="small" style="white-space:pre-wrap;max-height:180px;overflow:auto">${esc(u.notes)}</pre>
      ${u.can_apply && admin ? `<button class="btn p" id="apl">İndir ve kur</button>` : `<a class="btn" href="${esc(u.url)}" target="_blank">Sürüm sayfası</a>`}`;
    if ($("#apl")) $("#apl").onclick = async () => {
      if (!confirm("Güncelleme indirilip kurulacak; program kısa süre kapanıp yeniden açılacak. Önce otomatik yedek alınır. Devam?")) return;
      try { const r = await api("/api/update/apply", {method: "POST"}); $("#upd").innerHTML = `<p>${esc(r.message)}</p>`;
        setTimeout(function wait() { fetch("/api/state").then(() => location.reload()).catch(() => setTimeout(wait, 2000)); }, 6000); }
      catch (e) { fail(e); }
    };
  };
}

boot().catch(e => { document.body.innerHTML = `<p style="padding:20px">Sunucuya bağlanılamadı: ${esc(e.message)}</p>`; });
