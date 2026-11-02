"use strict";
/* NexEnvanter v0.4 sayfaları: durum panosu, alarmlar, onay kuyruğu, yedek havuzu, hizmet noktaları, arıza analizi */
const LIVE = {ok: ["#13a05a", "Çalışıyor"], uyarı: ["#e6930a", "Uyarı"], arıza: ["#d93636", "Arıza"], kritik: ["#d93636", "Kritik"], pasif: ["#8a96b0", "Pasif/Dışı"]};
const dot = s => `<span class="live" style="background:${(LIVE[s] || LIVE.pasif)[0]}" title="${(LIVE[s] || LIVE.pasif)[1]}"></span>`;
const sevPill = s => `<span class="pill ${s === "kritik" ? "hurda" : s === "uyarı" ? "bakımda" : "depoda"}">${esc(s)}</span>`;

/* ---------- durum panosu (NOC) ---------- */
PRO["/noc"] = async v => {
  const render = async () => {
    const d = await api("/api/noc");
    const pointCard = p => `<a class="card noc-pt" href="#/sp/${p.id}"><div class="row">${dot(p.status)}<b>${esc(p.name)}</b>${p.critical ? ' <span class="pill hurda">kritik</span>' : ""}<span class="sp"></span><span class="small muted">${esc(p.location || "")}</span></div>
      <div class="noc-items">${p.items.map(i => `<span class="noc-i" title="${esc(i.asset_code)} — ${(LIVE[i.live] || LIVE.pasif)[1]}">${dot(i.live)}${esc(i.role || i.brand_model || i.asset_code)}</span>`).join("") || '<span class="small muted">cihaz yok</span>'}</div></a>`;
    $("#noc").innerHTML = `${d.critical.length ? `<div class="card"><h2>Kritik cihazlar</h2><div class="tw"><table><thead><tr><th>Durum</th><th>Barkod</th><th>Cihaz</th><th>Birim</th></tr></thead><tbody>
      ${d.critical.map(x => `<tr class="cl" data-id="${x.id}"><td>${dot(x.live)} ${(LIVE[x.live] || LIVE.pasif)[1]}</td><td><b>${esc(x.asset_code)}</b></td><td>${esc(x.hardware_info || "")} ${esc(x.brand_model || "")}</td><td class="small">${esc(x.location || "")}</td></tr>`).join("")}</tbody></table></div></div>` : ""}
      <div class="card"><h2>Hizmet noktaları</h2><div class="grid g3">${d.points.map(pointCard).join("") || '<p class="muted">Henüz hizmet noktası tanımlanmadı. <a href="#/servicepoints">Tanımla</a></p>'}</div></div>
      ${d.alerts.length ? `<div class="card"><h2>Açık alarmlar (${d.alerts.length})</h2><ul class="tl">${d.alerts.map(a => `<li>${sevPill(a.severity)} ${esc(a.message)} <span class="small muted">${fmtDate(a.at)}</span></li>`).join("")}</ul></div>` : ""}`;
    $$("#noc tr.cl").forEach(r => r.onclick = () => go("/asset/" + r.dataset.id));
  };
  v.innerHTML = `<div class="row"><h1>Durum Panosu</h1><span class="sp"></span><label class="row small"><input type="checkbox" id="auto" checked> 30 sn'de yenile</label></div><div id="noc"></div>`;
  await render();
  clearInterval(S.nt); S.nt = setInterval(() => { if (location.hash.startsWith("#/noc") && $("#auto")?.checked) render(); else if (!location.hash.startsWith("#/noc")) clearInterval(S.nt); }, 30000);
};
PRO["/sp/:id"] = async (v, id) => { go("/servicepoints?open=" + id); };

