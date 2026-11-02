"use strict";
/* Etiket & Yazıcı: şablon, yazı stilleri, baskı kalitesi, yazıcı profili (kağıt boyutu / sığdırma), kalibrasyon */
const STYLE_EL = [["header", "Üst bant (kurum adı)"], ["subheader", "Alt başlık satırları"], ["label", "Satır başlıkları"],
  ["value", "Bilgi değerleri"], ["code", "QR altı no / barkod yazısı"]];

async function labelsPage(v, p) {
  const ids = (p.ids || "").split(",").filter(Boolean);
  const [T, P, jobs] = await Promise.all([api("/api/labels/template"), can("print") ? api("/api/printers") : {printers: [], adapters: []}, api("/api/print/jobs")]);
  const t = T.template, editable = can("labels"), fonts = T.fonts.length ? T.fonts : ["Arial"];
  const fieldOpts = sel => S.fields.map(f => `<option value="${f.key}" ${sel === f.key ? "selected" : ""}>${esc(f.label)}</option>`).join("");
  const rowHtml = r => `<div class="row lr" style="margin-bottom:6px"><input class="rl" value="${esc(r.label)}" placeholder="Başlık" style="width:180px"><select class="rf" style="width:200px">${fieldOpts(r.field)}</select><button type="button" class="btn s rdel">✕</button></div>`;
  const ck = (n, on, l) => `<label><input type="checkbox" name="${n}" ${on ? "checked" : ""}> ${l}</label>`;
  const styleRow = ([k, l]) => { const st = t.styles[k] || {};
    return `<tr><td class="small"><b>${l}</b></td><td><select name="st_${k}_family">${fonts.map(f => `<option ${st.family === f ? "selected" : ""}>${esc(f)}</option>`).join("")}</select></td>
      <td><input name="st_${k}_size" type="number" min="0" max="72" step="0.5" value="${st.size || 0}" style="width:76px" title="0 = otomatik sığdır"></td>
      <td style="text-align:center"><input type="checkbox" name="st_${k}_bold" ${st.bold ? "checked" : ""}></td>
      <td><select name="st_${k}_align">${[["left", "Sol"], ["center", "Orta"], ["right", "Sağ"]].map(([a, n]) => `<option value="${a}" ${st.align === a ? "selected" : ""}>${n}</option>`).join("")}</select></td></tr>`; };
  const rl = t.row_layout, q = t.quality, bc = t.barcode;
  const prnOpts = P.printers.map(x => `<option data-a="${x.adapter}" ${x.name === P.default || (!P.default && x.default) ? "selected" : ""}>${esc(x.name)}</option>`).join("");
  v.innerHTML = `<h1>Etiket & Yazıcı</h1>
    ${ids.length ? `<div class="card"><h2>Yazdır: ${ids.length} etiket</h2><div class="row">
      <select id="prn" style="max-width:320px">${prnOpts || "<option value=''>Doğrudan yazıcı yok (PDF kullanın)</option>"}</select>
      <label class="f" style="margin:0;width:90px"><input id="cp" type="number" min="1" max="20" value="1" title="Kopya"></label>
      <button class="btn p" id="doprint" ${P.printers.length ? "" : "disabled"}>▦ Yazdır</button><button class="btn" id="pdf">⇩ PDF</button><button class="btn s" id="pst">Durum</button>
      <span class="sp"></span><button class="btn s" id="clr">Seçimi temizle</button></div>
      <div class="row" style="margin-top:12px">${ids.slice(0, 6).map(i => `<img class="lbl-prev" style="width:230px" src="/api/labels/preview/${i}.png">`).join("")}${ids.length > 6 ? `<span class="muted">+${ids.length - 6}</span>` : ""}</div>
      <p class="small muted">Not: "Gönderildi" durumu fiziksel baskının başarılı olduğunu kanıtlamaz; ilk baskıda QR'ı telefonla okutun.</p></div>` : ""}
    <div class="grid g2"><form class="card" id="tf"><h2>Etiket şablonu</h2><fieldset ${editable ? "" : "disabled"} style="border:0;padding:0;margin:0">
      <label class="f"><span>Hazır ölçü</span><select id="preset"><option value="">— seçin —</option>${T.presets.map((x, i) => `<option value="${i}">${esc(x.name)}</option>`).join("")}</select></label>
      <div class="grid g4"><label class="f"><span>Genişlik (mm)</span><input name="width_mm" type="number" step="0.5" value="${t.width_mm}"></label>
      <label class="f"><span>Yükseklik (mm)</span><input name="height_mm" type="number" step="0.5" value="${t.height_mm}"></label>
      <label class="f"><span>DPI</span><select name="dpi">${[180, 203, 300, 360, 600, 720].map(d => `<option ${+t.dpi === d ? "selected" : ""}>${d}</option>`).join("")}</select></label>
      <label class="f"><span>Kenar (mm)</span><input name="margin_mm" type="number" step="0.1" value="${t.margin_mm}"></label></div>
      <div id="szwarn"></div>
      <label class="f"><span>Üst bant metni ({org_name} = kurum adı)</span><input name="h_text" value="${esc(t.header.text)}"></label>
      <div class="row small">${ck("h_en", t.header.enabled, "Üst bant")}${ck("h_inv", t.header.inverted, "Siyah zemin")}${ck("logo_left", t.logo_left, "Sol logo")}${ck("logo_right", t.logo_right, "Sağ logo")}${ck("uppercase", t.uppercase, "BÜYÜK HARF")}${ck("border", t.border, "Çerçeve")}</div>
      <div class="grid g2" style="margin-top:10px"><label class="f"><span>Üst bant yüksekliği (%)</span><input name="h_pct" type="number" min="10" max="45" value="${t.header.height_pct}"></label>
        <label class="f"><span>Alt başlık yüksekliği (%)</span><input name="s_pct" type="number" min="10" max="45" value="${t.subheader.height_pct}"></label></div>
      <label class="f"><span>Alt başlık satırları (her satır ayrı; {unit_name}, {system_title})</span><textarea name="s_lines" rows="2">${esc(t.subheader.lines.join("\n"))}</textarea></label>
      <label class="row small">${ck("s_en", t.subheader.enabled, "Alt başlık")}</label>
      <h3>Bilgi satırları</h3><div id="rows">${t.rows.map(rowHtml).join("")}</div><button type="button" class="btn s" id="radd">＋ Satır</button>
      <div class="grid g4" style="margin-top:10px"><label class="f"><span>Başlık sütunu (% , 0 = yan yana)</span><input name="rl_col" type="number" min="0" max="70" value="${rl.label_col_pct}"></label>
        <label class="f"><span>Ayraç</span><input name="rl_sep" value="${esc(rl.separator)}"></label>
        <label class="f"><span>Satır aralığı (2 satıra bölünce)</span><input name="rl_ls" type="number" min="0.8" max="2" step="0.1" value="${rl.line_spacing}"></label>
        <div class="small" style="padding-top:20px">${ck("rl_box", rl.row_boxes, "Satır kutuları")}<br>${ck("rl_wrap", rl.wrap_values, "Uzun değeri 2 satıra böl")}</div></div>
      <h3>Yazı stilleri</h3><div class="tw"><table class="small"><tr><th>Öğe</th><th>Yazı tipi</th><th>Boyut (pt)</th><th>Kalın</th><th>Hiza</th></tr>${STYLE_EL.map(styleRow).join("")}</table></div>
      <p class="small muted">Boyut 0 = alana sığan en büyük boyut. Verilen boyut alana sığmazsa otomatik küçültülür; hiçbir yazı etiket dışına taşmaz.</p>
      <h3>Baskı kalitesi</h3><div class="grid g3"><div class="small" style="padding-top:20px">${ck("q_mono", q.mono, "Saf siyah-beyaz (önerilir)")}</div>
        <label class="f"><span>Koyuluk eşiği (100–230)</span><input name="q_thr" type="range" min="100" max="230" value="${q.threshold}"></label>
        <label class="f"><span>Kalınlaştırma (0–3)</span><input name="q_boost" type="number" min="0" max="3" step="0.5" value="${q.boost}"></label></div>
      <p class="small muted">Termal şerit yazıcılarda gri tonlar silik çıkar. Saf siyah-beyaz + kalın yazı + gerekirse kalınlaştırma 1 ile ince karakterler netleşir. Etiket yazıcının kendi DPI'ında çizilip ölçeklenmeden gönderilir.</p>
      <h3>QR ve barkod</h3><div class="row small">${ck("q_en", t.qr.enabled, "QR kod")}${ck("q_code", t.qr.show_code, "Altında envanter no")}
        <label>Sessiz alan (modül) <input name="q_quiet" type="number" min="0" max="4" value="${t.qr.quiet_modules}" style="width:60px"></label></div>
      <div class="row small" style="margin-top:8px">${ck("bc_en", bc.enabled, "Code128 barkod şeridi (altta)")}<select name="bc_field" style="width:180px">${fieldOpts(bc.field)}</select>
        <label>Yükseklik % <input name="bc_pct" type="number" min="10" max="40" value="${bc.height_pct}" style="width:60px"></label>${ck("bc_txt", bc.show_text, "Altına yazı")}</div>
      ${editable ? `<div class="row" style="margin-top:12px"><span class="small">Logo yükle:</span><input type="file" id="lgf" accept="image/*" style="max-width:220px"><select id="lgs" style="width:90px"><option value="left">Sol</option><option value="right">Sağ</option></select><button type="button" class="btn s" id="lgu">Yükle</button></div>
      <p class="small muted">Yalnızca kullanım izni olan resmî logo dosyalarını yükleyin.</p>
      <div class="row" style="margin-top:12px"><button class="btn p">Şablonu kaydet</button><button type="button" class="btn" id="rst">Varsayılana dön</button></div>` : ""}</fieldset></form>
    <div><div class="card"><h2>Önizleme <span class="small muted">(basılacak siyah-beyaz görüntü)</span></h2><img id="pv" class="lbl-prev" alt="önizleme" style="width:100%">
      <div class="row" style="margin-top:8px"><button type="button" class="btn s" id="calv">Kalibrasyon görüntüsü</button><a class="btn s" href="/api/labels/calibration.pdf" target="_blank">Kalibrasyon PDF</a></div></div>
    ${can("print") ? `<div class="card" id="pcard"><h2>Yazıcı profili</h2>${P.printers.length ? `<label class="f"><span>Yazıcı</span><select id="pp">${prnOpts}</select></label><div id="pprof"></div>`
      : `<p class="small muted">Bu bilgisayarda Windows yazıcısı bulunamadı. PDF'i etiket ölçüsünde (gerçek boyut / %100) yazdırabilirsiniz.</p>`}</div>` : ""}
    <div class="card"><h2>Baskı geçmişi</h2><div class="tw" style="max-height:300px"><table><thead><tr><th>Tarih</th><th>Kullanıcı</th><th>Yazıcı</th><th>Adet</th><th>Durum</th></tr></thead><tbody>
      ${jobs.map(j => `<tr><td>${fmtDate(j.at)}</td><td>${esc(j.user)}</td><td>${esc(j.printer)}</td><td>${j.asset_ids.length}×${j.copies}</td><td class="${j.status === "failed" ? "res-hata" : ""}" title="${esc(j.error || "")}">${esc(j.status)}</td></tr>`).join("") || "<tr><td colspan=5 class=muted>Yok</td></tr>"}</tbody></table></div></div></div></div>`;
  const collect = () => {
    const f = new FormData($("#tf")), b = k => f.get(k) === "on", n = k => +f.get(k);
    const styles = Object.fromEntries(STYLE_EL.map(([k]) => [k, {family: f.get(`st_${k}_family`), size: n(`st_${k}_size`), bold: b(`st_${k}_bold`), align: f.get(`st_${k}_align`)}]));
    return {...t, width_mm: n("width_mm"), height_mm: n("height_mm"), dpi: n("dpi"), margin_mm: n("margin_mm"),
      uppercase: b("uppercase"), border: b("border"), logo_left: b("logo_left"), logo_right: b("logo_right"),
      header: {...t.header, enabled: b("h_en"), inverted: b("h_inv"), text: f.get("h_text"), height_pct: n("h_pct")},
      subheader: {...t.subheader, enabled: b("s_en"), height_pct: n("s_pct"), lines: f.get("s_lines").split("\n").map(s => s.trim()).filter(Boolean)},
      rows: $$(".lr").map(r => ({label: $(".rl", r).value, field: $(".rf", r).value})),
      row_layout: {label_col_pct: n("rl_col"), separator: f.get("rl_sep"), line_spacing: n("rl_ls"), row_boxes: b("rl_box"), wrap_values: b("rl_wrap")},
      qr: {enabled: b("q_en"), show_code: b("q_code"), quiet_modules: n("q_quiet")},
      barcode: {enabled: b("bc_en"), field: f.get("bc_field"), height_pct: n("bc_pct"), show_text: b("bc_txt")},
      styles, quality: {...t.quality, mono: b("q_mono"), threshold: n("q_thr"), boost: n("q_boost")}};
  };
  let pt, calib = false;
  const preview = () => { clearTimeout(pt); pt = setTimeout(async () => {
    const tp = collect();
    $("#szwarn").innerHTML = tp.height_mm > 32 && tp.width_mm > 32 ? `<p class="small err">Not: Brother PT-P900Wc en fazla 36 mm şerit alır (basılabilir ~32 mm). ${tp.width_mm}×${tp.height_mm} mm bu yazıcıda yazıcı profiline göre küçültülerek basılır; birebir baskı için daha geniş ortam destekleyen bir yazıcı gerekir.</p>` : "";
    try { const bl = await fetch("/api/labels/preview", {method: "POST", headers: {"x-nx": "1", "Content-Type": "application/json"}, body: JSON.stringify({template: tp, asset_id: +(ids[0] || 0), calibration: calib})});
      if (bl.ok) $("#pv").src = URL.createObjectURL(await bl.blob()); } catch (_) {} }, 250); };
  const bindRows = () => $$(".rdel").forEach(b => b.onclick = () => { b.parentElement.remove(); preview(); });
  bindRows(); preview();
  $("#tf").oninput = preview; $("#tf").onchange = preview;
  $("#calv").onclick = () => { calib = !calib; $("#calv").textContent = calib ? "Etiket görüntüsü" : "Kalibrasyon görüntüsü"; preview(); };
  $("#preset").onchange = e => { const x = T.presets[+e.target.value]; if (!x) return; $("[name=width_mm]").value = x.width_mm; $("[name=height_mm]").value = x.height_mm; preview(); };
  if (editable) {
    $("#radd").onclick = () => { $("#rows").insertAdjacentHTML("beforeend", rowHtml({label: "", field: "hardware_info"})); bindRows(); preview(); };
    $("#tf").onsubmit = async e => { e.preventDefault(); try { await api("/api/labels/template", {method: "PUT", body: {template: collect()}}); toast("Şablon kaydedildi"); if ($("#pp")) loadProfile(); } catch (err) { fail(err); } };
    $("#rst").onclick = async () => { if (!confirm("Varsayılan şablona dönülsün mü?")) return; await api("/api/labels/template", {method: "PUT", body: {template: T.default}}); route(); };
    $("#lgu").onclick = async () => { const f = $("#lgf").files[0]; if (!f) return; const fd = new FormData(); fd.append("file", f);
      try { await api("/api/labels/logo/" + $("#lgs").value, {method: "POST", form: fd}); toast("Logo yüklendi"); preview(); } catch (e) { fail(e); } };
  }
  /* ---- yazıcı profili ---- */
  async function loadProfile() {
    const name = $("#pp").value, pr = await api("/api/printers/profile?" + qs({name}));
    const sel = (n, opts, val) => `<select name="${n}">${opts.map(([v, l]) => `<option value="${v}" ${String(val) === String(v) ? "selected" : ""}>${l}</option>`).join("")}</select>`;
    $("#pprof").innerHTML = `<form id="pf"><div class="grid g2">
      <label class="f"><span>Kağıt</span><select name="paper" id="ppaper"><option value="custom" ${pr.paper === "custom" ? "selected" : ""}>Etiket ölçüsünü özel kağıt olarak gönder</option><option value="driver" ${pr.paper === "driver" ? "selected" : ""}>Sürücüde seçili kağıdı kullan</option>${pr.paper.startsWith("form:") ? `<option value="${esc(pr.paper)}" selected>${esc(pr.paper.slice(5))}</option>` : ""}</select></label>
      <label class="f"><span>Şerit genişliği (mm, şerit yazıcılar; 0 = yok)</span>${sel("tape_mm", [[0, "Kullanılmıyor"], [12, "12 mm"], [18, "18 mm"], [24, "24 mm"], [36, "36 mm (PT-P900Wc en geniş)"]], pr.tape_mm)}</label>
      <label class="f"><span>Döndürme</span>${sel("rotate", [["auto", "Otomatik"], [0, "0°"], [90, "90°"], [180, "180°"], [270, "270°"]], pr.rotate)}</label>
      <label class="f"><span>Sığdırma</span>${sel("fit", [["fit", "Basılabilir alana orantılı sığdır"], ["actual", "Birebir (taşarsa kesilir)"]], pr.fit)}</label>
      <label class="f"><span>Yatay kaydırma (mm)</span><input name="offset_x_mm" type="number" step="0.1" value="${pr.offset_x_mm}"></label>
      <label class="f"><span>Dikey kaydırma (mm)</span><input name="offset_y_mm" type="number" step="0.1" value="${pr.offset_y_mm}"></label></div>
      <div class="row">${editable ? `<button class="btn p">Profili kaydet</button>` : ""}<button type="button" class="btn" id="pinfo">Sürücüyü denetle</button>
      ${editable ? `<button type="button" class="btn" id="pform">Windows'a ${t.width_mm}×${t.height_mm} mm kağıt ekle</button>` : ""}<button type="button" class="btn" id="pcal">Kalibrasyon etiketi bas</button></div>
      <div id="pres" class="small" style="margin-top:10px"></div></form>`;
    if ($("#pf") && editable) $("#pf").onsubmit = async e => { e.preventDefault(); const b = Object.fromEntries(new FormData(e.target));
      try { await api("/api/printers/profile", {method: "PUT", body: {name, profile: b}}); toast("Profil kaydedildi"); } catch (err) { fail(err); } };
    $("#pinfo").onclick = async () => {
      $("#pres").innerHTML = "<span class=muted>Sürücü sorgulanıyor…</span>";
      try {
        const r = await api("/api/printers/info?" + qs({name})), wp = r.with_profile || {}, c = r.current || {};
        const papers = r.papers || [];
        const near = papers.filter(x => Math.abs(Math.min(x.w_mm, x.h_mm) - Math.min(t.width_mm, t.height_mm)) < 3 && Math.abs(Math.max(x.w_mm, x.h_mm) - Math.max(t.width_mm, t.height_mm)) < 3);
        $("#pres").innerHTML = `<dl class="kv"><dt>Sürücü</dt><dd>${esc(r.driver || "")}</dd>
          <dt>Şu anki kağıt</dt><dd>${esc(c.paper_name || "")} ${c.physical_mm ? c.physical_mm.join(" × ") + " mm" : ""} · basılabilir ${c.printable_mm ? c.printable_mm.join(" × ") + " mm" : ""} · ${c.dpi_x}×${c.dpi_y} dpi</dd>
          <dt>Profille</dt><dd>${wp.physical_mm ? wp.physical_mm.join(" × ") + " mm" : "—"} · basılabilir ${wp.printable_mm ? wp.printable_mm.join(" × ") + " mm" : "—"} · döndürme ${wp.rotate ?? "—"}° · ölçek %${wp.scale ? Math.round(wp.scale * 100) : "—"}</dd></dl>
          ${wp.scale && wp.scale < 0.98 ? `<p class="err">Etiket %${Math.round(wp.scale * 100)} oranında küçültülerek basılacak: yazıcının basılabilir alanı ${t.width_mm}×${t.height_mm} mm'den küçük. ${pr.tape_mm || /PT-|P-touch/i.test(r.driver || "") ? "Şerit yazıcılarda basılabilir yükseklik şerit genişliğinden azdır (36 mm şeritte ~32 mm)." : "Daha büyük bir kağıt formu seçin veya Windows'a özel kağıt ekleyin."}</p>`
            : wp.scale ? `<p class="res-eklendi">Etiket birebir (%100) basılacak.</p>` : ""}
          ${near.length ? `<p>Sürücüde uygun kağıt bulundu: ${near.map(x => `<button type="button" class="btn s" data-form="${esc(x.name)}">${esc(x.name)} (${x.w_mm}×${x.h_mm})</button>`).join(" ")}</p>` : ""}
          <details><summary>Sürücüdeki tüm kağıtlar (${papers.length})</summary><div class="row" style="margin-top:6px">${papers.map(x => `<button type="button" class="btn s" data-form="${esc(x.name)}" title="${x.w_mm}×${x.h_mm} mm">${esc(x.name)}</button>`).join("")}</div></details>`;
        $$("[data-form]").forEach(bt => bt.onclick = async () => { if (!editable) return;
          await api("/api/printers/profile", {method: "PUT", body: {name, profile: {paper: "form:" + bt.dataset.form}}}); toast("Kağıt seçildi: " + bt.dataset.form); loadProfile(); });
      } catch (e) { $("#pres").innerHTML = `<span class="err">${esc(e.message)}</span>`; }
    };
    if ($("#pform")) $("#pform").onclick = async () => { try { const r = await api("/api/printers/form", {method: "POST"}); toast(r.message);
      await api("/api/printers/profile", {method: "PUT", body: {name, profile: {paper: "form:" + r.name}}}); loadProfile(); } catch (e) { fail(e); } };
    $("#pcal").onclick = async () => { try { await api("/api/print", {method: "POST", body: {calibration: true, printer: name, adapter: "windows"}}); toast("Kalibrasyon etiketi gönderildi: çerçeve kenarlara oturmuyorsa kaydırma/ölçeği düzeltin"); } catch (e) { fail(e); } };
  }
  if ($("#pp")) { $("#pp").onchange = loadProfile; loadProfile(); }
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