/* ---------- alarmlar ---------- */
PRO["/alerts"] = async (v, p) => {
  const st = p.state || "açık";
  const r = await api("/api/alerts?" + qs({state: st}));
  const mg = can("alerts.manage");
  v.innerHTML = `<div class="row"><h1>Alarmlar</h1><span class="sp"></span>${mg ? `<button class="btn" id="chk">⟳ Şimdi denetle</button>` : ""}</div>
    <div class="card"><div class="steps">${[["açık", "Açık"], ["görüldü", "Görüldü"], ["kapalı", "Kapalı"], ["all", "Tümü"]].map(([k, l]) => `<a href="#/alerts?state=${k}"><span class="${st === k ? "on" : ""}">${l}</span></a>`).join("")}</div>
    <div class="tw"><table><thead><tr><th>Önem</th><th>Tür</th><th>Cihaz</th><th>Mesaj</th><th>Zaman</th><th></th></tr></thead><tbody>
    ${r.items.map(a => `<tr><td>${sevPill(a.severity)}</td><td class="small">${esc(a.kind)}</td><td>${a.asset_id ? `<a href="#/asset/${a.asset_id}">${esc(a.asset_code || "")}</a>` : ""}</td>
      <td>${esc(a.message)}${a.ticket_id ? ` <a class="small" href="#/ticket/${a.ticket_id}">(arıza #${a.ticket_id})</a>` : ""}</td><td class="small">${fmtDate(a.at)}</td>
      <td class="row">${a.state === "açık" && mg ? `<button class="btn s" data-ack="${a.id}">Gördüm</button><button class="btn s" data-tk="${a.id}">Arıza aç</button><button class="btn s" data-cl="${a.id}">Kapat</button>` : esc(a.state)}</td></tr>`).join("") || `<tr><td colspan=6 class=muted>Alarm yok</td></tr>`}</tbody></table></div></div>`;
  if ($("#chk")) $("#chk").onclick = async () => { await api("/api/alerts/check", {method: "POST"}); toast("Denetlendi"); route(); refreshBadges(); };
  $$("[data-ack]").forEach(b => b.onclick = async () => { await api(`/api/alerts/${b.dataset.ack}/ack`, {method: "POST"}); route(); refreshBadges(); });
  $$("[data-cl]").forEach(b => b.onclick = async () => { await api(`/api/alerts/${b.dataset.cl}/resolve`, {method: "POST", body: {}}); toast("Kapatıldı"); route(); refreshBadges(); });
  $$("[data-tk]").forEach(b => b.onclick = async () => { const r = await api(`/api/alerts/${b.dataset.tk}/resolve`, {method: "POST", body: {make_ticket: true}}); toast("Arıza kaydı açıldı #" + r.ticket_id); route(); refreshBadges(); });
};

/* ---------- onay kuyruğu ---------- */
PRO["/pending"] = async v => {
  const [r, cat] = await Promise.all([api("/api/pending"), api("/api/catalog")]);
  v.innerHTML = `<h1>Onay Kuyruğu <span class="small muted">(${r.count})</span></h1>
    <div class="card small muted">Tarama ve ajan tarafından bulunan, envanterde olmayan cihazlar burada bekler. Onaylarsanız envantere eklenir; misafir/geçici cihazları “Yok say” ile çıkarın. (Ayarlar'dan kapatılabilir.)</div>
    <div class="card"><div class="tw"><table><thead><tr><th>IP</th><th>MAC</th><th>Ad</th><th>Tahmin</th><th>Portlar</th><th>Kaynak</th><th>Görülme</th><th>Tür</th><th></th></tr></thead><tbody>
    ${r.items.map(x => `<tr data-id="${x.id}"><td class="mono">${esc(x.ip || "")}</td><td class="mono small">${esc(x.mac || "")}</td><td class="small">${esc(x.hostname || "")}</td>
      <td class="small">${esc(x.kind || "")}</td><td class="small mono">${esc((x.data.ports || []).join(","))}</td><td class="small">${esc(x.source)}</td><td class="small">${fmtDate(x.seen_at)}</td>
      <td><select class="pt" style="width:150px"><option value="">— tür seç —</option>${cat.types.filter(t => t.active).map(t => `<option ${x.kind && t.name.toLowerCase().includes(x.kind.toLowerCase()) ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select></td>
      <td class="row"><button class="btn s p" data-ap="${x.id}">Onayla</button><button class="btn s d" data-ig="${x.id}">Yok say</button></td></tr>`).join("") || `<tr><td colspan=9 class=muted>Bekleyen cihaz yok</td></tr>`}</tbody></table></div></div>`;
  $$("[data-ap]").forEach(b => b.onclick = async () => { const tr = b.closest("tr"), type = $(".pt", tr).value;
    try { const a = await api(`/api/pending/${b.dataset.ap}/approve`, {method: "POST", body: {type}}); toast("Eklendi: " + a.asset_code); route(); refreshBadges(); } catch (e) { fail(e); } });
  $$("[data-ig]").forEach(b => b.onclick = async () => { await api(`/api/pending/${b.dataset.ig}/ignore`, {method: "POST"}); route(); refreshBadges(); });
};

/* ---------- yedek havuzu ---------- */
PRO["/spares"] = async v => {
  const p = await api("/api/spares"), mg = can("spares");
  v.innerHTML = `<div class="row"><h1>Yedek Havuzu</h1><span class="sp"></span>${mg ? `<button class="btn" id="mk">＋ Havuza yedek ekle</button>` : ""}</div>
    <div class="grid g2"><div class="card"><h2>Havuzda (${p.available_count})</h2><table><thead><tr><th>Barkod</th><th>Cihaz</th><th></th></tr></thead><tbody>
      ${p.available.map(a => `<tr><td><a href="#/asset/${a.id}">${esc(a.asset_code)}</a></td><td class="small">${esc(a.data.brand_model || "")} ${esc(a.data.hardware_info || "")}</td>
        <td>${mg ? `<button class="btn s p" data-give="${a.id}">Sahaya ver</button>` : ""}</td></tr>`).join("") || "<tr><td colspan=3 class=muted>Havuzda yedek yok</td></tr>"}</tbody></table></div>
    <div class="card"><h2>Sahada dönen yedekler (${p.on_loan_count})</h2><table><thead><tr><th>Barkod</th><th>Nerede</th><th>Yerine</th><th>Çıkış</th><th></th></tr></thead><tbody>
      ${p.on_loan.map(l => `<tr><td><a href="#/asset/${l.asset_id}">${esc(l.asset_code)}</a></td><td class="small">${esc(l.to_unit || "")} ${esc(l.to_person || "")}</td><td class="small">${esc(l.replacing_code || "")}</td><td class="small">${fmtDate(l.out_at)}</td>
        <td>${mg ? `<button class="btn s" data-back="${l.asset_id}">Geri al</button>` : ""}</td></tr>`).join("") || "<tr><td colspan=5 class=muted>Sahada yedek yok</td></tr>"}</tbody></table></div></div>`;
  if ($("#mk")) $("#mk").onclick = () => modal("Havuza yedek ekle", `<label class="f"><span>Barkodlar (her satıra bir)</span><textarea name="codes" rows="4" required></textarea></label><p class="small muted">Seçilen cihazlar “yedek” durumuna alınır.</p>`,
    async b => { const ids = await codesToIds(b.codes); await api("/api/spares/mark", {method: "POST", body: {asset_ids: ids}}); toast("Eklendi"); route(); });
  $$("[data-give]").forEach(b => b.onclick = () => modal("Yedeği sahaya ver", `<div class="grid g2"><label class="f"><span>Birim</span><input name="to_unit" list="dl_loc"></label><label class="f"><span>Teslim alan</span><input name="to_person"></label></div>
    <label class="f"><span>Yerine geçtiği cihazın barkodu (arızalanan)</span><input name="replacing_code"></label><datalist id="dl_loc"></datalist><label class="f"><span>Not</span><input name="note"></label>`,
    async x => { let rep = null; if (x.replacing_code) { try { rep = (await api("/api/assets/by-code/" + encodeURIComponent(x.replacing_code))).id; } catch (_) { throw new Error("Yerine geçtiği barkod bulunamadı"); } }
      await api("/api/spares/give", {method: "POST", body: {asset_id: +b.dataset.give, to_unit: x.to_unit, to_person: x.to_person, replacing_asset_id: rep, note: x.note}}); toast("Verildi"); route(); }, "Ver"));
  $$("[data-back]").forEach(b => b.onclick = () => modal("Yedeği geri al", `<label class="f"><span>Not</span><input name="note" placeholder="örn. asıl cihaz onarıldı"></label>`,
    async x => { await api(`/api/spares/${b.dataset.back}/back`, {method: "POST", body: x}); toast("Havuza döndü"); route(); }, "Geri al"));
};

/* ---------- hizmet noktaları ---------- */
PRO["/servicepoints"] = async (v, p) => {
  const pts = await api("/api/service-points"), mg = can("servicepoints.manage");
  v.innerHTML = `<div class="row"><h1>Hizmet Noktaları</h1><span class="sp"></span>${mg ? `<button class="btn p" id="np">＋ Yeni nokta</button>` : ""}</div>
    <div class="card small muted">“Acil kayıt masası 3” gibi fiziksel noktalar tanımlayın; o noktadaki bilgisayar, yazıcı ve ekran tek kart olarak görünür. Arıza geldiğinde “hangi cihaz” değil “hangi masa çalışmıyor” nettir. Durum Panosunda canlı izlenir.</div>
    <div class="grid g3">${pts.map(pt => `<div class="card"><div class="row">${dot(pt.status)}<b>${esc(pt.name)}</b>${pt.critical ? ' <span class="pill hurda">kritik</span>' : ""}<span class="sp"></span>${mg ? `<button class="btn s" data-ed="${pt.id}">Düzenle</button>` : ""}</div>
      <div class="small muted">${esc(pt.location || "")}</div><ul class="tl" style="margin-top:8px">${pt.items.map(i => `<li>${dot(i.live)} <a href="#/asset/${i.asset_id}">${esc(i.asset_code)}</a> <span class="small muted">${esc(i.role || "")} ${esc(i.brand_model || "")}</span></li>`).join("") || "<li class=muted>Cihaz eklenmedi</li>"}</ul></div>`).join("") || '<div class="card muted">Henüz nokta yok.</div>'}</div>`;
  const edit = pt => { const w = modal(pt ? "Noktayı düzenle" : "Yeni hizmet noktası", `<div class="grid g2"><label class="f"><span>Ad *</span><input name="name" value="${esc(pt?.name || "")}" required></label>
    <label class="f"><span>Birim / konum</span><input name="location" value="${esc(pt?.location || "")}"></label></div><label class="row"><input type="checkbox" name="critical" ${pt?.critical ? "checked" : ""}> Kritik nokta (panoda öne çıkar)</label>
    <h3>Cihazlar</h3><div id="spitems">${(pt?.items || []).map(spItemRow).join("")}</div><button type="button" class="btn s" id="addit">＋ Cihaz ekle</button>
    ${pt ? `<div style="margin-top:14px"><button type="button" class="btn d" id="delp">Noktayı sil</button></div>` : ""}`,
    async b => { const point = pt ? await api("/api/service-points/" + pt.id, {method: "PATCH", body: {name: b.name, location: b.location, critical: !!b.critical}})
      : await api("/api/service-points", {method: "POST", body: {name: b.name, location: b.location, critical: !!b.critical}});
      const items = []; for (const r of $$("#spitems .spit")) { const code = $(".spc", r).value.trim(); if (!code) continue; const a = await api("/api/assets/by-code/" + encodeURIComponent(code)).catch(() => null); if (a) items.push({asset_id: a.id, role: $(".spr", r).value}); }
      await api("/api/service-points/" + point.id, {method: "PATCH", body: {items}}); toast("Kaydedildi"); route(); });
    $("#addit", w).onclick = () => { $("#spitems", w).insertAdjacentHTML("beforeend", spItemRow()); bindIt(w); };
    if ($("#delp", w)) $("#delp", w).onclick = async () => { if (confirm("Nokta silinsin mi?")) { await api("/api/service-points/" + pt.id, {method: "DELETE"}); w.remove(); route(); } };
    bindIt(w);
  };
  const bindIt = w => $$(".spit .del", w).forEach(b => b.onclick = () => b.closest(".spit").remove());
  if ($("#np")) $("#np").onclick = () => edit(null);
  $$("[data-ed]").forEach(b => b.onclick = () => edit(pts.find(x => x.id === +b.dataset.ed)));
  if (p.open) { const pt = pts.find(x => x.id === +p.open); if (pt && mg) edit(pt); }
};
function spItemRow(it) {
  return `<div class="row spit" style="margin-bottom:6px"><input class="spc" value="${esc(it?.asset_code || "")}" placeholder="Barkod" style="width:160px">
    <select class="spr" style="width:150px">${["", "Bilgisayar", "Monitör", "Yazıcı", "Telefon", "Tarayıcı", "Diğer"].map(r => `<option ${it?.role === r ? "selected" : ""}>${r}</option>`).join("")}</select><button type="button" class="btn s del">✕</button></div>`;
}

/* ---------- arıza analizi ---------- */
PRO["/analytics"] = async (v, p) => {
  const days = +(p.days || 90);
  const [r, wl] = await Promise.all([api("/api/analytics/tickets?" + qs({days})), api("/api/analytics/workload")]);
  const bars = (arr, key, lab) => { const mx = Math.max(1, ...arr.map(x => x[key])); return arr.map(x => `<div style="margin-bottom:7px"><div class="row small"><span>${esc(x[lab])}</span><span class="sp"></span><b>${x[key]}</b></div><div class="bar"><i style="width:${x[key] / mx * 100}%"></i></div></div>`).join("") || '<p class="muted">Veri yok</p>'; };
  const hourMax = Math.max(1, ...r.by_hour.map(x => x.count));
  v.innerHTML = `<div class="row"><h1>Arıza Analizi</h1><span class="sp"></span><select id="dd" style="width:auto">${[30, 90, 180, 365].map(d => `<option value="${d}" ${days === d ? "selected" : ""}>Son ${d} gün</option>`).join("")}</select></div>
    <div class="grid g4"><div class="card stat"><div><div class="n">${r.total}</div><div class="l">Toplam çağrı</div></div></div>
      <div class="card stat"><div><div class="n">${r.avg_resolution_hours ?? "—"}</div><div class="l">Ort. çözüm (saat)</div></div></div>
      <div class="card stat"><div><div class="n">${r.peak_hour != null ? r.peak_hour + ":00" : "—"}</div><div class="l">En yoğun saat</div></div></div>
      <div class="card stat"><div><div class="n">${r.recurring.length}</div><div class="l">Tekrar eden sorun</div></div></div></div>
    <div class="grid g2"><div class="card"><h2>Birimlere göre çağrı</h2>${bars(r.by_unit, "count", "unit")}</div>
      <div class="card"><h2>Kategoriye göre</h2>${bars(r.by_category, "count", "category")}</div></div>
    <div class="card"><h2>Saat dağılımı</h2><div class="hours">${r.by_hour.map(x => `<div class="hbar" title="${x.hour}:00 — ${x.count} çağrı"><i style="height:${x.count / hourMax * 100}%"></i><span>${x.hour}</span></div>`).join("")}</div></div>
    <div class="grid g2"><div class="card"><h2>Tekrar eden sorunlar <span class="small muted">(aynı modelde 3+ aynı kategori)</span></h2><table><thead><tr><th>Model</th><th>Sorun</th><th>Adet</th></tr></thead><tbody>
      ${r.recurring.map(x => `<tr><td class="small">${esc(x.model)}</td><td>${esc(x.category)}</td><td><b>${x.count}</b></td></tr>`).join("") || "<tr><td colspan=3 class=muted>Yok</td></tr>"}</tbody></table>
      <p class="small muted">Aynı modelde aynı sorun tekrar ediyorsa çözüm yeni cihaz değil, çoğu zaman kısa bir kullanıcı eğitimi olabilir.</p></div>
    <div class="card"><h2>En çok çağrı açan modeller</h2>${bars(r.top_models, "count", "model")}
      ${r.repeat_reporters.length ? `<h3>Sık çağrı açan kullanıcılar</h3><ul class="tl">${r.repeat_reporters.map(x => `<li>${esc(x.name)} <span class="small muted">${x.count} çağrı</span></li>`).join("")}</ul>` : ""}</div></div>
    <div class="card"><h2>BİM iş yükü (son ${wl.days} gün)</h2><table><thead><tr><th>Personel</th><th>Atanan</th><th>Çözülen</th></tr></thead><tbody>
      ${wl.staff.map(s => `<tr><td>${esc(s.user)}</td><td>${s.assigned}</td><td>${s.resolved}</td></tr>`).join("") || "<tr><td colspan=3 class=muted>Veri yok</td></tr>"}</tbody></table></div>`;
  $("#dd").onchange = e => go("/analytics?days=" + e.target.value);
};
